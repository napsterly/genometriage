"""Minimal provider boundary for exactly one model request per case."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional, Protocol


class ProviderError(RuntimeError):
    """The model provider could not return a usable response."""


@dataclass(frozen=True)
class ProviderResponse:
    output_text: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class LLMProvider(Protocol):
    provider_name: str
    model: str
    default_min_request_interval_seconds: float
    execution_config: Dict[str, object]

    def complete(self, prompt: str, response_schema: Dict[str, object]) -> ProviderResponse:
        """Perform one model call and return its structured text and usage."""


class OpenAIResponsesProvider:
    """Small standard-library client for the OpenAI Responses API."""

    provider_name = "openai"
    default_min_request_interval_seconds = 0.0
    execution_config = {
        "temperature": 0,
        "max_output_tokens": 2000,
        "structured_output": "strict_json_schema",
    }

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
        self.base_url = (
            base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds
        if not self.api_key:
            raise ProviderError(
                "OPENAI_API_KEY is required for a live baseline run; "
                "no synthetic predictions were generated"
            )

    def complete(
        self, prompt: str, response_schema: Dict[str, object]
    ) -> ProviderResponse:
        payload = {
            "model": self.model,
            "input": prompt,
            "store": False,
            "temperature": 0,
            "max_output_tokens": 2000,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "genometriage_variant_ranking",
                    "strict": True,
                    "schema": response_schema,
                }
            },
        }
        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ProviderError(f"Responses API returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Responses API request failed: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("Responses API returned an unreadable response") from exc

        output_text = self._extract_output_text(body)
        usage = body.get("usage") or {}
        return ProviderResponse(
            output_text=output_text,
            input_tokens=_optional_int(usage.get("input_tokens")),
            output_tokens=_optional_int(usage.get("output_tokens")),
            total_tokens=_optional_int(usage.get("total_tokens")),
        )

    @staticmethod
    def _extract_output_text(body: Dict[str, object]) -> str:
        direct = body.get("output_text")
        if isinstance(direct, str) and direct:
            return direct
        for item in body.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str) and text:
                        return text
        raise ProviderError("Responses API response contained no output text")


class GeminiGenerateContentProvider:
    """Small standard-library client for Gemini generateContent."""

    provider_name = "gemini"
    default_min_request_interval_seconds = 13.0
    execution_config = {
        "temperature": 0,
        "max_output_tokens": 8192,
        "thinking_level": "low",
        "structured_output": "response_json_schema",
    }

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
        self.base_url = (
            base_url
            or os.getenv(
                "GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta",
            )
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._include_temperature = not any(
            version in self.model.removeprefix("models/")
            for version in ("gemini-3.6-", "gemini-3.7-")
        )
        self.execution_config = dict(type(self).execution_config)
        if not self._include_temperature:
            self.execution_config.pop("temperature", None)
        if not self.api_key:
            raise ProviderError(
                "GEMINI_API_KEY is required for a live baseline run; "
                "no synthetic predictions were generated"
            )

    def complete(
        self, prompt: str, response_schema: Dict[str, object]
    ) -> ProviderResponse:
        generation_config = {
            "maxOutputTokens": 8192,
            "thinkingConfig": {"thinkingLevel": "low"},
            "responseMimeType": "application/json",
            "responseJsonSchema": response_schema,
        }
        if self._include_temperature:
            generation_config["temperature"] = 0
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": generation_config,
        }
        model_name = self.model.removeprefix("models/")
        encoded_model = urllib.parse.quote(model_name, safe="")
        request = urllib.request.Request(
            f"{self.base_url}/models/{encoded_model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ProviderError(f"Gemini API returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Gemini API request failed: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("Gemini API returned an unreadable response") from exc

        output_text = self._extract_output_text(body)
        usage = body.get("usageMetadata") or {}
        output_tokens = _sum_optional_ints(
            usage.get("candidatesTokenCount"),
            usage.get("thoughtsTokenCount"),
        )
        return ProviderResponse(
            output_text=output_text,
            input_tokens=_optional_int(usage.get("promptTokenCount")),
            output_tokens=output_tokens,
            total_tokens=_optional_int(usage.get("totalTokenCount")),
        )

    @staticmethod
    def _extract_output_text(body: Dict[str, object]) -> str:
        for candidate in body.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            text_parts = []
            for part in content.get("parts", []):
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
            if text_parts:
                return "".join(text_parts)

        reasons = []
        feedback = body.get("promptFeedback")
        if isinstance(feedback, dict) and feedback.get("blockReason"):
            reasons.append(f"prompt block reason {feedback['blockReason']}")
        for candidate in body.get("candidates", []):
            if isinstance(candidate, dict) and candidate.get("finishReason"):
                reasons.append(f"finish reason {candidate['finishReason']}")
        suffix = f" ({'; '.join(reasons)})" if reasons else ""
        raise ProviderError(f"Gemini API response contained no output text{suffix}")


def create_provider(provider_name: str, *, model: Optional[str] = None) -> LLMProvider:
    """Construct a supported live provider without changing baseline behavior."""

    normalized = provider_name.strip().lower()
    if normalized == "gemini":
        return GeminiGenerateContentProvider(model=model)
    if normalized == "openai":
        return OpenAIResponsesProvider(model=model)
    raise ProviderError(
        f"unsupported provider {provider_name!r}; choose 'gemini' or 'openai'"
    )


def _optional_int(value: object) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) else None


def _sum_optional_ints(*values: object) -> Optional[int]:
    converted = [_optional_int(value) for value in values]
    present = [value for value in converted if value is not None]
    return sum(present) if present else None
