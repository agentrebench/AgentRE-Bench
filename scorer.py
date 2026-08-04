#!/usr/bin/env python3
"""
AgentRE-Bench Scorer (v3)

Tiers:
  standard      ELF C2-recovery levels (1-12)
  pe_injection  Windows PE injection/evasion levels (14-22)
  bonus         deep-rubric levels (13, 23)

Scoring model:
  - Each tier has a field -> weight rubric (weights sum to 1.0).
  - Fields whose ground-truth value is null/empty are DROPPED and the
    remaining weights renormalized to sum to 1.0. (Fix: null C2 fields
    on non-C2 tasks used to be 50% of the weighted score for free.)
  - A non-null agent value on a null ground-truth field is a spurious
    claim and costs SPURIOUS_FIELD_PENALTY each.
  - Extra (hallucinated) technique claims cost HALLUCINATION_PENALTY each.
  - Standard + PE tiers are averaged -> main score (1.0 max).
  - Bonus levels are averaged        -> bonus score (1.0 max).
  - Total possible: 2.0 pts.

Tier resolution order:
  1. explicit "tier" in the ground truth JSON
  2. legacy name pattern (level13 / level23 -> bonus)
  3. PE file_type -> pe_injection
  4. default -> standard

Usage:
    # Single sample
    python scorer.py -g ground_truths/level1_TCPServer.json \
                     -a agent_outputs/level1_TCPServer.json

    # Full benchmark (batch)
    python scorer.py -G ground_truths/ -A agent_outputs/ -r results.json
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("scorer")

# ===================================================================
# Rubrics (base weights — renormalized when GT fields are null)
# ===================================================================

# Standard ELF levels: C2 recovery + techniques.
STANDARD_WEIGHTS = {
    "decoded_c2":      0.40,
    "techniques":      0.30,
    "file_type":       0.10,
    "encoded_strings": 0.10,
    "c2_protocol":     0.10,
}

# Windows PE levels: injection method, crypto recovery, anti-analysis.
# C2 fields are weighted for hypothetical PE-with-C2 tasks but drop out
# (renormalized) on the current 14-22 set, which has no C2.
PE_INJECTION_WEIGHTS = {
    "techniques":            0.25,
    "injection_details":     0.20,
    "decoded_c2":            0.10,
    "encryption_key":        0.10,
    "decoded_strings":       0.10,
    "anti_analysis":         0.10,
    "encryption_algorithm":  0.05,
    "c2_protocol":           0.05,
    "file_type":             0.03,
    "encoded_strings":       0.02,
}

# Bonus levels (13, 23): deep rubric with crypto + string recovery.
BONUS_WEIGHTS = {
    "decoded_c2":              0.15,
    "encryption_algorithm":    0.10,
    "encryption_key":          0.20,
    "encryption_key_storage":  0.05,
    "techniques":              0.15,
    "decoded_strings":         0.15,
    "anti_analysis":           0.10,
    "file_type":               0.03,
    "encoded_strings":         0.02,
    "c2_protocol":             0.05,
}

HALLUCINATION_PENALTY = 0.05        # standard / PE, per extra technique claim
BONUS_HALLUCINATION_PENALTY = 0.03  # bonus levels (more techniques expected)
SPURIOUS_FIELD_PENALTY = 0.05       # non-null claim on a null GT field
BONUS_SPURIOUS_FIELD_PENALTY = 0.03

BONUS_SAMPLE_PATTERN = re.compile(r"level(?:13|23)", re.IGNORECASE)

TIERS = ("standard", "pe_injection", "bonus")

# Agent strings that mean "no value" rather than a literal claim.
_NULLISH_RE = re.compile(
    r"^\s*(none|null|n/?a|no[ -]?c2|not[ -]present|unknown|nil|)\s*$",
    re.IGNORECASE,
)


# ===================================================================
# Shared helpers
# ===================================================================
def normalize_c2(value):
    if value is None:
        return None
    return str(value).strip().lower().rstrip("/")


def _is_null(value):
    """True if a ground-truth field has no scorable content."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict, set)):
        return len(value) == 0
    return False


def _agent_nullish(value):
    """True if the agent's value means 'no X' rather than a literal claim."""
    if value is None:
        return True
    if isinstance(value, str):
        return bool(_NULLISH_RE.match(value))
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def score_decoded_c2(gt_val, agent_val):
    gt_norm = normalize_c2(gt_val)
    agent_norm = normalize_c2(agent_val)

    if gt_norm == agent_norm:
        return 1.0
    if gt_norm is None and agent_norm is None:
        return 1.0
    if gt_norm is None or agent_norm is None:
        return 0.0

    # Partial: host/IP matches but port/path differs
    gt_host = gt_norm.split("://")[-1].split("/")[0].split(":")[0]
    agent_host = agent_norm.split("://")[-1].split("/")[0].split(":")[0]
    if gt_host == agent_host:
        return 0.5

    return 0.0


def score_set_overlap(gt_items, agent_items):
    """Jaccard overlap.  Returns (credit, extra_count)."""
    gt_set = set(gt_items or [])
    agent_set = set(agent_items or [])
    if not gt_set and not agent_set:
        return 1.0, 0
    if not gt_set:
        return 0.0, len(agent_set)
    union = gt_set | agent_set
    inter = gt_set & agent_set
    extra = agent_set - gt_set
    return (len(inter) / len(union) if union else 1.0), len(extra)


PE_CANONICAL_TECHNIQUES = frozenset("""
aes128_encryption aes128_file_encryption aes256_encryption
anti_debug_checkremotedebuggerpresent anti_debug_isdebuggerpresent
anti_debug_ntqueryinformationprocess anti_debug_peb
anti_debug_threadhidefromdebugger anti_hooking anti_sandbox_dll_check
antivm_cpuid antivm_driver_check antivm_sandboxie apc_injection
base_relocation_fixup base_relocation_fixup_remote c2_beacon
code_cave_injection cpp_class_obfuscation createremotethread
createremotethread_injection createthread_execution direct_nt_syscall
directory_traversal_encryption dll_injection dllmain_invocation
dynamic_syscall_resolution export_table_parsing file_extension_targeting
getthreadcontext ghost_process_hollowing hells_gate
hells_gate_syscall_resolution hidden_file_attributes import_table_resolution
killswitch_domain_check loadlibrary_injection manual_getprocaddress
manual_pe_mapping manual_pe_parsing mutex_single_instance
ntalertresumethread ntallocatevirtualmemory ntcreateprocess ntcreatethreadex
ntprotectvirtualmemory ntqueryinformationprocess_antidebug ntqueueapcthread
ntresumethread ntunmapviewofsection ntwritevirtualmemory pe_export_parsing
pe_header_parsing pe_section_mapping pe_section_parsing peb_antidebug
peb_parsing peb_walk_kernel32 port_445_scanning process_enumeration
process_hollowing ransom_note_drop rc4_encryption readprocessmemory
recursive_file_encryption reflective_dll_injection remote_pe_execution
resumethread rsa2048_key_embedding rtlcreateprocessparameters
rwx_memory_allocation sbox_substitution section_mapping service_persistence
setthreadcontext smb_worm_propagation suspended_process_creation
suspended_thread_manipulation syscall_stub_parsing system_info_exfiltration
thread_enumeration tls_callback virtual_method_dispatch virtualalloc_rwx
virtualallocex virtualallocex_write virtualprotect_rwx writeprocessmemory
xor_encryption xor_string_encryption xor_string_obfuscation
""".split())

_TECHNIQUE_ATOMS = (
    "checkremotedebuggerpresent",
    "createremotethread",
    "getthreadcontext",
    "isdebuggerpresent",
    "loadlibrary",
    "manualgetprocaddress",
    "ntalertresumethread",
    "ntallocatevirtualmemory",
    "ntcreateprocess",
    "ntcreatethreadex",
    "ntprotectvirtualmemory",
    "ntqueryinformationprocess",
    "ntqueueapcthread",
    "ntresumethread",
    "ntunmapviewofsection",
    "ntwritevirtualmemory",
    "readprocessmemory",
    "resumethread",
    "rtlcreateprocessparameters",
    "setthreadcontext",
    "virtualallocex",
    "virtualprotect",
    "writeprocessmemory",
)

_TECHNIQUE_GENERIC_SUFFIXES = {
    "allocation", "check", "creation", "encryption", "execution", "fixup",
    "injection", "mapping", "manipulation", "obfuscation", "parsing",
    "propagation", "resolution", "scanning", "targeting",
}


def _label_key(value):
    """Normalize prose/camelCase labels without requiring an exact taxonomy ID."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value or ""))
    text = text.lower().replace("hell's", "hells")
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text)).strip("_")


def _semantic_tokens(value):
    key = _label_key(value)
    compact = key.replace("_", "")
    aliases = {
        "allocate": "allocation", "allocated": "allocation",
        "create": "creation", "created": "creation",
        "decode": "encryption", "decoded": "encryption",
        "decoding": "encryption", "decrypt": "encryption",
        "decrypted": "encryption", "decryption": "encryption",
        "encode": "encryption", "encoded": "encryption",
        "encoding": "encryption", "encrypt": "encryption",
        "encrypted": "encryption", "obfuscate": "encryption",
        "obfuscated": "encryption", "obfuscation": "encryption",
        "enumerate": "enumeration", "enumerated": "enumeration",
        "inspect": "parsing", "inspection": "parsing", "lookup": "parsing",
        "map": "mapping", "mapped": "mapping", "parse": "parsing",
        "parsed": "parsing", "suspend": "suspended",
        "suspension": "suspended", "walk": "parsing", "walking": "parsing",
    }
    tokens = {aliases.get(token, token) for token in key.split("_") if token}

    for atom in _TECHNIQUE_ATOMS:
        if atom in compact:
            tokens.add(atom)

    if "manualgetprocaddress" in tokens:
        tokens.update({"manual", "getprocaddress"})
    if "loadlibrary" in compact:
        tokens.add("loadlibrary")
    if "hellsgate" in compact:
        tokens.add("hellsgate")
    if "beingdebugged" in compact or "debuggerpresent" in compact:
        tokens.add("antidebug")
    if {"anti", "debug"} <= tokens:
        tokens.add("antidebug")
    if "toolhelp" in compact or "snapshot" in tokens:
        if "process" in tokens or "thread" in tokens:
            tokens.add("enumeration")
    if "writeprocessmemory" in tokens:
        tokens.add("write")
    if "relocation" in tokens or "relocations" in tokens:
        tokens.update({"relocation", "fixup"})
    if "sbox" in tokens:
        tokens.add("substitution")
    if "cpuid" in tokens and "hypervisor" in tokens:
        tokens.add("antivm")
    if "hook" in tokens or "hooks" in tokens:
        tokens.update({"hooking", "anti"})
    if "createprocess" in compact and "suspended" in tokens:
        tokens.update({"process", "creation"})
    if any(name in compact for name in ("xor", "rc4", "aes128", "aes256")):
        tokens.add("encryption")
    return key, compact, tokens


def _semantic_label_match(expected, claimed):
    """Whether a free-form PE label expresses a canonical expected label."""
    g_key, g_compact, g_tokens = _semantic_tokens(expected)
    a_key, a_compact, a_tokens = _semantic_tokens(claimed)
    if not g_key or not a_key:
        return False
    if g_key == a_key:
        return True
    if min(len(g_compact), len(a_compact)) >= 7:
        if g_compact in a_compact or a_compact in g_compact:
            return True
    if g_tokens <= a_tokens:
        return True

    missing = g_tokens - a_tokens
    identifying = g_tokens - _TECHNIQUE_GENERIC_SUFFIXES
    strong = identifying & set(_TECHNIQUE_ATOMS)
    if missing <= _TECHNIQUE_GENERIC_SUFFIXES and identifying <= a_tokens:
        if strong or len(identifying) >= 2:
            return True

    hits = len(g_tokens & a_tokens)
    return len(g_tokens) >= 2 and hits >= 2 and hits / len(g_tokens) >= 0.75


def score_semantic_techniques(gt_items, agent_items):
    """PE technique F1 with semantic labels and compound-label expansion."""
    gt_list = [str(item) for item in (gt_items or [])]
    agent_list = [str(item) for item in (agent_items or [])]
    if not gt_list and not agent_list:
        return 1.0, [], []

    agent_blob = " ".join(agent_list)
    matched_gt = {
        expected for expected in gt_list
        if any(_semantic_label_match(expected, claim) for claim in agent_list)
        or _semantic_label_match(expected, agent_blob)
    }
    unmatched_claims = [
        claim for claim in agent_list
        if not any(_semantic_label_match(expected, claim) for expected in gt_list)
    ]
    missing = sorted(set(gt_list) - matched_gt)
    tp = len(matched_gt)
    fp = len(unmatched_claims)
    fn = len(missing)
    denom = 2 * tp + fp + fn
    credit = (2 * tp / denom) if denom else 1.0
    return credit, sorted(set(unmatched_claims)), missing


def score_semantic_list_recall(gt_items, agent_items):
    """Recall for canonical expected labels reported as explanatory prose."""
    gt_list = [str(item) for item in (gt_items or [])]
    agent_list = [str(item) for item in (agent_items or [])]
    if not gt_list:
        return 1.0
    blob = " ".join(agent_list)
    hits = sum(
        1 for expected in gt_list
        if any(_semantic_label_match(expected, claim) for claim in agent_list)
        or _semantic_label_match(expected, blob)
    )
    return hits / len(gt_list)


def score_exact(gt_val, agent_val):
    if gt_val is None and agent_val is None:
        return 1.0
    if isinstance(gt_val, str) and isinstance(agent_val, str):
        return 1.0 if gt_val.strip().lower() == agent_val.strip().lower() else 0.0
    return 1.0 if gt_val == agent_val else 0.0


def score_fuzzy_string(gt_val, agent_val):
    """Case-insensitive substring / contains check for partial credit."""
    if gt_val is None and agent_val is None:
        return 1.0
    if gt_val is None or agent_val is None:
        return 0.0
    g = str(gt_val).strip().lower()
    a = str(agent_val).strip().lower()
    if g == a:
        return 1.0
    if g in a:
        return 1.0
    if a in g:
        return 0.5

    # Ground-truth detail strings are concise while agents often submit a
    # longer evidence-backed explanation. Score expected content tokens, not
    # identical prose or identical model-chosen JSON key names.
    stop = {"and", "for", "from", "into", "the", "then", "via", "with"}
    g_tokens = {
        token for token in re.findall(r"[a-z0-9]{3,}", g)
        if token not in stop
    }
    if g_tokens:
        a_tokens = set(re.findall(r"[a-z0-9]{3,}", a))
        coverage = len(g_tokens & a_tokens) / len(g_tokens)
        if coverage >= 0.75:
            return 1.0
        if coverage >= 0.4:
            return 0.5
    return 0.0


# ===================================================================
# file_type canonicalization (PE64 vs PE32+, ELF64 vs ELF64-SO, ...)
# ===================================================================
def canonical_file_type(value):
    """Map a file-type string to (family, bits).  None if unparseable."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    if v.startswith("pe"):
        # "PE32+" is 64-bit; plain "PE32" is 32-bit; "PE64" is 64-bit.
        if "pe32+" in v or "pe64" in v or "64" in v:
            return ("pe", 64)
        if "pe32" in v or "32" in v:
            return ("pe", 32)
        return ("pe", None)
    if v.startswith("elf"):
        if "64" in v:
            return ("elf", 64)
        if "32" in v:
            return ("elf", 32)
        return ("elf", None)
    if "mach" in v:
        return ("macho", 64 if "64" in v else None)
    return (v, None)


def score_file_type(gt_val, agent_val):
    gt_c = canonical_file_type(gt_val)
    ag_c = canonical_file_type(agent_val)
    if gt_c is None and ag_c is None:
        return 1.0
    if gt_c is None or ag_c is None:
        return 0.0
    if gt_c == ag_c:
        return 1.0
    if gt_c[0] == ag_c[0]:
        return 0.5
    return 0.0


# ===================================================================
# Encryption helpers — walk arbitrarily nested encryption_details
# (L13 is flat; L23 nests file_encryption / string_obfuscation / rsa_key)
# ===================================================================
def _walk_dicts(node):
    """Yield every dict in a nested structure."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_dicts(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_dicts(item)


def _bytes_to_hex(byte_list):
    try:
        return "".join(f"{int(b) & 0xFF:02x}" for b in byte_list)
    except (TypeError, ValueError):
        return ""


def _printable_ascii(byte_list):
    try:
        chars = bytes(int(b) & 0xFF for b in byte_list)
    except (TypeError, ValueError):
        return ""
    if chars and all(0x20 <= b < 0x7F for b in chars):
        return chars.decode("ascii")
    return ""


def _hex_to_ascii(hex_str):
    try:
        raw = bytes.fromhex(hex_str)
    except ValueError:
        return ""
    if raw and all(0x20 <= b < 0x7F for b in raw):
        return raw.decode("ascii")
    return ""


def _enc_algorithms(enc_details):
    """All algorithm strings found anywhere in encryption_details."""
    algos = []
    for node in _walk_dicts(enc_details):
        algo = node.get("algorithm")
        if isinstance(algo, str) and algo.strip():
            algos.append(algo.strip().lower())
    return algos


def _enc_key_candidates(enc_details):
    """All plausible string forms of every key in encryption_details.

    Covers byte lists, key_hex, key_string, and ASCII<->hex conversion
    so an agent reporting either form gets credit.
    """
    cands = set()
    for node in _walk_dicts(enc_details):
        key = node.get("key")
        if isinstance(key, list) and key:
            hex_form = _bytes_to_hex(key)
            if hex_form:
                cands.add(hex_form)
            ascii_form = _printable_ascii(key)
            if ascii_form:
                cands.add(ascii_form.lower())
        elif isinstance(key, str) and key.strip():
            cands.add(key.strip().lower())
            as_ascii_hex = _bytes_to_hex(key.encode("utf-8", errors="ignore"))
            if as_ascii_hex:
                cands.add(as_ascii_hex)
        for field in ("key_hex", "key_string"):
            alt = node.get(field)
            if isinstance(alt, str) and alt.strip():
                cands.add(alt.strip().lower())
                if field == "key_hex":
                    ascii_form = _hex_to_ascii(alt.strip())
                    if ascii_form:
                        cands.add(ascii_form.lower())
    return {c for c in cands if c}


def _norm_hexish(s):
    """Hex-normalized form: strip 0x, separators, lowercase; '' if not hex."""
    cleaned = re.sub(r"0x", "", str(s).lower())
    cleaned = re.sub(r"[^0-9a-f]", "", cleaned)
    if cleaned and len(cleaned) % 2 == 0 and re.fullmatch(r"[0-9a-f]+", cleaned):
        return cleaned
    return ""


def score_encryption_algorithm(gt_enc, agent_val):
    if _agent_nullish(agent_val):
        return 0.0
    algos = _enc_algorithms(gt_enc)
    if not algos:
        return 1.0
    a = str(agent_val).strip().lower()
    # GT strings may carry descriptive commentary ("AES-128 (simplified
    # S-box, 10 rounds)"); the algorithm name proper is what must match.
    def bases(g):
        yield g
        stripped = re.sub(r"\s*\([^)]*\)", "", g).strip()
        if stripped and stripped != g:
            yield stripped
    all_bases = {base for g in algos for base in bases(g)}
    for base in all_bases:
        if a == base:
            return 1.0

    # Models commonly put a precise algorithm recovery inside a short
    # explanation (for example, ``RC4 (custom KSA/PRGA)``). Treat an exact
    # algorithm token at safe boundaries as full credit without allowing a
    # near-prefix typo to match a longer alphanumeric token.
    for base in all_bases:
        if re.search(rf"(?<![a-z0-9]){re.escape(base)}(?![a-z0-9])", a):
            return 1.0

    # Family-level credit applies to the parameterized cipher families in
    # this benchmark. Do not reduce arbitrary numbered names to letters:
    # RC5 is a different algorithm, not partial credit for RC4.
    for family in ("aes", "rsa"):
        if a == family and any(re.match(rf"^{family}[-_ ]?\d+", base) for base in all_bases):
            return 0.5
    return 0.0


def score_encryption_key(gt_enc, agent_val):
    if _agent_nullish(agent_val):
        return 0.0
    cands = _enc_key_candidates(gt_enc)
    if not cands:
        return 1.0
    a_raw = str(agent_val).strip().lower()
    a_hex = _norm_hexish(agent_val)
    for c in cands:
        if a_raw == c:
            return 1.0
        c_hex = _norm_hexish(c)
        if a_hex and c_hex and a_hex == c_hex:
            return 1.0

    # Structured model answers frequently annotate a recovered key in the
    # key field (for example: ``R3m0t3_PE_3x3c_K (16 bytes, ASCII)``) or
    # report multiple keys with labels. Requiring the entire field to equal
    # the bare key discards an otherwise exact recovery. Accept a candidate
    # embedded at non-alphanumeric boundaries, while deliberately rejecting
    # prefix matches inside a longer token (``...T3c`` must not match
    # ``...T3cn``).
    for c in cands:
        if len(c) < 4:
            continue
        pattern = rf"(?<![0-9a-z]){re.escape(c)}(?![0-9a-z])"
        if re.search(pattern, a_raw):
            return 1.0

    # Also recognize annotated byte sequences such as
    # ``key: DE AD BE EF 13 37 CA FE (8 bytes)``. Only compare these runs
    # with ground-truth candidates that are themselves canonical hex, which
    # avoids treating incidental a-f characters in an ASCII key as hex.
    gt_hexes = {
        c for c in cands
        if len(c) >= 8 and len(c) % 2 == 0
        and re.fullmatch(r"[0-9a-f]+", c)
    }
    byte_run = re.compile(
        r"(?:0x)?[0-9a-f]{2}(?:(?:[\s,:-]+)(?:0x)?[0-9a-f]{2}){3,}"
        r"|(?:0x)?[0-9a-f]{8,}",
    )
    for match in byte_run.finditer(a_raw):
        if _norm_hexish(match.group(0)) in gt_hexes:
            return 1.0
    return 0.0


def score_key_storage(gt_ks, agent_ks):
    """GT-driven token overlap (replaces the hardcoded xor/0xa5 check)."""
    if _agent_nullish(agent_ks):
        return 0.0
    g = str(gt_ks).strip().lower()
    a = str(agent_ks).strip().lower()
    if not g:
        return 1.0
    if g == a:
        return 1.0
    tokens = set(re.findall(r"0x[0-9a-f]+|[a-z]{3,}\d*[a-z]*", g))
    tokens = {t for t in tokens if t not in ("the", "and", "with", "from")}
    if not tokens:
        return score_fuzzy_string(gt_ks, agent_ks)
    hits = sum(1 for t in tokens if t in a)
    return hits / len(tokens)


# ===================================================================
# Nested detail scoring (injection_details, decoded_strings)
# ===================================================================
def _score_detail_value(gt_val, ag_val):
    """Score one value: scalar fuzzy match, or set overlap for lists."""
    if ag_val is None:
        return 0.0
    if isinstance(gt_val, list):
        gt_set = {str(x).strip().lower() for x in gt_val}
        if isinstance(ag_val, list):
            ag_set = {str(x).strip().lower() for x in ag_val}
        else:
            ag_set = {str(ag_val).strip().lower()}
        if not gt_set:
            return 1.0
        inter = len(gt_set & ag_set)
        if inter == len(gt_set):
            return 1.0
        if inter >= max(1, len(gt_set) // 2):
            return 0.5
        # Substring credit: agent string mentions several items.
        a_blob = " ".join(ag_set)
        hits = sum(1 for g in gt_set if g in a_blob)
        return 0.5 if hits >= max(1, len(gt_set) // 2) else 0.0

    # Exact byte strings are commonly reported as either spaced bytes or one
    # continuous hex string under a model-chosen key.
    g_text = str(gt_val).strip()
    a_text = str(ag_val).strip()
    if re.fullmatch(r"(?:[0-9a-fA-F]{2}[\s:-]*){4,}", g_text):
        g_hex = re.sub(r"[^0-9a-f]", "", g_text.lower())
        if re.fullmatch(r"[0-9a-fA-F]{8,}", a_text):
            if g_hex == a_text.lower():
                return 1.0
        byte_runs = re.findall(
            r"(?<![0-9a-fA-F])(?:0x)?([0-9a-fA-F]{2})(?![0-9a-fA-F])",
            a_text,
        )
        if g_hex and g_hex in "".join(byte_runs).lower():
            return 1.0
    return score_fuzzy_string(gt_val, ag_val)


def _flatten_detail_values(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _flatten_detail_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _flatten_detail_values(value)
    elif node is not None:
        yield str(node)


def score_nested_details(gt_dict, agent_dict):
    """Fraction of GT details matched by key or anywhere in agent evidence."""
    if not isinstance(gt_dict, dict) or not gt_dict:
        return 1.0 if not agent_dict else 0.0
    if not isinstance(agent_dict, dict) or not agent_dict:
        return 0.0
    candidates = list(_flatten_detail_values(agent_dict))
    total = 0.0
    for key, gt_val in gt_dict.items():
        direct = _score_detail_value(gt_val, agent_dict.get(key))
        anywhere = max(
            (_score_detail_value(gt_val, candidate) for candidate in candidates),
            default=0.0,
        )
        total += max(direct, anywhere)
    return total / len(gt_dict)


# ===================================================================
# Weight renormalization + spurious-field accounting
# ===================================================================
def _renormalize(base_weights, present):
    """Keep weights for present GT fields; renormalize to sum 1.0."""
    active = {f: w for f, w in base_weights.items() if present.get(f, False)}
    total = sum(active.values())
    if total <= 0:
        return {}
    return {f: w / total for f, w in active.items()}


def _spurious_fields(base_weights, present, agent_getter):
    """Fields dropped as null in GT where the agent still made a claim."""
    spurious = []
    for f in base_weights:
        if not present.get(f, False):
            if not _agent_nullish(agent_getter(f)):
                spurious.append(f)
    return spurious


def _base_result(tier):
    return {
        "tier": tier,
        "field_scores": {},
        "hallucinated_techniques": [],
        "missing_techniques": [],
        "unmatched_techniques": [],
        "spurious_fields": [],
        "hallucination_penalty": 0.0,
        "spurious_penalty": 0.0,
        "weighted_score": 0.0,
        "final_score": 0.0,
    }


def _finalize(result, weights, halluc_count, halluc_rate, spurious, spurious_rate):
    weighted = sum(result["field_scores"].get(f, 0.0) * w for f, w in weights.items())
    result["weighted_score"] = round(weighted, 4)
    result["hallucination_penalty"] = round(halluc_rate * halluc_count, 4)
    result["spurious_fields"] = spurious
    result["spurious_penalty"] = round(spurious_rate * len(spurious), 4)
    final = weighted - result["hallucination_penalty"] - result["spurious_penalty"]
    result["final_score"] = round(max(0.0, final), 4)
    return result


def _score_techniques(result, gt, agent, semantic=False):
    if semantic:
        tech_credit, hallucinated, missing = score_semantic_techniques(
            gt.get("techniques"), agent.get("techniques"),
        )
        result["field_scores"]["techniques"] = tech_credit
        result["unmatched_techniques"] = hallucinated
        result["hallucinated_techniques"] = [
            claim for claim in hallucinated if _label_key(claim) in PE_CANONICAL_TECHNIQUES
        ]
        result["missing_techniques"] = missing
        # PE semantic F1 already accounts for unmatched claims. Returning zero
        # prevents the former double penalty from erasing unrelated fields.
        return 0

    tech_credit, halluc_count = score_set_overlap(
        gt.get("techniques"), agent.get("techniques"),
    )
    result["field_scores"]["techniques"] = tech_credit
    gt_t = set(gt.get("techniques", []))
    ag_t = set(agent.get("techniques", []))
    result["hallucinated_techniques"] = sorted(ag_t - gt_t)
    result["missing_techniques"] = sorted(gt_t - ag_t)
    return halluc_count


# ===================================================================
# Standard scoring (ELF levels 1-12)
# ===================================================================
def score_standard(gt, agent):
    result = _base_result("standard")

    getters = {
        "decoded_c2": lambda d: d.get("decoded_c2"),
        "techniques": lambda d: d.get("techniques"),
        "file_type": lambda d: d.get("file_type"),
        "encoded_strings": lambda d: d.get("encoded_strings"),
        "c2_protocol": lambda d: d.get("c2_protocol"),
    }
    present = {f: not _is_null(getters[f](gt)) for f in STANDARD_WEIGHTS}
    weights = _renormalize(STANDARD_WEIGHTS, present)

    if "decoded_c2" in weights:
        result["field_scores"]["decoded_c2"] = score_decoded_c2(
            gt.get("decoded_c2"), agent.get("decoded_c2"),
        )
    halluc_count = _score_techniques(result, gt, agent)
    if "file_type" in weights:
        result["field_scores"]["file_type"] = score_file_type(
            gt.get("file_type"), agent.get("file_type"),
        )
    if "encoded_strings" in weights:
        result["field_scores"]["encoded_strings"] = score_exact(
            gt.get("encoded_strings"), agent.get("encoded_strings"),
        )
    if "c2_protocol" in weights:
        result["field_scores"]["c2_protocol"] = score_exact(
            gt.get("c2_protocol"), agent.get("c2_protocol"),
        )

    spurious = _spurious_fields(STANDARD_WEIGHTS, present, lambda f: getters[f](agent))
    return _finalize(result, weights, halluc_count, HALLUCINATION_PENALTY,
                     spurious, SPURIOUS_FIELD_PENALTY)


# ===================================================================
# PE injection scoring (Windows levels 14-22)
# ===================================================================
def score_pe_injection(gt, agent):
    result = _base_result("pe_injection")

    gt_enc = gt.get("encryption_details")
    ag_enc = agent.get("encryption_details")
    if not isinstance(ag_enc, dict):
        ag_enc = {}

    present = {
        "techniques": not _is_null(gt.get("techniques")),
        "injection_details": not _is_null(gt.get("injection_details")),
        "decoded_c2": not _is_null(gt.get("decoded_c2")),
        "encryption_key": bool(_enc_key_candidates(gt_enc)),
        "decoded_strings": not _is_null(gt.get("decoded_strings")),
        "anti_analysis": not _is_null(gt.get("anti_analysis")),
        "encryption_algorithm": bool(_enc_algorithms(gt_enc)),
        "c2_protocol": not _is_null(gt.get("c2_protocol")),
        "file_type": not _is_null(gt.get("file_type")),
        "encoded_strings": gt.get("encoded_strings") is not None,
    }
    weights = _renormalize(PE_INJECTION_WEIGHTS, present)

    halluc_count = _score_techniques(result, gt, agent, semantic=True)

    if "injection_details" in weights:
        result["field_scores"]["injection_details"] = score_nested_details(
            gt.get("injection_details"), agent.get("injection_details"),
        )
    if "decoded_c2" in weights:
        result["field_scores"]["decoded_c2"] = score_decoded_c2(
            gt.get("decoded_c2"), agent.get("decoded_c2"),
        )
    if "encryption_key" in weights:
        result["field_scores"]["encryption_key"] = score_encryption_key(
            gt_enc, ag_enc.get("key"),
        )
    if "decoded_strings" in weights:
        result["field_scores"]["decoded_strings"] = score_nested_details(
            gt.get("decoded_strings"), agent.get("decoded_strings"),
        )
    if "anti_analysis" in weights:
        aa_credit = score_semantic_list_recall(
            gt.get("anti_analysis"), agent.get("anti_analysis"),
        )
        result["field_scores"]["anti_analysis"] = aa_credit
    if "encryption_algorithm" in weights:
        result["field_scores"]["encryption_algorithm"] = score_encryption_algorithm(
            gt_enc, ag_enc.get("algorithm"),
        )
    if "c2_protocol" in weights:
        result["field_scores"]["c2_protocol"] = score_exact(
            gt.get("c2_protocol"), agent.get("c2_protocol"),
        )

    if "file_type" in weights:
        result["field_scores"]["file_type"] = score_file_type(
            gt.get("file_type"), agent.get("file_type"),
        )
    if "encoded_strings" in weights:
        result["field_scores"]["encoded_strings"] = score_exact(
            gt.get("encoded_strings"), agent.get("encoded_strings"),
        )

    agent_getter = {
        "techniques": lambda: agent.get("techniques"),
        "injection_details": lambda: agent.get("injection_details"),
        "decoded_c2": lambda: agent.get("decoded_c2"),
        "encryption_key": lambda: ag_enc.get("key"),
        "decoded_strings": lambda: agent.get("decoded_strings"),
        "anti_analysis": lambda: agent.get("anti_analysis"),
        "encryption_algorithm": lambda: ag_enc.get("algorithm"),
        "c2_protocol": lambda: agent.get("c2_protocol"),
        "file_type": lambda: agent.get("file_type"),
        "encoded_strings": lambda: agent.get("encoded_strings"),
    }
    spurious = _spurious_fields(
        PE_INJECTION_WEIGHTS, present, lambda f: agent_getter[f](),
    )
    return _finalize(result, weights, halluc_count, HALLUCINATION_PENALTY,
                     spurious, SPURIOUS_FIELD_PENALTY)


# ===================================================================
# Bonus scoring (levels 13, 23) — deep rubric
# ===================================================================
def _get_nested(d, *keys, default=None):
    """Safely traverse nested dicts."""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d


def score_bonus(gt, agent):
    result = _base_result("bonus")

    gt_enc = gt.get("encryption_details")
    ag_enc = agent.get("encryption_details")
    if not isinstance(ag_enc, dict):
        ag_enc = {}
    gt_ks = _get_nested(gt, "encryption_details", "key_storage", default="")
    ag_ks = _get_nested(agent, "encryption_details", "key_storage", default="")

    present = {
        "decoded_c2": not _is_null(gt.get("decoded_c2")),
        "encryption_algorithm": bool(_enc_algorithms(gt_enc)),
        "encryption_key": bool(_enc_key_candidates(gt_enc)),
        "encryption_key_storage": not _is_null(gt_ks),
        "techniques": not _is_null(gt.get("techniques")),
        "decoded_strings": not _is_null(gt.get("decoded_strings")),
        "anti_analysis": not _is_null(gt.get("anti_analysis")),
        "file_type": not _is_null(gt.get("file_type")),
        "encoded_strings": gt.get("encoded_strings") is not None,
        "c2_protocol": not _is_null(gt.get("c2_protocol")),
    }
    weights = _renormalize(BONUS_WEIGHTS, present)

    if "decoded_c2" in weights:
        result["field_scores"]["decoded_c2"] = score_decoded_c2(
            gt.get("decoded_c2"), agent.get("decoded_c2"),
        )
    if "encryption_algorithm" in weights:
        result["field_scores"]["encryption_algorithm"] = score_encryption_algorithm(
            gt_enc, ag_enc.get("algorithm"),
        )
    if "encryption_key" in weights:
        result["field_scores"]["encryption_key"] = score_encryption_key(
            gt_enc, ag_enc.get("key"),
        )
    if "encryption_key_storage" in weights:
        result["field_scores"]["encryption_key_storage"] = score_key_storage(
            gt_ks, ag_ks,
        )

    is_pe = (canonical_file_type(gt.get("file_type")) or (None, None))[0] == "pe"
    halluc_count = _score_techniques(result, gt, agent, semantic=is_pe)

    if "decoded_strings" in weights:
        result["field_scores"]["decoded_strings"] = score_nested_details(
            gt.get("decoded_strings"), agent.get("decoded_strings"),
        )
    if "anti_analysis" in weights:
        if is_pe:
            aa_credit = score_semantic_list_recall(
                gt.get("anti_analysis"), agent.get("anti_analysis"),
            )
        else:
            aa_credit, _ = score_set_overlap(
                gt.get("anti_analysis"), agent.get("anti_analysis"),
            )
        result["field_scores"]["anti_analysis"] = aa_credit
    if "file_type" in weights:
        result["field_scores"]["file_type"] = score_file_type(
            gt.get("file_type"), agent.get("file_type"),
        )
    if "encoded_strings" in weights:
        result["field_scores"]["encoded_strings"] = score_exact(
            gt.get("encoded_strings"), agent.get("encoded_strings"),
        )
    if "c2_protocol" in weights:
        result["field_scores"]["c2_protocol"] = score_exact(
            gt.get("c2_protocol"), agent.get("c2_protocol"),
        )

    agent_getter = {
        "decoded_c2": lambda: agent.get("decoded_c2"),
        "encryption_algorithm": lambda: ag_enc.get("algorithm"),
        "encryption_key": lambda: ag_enc.get("key"),
        "encryption_key_storage": lambda: ag_ks,
        "techniques": lambda: agent.get("techniques"),
        "decoded_strings": lambda: agent.get("decoded_strings"),
        "anti_analysis": lambda: agent.get("anti_analysis"),
        "file_type": lambda: agent.get("file_type"),
        "encoded_strings": lambda: agent.get("encoded_strings"),
        "c2_protocol": lambda: agent.get("c2_protocol"),
    }
    spurious = _spurious_fields(
        BONUS_WEIGHTS, present, lambda f: agent_getter[f](),
    )
    return _finalize(result, weights, halluc_count, BONUS_HALLUCINATION_PENALTY,
                     spurious, BONUS_SPURIOUS_FIELD_PENALTY)


# ===================================================================
# Tier resolution + dispatch
# ===================================================================
def resolve_tier(ground_truth, gt_path=""):
    """Pick the scoring tier for a ground truth.

    Order: explicit "tier" field -> legacy level13/23 name pattern ->
    PE file_type -> standard.
    """
    explicit = ground_truth.get("tier")
    if explicit in TIERS:
        return explicit

    name = ground_truth.get("sample", "") or Path(gt_path).stem
    if BONUS_SAMPLE_PATTERN.search(name):
        return "bonus"

    ft = canonical_file_type(ground_truth.get("file_type"))
    if ft and ft[0] == "pe":
        return "pe_injection"

    return "standard"


def is_bonus(ground_truth, gt_path=""):
    """Backward-compatible shim (pre-v3 callers)."""
    return resolve_tier(ground_truth, gt_path) == "bonus"


def score_sample(gt, agent, gt_path=""):
    tier = resolve_tier(gt, gt_path)
    if tier == "bonus":
        return score_bonus(gt, agent)
    if tier == "pe_injection":
        return score_pe_injection(gt, agent)
    return score_standard(gt, agent)


# ===================================================================
# I/O helpers
# ===================================================================
def load_json(path):
    with open(path) as f:
        return json.load(f)


def score_single(gt_path, agent_path):
    gt = load_json(gt_path)
    agent = load_json(agent_path)

    sample_name = gt.get("sample", Path(gt_path).stem)
    result = score_sample(gt, agent, gt_path)
    result["sample"] = sample_name

    log.info("Sample: %s [%s]", sample_name, result["tier"])
    for field, val in result["field_scores"].items():
        log.info("  %-28s %.4f", field, val)
    log.info("  Weighted score:            %.4f", result["weighted_score"])
    log.info("  Hallucination penalty:     %.4f", result["hallucination_penalty"])
    if result["spurious_penalty"]:
        log.info("  Spurious-field penalty:    %.4f", result["spurious_penalty"])
    log.info("  Final score:               %.4f", result["final_score"])

    if result["hallucinated_techniques"]:
        log.warning("  Hallucinated: %s", result["hallucinated_techniques"])
    if result["missing_techniques"]:
        log.info("  Missing:      %s", result["missing_techniques"])
    if result["spurious_fields"]:
        log.warning("  Spurious:     %s", result["spurious_fields"])

    return result


def score_batch(gt_dir, agent_dir):
    gt_dir = Path(gt_dir)
    agent_dir = Path(agent_dir)

    results = []
    gt_files = sorted(gt_dir.glob("*.json"))

    if not gt_files:
        log.error("No ground truth JSON files found in %s", gt_dir)
        return results

    for gt_file in gt_files:
        agent_file = agent_dir / gt_file.name
        if not agent_file.exists():
            log.warning("No agent output for %s, skipping", gt_file.name)
            continue
        results.append(score_single(str(gt_file), str(agent_file)))

    return results


# ===================================================================
# Summary output
# ===================================================================
_TIER_LABELS = {
    "standard": "STANDARD ELF LEVELS",
    "pe_injection": "WINDOWS PE INJECTION LEVELS",
    "bonus": "BONUS LEVELS",
}

_TIER_WEIGHTS = {
    "standard": STANDARD_WEIGHTS,
    "pe_injection": PE_INJECTION_WEIGHTS,
    "bonus": BONUS_WEIGHTS,
}


def _print_tier_table(tier, rows):
    print("\n" + "=" * 76)
    print(f"  {_TIER_LABELS[tier]}   each 0-1 (renormalized rubric)")
    print("=" * 76)
    print(f"  {'Sample':<40} {'Raw':>7} {'Pen':>8} {'Final':>7}")
    print("  " + "-" * 72)
    for r in rows:
        name = r["sample"][:39]
        pen = r["hallucination_penalty"] + r.get("spurious_penalty", 0.0)
        print(
            f"  {name:<40} {r['weighted_score']:>7.4f}"
            f" {pen:>8.4f}"
            f" {r['final_score']:>7.4f}"
        )
    print("  " + "-" * 72)
    avg = sum(r["final_score"] for r in rows) / len(rows) if rows else 0.0
    print(f"  {'TIER AVERAGE (' + str(len(rows)) + ' levels)':<40}"
          f" {'':>7} {'':>8} {avg:>7.4f}")
    print("=" * 76)
    return avg


def print_summary(results):
    if not results:
        log.info("No results to summarize.")
        return

    by_tier = {t: [r for r in results if r.get("tier") == t] for t in TIERS}
    main_rows = by_tier["standard"] + by_tier["pe_injection"]
    bonus_rows = by_tier["bonus"]

    avgs = {}
    for tier in TIERS:
        if by_tier[tier]:
            avgs[tier] = _print_tier_table(tier, by_tier[tier])

    main_score = (
        sum(r["final_score"] for r in main_rows) / len(main_rows)
        if main_rows else 0.0
    )
    bonus_score = (
        sum(r["final_score"] for r in bonus_rows) / len(bonus_rows)
        if bonus_rows else 0.0
    )

    print("\n" + "=" * 76)
    print("  GRAND TOTAL")
    print("=" * 76)
    if main_rows:
        print(f"    Main score  ({len(main_rows)} standard+PE levels): {main_score:>7.4f} / 1.0")
    if bonus_rows:
        print(f"    Bonus score ({len(bonus_rows)} levels):             {bonus_score:>7.4f} / 1.0")
    total = main_score + bonus_score
    max_total = (1.0 if main_rows else 0.0) + (1.0 if bonus_rows else 0.0)
    print(f"    ─────────────────────────────────────")
    print(f"    TOTAL:                               {total:>7.4f} / {max_total:.1f}")
    print("=" * 76 + "\n")


def build_report(results):
    by_tier = {t: [r for r in results if r.get("tier") == t] for t in TIERS}
    main_rows = by_tier["standard"] + by_tier["pe_injection"]
    bonus_rows = by_tier["bonus"]

    main_score = (
        sum(r["final_score"] for r in main_rows) / len(main_rows)
        if main_rows else 0.0
    )
    bonus_score = (
        sum(r["final_score"] for r in bonus_rows) / len(bonus_rows)
        if bonus_rows else 0.0
    )

    return {
        "results": results,
        "summary": {
            "main_score": round(main_score, 4),
            "main_max": 1.0,
            "main_levels": len(main_rows),
            "bonus_score": round(bonus_score, 4),
            "bonus_max": 1.0,
            "bonus_levels": len(bonus_rows),
            "total_score": round(main_score + bonus_score, 4),
            "total_max": (1.0 if main_rows else 0.0) + (1.0 if bonus_rows else 0.0),
            "tier_levels": {t: len(by_tier[t]) for t in TIERS},
            "tier_averages": {
                t: round(
                    sum(r["final_score"] for r in by_tier[t]) / len(by_tier[t]), 4,
                )
                for t in TIERS if by_tier[t]
            },
            "standard_weights": STANDARD_WEIGHTS,
            "pe_injection_weights": PE_INJECTION_WEIGHTS,
            "bonus_weights": BONUS_WEIGHTS,
            "hallucination_penalty_standard": HALLUCINATION_PENALTY,
            "hallucination_penalty_bonus": BONUS_HALLUCINATION_PENALTY,
            "spurious_field_penalty": SPURIOUS_FIELD_PENALTY,
        },
    }


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(
        description="AgentRE-Bench Scorer: compare agent RE output against ground truth"
    )
    parser.add_argument(
        "--ground-truth", "-g",
        help="Path to a single ground truth JSON file",
    )
    parser.add_argument(
        "--agent-output", "-a",
        help="Path to a single agent output JSON file",
    )
    parser.add_argument(
        "--ground-truth-dir", "-G",
        help="Directory of ground truth JSON files (batch mode)",
    )
    parser.add_argument(
        "--agent-output-dir", "-A",
        help="Directory of agent output JSON files (batch mode)",
    )
    parser.add_argument(
        "--report", "-r",
        help="Write JSON report to this path",
    )

    args = parser.parse_args()

    if args.ground_truth and args.agent_output:
        result = score_single(args.ground_truth, args.agent_output)
        results = [result]
    elif args.ground_truth_dir and args.agent_output_dir:
        results = score_batch(args.ground_truth_dir, args.agent_output_dir)
    else:
        parser.error(
            "Provide either --ground-truth + --agent-output "
            "or --ground-truth-dir + --agent-output-dir"
        )
        return

    print_summary(results)

    if args.report:
        report = build_report(results)
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2)
        log.info("Report written to %s", args.report)


if __name__ == "__main__":
    main()
