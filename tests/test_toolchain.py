"""Tests for the PE-capable toolchain: dispatch, flags, schema surface.

These exercise command *building* only — no Docker daemon or pefile needed.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "src"))

from agentre_bench.harness.config import BenchmarkConfig  # noqa: E402
from agentre_bench.harness.tools import (  # noqa: E402
    ENTROPY_SCRIPT,
    PE_INFO_SCRIPT,
    TOOL_SCHEMAS,
    ToolExecutor,
    _is_pe_file,
    schemas_to_gemini_declarations,
)


@pytest.fixture()
def workspace(tmp_path):
    (tmp_path / "sample.exe").write_bytes(b"MZ" + b"\x00" * 256)
    (tmp_path / "sample.elf").write_bytes(b"\x7fELF" + b"\x00" * 256)
    return tmp_path


@pytest.fixture()
def executor(workspace):
    cfg = BenchmarkConfig(
        project_root=workspace,
        workspace_dir=workspace,
        ground_truths_dir=workspace,
        use_docker=False,
    )
    return ToolExecutor(cfg, workspace / "sample.exe")


def test_schema_surface(executor):
    names = [t["name"] for t in TOOL_SCHEMAS]
    assert "pe_info" in names
    assert names.index("pe_info") < names.index("final_answer")
    objdump = next(t for t in TOOL_SCHEMAS if t["name"] == "objdump")
    assert "-p" in objdump["input_schema"]["properties"]["flags"]["enum"]
    strings = next(t for t in TOOL_SCHEMAS if t["name"] == "strings")
    assert "encoding" in strings["input_schema"]["properties"]


def test_gemini_schema_converts_nullable_type_unions():
    declarations = schemas_to_gemini_declarations(TOOL_SCHEMAS)
    final_answer = next(d for d in declarations if d["name"] == "final_answer")
    properties = final_answer["parameters"]["properties"]

    assert properties["decoded_c2"]["type"] == "string"
    assert properties["decoded_c2"]["nullable"] is True
    assert properties["c2_protocol"]["type"] == "string"
    assert properties["c2_protocol"]["nullable"] is True


def test_magic_sniffing(workspace):
    assert _is_pe_file(workspace / "sample.exe") is True
    assert _is_pe_file(workspace / "sample.elf") is False
    assert _is_pe_file(workspace / "missing.bin") is False


def test_objdump_dispatches_to_mingw_for_pe(executor):
    cmd = executor._build_command("objdump", {"path": "sample.exe", "flags": "-p"})
    assert cmd[0] == "x86_64-w64-mingw32-objdump"
    assert "-p" in cmd


def test_objdump_stays_gnu_for_elf(executor):
    cmd = executor._build_command("objdump", {"path": "sample.elf", "flags": "-d"})
    assert cmd[0] == "objdump"


def test_nm_dispatches_to_mingw_for_pe(executor):
    cmd = executor._build_command("nm", {"path": "sample.exe"})
    assert cmd[0] == "x86_64-w64-mingw32-nm"


def test_readelf_rejects_pe_with_hint(executor):
    with pytest.raises(ValueError, match="pe_info"):
        executor._build_command("readelf", {"path": "sample.exe", "flags": "-h"})


def test_pe_info_rejects_elf(executor):
    with pytest.raises(ValueError, match="not PE"):
        executor._build_command("pe_info", {"path": "sample.elf"})


def test_strings_encoding_flag(executor):
    cmd = executor._build_command(
        "strings", {"path": "sample.exe", "encoding": "l", "min_length": 6}
    )
    assert cmd == ["strings", "-n", "6", "-e", "l", cmd[-1]]
    with pytest.raises(ValueError):
        executor._build_command("strings", {"path": "sample.exe", "encoding": "z9"})


def test_scripts_are_valid_python():
    compile(ENTROPY_SCRIPT, "entropy", "exec")
    compile(PE_INFO_SCRIPT, "pe_info", "exec")
