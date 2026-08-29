"""Local development configuration with environment-first precedence."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from genometriage.benchmark.loader import PROJECT_ROOT


def load_project_environment(path: Optional[Path] = None) -> bool:
    """Load an ignored .env file without replacing process environment values."""

    env_path = Path(path) if path is not None else PROJECT_ROOT / ".env"
    return load_dotenv(dotenv_path=env_path, override=False)
