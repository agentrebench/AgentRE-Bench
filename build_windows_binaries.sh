#!/usr/bin/env bash
#
# build_windows_binaries.sh — Compile all 10 Windows C/C++ samples to PE32+ .exe binaries.
#
# Requires MinGW cross-compiler (x86_64-w64-mingw32-gcc/g++).
# Falls back to Docker (mstorsjo/llvm-mingw) if MinGW is not installed locally.
#
# Output: binaries/windows/ directory with 10 PE32+ executables.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLES_DIR="$SCRIPT_DIR/samples"
OUT_DIR="$SCRIPT_DIR/binaries/windows"
DOCKER_IMAGE="mstorsjo/llvm-mingw:latest"

# Common flags
CFLAGS="-O0 -static"

mkdir -p "$OUT_DIR"

# Detect build mode
USE_DOCKER=false
CROSS_CC=""
CROSS_CXX=""

if command -v x86_64-w64-mingw32-gcc &>/dev/null; then
    CROSS_CC="x86_64-w64-mingw32-gcc"
    CROSS_CXX="x86_64-w64-mingw32-g++"
fi

if [ -z "$CROSS_CC" ]; then
    if command -v docker &>/dev/null; then
        USE_DOCKER=true
    else
        echo "Error: No MinGW cross-compiler or Docker found."
        echo ""
        echo "Options:"
        echo "  1. Install MinGW:  sudo apt install gcc-mingw-w64-x86-64 g++-mingw-w64-x86-64"
        echo "  2. Install Docker:  sudo apt install docker.io"
        exit 1
    fi
fi

echo "=== AgentRE-Bench: Building Windows PE32+ binaries ==="
echo "Samples dir:  $SAMPLES_DIR"
echo "Output dir:   $OUT_DIR"
if [ "$USE_DOCKER" = true ]; then
    echo "Build mode:   Docker ($DOCKER_IMAGE)"
    docker pull "$DOCKER_IMAGE" 2>/dev/null || true
else
    echo "Build mode:   Local ($CROSS_CC)"
    echo "Compiler:     $($CROSS_CC --version | head -1)"
fi
echo ""

# Build list: source -> (output name, extra linker flags)
# Format: "source_file|output_name|linker_flags"
declare -a SOURCES=(
    "windows_level14_DLLInjection.c|windows_level14_DLLInjection|"
    "windows_level15_APCInjection.c|windows_level15_APCInjection|"
    "windows_level16_CodeCave.c|windows_level16_CodeCave|"
    "windows_level17_ProcessHollowing.c|windows_level17_ProcessHollowing|"
    "windows_level18_HellsGate.c|windows_level18_HellsGate|"
    "windows_level19_ReflectiveDLLInjection.c|windows_level19_ReflectiveDLLInjection|"
    "windows_level20_RemotePEExecution.c|windows_level20_RemotePEExecution|"
    "windows_level21_GhostProcessHollowing.c|windows_level21_GhostProcessHollowing|"
    "windows_level22_AESEncryptedMultiTechnique.cpp|windows_level22_AESEncryptedMultiTechnique|c++"
    "windows_level23_WannaCryWorm.c|windows_level23_WannaCryWorm|-lwininet -lws2_32"
)

SUCCESS=0
FAIL=0

build_local() {
    local src="$1" out="$2" lflags="$3" is_cxx="$4"
    local cc="$CROSS_CC"
    if [ "$is_cxx" = "c++" ]; then
        cc="$CROSS_CXX"
    fi
    # shellcheck disable=SC2086
    $cc $CFLAGS -o "$OUT_DIR/$out.exe" "$SAMPLES_DIR/$src" $lflags 2>&1
}

build_docker() {
    local src="$1" out="$2" lflags="$3" is_cxx="$4"
    local cc="x86_64-w64-mingw32-gcc"
    if [ "$is_cxx" = "c++" ]; then
        cc="x86_64-w64-mingw32-g++"
    fi
    docker run --rm \
        -v "$SAMPLES_DIR:/src:ro" \
        -v "$OUT_DIR:/out" \
        -w /src \
        "$DOCKER_IMAGE" \
        bash -c "$cc $CFLAGS -o /out/$out.exe /src/$src $lflags" 2>&1
}

for entry in "${SOURCES[@]}"; do
    IFS='|' read -r SRC OUT LFLAGS <<< "$entry"
    IS_CXX=""
    if [ "$LFLAGS" = "c++" ]; then
        IS_CXX="c++"
        LFLAGS=""
    fi

    echo -n "Building $OUT ... "

    if [ "$USE_DOCKER" = true ]; then
        if build_docker "$SRC" "$OUT" "$LFLAGS" "$IS_CXX"; then
            echo "OK"
            SUCCESS=$((SUCCESS + 1))
        else
            echo "FAILED"
            FAIL=$((FAIL + 1))
        fi
    else
        if build_local "$SRC" "$OUT" "$LFLAGS" "$IS_CXX"; then
            echo "OK"
            SUCCESS=$((SUCCESS + 1))
        else
            echo "FAILED"
            FAIL=$((FAIL + 1))
        fi
    fi
done

echo ""
echo "=== Build complete: $SUCCESS succeeded, $FAIL failed ==="
echo "Binaries in: $OUT_DIR"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
