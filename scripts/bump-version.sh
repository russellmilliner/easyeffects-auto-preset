#!/usr/bin/env bash
# Interactive Version Incrementer for EasyEffects Auto Preset
# Updates Cargo.toml, src/main.rs, python/easyeffects_auto_preset.py,
# README.md, AppStream metainfo.xml, and optionally regenerates screenshots.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BOLD="\033[1m"
CYAN="\033[1;36m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

CURRENT_VERSION="$(grep -E '^version\s*=' "$REPO_ROOT/Cargo.toml" | head -n 1 | sed -E 's/.*"([^"]+)".*/\1/')"
IFS='.' read -r CUR_MAJOR CUR_MINOR CUR_PATCH <<< "${CURRENT_VERSION%%-*}"

NEXT_PATCH="${CUR_MAJOR}.${CUR_MINOR}.$((CUR_PATCH + 1))"
NEXT_MINOR="${CUR_MAJOR}.$((CUR_MINOR + 1)).0"
NEXT_MAJOR="$((CUR_MAJOR + 1)).0.0"

NEW_VERSION=""
RELEASE_SUMMARY=""
AUTO_YES=false
REGEN_SCREENSHOTS=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [NEW_VERSION]

Interactive script to increment the EasyEffects Auto Preset version across all files.

Options:
  --patch                Increment patch version ($CURRENT_VERSION -> $NEXT_PATCH)
  --minor                Increment minor version ($CURRENT_VERSION -> $NEXT_MINOR)
  --major                Increment major version ($CURRENT_VERSION -> $NEXT_MAJOR)
  --version <X.Y.Z>      Set explicit version
  --summary "<text>"     Release summary for AppStream metainfo.xml
  --screenshots          Regenerate UI screenshots with the new version badge
  --no-screenshots       Skip regenerating UI screenshots
  -y, --yes              Non-interactive mode (accept defaults)
  -h, --help             Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --patch) NEW_VERSION="$NEXT_PATCH"; shift ;;
    --minor) NEW_VERSION="$NEXT_MINOR"; shift ;;
    --major) NEW_VERSION="$NEXT_MAJOR"; shift ;;
    --version) NEW_VERSION="${2:-}"; shift 2 ;;
    --summary) RELEASE_SUMMARY="${2:-}"; shift 2 ;;
    --screenshots) REGEN_SCREENSHOTS="yes"; shift ;;
    --no-screenshots) REGEN_SCREENSHOTS="no"; shift ;;
    -y|--yes) AUTO_YES=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      if [[ -z "$NEW_VERSION" && "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        NEW_VERSION="$1"
        shift
      else
        echo -e "${RED}Unknown argument: $1${RESET}" >&2
        usage
        exit 1
      fi
      ;;
  esac
done

echo -e "${CYAN}============================================================${RESET}"
echo -e "${BOLD}  EasyEffects Auto Preset — Version Incrementer${RESET}"
echo -e "${CYAN}============================================================${RESET}"
echo -e "Current version: ${YELLOW}v${CURRENT_VERSION}${RESET}"
echo ""

if [[ -z "$NEW_VERSION" ]]; then
  if $AUTO_YES; then
    NEW_VERSION="$NEXT_PATCH"
  else
    echo -e "${BOLD}Select version bump type:${RESET}"
    echo -e "  ${GREEN}1)${RESET} Patch  -> ${BOLD}v${NEXT_PATCH}${RESET} (bug fixes / minor tweaks)"
    echo -e "  ${GREEN}2)${RESET} Minor  -> ${BOLD}v${NEXT_MINOR}${RESET} (new features / backwards-compatible)"
    echo -e "  ${GREEN}3)${RESET} Major  -> ${BOLD}v${NEXT_MAJOR}${RESET} (major release)"
    echo -e "  ${GREEN}4)${RESET} Custom version"
    echo -e "  ${GREEN}q)${RESET} Cancel"
    echo ""
    read -r -p "Choice [1-4, default=1]: " choice
    choice="${choice:-1}"
    case "$choice" in
      1) NEW_VERSION="$NEXT_PATCH" ;;
      2) NEW_VERSION="$NEXT_MINOR" ;;
      3) NEW_VERSION="$NEXT_MAJOR" ;;
      4)
        read -r -p "Enter custom semantic version (e.g. 0.4.0): " custom_ver
        custom_ver="${custom_ver#v}"
        if [[ ! "$custom_ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
          echo -e "${RED}Invalid version format: '$custom_ver' (expected X.Y.Z)${RESET}" >&2
          exit 1
        fi
        NEW_VERSION="$custom_ver"
        ;;
      q|Q) echo "Cancelled."; exit 0 ;;
      *) echo -e "${RED}Invalid selection.${RESET}" >&2; exit 1 ;;
    esac
  fi
fi

NEW_VERSION="${NEW_VERSION#v}"
if [[ ! "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo -e "${RED}Error: Version '$NEW_VERSION' is not valid X.Y.Z format.${RESET}" >&2
  exit 1
fi

if [[ -z "$RELEASE_SUMMARY" ]]; then
  if ! $AUTO_YES; then
    echo ""
    read -r -p "Enter one-line release summary for AppStream metainfo (optional, Enter for default): " RELEASE_SUMMARY
  fi
  if [[ -z "$RELEASE_SUMMARY" ]]; then
    RELEASE_SUMMARY="Release v${NEW_VERSION} of EasyEffects Auto Preset."
  fi
fi

if [[ -z "$REGEN_SCREENSHOTS" ]]; then
  if $AUTO_YES; then
    REGEN_SCREENSHOTS="yes"
  else
    read -r -p "Regenerate UI screenshots with v${NEW_VERSION} badge? [Y/n]: " sc_ans
    sc_ans="${sc_ans:-Y}"
    if [[ "$sc_ans" =~ ^[Yy] ]]; then
      REGEN_SCREENSHOTS="yes"
    else
      REGEN_SCREENSHOTS="no"
    fi
  fi
fi

echo ""
echo -e "Updating version: ${YELLOW}v${CURRENT_VERSION}${RESET} -> ${GREEN}v${NEW_VERSION}${RESET}"

if ! $AUTO_YES; then
  read -r -p "Proceed with file updates? [Y/n]: " confirm
  confirm="${confirm:-Y}"
  if [[ ! "$confirm" =~ ^[Yy] ]]; then
    echo "Aborted."
    exit 0
  fi
fi

TODAY="$(date +%Y-%m-%d)"

python3 - "$CURRENT_VERSION" "$NEW_VERSION" "$TODAY" "$RELEASE_SUMMARY" << 'PYEOF'
import re
import sys
import xml.sax.saxutils as saxutils
from pathlib import Path

old_ver, new_ver, today, summary = sys.argv[1:5]

# 1. Cargo.toml
cargo_toml = Path("Cargo.toml")
text = cargo_toml.read_text(encoding="utf-8")
text = re.sub(r'(?m)^version\s*=\s*"[^"]+"', f'version = "{new_ver}"', text, count=1)
cargo_toml.write_text(text, encoding="utf-8")
print(f"  [OK] Updated Cargo.toml -> {new_ver}")

# 2. src/main.rs
main_rs = Path("src/main.rs")
text = main_rs.read_text(encoding="utf-8")
text = re.sub(r'(\bversion\s*=\s*)"[^"]+"', rf'\1"{new_ver}"', text, count=1)
main_rs.write_text(text, encoding="utf-8")
print(f"  [OK] Updated src/main.rs -> {new_ver}")

# 3. python/easyeffects_auto_preset.py
py_app = Path("python/easyeffects_auto_preset.py")
text = py_app.read_text(encoding="utf-8")
text = re.sub(r'(?m)^APP_VERSION\s*=\s*"[^"]+"', f'APP_VERSION = "{new_ver}"', text, count=1)
py_app.write_text(text, encoding="utf-8")
print(f"  [OK] Updated python/easyeffects_auto_preset.py -> {new_ver}")

# 4. README.md
readme = Path("README.md")
if readme.is_file():
    text = readme.read_text(encoding="utf-8")
    text = text.replace(f"v{old_ver}", f"v{new_ver}").replace(old_ver, new_ver)
    readme.write_text(text, encoding="utf-8")
    print(f"  [OK] Updated README.md -> v{new_ver}")

# 5. data/io.github.russellmilliner.easyeffects_auto_preset.metainfo.xml
metainfo = Path("data/io.github.russellmilliner.easyeffects_auto_preset.metainfo.xml")
if metainfo.is_file():
    text = metainfo.read_text(encoding="utf-8")
    if f'version="{new_ver}"' not in text:
        esc_summary = saxutils.escape(summary)
        new_release_block = (
            f'  <releases>\n'
            f'    <release version="{new_ver}" date="{today}">\n'
            f'      <description>\n'
            f'        <p>{esc_summary}</p>\n'
            f'      </description>\n'
            f'    </release>'
        )
        text = text.replace("  <releases>", new_release_block, 1)
        metainfo.write_text(text, encoding="utf-8")
        print(f"  [OK] Added <release version=\"{new_ver}\" date=\"{today}\"> to metainfo.xml")
    else:
        print(f"  [OK] metainfo.xml already contains release {new_ver}")
PYEOF

# Update Cargo.lock package version
cargo check --quiet
echo "  [OK] Updated Cargo.lock"

if [[ "$REGEN_SCREENSHOTS" == "yes" ]]; then
  echo "  [..] Regenerating UI screenshots in docs/screenshots/..."
  QT_QPA_PLATFORM=offscreen python3 - << 'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path("python").resolve()))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

import easyeffects_auto_preset as ee

app = QApplication(sys.argv)
app.setStyle("Fusion")

palette = QPalette()
palette.setColor(QPalette.ColorRole.Window, QColor(30, 34, 42))
palette.setColor(QPalette.ColorRole.WindowText, QColor(235, 240, 245))
palette.setColor(QPalette.ColorRole.Base, QColor(22, 25, 32))
palette.setColor(QPalette.ColorRole.AlternateBase, QColor(40, 45, 56))
palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(30, 34, 42))
palette.setColor(QPalette.ColorRole.ToolTipText, QColor(235, 240, 245))
palette.setColor(QPalette.ColorRole.Text, QColor(235, 240, 245))
palette.setColor(QPalette.ColorRole.Button, QColor(45, 51, 64))
palette.setColor(QPalette.ColorRole.ButtonText, QColor(235, 240, 245))
palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
palette.setColor(QPalette.ColorRole.Link, QColor(56, 189, 248))
palette.setColor(QPalette.ColorRole.Highlight, QColor(2, 132, 199))
palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
app.setPalette(palette)

out_dir = Path("docs/screenshots")
out_dir.mkdir(parents=True, exist_ok=True)
cfg = ee.DEFAULT_CONFIG.copy()
worker = ee.AudioMonitorWorker(cfg)
win = ee.MainWindow(cfg, worker)
win.resize(780, 660)

for combo in (win.combo_youtube, win.combo_meeting, win.combo_default):
    if combo.count() == 0:
        for p in ["Compressed-Max", "Crystal more Bass", "Meeting-Voice-Clear"]:
            combo.addItem(p)
if win.combo_mic.count() <= 1:
    win.combo_mic.addItem("Meeting-Mic-Clean")
win._load_config_to_ui()

sample_streams = [
    {
        "type": "Audio Playback",
        "app": "Zen Browser",
        "media": "Turn My Way | YouTube Music",
        "state": "Playing",
        "trigger": "YouTube Playing",
    },
    {
        "type": "Audio Playback",
        "app": "VLC media player",
        "media": "Dune Part Two (4K HDR).mkv",
        "state": "Playing",
        "trigger": "Media App (VLC media player)",
    },
    {
        "type": "Audio Playback",
        "app": "Spotify",
        "media": "Daft Punk — Random Access Memories",
        "state": "Paused",
        "trigger": "None",
    },
    {
        "type": "Microphone (Input)",
        "app": "Chromium (meet.google.com)",
        "media": "WebRTC Voice Input",
        "state": "Idle",
        "trigger": "None",
    },
]

win._on_state_changed("youtube", "Crystal more Bass", sample_streams)
win.lbl_version_status.setText(f"<b>Version:</b> v{ee.APP_VERSION} — Up to date (v{ee.APP_VERSION})")
win.show()
app.processEvents()

win.tabs.setCurrentIndex(0)
app.processEvents()
win.grab().save(str(out_dir / "preset-triggers.png"))

win.tabs.setCurrentIndex(1)
app.processEvents()
win.grab().save(str(out_dir / "live-audio-streams.png"))

win.resize(780, 720)
win.tabs.setCurrentIndex(2)
app.processEvents()
win.grab().save(str(out_dir / "preset-details.png"))
PYEOF
  echo "  [OK] Regenerated screenshots for v${NEW_VERSION}"
fi

echo ""
echo -e "${GREEN}Successfully bumped version to v${NEW_VERSION}!${RESET}"
