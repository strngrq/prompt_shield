#!/usr/bin/env bash
# Build PromptShield with PyInstaller.
# Usage: ./scripts/build.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

echo "PromptShield build..."
echo "Root: $ROOT"

# ── 1. Ensure venv and deps ──
if [ ! -f "$PYTHON" ]; then
    echo "Creating venv..."
    python3 -m venv "$VENV"
fi

echo "Installing dependencies..."
"$PIP" install --quiet \
    PySide6 \
    presidio-analyzer presidio-anonymizer \
    spacy \
    pyinstaller

# ── 2. Ensure at least one spaCy model exists (en_core_web_sm) ──
"$PYTHON" -c "import spacy; spacy.load('en_core_web_sm')" 2>/dev/null || {
    echo "Downloading en_core_web_sm model..."
    "$PYTHON" -m spacy download en_core_web_sm
}

# ── 3. Clean previous build ──
echo "Cleaning previous build..."
rm -rf "$ROOT/build" "$ROOT/dist"

# ── 4. Run PyInstaller ──
echo "Running PyInstaller..."
cd "$ROOT"
"$PYTHON" -m PyInstaller prompt_shield.spec \
    --noconfirm \
    --clean \
    2>&1 | tail -20

# ── 5. Strip debug symbols (macOS) ──
if [[ "$OSTYPE" == darwin* ]]; then
    echo "Stripping debug symbols from .dylib/.so files..."
    find "$ROOT/dist/PromptShield" \( -name '*.dylib' -o -name '*.so' \) \
        -exec strip -x {} + 2>/dev/null || true

    # Remove __pycache__ dirs from the bundle
    find "$ROOT/dist/PromptShield" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

    # Remove .pyi type stubs
    find "$ROOT/dist/PromptShield" -name '*.pyi' -delete 2>/dev/null || true
fi

# ── 6. Report size ──
echo ""
echo "Build complete."
SIZE=$(du -sh "$ROOT/dist/PromptShield" | cut -f1)
echo "Directory:  dist/PromptShield/ ($SIZE)"
echo ""
echo "Run with: dist/PromptShield/PromptShield"
if [[ "$OSTYPE" == darwin* ]]; then
    echo "Or:       open dist/PromptShield.app"
fi
