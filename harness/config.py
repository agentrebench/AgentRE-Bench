from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_KEY_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

DEFAULT_TOOLS = [
    "file", "strings", "readelf", "objdump", "nm", "hexdump", "xxd", "entropy",
]


def _load_dotenv(project_root: Path) -> None:
    """Load .env file from project root into os.environ (without overwriting)."""
    env_path = project_root / ".env"
    if not env_path.is_file():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            # Don't overwrite existing env vars (CLI/shell takes priority)
            if key not in os.environ:
                os.environ[key] = value


@dataclass
class BenchmarkConfig:
    project_root: Path
    workspace_dir: Path          # binaries/
    ground_truths_dir: Path

    model: str = "claude-opus-4-6"
    provider: str = "anthropic"
    api_key: str = ""

    max_tool_calls: int = 25
    tool_timeout_seconds: int = 30
    max_output_chars: int = 50000
    max_tokens: int = 4096

    docker_image: str = "agentre-bench-tools:latest"
    use_docker: bool = True

    allowed_tools: list[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))

    results_dir: Path = field(default=None)
    verbose: bool = False

    def __post_init__(self):
        self.project_root = Path(self.project_root).resolve()
        self.workspace_dir = Path(self.workspace_dir).resolve()
        self.ground_truths_dir = Path(self.ground_truths_dir).resolve()

        if self.results_dir is None:
            # Namespace by provider/model to avoid overwriting across runs
            safe_model = self.model.replace("/", "_").replace(":", "_")
            self.results_dir = self.project_root / "results" / f"{self.provider}_{safe_model}"
        else:
            self.results_dir = Path(self.results_dir).resolve()

        # Load .env file so API keys are available via env vars
        _load_dotenv(self.project_root)

    def resolve_api_key(self) -> str:
        # 1. Explicit --api-key flag (highest priority)
        if self.api_key:
            return self.api_key
        # 2. Environment variable (includes values loaded from .env)
        env_var = ENV_KEY_MAP.get(self.provider)
        if env_var:
            key = os.environ.get(env_var, "")
            if key:
                return key
        raise ValueError(
            f"No API key for provider {self.provider!r}. "
            f"Set {ENV_KEY_MAP.get(self.provider, 'PROVIDER_API_KEY')} in .env or environment, "
            f"or pass --api-key."
        )

    @property
    def agent_outputs_dir(self) -> Path:
        return self.results_dir / "agent_outputs"

    @property
    def transcripts_dir(self) -> Path:
        return self.results_dir / "transcripts"
