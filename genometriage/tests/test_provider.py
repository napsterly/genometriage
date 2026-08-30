from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message

import pytest

from genometriage.baseline.prompt import baseline_response_schema
from genometriage.baseline.provider import (
    GeminiGenerateContentProvider,
    OpenAIResponsesProvider,
    ProviderError,
    create_provider,
)


class FakeHTTPResponse:
    def __init__(self, body: dict) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self.body).encode("utf-8")


def test_provider_requires_credentials_without_generating_output(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="no synthetic predictions were generated"):
        OpenAIResponsesProvider(api_key=None)


def test_provider_sends_one_strict_responses_request(monkeypatch) -> None:
    captured = []

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return FakeHTTPResponse(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"ranked_variants":[],"escalated_uncertainty":true,"notes":null}',
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 123,
                    "output_tokens": 17,
                    "total_tokens": 140,
                },
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OpenAIResponsesProvider(
        api_key="test-only-key",
        model="fake-model",
        base_url="https://example.invalid/v1",
        timeout_seconds=9,
    )
    response = provider.complete("synthetic case", baseline_response_schema())
    assert len(captured) == 1
    request, timeout = captured[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "https://example.invalid/v1/responses"
    assert timeout == 9
    assert payload["model"] == "fake-model"
    assert payload["store"] is False
    assert payload["temperature"] == 0
    assert payload["max_output_tokens"] == 2000
    assert "tools" not in payload
    assert payload["text"]["format"]["strict"] is True
    assert "uniqueItems" not in json.dumps(payload["text"]["format"]["schema"])
    assert response.input_tokens == 123
    assert response.output_tokens == 17
    assert response.total_tokens == 140


def test_output_text_extraction_rejects_missing_content() -> None:
    with pytest.raises(ProviderError, match="no output text"):
        OpenAIResponsesProvider._extract_output_text({"output": []})


def test_gemini_provider_requires_credentials_without_generating_output(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="no synthetic predictions were generated"):
        GeminiGenerateContentProvider(api_key=None)


def test_gemini_provider_sends_one_structured_generate_content_request(
    monkeypatch,
) -> None:
    captured = []

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return FakeHTTPResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "text": '{"ranked_variants":[],"escalated_uncertainty":true,"notes":null}'
                                }
                            ],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 111,
                    "candidatesTokenCount": 19,
                    "thoughtsTokenCount": 31,
                    "totalTokenCount": 161,
                },
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiGenerateContentProvider(
        api_key="test-only-gemini-key",
        model="models/fake-gemini-model",
        base_url="https://example.invalid/v1beta",
        timeout_seconds=7,
    )
    response = provider.complete("synthetic case", baseline_response_schema())

    assert len(captured) == 1
    request, timeout = captured[0]
    payload = json.loads(request.data.decode("utf-8"))
    headers = {key.lower(): value for key, value in request.header_items()}
    assert request.full_url == (
        "https://example.invalid/v1beta/models/fake-gemini-model:generateContent"
    )
    assert timeout == 7
    assert headers["x-goog-api-key"] == "test-only-gemini-key"
    assert payload["contents"][0]["parts"][0]["text"] == "synthetic case"
    config = payload["generationConfig"]
    assert config["temperature"] == 0
    assert config["maxOutputTokens"] == 8192
    assert config["thinkingConfig"] == {"thinkingLevel": "low"}
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == baseline_response_schema()
    assert "tools" not in payload
    assert response.input_tokens == 111
    assert response.output_tokens == 50
    assert response.total_tokens == 161


def test_gemini_output_text_extraction_reports_block_reason() -> None:
    with pytest.raises(ProviderError, match="SAFETY"):
        GeminiGenerateContentProvider._extract_output_text(
            {"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []}
        )


def test_gemini_retries_transient_error_with_bounded_accounting(monkeypatch) -> None:
    calls = []
    headers = Message()
    headers["Retry-After"] = "0"

    def fake_urlopen(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                503,
                "temporary",
                headers,
                io.BytesIO(b'{"error":"temporary"}'),
            )
        return FakeHTTPResponse(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}
                ]
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _: None)
    provider = GeminiGenerateContentProvider(
        api_key="test-only-gemini-key",
        model="fake-gemini-model",
        base_url="https://example.invalid/v1beta",
        max_attempts=2,
    )
    response = provider.complete("synthetic case", {"type": "object"})
    assert len(calls) == 2
    assert response.request_attempt_count == 2
    assert len(response.retry_errors) == 1
    assert "HTTP 503" in response.retry_errors[0]


def test_gemini_37_omits_deprecated_temperature(monkeypatch) -> None:
    captured = []

    def fake_urlopen(request, timeout):
        captured.append(request)
        return FakeHTTPResponse(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}
                ]
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiGenerateContentProvider(
        api_key="test-only-gemini-key",
        model="gemini-3.7-flash",
        base_url="https://example.invalid/v1beta",
    )
    provider.complete("synthetic case", {"type": "object"})
    config = json.loads(captured[0].data.decode("utf-8"))["generationConfig"]
    assert "temperature" not in config
    assert "temperature" not in provider.execution_config


def test_provider_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ProviderError, match="unsupported provider"):
        create_provider("unknown")
