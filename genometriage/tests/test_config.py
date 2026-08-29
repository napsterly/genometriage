from __future__ import annotations

import os

from genometriage.config import load_project_environment


def test_dotenv_loads_without_overriding_process_environment(
    tmp_path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GENOMETRIAGE_TEST_FROM_FILE=file-value\n"
        "GENOMETRIAGE_TEST_PRECEDENCE=file-value\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GENOMETRIAGE_TEST_FROM_FILE", raising=False)
    monkeypatch.setenv("GENOMETRIAGE_TEST_PRECEDENCE", "process-value")

    assert load_project_environment(env_file) is True
    assert os.environ["GENOMETRIAGE_TEST_FROM_FILE"] == "file-value"
    assert os.environ["GENOMETRIAGE_TEST_PRECEDENCE"] == "process-value"
