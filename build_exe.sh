#!/usr/bin/env bash
# Build standalone executable using PyInstaller
# Usage: ./build_exe.sh
# Output: dist/layout_editor

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== IC Layout Editor — PyInstaller Build ==="

# Create venv with access to system packages (klayout, PyQt5 already installed system-wide)
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment (with system site-packages)..."
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# Only install PyInstaller (build tool only — klayout/PyQt5 come from system)
pip install --quiet pyinstaller

# Collect klayout data files
KLAYOUT_PATH=$(python3 -c "import klayout; import os; print(os.path.dirname(klayout.__file__))")
echo "klayout path: $KLAYOUT_PATH"

# Clean previous build
rm -rf build dist layout_editor.spec

pyinstaller \
  --onefile \
  --windowed \
  --name "layout_editor" \
  --add-data "$KLAYOUT_PATH:klayout" \
  --add-data "$SCRIPT_DIR/pdk:pdk" \
  --add-data "$SCRIPT_DIR/schematic:schematic" \
  --add-data "$SCRIPT_DIR/lvs:lvs" \
  --add-data "$SCRIPT_DIR/pex:pex" \
  --hidden-import PyQt5.sip \
  --hidden-import klayout.db \
  --hidden-import klayout.lay \
  --hidden-import pdk_loader \
  --hidden-import pex.pex_engine \
  --hidden-import pex.pex_report \
  --hidden-import lvs.lvs_engine \
  --hidden-import lvs.lvs_report \
  --hidden-import lvs.layout_extractor \
  --hidden-import schematic.schematic_window \
  --hidden-import schematic.schematic_canvas \
  --hidden-import schematic.netlist_export \
  --hidden-import schematic.symbols \
  main.py

echo ""
echo "Build complete. Size: $(du -sh dist/layout_editor | cut -f1)"
echo "Run with: ./dist/layout_editor"
