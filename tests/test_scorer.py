"""Tests for the v3 scorer: tiers, null renormalization, aliases, spurious fields."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

from scorer import (  # noqa: E402
    BONUS_WEIGHTS,
    PE_INJECTION_WEIGHTS,
    STANDARD_WEIGHTS,
    canonical_file_type,
    resolve_tier,
    score_encryption_algorithm,
    score_encryption_key,
    score_file_type,
    score_nested_details,
    score_sample,
    score_semantic_list_recall,
    score_semantic_techniques,
)

GT_DIR = pathlib.Path(__file__).parents[1] / "ground_truths"
V3_GT_DIR = pathlib.Path(__file__).parents[1] / "version3" / "ground_truths"


# ── Rubric sanity ──────────────────────────────────────────────────

def test_rubrics_sum_to_one():
    assert sum(STANDARD_WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(PE_INJECTION_WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(BONUS_WEIGHTS.values()) == pytest.approx(1.0)


# ── file_type canonicalization ─────────────────────────────────────

@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("PE64", "PE32+", 1.0),      # what GT says vs what `file` says
        ("PE64", "pe64", 1.0),
        ("PE64", "PE32", 0.5),       # same family, wrong bitness
        ("ELF64", "ELF64-SO", 1.0),
        ("ELF64", "PE64", 0.0),
        ("PE64", None, 0.0),
    ],
)
def test_file_type_aliases(a, b, expected):
    assert score_file_type(a, b) == expected


def test_canonical_pe32_plus_is_64bit():
    assert canonical_file_type("PE32+") == ("pe", 64)
    assert canonical_file_type("PE32") == ("pe", 32)


# ── Tier resolution ────────────────────────────────────────────────

def test_tier_explicit_field_wins():
    assert resolve_tier({"tier": "bonus", "sample": "level1_x"}) == "bonus"
    assert resolve_tier({"tier": "pe_injection"}) == "pe_injection"


def test_tier_legacy_and_pe_fallbacks():
    assert resolve_tier({"sample": "level13_MetamorphicDropper"}) == "bonus"
    assert resolve_tier({"sample": "windows_level23_WannaCryWorm"}) == "bonus"
    assert resolve_tier({"sample": "x", "file_type": "PE64"}) == "pe_injection"
    assert resolve_tier({"sample": "level1_TCPServer", "file_type": "ELF64"}) == "standard"


# ── Standard tier: null renormalization + spurious ────────────────

GT_L4 = {  # level4 shape: no C2
    "sample": "level4_polymorphicReverseShell",
    "tier": "standard",
    "file_type": "ELF64",
    "encoded_strings": True,
    "decoded_c2": None,
    "c2_protocol": None,
    "techniques": ["runtime_polymorphism", "nop_sled", "shellcode_gen"],
}


def test_null_c2_fields_are_dropped_not_free():
    perfect = {
        "file_type": "ELF64",
        "encoded_strings": True,
        "decoded_c2": None,
        "c2_protocol": None,
        "techniques": GT_L4["techniques"],
    }
    r = score_sample(GT_L4, perfect)
    assert r["final_score"] == 1.0
    assert "decoded_c2" not in r["field_scores"]


def test_spurious_c2_claim_is_penalized():
    liar = {
        "file_type": "ELF64",
        "encoded_strings": True,
        "decoded_c2": "1.2.3.4:5555",
        "c2_protocol": "TCP",
        "techniques": GT_L4["techniques"],
    }
    r = score_sample(GT_L4, liar)
    assert set(r["spurious_fields"]) == {"decoded_c2", "c2_protocol"}
    assert r["spurious_penalty"] == pytest.approx(0.10)
    assert r["final_score"] == pytest.approx(0.90)


def test_nullish_strings_are_not_spurious():
    cautious = {
        "file_type": "ELF64",
        "encoded_strings": True,
        "decoded_c2": "none",
        "c2_protocol": "N/A",
        "techniques": GT_L4["techniques"],
    }
    r = score_sample(GT_L4, cautious)
    assert r["spurious_fields"] == []
    assert r["final_score"] == 1.0


# ── PE tier ────────────────────────────────────────────────────────

def _load_gt(name):
    import json

    path = GT_DIR / name
    if name.startswith("windows_"):
        path = V3_GT_DIR / name
    with open(path) as f:
        return json.load(f)


def test_pe_perfect_answer_scores_one():
    gt = _load_gt("windows_level14_DLLInjection.json")
    perfect = {
        "file_type": "PE32+",  # alias of GT's "PE64"
        "encoded_strings": True,
        "decoded_c2": None,
        "c2_protocol": None,
        "techniques": gt["techniques"],
        "injection_details": gt["injection_details"],
        "decoded_strings": gt["decoded_strings"],
        "anti_analysis": gt["anti_analysis"],
        "encryption_details": {"algorithm": "XOR", "key": "5A3C7FE12D94B86A"},
    }
    r = score_sample(gt, perfect)
    assert r["tier"] == "pe_injection"
    assert r["final_score"] == 1.0, r["field_scores"]


def test_pe_level_without_injection_details_still_perfect():
    gt = _load_gt("windows_level18_HellsGate.json")  # no injection_details in GT
    perfect = {
        "file_type": "PE64",
        "encoded_strings": True,
        "techniques": gt["techniques"],
        "anti_analysis": gt["anti_analysis"],
        "encryption_details": {"algorithm": "RC4", "key": "deadbeef"},
    }
    r = score_sample(gt, perfect)
    # renormalized: injection_details weight redistributes; encryption key
    # correctness is checked against GT candidates, not our made-up one.
    assert "injection_details" not in r["field_scores"]
    assert r["field_scores"]["encryption_key"] == 0.0  # wrong key
    assert 0.0 < r["final_score"] < 1.0


def test_encryption_key_hex_formats():
    gt_enc = {"algorithm": "XOR", "key": [90, 60, 127, 225, 45, 148, 184, 106]}
    assert score_encryption_key(gt_enc, "5A3C7FE12D94B86A") == 1.0
    assert score_encryption_key(gt_enc, "0x5a 3c 7f e1 2d 94 b8 6a") == 1.0
    assert score_encryption_key(gt_enc, "wrong") == 0.0
    assert score_encryption_key(gt_enc, None) == 0.0


def test_encryption_key_ascii_byte_equivalence():
    # L23: byte list whose ASCII form is the key string
    gt_enc = {
        "file_encryption": {
            "algorithm": "AES-128",
            "key": [87, 64, 110, 67, 114, 121, 80, 116, 48, 75, 51, 121, 50, 48, 50, 52],
            "key_string": "W@nCryPt0K3y2024",
        }
    }
    assert score_encryption_key(gt_enc, "W@nCryPt0K3y2024") == 1.0
    assert score_encryption_key(gt_enc, "57406e4372795074304b337932303234") == 1.0


def test_encryption_key_allows_explanatory_annotations():
    gt_enc = {
        "algorithm": "RC4",
        "key": [82, 51, 109, 48, 116, 51, 95, 80, 69, 95, 51, 120, 51, 99, 95, 75],
    }
    assert score_encryption_key(
        gt_enc,
        "R3m0t3_PE_3x3c_K (16 bytes ASCII, passed to rc4_init)",
    ) == 1.0
    assert score_encryption_key(
        gt_enc,
        "RC4 key: 52 33 6D 30 74 33 5F 50 45 5F 33 78 33 63 5F 4B (16 bytes)",
    ) == 1.0


def test_encryption_key_annotation_does_not_accept_prefix_of_longer_key():
    gt_enc = {"algorithm": "AES-256", "key_string": "AES-256-S3cur3-K3y-F0r-Mult1-T3c"}
    assert score_encryption_key(
        gt_enc,
        "AES-256-S3cur3-K3y-F0r-Mult1-T3cn (33 bytes)",
    ) == 0.0


def test_encryption_algorithm_annotation_gets_full_credit():
    assert score_encryption_algorithm(
        {"algorithm": "RC4"},
        "RC4 (custom KSA/PRGA)",
    ) == 1.0
    assert score_encryption_algorithm(
        {"algorithms": ["XOR", "RC4"]},
        "XOR + RC4 (two-layer encryption)",
    ) == 1.0


def test_encryption_algorithm_family_only_gets_partial_credit():
    assert score_encryption_algorithm(
        {"algorithm": "AES-128 (simplified S-box, 10 rounds)"},
        "AES",
    ) == 0.5


def test_encryption_algorithm_wrong_name_gets_no_credit():
    assert score_encryption_algorithm({"algorithm": "RC4"}, "RC5") == 0.0


def test_pe_compound_technique_labels_match_semantically():
    gt = _load_gt("windows_level14_DLLInjection.json")
    techniques = [
        "dll_injection_CreateRemoteThread_LoadLibraryA",
        "toolhelp_process_enumeration",
        "VirtualAllocEx_WriteProcessMemory",
        "manual_getprocaddress_PE_export_table_walking",
        "repeating_key_XOR_string_obfuscation",
        "PEB_BeingDebugged_antidebug",
    ]

    credit, extras, missing = score_semantic_techniques(gt["techniques"], techniques)

    assert credit == pytest.approx(1.0)
    assert extras == []
    assert missing == []


def test_pe_anti_analysis_accepts_evidence_prose():
    credit = score_semantic_list_recall(
        ["peb_beingdebugged_check"],
        [
            "Direct PEB BeingDebugged check reads GS:[0x60], tests PEB+2, "
            "and exits early when a debugger is attached"
        ],
    )

    assert credit == pytest.approx(1.0)


def test_nested_details_match_values_under_model_chosen_keys():
    gt = {
        "method": "CreateRemoteThread + LoadLibraryA",
        "target_process": "explorer.exe",
        "dll_path_hex": "49532A686034252B3D312D41680858606D322D417468576F6D4238686E616D6A",
    }
    answer = {
        "execution": "Classic remote DLL injection with CreateRemoteThread + LoadLibraryA",
        "target": "The selected target process is explorer.exe",
        "decoded_bytes": "49532a686034252b3d312d41680858606d322d417468576f6d4238686e616d6a",
    }

    assert score_nested_details(gt, answer) == pytest.approx(1.0)


def test_pe_semantic_extras_are_not_double_penalized():
    gt = _load_gt("windows_level14_DLLInjection.json")
    answer = {
        "file_type": "PE64",
        "encoded_strings": True,
        "techniques": gt["techniques"] + ["invented_one", "invented_two"],
    }

    result = score_sample(gt, answer)

    assert result["field_scores"]["techniques"] < 1.0
    assert result["hallucination_penalty"] == 0.0


# ── Bonus tier (L23 nested encryption) ────────────────────────────

def test_bonus_l23_nested_encryption_scored():
    gt = _load_gt("windows_level23_WannaCryWorm.json")
    perfect = {
        "file_type": "PE32+",
        "encoded_strings": True,
        "decoded_c2": gt["decoded_c2"],
        "c2_protocol": gt["c2_protocol"],
        "techniques": gt["techniques"],
        "decoded_strings": gt["decoded_strings"],
        "anti_analysis": gt["anti_analysis"],
        "encryption_details": {"algorithm": "AES-128", "key": "W@nCryPt0K3y2024"},
    }
    r = score_sample(gt, perfect)
    assert r["tier"] == "bonus"
    assert r["field_scores"]["encryption_algorithm"] == 1.0
    assert r["field_scores"]["encryption_key"] == 1.0
    assert r["field_scores"]["decoded_strings"] == 1.0
    assert r["final_score"] == 1.0, r["field_scores"]


def test_bonus_hallucination_uses_lighter_penalty():
    gt = _load_gt("windows_level23_WannaCryWorm.json")
    answer = {
        "file_type": "PE64",
        "encoded_strings": True,
        "decoded_c2": gt["decoded_c2"],
        "c2_protocol": gt["c2_protocol"],
        "techniques": gt["techniques"] + ["invented_one", "invented_two"],
        "decoded_strings": gt["decoded_strings"],
        "anti_analysis": gt["anti_analysis"],
        "encryption_details": {"algorithm": "AES-128", "key": "W@nCryPt0K3y2024"},
    }
    r = score_sample(gt, answer)
    # PE semantic F1 accounts for the extras inside the technique field; the
    # old scorer charged the same claims a second time as a global penalty.
    assert r["hallucination_penalty"] == 0.0
    assert r["field_scores"]["techniques"] < 1.0
