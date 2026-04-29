#!/usr/bin/env bash
#
# build_binaries.sh — Compile all 13 C samples to ELF64 x86-64 binaries.
#
# On Linux x86-64: uses local gcc directly (no Docker needed).
# On macOS / other: uses Docker with --platform linux/amd64 to cross-compile.
#
# Output: binaries/ directory with 13 ELF64 executables.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLES_DIR="$SCRIPT_DIR/samples"
BINARIES_DIR="$SCRIPT_DIR/binaries"
DOCKER_IMAGE="gcc:latest"

# Common compilation flags
CFLAGS="-O0 -fno-stack-protector -no-pie -z execstack -static"

mkdir -p "$BINARIES_DIR"

# Detect build mode: local gcc or Docker
USE_DOCKER=true
if command -v gcc &>/dev/null && [[ "$(uname -s)" == "Linux" ]] && [[ "$(uname -m)" == "x86_64" ]]; then
    USE_DOCKER=false
elif ! command -v docker &>/dev/null; then
    echo "Error: Neither local gcc (on Linux x86-64) nor docker found."
    echo "Install gcc (apt install gcc) or Docker to build binaries."
    exit 1
fi

echo "=== AgentRE-Bench: Building ELF64 binaries ==="
echo "Samples dir:  $SAMPLES_DIR"
echo "Output dir:   $BINARIES_DIR"
if [ "$USE_DOCKER" = true ]; then
    echo "Build mode:   Docker ($DOCKER_IMAGE)"
    docker pull "$DOCKER_IMAGE" 2>/dev/null || true
else
    echo "Build mode:   Local gcc ($(gcc --version | head -1))"
fi
echo ""

# Output binary name: replace spaces with underscores in the basename
_name_map() {
    echo "$1" | sed 's/ /_/g'
}

SUCCESS=0
FAIL=0

for SRC in "$SAMPLES_DIR"/*.c; do
    # Extract base name without extension
    BASENAME="$(basename "$SRC" .c)"
    OUTNAME="$(_name_map "$BASENAME")"

    echo -n "Building $OUTNAME ... "

    # Level 9 is a shared object — needs -shared -fPIC, must NOT use -static
    EXTRA_FLAGS=""
    BUILD_CFLAGS="$CFLAGS"
    if [[ "$BASENAME" == *"level9"* ]]; then
        EXTRA_FLAGS="-shared -fPIC -ldl"
        BUILD_CFLAGS="${CFLAGS//-static/}"
    fi

    if [ "$USE_DOCKER" = true ]; then
        # Docker build (macOS / non-x86-64)
        if docker run --rm \
            --platform linux/amd64 \
            -v "$SAMPLES_DIR:/src:ro" \
            -v "$BINARIES_DIR:/out" \
            -w /src \
            "$DOCKER_IMAGE" \
            bash -c "gcc $BUILD_CFLAGS $EXTRA_FLAGS -o '/out/$OUTNAME' '/src/$BASENAME.c' -lm 2>&1" \
        ; then
            echo "OK"
            SUCCESS=$((SUCCESS + 1))
        else
            echo "FAILED"
            FAIL=$((FAIL + 1))
        fi
    else
        # Local gcc build (Linux x86-64)
        if gcc $BUILD_CFLAGS $EXTRA_FLAGS -o "$BINARIES_DIR/$OUTNAME" "$SRC" -lm 2>&1; then
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
echo "Binaries in: $BINARIES_DIR"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
