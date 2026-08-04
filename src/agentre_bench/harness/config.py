from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_KEY_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "glm": "GLM_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
}

API_FILE_LABEL_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "fable": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "glm": "GLM_API_KEY",
}

DEFAULT_TOOLS = [
    "file", "strings", "readelf", "objdump", "nm", "hexdump", "xxd", "entropy",
    "pe_info",
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


def _read_api_file(api_path: Path) -> dict[str, str]:
    """Read the repo-local ``api`` key file without mutating the environment.

    The private development file uses friendly labels such as ``Claude:`` and
    ``Kimi:``, while .env uses conventional environment-variable names. Both
    forms are accepted here. Values are never logged or included in config
    serialization.
    """
    if not api_path.is_file():
        return {}

    keys: dict[str, str] = {}
    with open(api_path) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()

            equals = line.find("=")
            colon = line.find(":")
            separators = [i for i in (equals, colon) if i >= 0]
            if not separators:
                # The private benchmark key file may put an Anthropic key on
                # the line below a human-readable ``Claude: <model>`` label.
                # Recognize the provider-specific key prefix so the actual key
                # supersedes that descriptor.
                if line.startswith("sk-ant-"):
                    keys["ANTHROPIC_API_KEY"] = line
                continue
            split_at = min(separators)
            label = line[:split_at].strip()
            value = line[split_at + 1:].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if not value:
                continue

            normalized = "".join(ch for ch in label.lower() if ch.isalnum())
            env_name = API_FILE_LABEL_MAP.get(normalized)
            if env_name is None and label.upper() in ENV_KEY_MAP.values():
                env_name = label.upper()
            if env_name:
                keys[env_name] = value
    return keys


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

    # Provider-specific reasoning knobs (forwarded via create_provider).
    reasoning_effort: str | None = None   # OpenAI reasoning models
    thinking_effort: str | None = None    # Anthropic thinking models

    docker_image: str = "agentre-bench-tools:latest"
    # None = native host arch; set "linux/amd64" on x86 runners to pin.
    docker_platform: str | None = None
    use_docker: bool = True

    # Seconds to sleep between tasks. Useful for providers with strict
    # per-minute token caps (e.g. Gemini free tier).
    inter_task_sleep_seconds: float = 0.0

    allowed_tools: list[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))

    # Optional custom manifest path (defaults to project_root / "tasks.json").
    manifest_path: Path | None = None
    # Optional private key file. Defaults to project_root / "api" when present.
    api_file: Path | None = None

    results_dir: Path = field(default=None)
    verbose: bool = False
    resume: bool = False

    def __post_init__(self):
        self.project_root = Path(self.project_root).resolve()
        self.workspace_dir = Path(self.workspace_dir).resolve()
        self.ground_truths_dir = Path(self.ground_truths_dir).resolve()
        if self.api_file is None:
            default_api_file = self.project_root / "api"
            self.api_file = default_api_file if default_api_file.is_file() else None
        else:
            self.api_file = Path(self.api_file).resolve()

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
        # 2. Repo-local api file requested for development benchmark runs.
        env_var = ENV_KEY_MAP.get(self.provider)
        if env_var and self.api_file:
            key = _read_api_file(self.api_file).get(env_var, "")
            if key:
                return key
        # 3. Environment variable (includes values loaded from .env)
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
