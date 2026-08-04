from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    stdout: str
    stderr: str
    returncode: int
    truncated: bool = False
    timed_out: bool = False


class PathValidator:
    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir.resolve()

    def validate(self, path_str: str) -> Path:
        path = (self.workspace_dir / path_str).resolve()

        if not str(path).startswith(str(self.workspace_dir)):
            raise ValueError(
                f"Path escapes workspace: {path_str!r} "
                f"resolves outside {self.workspace_dir}"
            )

        # Reject symlinks pointing outside workspace
        if path.is_symlink():
            target = path.resolve()
            if not str(target).startswith(str(self.workspace_dir)):
                raise ValueError(
                    f"Symlink {path_str!r} points outside workspace: {target}"
                )

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        return path


class DockerRunner:
    def __init__(
        self,
        image: str,
        workspace_dir: Path,
        timeout: int = 30,
        max_output_chars: int = 8000,
        platform: str | None = None,
    ):
        self.image = image
        self.workspace_dir = workspace_dir.resolve()
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        # None = native host architecture (required on ARM hosts, where
        # amd64 containers cannot run without qemu binfmt).
        self.platform = platform

    def run(self, command: list[str]) -> RunResult:
        docker_cmd = [
            "docker", "run", "--rm",
            "--network=none",
            "--read-only",
            f"--memory=512m",
            f"--cpus=1",
            "-v", f"{self.workspace_dir}:/workspace:ro",
            "-w", "/workspace",
        ]
        if self.platform:
            docker_cmd += ["--platform", self.platform]
        docker_cmd += [self.image] + command

        log.debug("Docker command: %s", " ".join(docker_cmd))
        return self._exec(docker_cmd)

    def _exec(self, cmd: list[str]) -> RunResult:
        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            stdout = proc.stdout
            stderr = proc.stderr
            returncode = proc.returncode
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or b"").decode("utf-8", errors="replace")
            stderr = (e.stderr or b"").decode("utf-8", errors="replace")
            returncode = -1
            timed_out = True

        truncated = False
        if len(stdout) > self.max_output_chars:
            stdout = stdout[: self.max_output_chars] + "\n... [output truncated]"
            truncated = True
        if len(stderr) > self.max_output_chars:
            stderr = stderr[: self.max_output_chars] + "\n... [output truncated]"
            truncated = True

        return RunResult(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            truncated=truncated,
            timed_out=timed_out,
        )


class SubprocessRunner:
    def __init__(
        self,
        workspace_dir: Path,
        timeout: int = 30,
        max_output_chars: int = 8000,
    ):
        self.workspace_dir = workspace_dir.resolve()
        self.timeout = timeout
        self.max_output_chars = max_output_chars

    def run(self, command: list[str]) -> RunResult:
        log.debug("Subprocess command: %s", " ".join(command))
        timed_out = False
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.workspace_dir),
            )
            stdout = proc.stdout
            stderr = proc.stderr
            returncode = proc.returncode
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or b"").decode("utf-8", errors="replace")
            stderr = (e.stderr or b"").decode("utf-8", errors="replace")
            returncode = -1
            timed_out = True
        except FileNotFoundError:
            return RunResult(
                stdout="",
                stderr=f"Command not found: {command[0]}",
                returncode=127,
            )

        truncated = False
        if len(stdout) > self.max_output_chars:
            stdout = stdout[: self.max_output_chars] + "\n... [output truncated]"
            truncated = True
        if len(stderr) > self.max_output_chars:
            stderr = stderr[: self.max_output_chars] + "\n... [output truncated]"
            truncated = True

        return RunResult(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            truncated=truncated,
            timed_out=timed_out,
        )
