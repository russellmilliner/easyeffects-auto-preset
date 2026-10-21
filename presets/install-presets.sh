#!/usr/bin/env bash
set -euo pipefail

DEST_DIR="${XDG_DATA_HOME:-$HOME/.var/app/com.github.wwmm.easyeffects/data}/easyeffects"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$DEST_DIR/output" "$DEST_DIR/input"

echo "==> Installing EasyEffects presets to $DEST_DIR..."

cp "$SCRIPT_DIR/Meeting-Voice-Clear.json" "$DEST_DIR/output/"
cp "$SCRIPT_DIR/Crystal more Bass.json" "$DEST_DIR/output/"
cp "$SCRIPT_DIR/Compressed-Max.json" "$DEST_DIR/output/"
cp "$SCRIPT_DIR/Meeting-Mic-Clean.json" "$DEST_DIR/input/"

echo "==> Presets installed successfully!"
echo "Available output presets:"
ls -1 "$DEST_DIR/output"
