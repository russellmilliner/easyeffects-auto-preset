#!/usr/bin/env python3
"""easyeffects-auto-preset: Automated preset switcher and tray manager for EasyEffects.

Automatically switches EasyEffects presets based on active audio activity:
- "Crystal more Bass" when YouTube / music / movie / video is playing
- "Compressed-Max" (or "Meeting-Voice-Clear" / "Meeting-Voice-Clear-Max-Level" / "Meeting-Voice-Deep" /
  "Meeting-Breath-Block-Max" / "Meeting-Voice-Deep-Breath-Max") when in any voice meeting
- Restores default preset when audio is idle
Provides a system tray icon, background daemon, bundled preset installer, dependency checker, and settings GUI (PyQt6).
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QThread, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

CONFIG_DIR = Path.home() / ".config" / "easyeffects-auto-preset"
CONFIG_FILE = CONFIG_DIR / "config.json"
PID_FILE = CONFIG_DIR / "instance.pid"
APP_ICON_FILE = CONFIG_DIR / "app-icon.png"
AUTOSTART_FILE = Path.home() / ".config" / "autostart" / "easyeffects-auto-preset.desktop"
APP_DESKTOP_FILE = Path.home() / ".local" / "share" / "applications" / "easyeffects-auto-preset.desktop"
USER_SHARED_PRESETS_DIR = Path.home() / ".local" / "share" / "easyeffects-auto-preset" / "presets"

APP_VERSION = "0.5.1"
GITHUB_RELEASES_API_URL = "https://api.github.com/repos/russellmilliner/easyeffects-auto-preset/releases/latest"
GITHUB_RELEASES_PAGE_URL = "https://github.com/russellmilliner/easyeffects-auto-preset/releases"

DEFAULT_CONFIG = {
    "enabled": True,
    "youtube_preset": "Crystal more Bass",
    "meeting_preset": "Compressed-Max",
    "default_preset": "Crystal more Bass",
    "meeting_mic_preset": "Meeting-Mic-Clean",
    "apply_mic_preset": False,
    "debounce_seconds": 2.0,
    "check_interval_seconds": 1.0,
    "detect_microphone": True,
    "detect_communication_role": True,
    "detect_meeting_apps": True,
    "detect_youtube": True,
    "detect_media_apps": True,
    "pause_media_in_meetings": True,
    "show_notifications": True,
    "minimize_on_startup": True,
    "check_updates_on_startup": True,
    "bundled_presets_prompted": False,
}

KNOWN_MEETING_BINARIES = {
    "zoom", "zoom.real", "teams", "slack", "discord", "discord-canary",
    "webex", "skype", "skypeforlinux", "signal-desktop", "telegram-desktop",
}

MEETING_KEYWORDS = [
    "meet.google.com", "google meet", "zoom meeting", "teams call",
    "slack huddle", "discord call", "webex", "gotomeeting", "chime",
]

KNOWN_MEDIA_BINARIES = {
    # Video & movie players / media centers
    "vlc", "mpv", "celluloid", "totem", "haruna", "dragon", "kaffeine",
    "smplayer", "mplayer", "parole", "clapper", "showtime", "bomi", "qmplay2",
    "kodi", "kodi.bin", "plex", "plexmediaplayer", "plex-htpc",
    "jellyfinmediaplayer", "jellyfin-mpv-shim", "stremio", "freetube",
    "newpipe", "pipeline", "tubefeeder", "hypnotix", "ffplay",
    # Music players & audio streaming apps
    "spotify", "nuclear", "tidal-hifi", "high-tide", "qobuz", "deezer",
    "cider", "apple-music", "youtube-music", "pear-desktop", "spotube",
    "psst", "ncspot", "spotifyd", "elisa", "strawberry", "clementine",
    "rhythmbox", "amberol", "lollypop", "g4music", "gapless", "audacious",
    "deadbeef", "qmmp", "cmus", "mpd", "cantata", "amarok", "pragha",
    "sayonara", "quodlibet", "fooyin", "tauonmb", "tauon", "feishin",
    "supersonic", "finamp", "sonixd", "harmony", "plexamp", "radiotray-ng",
    "shortwave", "goodvibes", "gradio",
}

KNOWN_MEDIA_APP_IDS = (
    "org.videolan.vlc",
    "io.mpv.mpv",
    "io.github.celluloid_player",
    "org.kde.haruna",
    "org.kde.dragonplayer",
    "org.kde.elisa",
    "org.gnome.totem",
    "org.gnome.showtime",
    "com.rafostar.clapper",
    "tv.kodi.kodi",
    "tv.plex.",
    "com.github.iwalton3.jellyfin-media-player",
    "com.stremio.stremio",
    "io.freetubeapp.freetube",
    "com.spotify.client",
    "org.strawberrymusicplayer.strawberry",
    "org.clementine_player.clementine",
    "org.gnome.rhythmbox",
    "io.bassi.amberol",
    "org.gnome.lollypop",
    "com.github.neithern.g4music",
    "org.atheme.audacious",
    "com.plexamp.plexamp",
    "de.haeckerfelix.shortwave",
)

MEDIA_KEYWORDS = [
    # Video & movie streaming / players
    "youtube", "youtu.be", "netflix", "disney+", "disneyplus", "prime video",
    "amazon video", "hulu", "hbomax", "max.com", "peacock", "paramount+",
    "apple tv", "crunchyroll", "twitch", "vimeo", "dailymotion", "nebula",
    "curiositystream", "plex", "jellyfin", "emby", "kodi", "vlc", "mpv",
    "celluloid", "haruna", "totem", "clapper", "stremio", "freetube",
    "smplayer", "dragon player",
    # Music streaming & desktop players
    "spotify", "soundcloud", "tidal", "deezer", "qobuz", "bandcamp",
    "pandora", "apple music", "amazon music", "iheart", "tunein", "mixcloud",
    "audiomack", "pocket casts", "overcast", "elisa", "strawberry",
    "rhythmbox", "clementine", "amberol", "lollypop", "audacious",
    "deadbeef", "plexamp", "feishin", "supersonic",
]

MEDIA_ROLES = {"music", "video", "movie"}


# ==============================================================================
# Bundled Presets Packaging & Installation
# ==============================================================================

def _build_10band_eq(freqs: list[float], gains: list[float], qs: list[float] | None = None) -> dict:
    if qs is None:
        qs = [1.6] * len(freqs)
    bands = {}
    for idx, (freq, gain, q_val) in enumerate(zip(freqs, gains, qs)):
        bands[f"band{idx}"] = {
            "frequency": float(freq),
            "gain": float(gain),
            "mode": "RLC (BT)",
            "mute": False,
            "q": float(q_val),
            "slope": "x1",
            "solo": False,
            "type": "Bell",
            "width": 4.0,
        }
    return {
        "balance": 0.0,
        "bypass": False,
        "input-gain": 0.0,
        "left": bands,
        "mode": "IIR",
        "num-bands": len(freqs),
        "output-gain": 0.0,
        "pitch-left": 0.0,
        "pitch-right": 0.0,
        "right": json.loads(json.dumps(bands)),
        "split-channels": False,
    }


def _build_meeting_preset(
    *,
    eq_gains: list[float],
    eq_qs: list[float] | None = None,
    rnnoise_vad_thres: float = 65.0,
    rnnoise_release: float = 60.0,
    rnnoise_wet: float = -2.0,
    speex_agc: bool = False,
    speex_suppression: int = -35,
    speex_vad_start: int = 92,
    speex_vad_cont: int = 85,
    comp_hpf: float = 75.0,
    comp_lpf: float = 18000.0,
    comp_threshold: float = -16.0,
    comp_ratio: float = 3.5,
    comp_attack: float = 15.0,
    comp_release: float = 120.0,
    comp_release_thres: float = -45.0,
    comp_makeup: float = 2.0,
    comp_boost_amount: float = 0.0,
    comp_boost_thres: float = -70.0,
    comp_knee: float = -6.0,
    comp_lookahead: float = 0.0,
    max_input_gain: float = 12.0,
    max_output_gain: float = 0.0,
    max_threshold: float = -1.0,
) -> dict:
    freqs = [32.0, 64.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0]
    return {
        "output": {
            "blocklist": [],
            "rnnoise#0": {
                "bypass": False,
                "enable-vad": True,
                "input-gain": 0.0,
                "model-name": '""',
                "output-gain": 0.0,
                "release": float(rnnoise_release),
                "use-standard-model": True,
                "vad-thres": float(rnnoise_vad_thres),
                "wet": float(rnnoise_wet),
            },
            "speex#0": {
                "bypass": False,
                "enable-agc": bool(speex_agc),
                "enable-denoise": True,
                "enable-dereverb": True,
                "input-gain": 0.0,
                "noise-suppression": int(speex_suppression),
                "output-gain": 0.0,
                "vad": {
                    "enable": True,
                    "probability-continue": int(speex_vad_cont),
                    "probability-start": int(speex_vad_start),
                },
            },
            "equalizer#0": _build_10band_eq(freqs, eq_gains, eq_qs),
            "compressor#0": {
                "attack": float(comp_attack),
                "boost-amount": float(comp_boost_amount),
                "boost-threshold": float(comp_boost_thres),
                "bypass": False,
                "dry": -80.0,
                "hpf-frequency": float(comp_hpf),
                "hpf-mode": "12 dB/oct Highpass",
                "input-gain": 0.0,
                "input-to-link": 0.0,
                "input-to-sidechain": 0.0,
                "knee": float(comp_knee),
                "link-to-input": 0.0,
                "link-to-sidechain": 0.0,
                "lpf-frequency": float(comp_lpf),
                "lpf-mode": "Off",
                "makeup": float(comp_makeup),
                "mode": "Downward",
                "output-gain": 0.0,
                "ratio": float(comp_ratio),
                "release": float(comp_release),
                "release-threshold": float(comp_release_thres),
                "sidechain": {
                    "lookahead": float(comp_lookahead),
                    "mode": "RMS",
                    "preamp": 0.0,
                    "reactivity": 10.0,
                    "source": "Middle",
                    "stereo-split-source": "Left/Right",
                    "type": "Feed-forward",
                },
                "sidechain-to-input": 0.0,
                "sidechain-to-link": 0.0,
                "stereo-split": False,
                "threshold": float(comp_threshold),
                "wet": 0.0,
            },
            "maximizer#0": {
                "bypass": False,
                "input-gain": float(max_input_gain),
                "output-gain": float(max_output_gain),
                "release": 25.0,
                "threshold": float(max_threshold),
            },
            "plugins_order": [
                "rnnoise#0",
                "speex#0",
                "equalizer#0",
                "compressor#0",
                "maximizer#0",
            ],
        }
    }


def get_embedded_presets() -> dict[str, dict[str, dict]]:
    """Return all bundled output and input presets embedded directly in the application."""
    crystal_bands = {}
    for idx, intensity in enumerate([0.0, -1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -7.0, -8.0, -9.0, -10.0, -12.0, -14.0]):
        crystal_bands[f"band{idx}"] = {"bypass": False, "intensity": intensity, "mute": False}

    crystal_more_bass = {
        "output": {
            "blocklist": [],
            "crystalizer#0": {
                "adaptive-intensity": True,
                **crystal_bands,
                "bypass": False,
                "fixed-quantum": False,
                "input-gain": 0.0,
                "output-gain": 0.0,
                "oversampling": True,
                "oversampling-quality": 5.0,
            },
            "equalizer#0": _build_10band_eq(
                [32.0, 64.0, 128.0, 256.0, 512.0, 1024.0, 2048.0, 4096.0, 8192.0, 16384.0],
                [7.93, 6.85, 2.19, 1.94, 5.03, 5.11, 2.77, 1.92, 7.46, 11.5],
            ),
            "plugins_order": ["crystalizer#0", "equalizer#0"],
        }
    }

    compressed_max = {
        "output": {
            "blocklist": [],
            "compressor#0": {
                "attack": 20.0,
                "boost-amount": 6.0,
                "boost-threshold": -72.0,
                "bypass": False,
                "dry": -80.01,
                "hpf-frequency": 10.0,
                "hpf-mode": "Off",
                "input-gain": 0.0,
                "input-to-link": 0.0,
                "input-to-sidechain": 0.0,
                "knee": -6.0,
                "link-to-input": 0.0,
                "link-to-sidechain": 0.0,
                "lpf-frequency": 20000.0,
                "lpf-mode": "Off",
                "makeup": 0.0,
                "mode": "Downward",
                "output-gain": 0.0,
                "ratio": 4.0,
                "release": 100.0,
                "release-threshold": -80.01,
                "sidechain": {
                    "lookahead": 0.0,
                    "mode": "Peak",
                    "preamp": 0.0,
                    "reactivity": 10.0,
                    "source": "Middle",
                    "stereo-split-source": "Left/Right",
                    "type": "Feed-forward",
                },
                "sidechain-to-input": 0.0,
                "sidechain-to-link": 0.0,
                "stereo-split": False,
                "threshold": -12.0,
                "wet": 0.0,
            },
            "maximizer#0": {
                "bypass": False,
                "input-gain": 36.0,
                "output-gain": 3.0,
                "release": 25.0,
                "threshold": 0.0,
            },
            "plugins_order": ["compressor#0", "maximizer#0"],
        }
    }

    meeting_mic_clean = {
        "input": {
            "blocklist": [],
            "speex#0": {
                "bypass": False,
                "enable-agc": True,
                "enable-denoise": True,
                "enable-dereverb": True,
                "input-gain": 0.0,
                "noise-suppression": -70,
                "output-gain": 0.0,
                "vad": {
                    "enable": False,
                    "probability-continue": 90,
                    "probability-start": 95,
                },
            },
            "plugins_order": ["speex#0"],
        }
    }

    return {
        "output": {
            "Meeting-Voice-Clear": _build_meeting_preset(
                eq_gains=[-28.0, -14.0, 2.0, 1.5, 1.5, 2.0, 2.0, 1.5, 2.5, 2.0],
                rnnoise_vad_thres=65.0,
                rnnoise_release=60.0,
                rnnoise_wet=-2.0,
                speex_agc=False,
                speex_suppression=-35,
                comp_hpf=75.0,
                comp_threshold=-16.0,
                comp_ratio=3.5,
                comp_release_thres=-45.0,
                comp_makeup=2.0,
                max_input_gain=12.0,
                max_output_gain=0.0,
                max_threshold=-1.0,
            ),
            "Meeting-Voice-Clear-Max-Level": _build_meeting_preset(
                eq_gains=[-28.0, -14.0, 2.0, 1.5, 1.5, 2.0, 2.0, 1.5, 2.5, 2.0],
                rnnoise_vad_thres=72.0,
                rnnoise_release=50.0,
                rnnoise_wet=0.0,
                speex_agc=True,
                speex_suppression=-45,
                speex_vad_start=94,
                speex_vad_cont=88,
                comp_hpf=75.0,
                comp_threshold=-24.0,
                comp_ratio=6.0,
                comp_attack=10.0,
                comp_release=100.0,
                comp_release_thres=-55.0,
                comp_makeup=6.0,
                comp_boost_amount=6.0,
                comp_boost_thres=-55.0,
                comp_knee=-9.0,
                comp_lookahead=2.0,
                max_input_gain=28.0,
                max_output_gain=1.0,
                max_threshold=-0.5,
            ),
            "Meeting-Voice-Deep": _build_meeting_preset(
                eq_gains=[-26.0, -10.0, 4.0, 3.0, 1.5, 1.5, 1.8, 1.5, 2.5, 2.5],
                eq_qs=[1.6, 1.6, 1.5, 1.5, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6],
                rnnoise_vad_thres=65.0,
                rnnoise_release=60.0,
                rnnoise_wet=-2.0,
                speex_agc=False,
                speex_suppression=-35,
                comp_hpf=65.0,
                comp_threshold=-16.0,
                comp_ratio=3.5,
                comp_release_thres=-45.0,
                comp_makeup=2.0,
                max_input_gain=12.0,
                max_output_gain=0.0,
                max_threshold=-1.0,
            ),
            "Meeting-Breath-Block-Max": _build_meeting_preset(
                eq_gains=[-30.0, -18.0, 2.0, 1.5, 1.5, 2.0, 2.0, 0.5, 0.5, 0.0],
                rnnoise_vad_thres=80.0,
                rnnoise_release=40.0,
                rnnoise_wet=0.0,
                speex_agc=False,
                speex_suppression=-50,
                speex_vad_start=96,
                speex_vad_cont=90,
                comp_hpf=80.0,
                comp_lpf=16000.0,
                comp_threshold=-16.0,
                comp_ratio=3.5,
                comp_release_thres=-38.0,
                comp_makeup=1.5,
                max_input_gain=10.0,
                max_output_gain=0.0,
                max_threshold=-1.0,
            ),
            "Meeting-Voice-Deep-Breath-Max": _build_meeting_preset(
                eq_gains=[-28.0, -12.0, 4.0, 3.0, 1.5, 1.8, 1.8, 1.0, 1.0, 1.0],
                eq_qs=[1.6, 1.6, 1.5, 1.5, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6],
                rnnoise_vad_thres=80.0,
                rnnoise_release=45.0,
                rnnoise_wet=0.0,
                speex_agc=False,
                speex_suppression=-45,
                speex_vad_start=95,
                speex_vad_cont=90,
                comp_hpf=68.0,
                comp_threshold=-16.0,
                comp_ratio=3.5,
                comp_release_thres=-38.0,
                comp_makeup=2.0,
                max_input_gain=11.0,
                max_output_gain=0.0,
                max_threshold=-1.0,
            ),
            "Crystal more Bass": crystal_more_bass,
            "Compressed-Max": compressed_max,
        },
        "input": {
            "Meeting-Mic-Clean": meeting_mic_clean,
        },
    }


BUNDLED_PRESET_DESCRIPTIONS = {
    "Meeting-Voice-Clear": (
        "Output",
        "Balanced voice-call preset: warm vocal depth (+2 dB @ 125Hz, +1.5 dB @ 250Hz), steep sub-75Hz mic-thump filter, and RNNoise (65% VAD) + Speex (-35 dB) mic-breathing suppression.",
    ),
    "Meeting-Voice-Clear-Max-Level": (
        "Output",
        "Aggressive loud-vs-soft voice volume leveler: Speex AGC + 6:1 Compressor (-24 dB, +6 dB makeup) + Maximizer (+28 dB gain) while RNNoise (72% VAD) blocks mic breathing first.",
    ),
    "Meeting-Voice-Deep": (
        "Output",
        "Extra vocal depth & broadcast warmth: +4.0 dB @ 125Hz and +3.0 dB @ 250Hz (65Hz HPF) for rich radio-style voices while still filtering sub-60Hz desk thumps.",
    ),
    "Meeting-Breath-Block-Max": (
        "Output",
        "Maximum anti-breathing filter: 100% wet RNNoise with 80% VAD threshold (40ms release), Speex -50 dB denoise (96% VAD), 80Hz HPF, and tamed 4–16kHz aspiration hiss.",
    ),
    "Meeting-Voice-Deep-Breath-Max": (
        "Output",
        "Combined deep broadcast voice (+4 dB @ 125Hz, +3 dB @ 250Hz) + maximum 80% neural VAD breath suppression.",
    ),
    "Crystal more Bass": (
        "Output",
        "Rich low-end bass punch and crystalline highs tuned for YouTube, music, movies, and video playback.",
    ),
    "Compressed-Max": (
        "Output",
        "High-ratio dynamic compressor + +36 dB maximizer ceiling for maximum volume normalization.",
    ),
    "Meeting-Mic-Clean": (
        "Input (Mic)",
        "Outbound microphone Speex noise suppression (-70 dB), room dereverberation, and Automatic Gain Control (AGC).",
    ),
}


def get_easyeffects_target_preset_dirs() -> list[Path]:
    """Return all active EasyEffects base preset directories (Flatpak and/or Native)."""
    targets: list[Path] = []
    flatpak_base = Path.home() / ".var/app/com.github.wwmm.easyeffects/data/easyeffects"
    native_data_base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "easyeffects"
    native_cfg_base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "easyeffects"

    if flatpak_base.parent.exists() or is_flatpak_easyeffects_installed():
        targets.append(flatpak_base)
    if shutil.which("easyeffects") or native_data_base.exists():
        if native_data_base not in targets:
            targets.append(native_data_base)
    if native_cfg_base.exists() and (native_cfg_base / "output").exists():
        if native_cfg_base not in targets:
            targets.append(native_cfg_base)

    if not targets:
        # Default to both Flatpak and standard XDG data dir so presets are ready whichever gets installed
        targets.append(flatpak_base)
        targets.append(native_data_base)
    return targets


def get_bundled_preset_status() -> dict[str, bool]:
    """Check whether each bundled preset is currently installed in EasyEffects."""
    embedded = get_embedded_presets()
    targets = get_easyeffects_target_preset_dirs()
    status: dict[str, bool] = {}

    for preset_name in embedded["output"]:
        installed = any((base / "output" / f"{preset_name}.json").is_file() for base in targets)
        status[preset_name] = installed
    for preset_name in embedded["input"]:
        installed = any((base / "input" / f"{preset_name}.json").is_file() for base in targets)
        status[preset_name] = installed

    return status


def install_bundled_presets(overwrite: bool = True) -> tuple[int, list[str], list[Path]]:
    """Install bundled output and input presets into EasyEffects and user share dir.

    Returns (installed_count, installed_preset_names, target_directories).
    """
    embedded = get_embedded_presets()
    # Also check if newer JSON files exist in repo/system preset directories
    candidate_source_dirs = [
        Path(__file__).resolve().parent.parent / "presets",
        Path("/app/share/easyeffects-auto-preset/presets"),
        Path("/usr/share/easyeffects-auto-preset/presets"),
        USER_SHARED_PRESETS_DIR,
    ]

    targets = get_easyeffects_target_preset_dirs()
    installed_names: list[str] = []
    installed_count = 0

    # Ensure user shared presets cache also has copies
    try:
        USER_SHARED_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    for channel in ("output", "input"):
        for preset_name, default_payload in embedded[channel].items():
            # Prefer on-disk source file if present in repo
            payload = default_payload
            for src_dir in candidate_source_dirs:
                src_file = src_dir / f"{preset_name}.json"
                if src_file.is_file():
                    try:
                        payload = json.loads(src_file.read_text(encoding="utf-8"))
                        break
                    except Exception:
                        pass

            # Save copy to ~/.local/share/easyeffects-auto-preset/presets/
            try:
                shared_file = USER_SHARED_PRESETS_DIR / f"{preset_name}.json"
                if overwrite or not shared_file.is_file():
                    shared_file.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")
            except Exception:
                pass

            wrote_this_preset = False
            for base_dir in targets:
                dest_dir = base_dir / channel
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_file = dest_dir / f"{preset_name}.json"
                if overwrite or not dest_file.is_file():
                    dest_file.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")
                    wrote_this_preset = True

            if wrote_this_preset:
                installed_count += 1
                installed_names.append(preset_name)

    return installed_count, installed_names, targets


# ==============================================================================
# System & Dependency Detection and Package Installer
# ==============================================================================

def detect_linux_distro() -> dict[str, str]:
    """Read /etc/os-release and detect available package managers."""
    info = {"id": "linux", "id_like": "", "name": "Linux", "pkg_mgr": ""}
    os_rel = Path("/etc/os-release")
    if os_rel.is_file():
        try:
            for line in os_rel.read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    if k == "ID":
                        info["id"] = v.lower()
                    elif k == "ID_LIKE":
                        info["id_like"] = v.lower()
                    elif k == "PRETTY_NAME":
                        info["name"] = v
        except Exception:
            pass

    if shutil.which("pacman"):
        info["pkg_mgr"] = "pacman"
    elif shutil.which("apt"):
        info["pkg_mgr"] = "apt"
    elif shutil.which("dnf"):
        info["pkg_mgr"] = "dnf"
    elif shutil.which("zypper"):
        info["pkg_mgr"] = "zypper"
    elif shutil.which("flatpak"):
        info["pkg_mgr"] = "flatpak"

    return info


def is_flatpak_easyeffects_installed() -> bool:
    """Return True if com.github.wwmm.easyeffects is installed in Flatpak."""
    if not shutil.which("flatpak"):
        return False
    try:
        res = subprocess.run(
            ["flatpak", "info", "com.github.wwmm.easyeffects"],
            capture_output=True,
            text=True,
            timeout=4,
        )
        return res.returncode == 0
    except Exception:
        return False


def check_system_dependencies() -> dict:
    """Inspect system for EasyEffects and required audio/DSP packages.

    Returns a dictionary containing:
    - 'all_required_ok': bool
    - 'all_recommended_ok': bool
    - 'distro': dict
    - 'items': list of dicts with keys (name, required, installed, status_text, description, fix_cmd)
    - 'combined_fix_commands': list of shell command strings to install missing items
    """
    distro = detect_linux_distro()
    pkg_mgr = distro["pkg_mgr"]

    native_ee = shutil.which("easyeffects") is not None
    flatpak_ee = is_flatpak_easyeffects_installed()
    ee_installed = native_ee or flatpak_ee

    pactl_installed = shutil.which("pactl") is not None
    pipewire_installed = shutil.which("pw-cli") is not None or shutil.which("pipewire") is not None

    # Check if native EasyEffects has required LV2/LADSPA DSP plugins (Flatpak EasyEffects bundles its own)
    lv2_dirs = [Path("/usr/lib/lv2"), Path("/usr/lib64/lv2"), Path("/usr/local/lib/lv2")]
    ladspa_dirs = [Path("/usr/lib/ladspa"), Path("/usr/lib64/ladspa")]

    def _has_file_matching(dirs: list[Path], pattern: str) -> bool:
        for d in dirs:
            if d.is_dir() and list(d.glob(pattern)):
                return True
        return False

    lsp_installed = flatpak_ee or _has_file_matching(lv2_dirs, "*lsp-plugins*")
    rnnoise_installed = (
        flatpak_ee
        or _has_file_matching(ladspa_dirs, "*rnnoise*")
        or _has_file_matching(lv2_dirs, "*rnnoise*")
        or Path("/usr/lib/librnnoise.so").exists()
        or Path("/usr/lib64/librnnoise.so").exists()
    )

    # Distro-specific package installation commands
    if pkg_mgr == "pacman":
        ee_fix = "sudo pacman -S --needed easyeffects lsp-plugins-lv2 calf zam-plugins-lv2 rnnoise"
        pactl_fix = "sudo pacman -S --needed libpulse pipewire-pulse"
        pw_fix = "sudo pacman -S --needed pipewire wireplumber"
        dsp_fix = "sudo pacman -S --needed lsp-plugins-lv2 calf zam-plugins-lv2 rnnoise speexdsp"
    elif pkg_mgr == "apt":
        ee_fix = "sudo apt update && sudo apt install -y easyeffects lsp-plugins-lv2 calf-plugins zam-plugins"
        pactl_fix = "sudo apt update && sudo apt install -y pulseaudio-utils pipewire-pulse"
        pw_fix = "sudo apt update && sudo apt install -y pipewire wireplumber"
        dsp_fix = "sudo apt update && sudo apt install -y lsp-plugins-lv2 calf-plugins zam-plugins librnnoise0"
    elif pkg_mgr == "dnf":
        ee_fix = "sudo dnf install -y easyeffects lsp-plugins-lv2 calf zam-plugins"
        pactl_fix = "sudo dnf install -y pulseaudio-utils pipewire-pulseaudio"
        pw_fix = "sudo dnf install -y pipewire wireplumber"
        dsp_fix = "sudo dnf install -y lsp-plugins-lv2 calf zam-plugins rnnoise"
    elif pkg_mgr == "zypper":
        ee_fix = "sudo zypper install -y easyeffects lsp-plugins-lv2 calf"
        pactl_fix = "sudo zypper install -y pulseaudio-utils pipewire-pulseaudio"
        pw_fix = "sudo zypper install -y pipewire wireplumber"
        dsp_fix = "sudo zypper install -y lsp-plugins-lv2 calf rnnoise"
    else:
        ee_fix = "flatpak install -y flathub com.github.wwmm.easyeffects"
        pactl_fix = "Install 'pulseaudio-utils' or 'libpulse' using your system package manager"
        pw_fix = "Install 'pipewire' using your system package manager"
        dsp_fix = "flatpak install -y flathub com.github.wwmm.easyeffects"

    flatpak_ee_fix = "flatpak install -y flathub com.github.wwmm.easyeffects"

    if flatpak_ee and native_ee:
        ee_status = "Installed (Native + Flatpak)"
    elif flatpak_ee:
        ee_status = "Installed (Flatpak: com.github.wwmm.easyeffects)"
    elif native_ee:
        ee_status = "Installed (Native: /usr/bin/easyeffects)"
    else:
        ee_status = "Missing (Required)"

    items = [
        {
            "id": "easyeffects",
            "name": "EasyEffects Audio Processor",
            "required": True,
            "installed": ee_installed,
            "status_text": ee_status,
            "description": "Core PipeWire DSP effects engine used to load and process output/input presets.",
            "fix_cmd": f"{ee_fix}\n# Or via Flatpak (includes all DSP plugins):\n{flatpak_ee_fix}",
            "install_pkg_cmd": ee_fix,
            "install_flatpak_cmd": flatpak_ee_fix if shutil.which("flatpak") else "",
        },
        {
            "id": "pactl",
            "name": "PulseAudio / PipeWire CLI (pactl)",
            "required": True,
            "installed": pactl_installed,
            "status_text": "Installed" if pactl_installed else "Missing (Required)",
            "description": "Required to inspect live PipeWire/PulseAudio sink-inputs and microphone streams.",
            "fix_cmd": pactl_fix,
            "install_pkg_cmd": pactl_fix,
            "install_flatpak_cmd": "",
        },
        {
            "id": "pipewire",
            "name": "PipeWire Audio Server",
            "required": False,
            "installed": pipewire_installed,
            "status_text": "Installed" if pipewire_installed else "Missing (Recommended)",
            "description": "Low-latency audio and video routing server required by EasyEffects.",
            "fix_cmd": pw_fix,
            "install_pkg_cmd": pw_fix,
            "install_flatpak_cmd": "",
        },
        {
            "id": "dsp_plugins",
            "name": "EasyEffects DSP Plugins (LSP / RNNoise / Maximizer)",
            "required": False,
            "installed": lsp_installed and rnnoise_installed,
            "status_text": (
                "Bundled in Flatpak"
                if flatpak_ee
                else ("Installed" if (lsp_installed and rnnoise_installed) else "Missing some LV2/RNNoise plugins")
            ),
            "description": (
                "Required by the Meeting-Voice-Clear, Crystal more Bass, and Compressed-Max presets "
                "(Equalizer, Compressor, RNNoise breath suppression, Speex, and Maximizer)."
            ),
            "fix_cmd": dsp_fix,
            "install_pkg_cmd": dsp_fix,
            "install_flatpak_cmd": "",
        },
    ]

    missing_pkg_cmds: list[str] = []
    for it in items:
        if not it["installed"] and it["install_pkg_cmd"] and not it["install_pkg_cmd"].startswith("Install "):
            if it["install_pkg_cmd"] not in missing_pkg_cmds:
                missing_pkg_cmds.append(it["install_pkg_cmd"])

    all_required_ok = all(it["installed"] for it in items if it["required"])
    all_recommended_ok = all(it["installed"] for it in items)

    return {
        "all_required_ok": all_required_ok,
        "all_recommended_ok": all_recommended_ok,
        "distro": distro,
        "items": items,
        "combined_fix_commands": missing_pkg_cmds,
    }


def launch_package_installation(cmd_str: str, parent: QWidget | None = None) -> bool:
    """Run an installation command using a terminal emulator or pkexec."""
    # Strip leading 'sudo ' if we use pkexec without terminal
    clean_cmd = cmd_str.strip()

    # Prefer opening an interactive terminal emulator so the user can see package manager progress
    terminals = [
        ("konsole", ["konsole", "-e", "bash", "-c"]),
        ("yakuake", None),
        ("gnome-terminal", ["gnome-terminal", "--", "bash", "-c"]),
        ("xfce4-terminal", ["xfce4-terminal", "-x", "bash", "-c"]),
        ("kitty", ["kitty", "bash", "-c"]),
        ("alacritty", ["alacritty", "-e", "bash", "-c"]),
        ("ptyxis", ["ptyxis", "--", "bash", "-c"]),
        ("xterm", ["xterm", "-e", "bash", "-c"]),
    ]

    interactive_script = (
        f"echo '==> Running: {clean_cmd}'; "
        f"{clean_cmd}; "
        "echo ''; echo '==> Finished! Press Enter to close this window...'; read -r _"
    )

    for term_bin, term_prefix in terminals:
        if term_prefix and shutil.which(term_bin):
            try:
                subprocess.Popen(term_prefix + [interactive_script])
                return True
            except Exception:
                pass

    # Fallback: if it's a flatpak command or pkexec is available
    if clean_cmd.startswith("flatpak "):
        try:
            subprocess.Popen(["bash", "-c", clean_cmd])
            return True
        except Exception:
            pass

    if shutil.which("pkexec"):
        pk_cmd = re.sub(r"^sudo\s+", "", clean_cmd)
        try:
            subprocess.Popen(["pkexec", "bash", "-c", pk_cmd])
            return True
        except Exception:
            pass

    if parent:
        QMessageBox.information(
            parent,
            "Run Command in Terminal",
            f"Could not detect a terminal launcher automatically.\n\nPlease run this command in your terminal:\n\n{clean_cmd}",
        )
    return False


# ==============================================================================
# Stream Detection & Icon Rendering
# ==============================================================================

def detect_media_playback_stream(sk: dict[str, str], config: dict) -> tuple[bool, str, str]:
    """Check if a sink-input dict represents YouTube, music, movie, or video playback.

    Returns (is_media_playing, trigger_label_for_table, detailed_reason).
    """
    if not config.get("detect_youtube", True) and not config.get("detect_media_apps", True):
        return False, "None", ""

    app = sk.get("application.name", "")
    binary = sk.get("application.process.binary", "").lower()
    media = sk.get("media.name", "")
    role = sk.get("media.role", "").lower()
    app_id = (sk.get("pipewire.access.portal.app_id") or sk.get("application.id") or "").lower()

    app_lower = app.lower()
    media_lower = media.lower()

    if (
        "speech-dispatcher" in binary
        or "sd_dummy" in binary
        or "easyeffects" in binary
        or "speech-dispatcher" in app_lower
        or "easyeffects" in app_lower
    ):
        return False, "None", ""

    display_label = f"{media} ({app})" if (media and app) else (app or media or binary or "Media")

    # 1. Native music, movie, or video application binary / Flatpak ID / PipeWire media.role
    if config.get("detect_media_apps", True) or config.get("detect_youtube", True):
        if binary in KNOWN_MEDIA_BINARIES:
            return True, f"Media App ({app or binary})", f"Media App: {display_label}"
        if app_id and any(aid in app_id for aid in KNOWN_MEDIA_APP_IDS):
            return True, f"Media App ({app or app_id})", f"Media App: {display_label}"
        if role in MEDIA_ROLES:
            return True, f"Media Role ({role.capitalize()})", f"Media ({role}): {display_label}"

    # 2. YouTube, music, movie, and video streaming keywords in media.name or application.name
    if config.get("detect_youtube", True) or config.get("detect_media_apps", True):
        if "youtube" in media_lower or "youtube" in app_lower:
            return True, "YouTube Playing", f"YouTube: {display_label}"
        for kw in MEDIA_KEYWORDS:
            if kw in media_lower or kw in app_lower:
                return True, f"Media ({kw})", f"Media ({kw}): {display_label}"

    return False, "None", ""


def generate_app_icon(path: Path, size: int = 128) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    scale = size / 64.0

    # Draw rounded dark background squircle
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(28, 32, 42)))
    painter.drawRoundedRect(QRectF(3 * scale, 3 * scale, 58 * scale, 58 * scale), 14 * scale, 14 * scale)

    # Equalizer tracks
    pen = QPen(QColor(135, 150, 175), 3.5 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    xs = [16 * scale, 32 * scale, 48 * scale]
    knob_ys = [20 * scale, 36 * scale, 24 * scale]

    for i, x in enumerate(xs):
        painter.drawLine(int(x), int(14 * scale), int(x), int(50 * scale))
        painter.setBrush(QBrush(QColor(245, 248, 252)))
        painter.setPen(QPen(QColor(15, 18, 24), 1.5 * scale))
        painter.drawRoundedRect(
            QRectF(x - 5.5 * scale, knob_ys[i] - 3.5 * scale, 11 * scale, 7 * scale),
            2 * scale,
            2 * scale,
        )

    # Accent badge: auto indicator pip
    painter.setBrush(QBrush(QColor(0, 168, 255)))
    painter.setPen(QPen(QColor(15, 18, 24), 2 * scale))
    painter.drawEllipse(QRectF(42 * scale, 42 * scale, 18 * scale, 18 * scale))

    painter.end()
    img.save(str(path))


def _render_tray_pixmap(mode: str = "default", enabled: bool = True, size: int = 64) -> QPixmap:
    """Render a single resolution pixmap showing both a mode icon glyph and a bold mode text badge."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    scale = size / 64.0

    if not enabled:
        bg_color = QColor(45, 16, 20, 248)
        border_color = QColor(248, 113, 113)
        badge_color = QColor(220, 38, 38)
        badge_text = "OFF"
    elif mode == "meeting":
        bg_color = QColor(10, 44, 32, 248)
        border_color = QColor(52, 211, 153)
        badge_color = QColor(5, 150, 105)
        badge_text = "MTG"
    elif mode == "youtube":
        bg_color = QColor(12, 34, 58, 248)
        border_color = QColor(56, 189, 248)
        badge_color = QColor(2, 132, 199)
        badge_text = "MED"
    else:
        bg_color = QColor(24, 28, 38, 248)
        border_color = QColor(148, 163, 184)
        badge_color = QColor(71, 85, 105)
        badge_text = "DEF"

    # 1. Outer rounded squircle container
    outer_rect = QRectF(2.0 * scale, 2.0 * scale, 60.0 * scale, 60.0 * scale)
    painter.setBrush(QBrush(bg_color))
    painter.setPen(QPen(border_color, max(1.5, 2.4 * scale)))
    painter.drawRoundedRect(outer_rect, 13.0 * scale, 13.0 * scale)

    # 2. Upper Mode Symbol / Glyph (y = 6..36)
    if not enabled:
        # Pause bars (⏸)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(254, 202, 202)))
        painter.drawRoundedRect(
            QRectF(21.0 * scale, 9.5 * scale, 7.5 * scale, 22.0 * scale),
            2.5 * scale,
            2.5 * scale,
        )
        painter.drawRoundedRect(
            QRectF(35.5 * scale, 9.5 * scale, 7.5 * scale, 22.0 * scale),
            2.5 * scale,
            2.5 * scale,
        )
    elif mode == "meeting":
        # Microphone glyph (🎤) + sound waves
        # Sound wave arcs on left & right
        wave_pen = QPen(QColor(110, 231, 183), max(1.2, 2.2 * scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(wave_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(12.0 * scale, 9.0 * scale, 10.0 * scale, 16.0 * scale), 120 * 16, 120 * 16)
        painter.drawArc(QRectF(42.0 * scale, 9.0 * scale, 10.0 * scale, 16.0 * scale), -60 * 16, 120 * 16)

        # Microphone capsule
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawRoundedRect(
            QRectF(26.5 * scale, 6.5 * scale, 11.0 * scale, 16.5 * scale),
            5.5 * scale,
            5.5 * scale,
        )

        # Microphone U-cradle, stem, and base
        mic_pen = QPen(QColor(255, 255, 255), max(1.5, 2.8 * scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(mic_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(22.0 * scale, 10.5 * scale, 20.0 * scale, 17.5 * scale), 180 * 16, 180 * 16)
        painter.drawLine(QPointF(32.0 * scale, 28.5 * scale), QPointF(32.0 * scale, 34.0 * scale))
        painter.drawLine(QPointF(25.5 * scale, 34.0 * scale), QPointF(38.5 * scale, 34.0 * scale))
    elif mode == "youtube":
        # Play triangle glyph (▶) + sound waves
        painter.setPen(QPen(QColor(255, 255, 255), max(1.0, 1.6 * scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        play_poly = QPolygonF(
            [
                QPointF(20.0 * scale, 8.5 * scale),
                QPointF(20.0 * scale, 33.0 * scale),
                QPointF(41.5 * scale, 20.75 * scale),
            ]
        )
        painter.drawPolygon(play_poly)

        # Subtle audio wave arc on the right
        wave_pen = QPen(QColor(125, 211, 252), max(1.3, 2.5 * scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(wave_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(37.0 * scale, 10.5 * scale, 12.0 * scale, 20.5 * scale), -55 * 16, 110 * 16)
    else:
        # Equalizer sliders glyph (3 vertical tracks + knobs)
        xs = [18.0 * scale, 32.0 * scale, 46.0 * scale]
        knob_ys = [15.0 * scale, 25.5 * scale, 18.0 * scale]
        track_pen = QPen(QColor(203, 213, 225), max(1.4, 3.2 * scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        for i, x in enumerate(xs):
            painter.setPen(track_pen)
            painter.drawLine(QPointF(x, 8.5 * scale), QPointF(x, 33.0 * scale))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(QPen(QColor(15, 23, 42, 210), max(1.0, 1.3 * scale)))
            painter.drawRoundedRect(
                QRectF(x - 4.8 * scale, knob_ys[i] - 3.0 * scale, 9.6 * scale, 6.0 * scale),
                1.8 * scale,
                1.8 * scale,
            )

    # 3. Bottom Mode Text Badge Pill (y = 37.5..60)
    badge_rect = QRectF(3.5 * scale, 37.5 * scale, 57.0 * scale, 23.0 * scale)
    painter.setBrush(QBrush(badge_color))
    painter.setPen(QPen(border_color, max(1.0, 1.4 * scale)))
    painter.drawRoundedRect(badge_rect, 8.5 * scale, 8.5 * scale)

    font = QFont("Sans Serif")
    font.setWeight(QFont.Weight.Black)
    font.setPixelSize(max(8, int(round(16.0 * scale))))
    painter.setFont(font)

    # Subtle dark drop-shadow for maximum text legibility at small tray sizes
    painter.setPen(QColor(0, 0, 0, 160))
    painter.drawText(
        badge_rect.translated(0, max(0.6, 0.9 * scale)),
        Qt.AlignmentFlag.AlignCenter,
        badge_text,
    )
    painter.setPen(QColor(255, 255, 255))
    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

    painter.end()
    return QPixmap.fromImage(img)


def build_tray_icon(mode: str = "default", enabled: bool = True, size: int = 64) -> QIcon:
    icon = QIcon()
    for sz in sorted({22, 24, 32, 48, 64, 128, size}):
        icon.addPixmap(_render_tray_pixmap(mode=mode, enabled=enabled, size=sz))
    return icon


def parse_semver(version: str) -> tuple[int, int, int] | None:
    """Parse a semantic version string (e.g., 'v0.1.0' or '0.1.0') into a (major, minor, patch) tuple."""
    cleaned = version.strip().lstrip("vV").split("-", 1)[0].split("+", 1)[0]
    parts = cleaned.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except (ValueError, IndexError):
        return None


def is_newer_version(current: str, latest: str) -> bool:
    cur_t = parse_semver(current)
    lat_t = parse_semver(latest)
    if cur_t is not None and lat_t is not None:
        return lat_t > cur_t
    cur_c = current.strip().lstrip("vV")
    lat_c = latest.strip().lstrip("vV")
    return bool(lat_c) and lat_c != cur_c


def check_for_updates(current_version: str = APP_VERSION, timeout: float = 8.0) -> dict:
    """Check GitHub Releases for a newer version of EasyEffects Auto Preset."""
    req = urllib.request.Request(
        GITHUB_RELEASES_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"EasyEffectsAutoPreset/{current_version}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        tag_name = str(payload.get("tag_name", "")).strip()
        latest_clean = tag_name.lstrip("vV") or current_version.lstrip("vV")
        current_clean = current_version.strip().lstrip("vV")
        latest_tag = f"v{latest_clean}"
        current_tag = f"v{current_clean}"
        update_available = is_newer_version(current_clean, latest_clean)
        release_url = str(payload.get("html_url", "")).strip() or GITHUB_RELEASES_PAGE_URL
        release_notes = str(payload.get("body", "") or "")

        flatpak_url = ""
        tarball_url = ""
        binary_url = ""
        for asset in payload.get("assets", []) or []:
            name = str(asset.get("name", "")).lower()
            dl_url = str(asset.get("browser_download_url", "")).strip()
            if not dl_url or name.endswith(".sha256"):
                continue
            if name.endswith(".flatpak"):
                flatpak_url = dl_url
            elif name.endswith(".tar.gz"):
                tarball_url = dl_url
            elif name.startswith("easyeffects-auto-preset-"):
                binary_url = dl_url

        download_url = tarball_url or flatpak_url or binary_url or release_url

        message = (
            f"Update available: {latest_tag} (current: {current_tag})"
            if update_available
            else f"Up to date ({current_tag})"
        )
        return {
            "checked": True,
            "ok": True,
            "update_available": update_available,
            "current_version": current_tag,
            "latest_version": latest_tag,
            "release_url": release_url,
            "download_url": download_url,
            "flatpak_download_url": flatpak_url,
            "tarball_download_url": tarball_url,
            "release_notes": release_notes,
            "message": message,
        }
    except Exception as exc:
        return {
            "checked": True,
            "ok": False,
            "update_available": False,
            "current_version": f"v{current_version.lstrip('vV')}",
            "latest_version": f"v{current_version.lstrip('vV')}",
            "release_url": GITHUB_RELEASES_PAGE_URL,
            "download_url": GITHUB_RELEASES_PAGE_URL,
            "flatpak_download_url": "",
            "tarball_download_url": "",
            "release_notes": "",
            "message": f"Update check failed: {exc}",
        }


def install_update_from_github(
    tarball_url: str = "",
    flatpak_url: str = "",
    latest_version: str = "",
    timeout: float = 120.0,
) -> dict:
    """Download and install the latest release of EasyEffects Auto Preset from GitHub Releases."""
    import tempfile

    try:
        if not tarball_url and not flatpak_url:
            info = check_for_updates(APP_VERSION)
            if not info.get("ok"):
                return {"ok": False, "message": info.get("message", "Update check failed")}
            if not info.get("update_available"):
                return {"ok": True, "updated": False, "message": f"Already up to date ({info.get('current_version')})"}
            tarball_url = info.get("tarball_download_url", "")
            flatpak_url = info.get("flatpak_download_url", "")
            latest_version = info.get("latest_version", "")

        in_flatpak = Path("/.flatpak-info").exists() or bool(os.environ.get("FLATPAK_ID"))
        if in_flatpak and flatpak_url:
            with tempfile.TemporaryDirectory(prefix="ee-auto-preset-fp-") as tmpd:
                bundle_path = Path(tmpd) / f"easyeffects-auto-preset-{latest_version or 'latest'}.flatpak"
                req = urllib.request.Request(
                    flatpak_url,
                    headers={"User-Agent": f"EasyEffectsAutoPreset/{APP_VERSION}"},
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    bundle_path.write_bytes(resp.read())
                res = subprocess.run(
                    ["flatpak-spawn", "--host", "flatpak", "install", "--user", "-y", "--reinstall", str(bundle_path)],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if res.returncode != 0:
                    return {"ok": False, "message": f"Flatpak install failed: {res.stderr.strip()}"}
                return {
                    "ok": True,
                    "updated": True,
                    "latest_version": latest_version,
                    "message": f"Installed EasyEffects Auto Preset {latest_version} Flatpak successfully.",
                }

        if not tarball_url:
            return {"ok": False, "message": "No Linux release archive (.tar.gz) found on GitHub Releases."}

        with tempfile.TemporaryDirectory(prefix="ee-auto-preset-upd-") as tmpd:
            tmp_path = Path(tmpd)
            archive_path = tmp_path / "release.tar.gz"
            req = urllib.request.Request(
                tarball_url,
                headers={"User-Agent": f"EasyEffectsAutoPreset/{APP_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                archive_path.write_bytes(resp.read())

            untar = subprocess.run(
                ["tar", "-xzf", str(archive_path), "-C", str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if untar.returncode != 0:
                return {"ok": False, "message": f"Failed to extract update archive: {untar.stderr.strip()}"}

            local_bin = Path.home() / ".local" / "bin"
            local_bin.mkdir(parents=True, exist_ok=True)
            updated_script = False

            for child in tmp_path.iterdir():
                if child.is_dir():
                    py_src = child / "python" / "easyeffects_auto_preset.py"
                    if py_src.is_file():
                        dest_py = local_bin / "easyeffects-auto-preset"
                        shutil.copy2(py_src, dest_py)
                        dest_py.chmod(0o755)
                        updated_script = True
                    rust_src = child / "easyeffects-auto-preset"
                    if rust_src.is_file():
                        dest_rust = local_bin / "easyeffects-auto-preset-daemon"
                        shutil.copy2(rust_src, dest_rust)
                        dest_rust.chmod(0o755)

            if not updated_script:
                return {"ok": False, "message": "Extracted archive did not contain python/easyeffects_auto_preset.py"}

        return {
            "ok": True,
            "updated": True,
            "latest_version": latest_version,
            "message": f"Updated ~/.local/bin/easyeffects-auto-preset to {latest_version}.",
        }
    except Exception as exc:
        return {"ok": False, "message": f"Update installation failed: {exc}"}


class UpdateCheckWorker(QThread):
    """Background worker thread for non-blocking GitHub Release update checks."""

    result_ready = pyqtSignal(dict, bool)  # (result_dict, manual_trigger)

    def __init__(self, manual: bool = False, parent: QObject | None = None):
        super().__init__(parent)
        self.manual = manual

    def run(self):
        result = check_for_updates(APP_VERSION)
        self.result_ready.emit(result, self.manual)


class UpdateInstallWorker(QThread):
    """Background worker thread for downloading and installing an update from GitHub Releases."""

    install_finished = pyqtSignal(dict)

    def __init__(
        self,
        tarball_url: str = "",
        flatpak_url: str = "",
        latest_version: str = "",
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.tarball_url = tarball_url
        self.flatpak_url = flatpak_url
        self.latest_version = latest_version

    def run(self):
        res = install_update_from_github(
            tarball_url=self.tarball_url,
            flatpak_url=self.flatpak_url,
            latest_version=self.latest_version,
        )
        self.install_finished.emit(res)


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.is_file():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
                cfg.update(loaded)
        except Exception as e:
            print(f"Error loading config: {e}", file=sys.stderr)
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}", file=sys.stderr)


def get_easyeffects_cmd() -> list[str]:
    """Find the best command to invoke EasyEffects CLI."""
    if shutil.which("easyeffects"):
        return ["easyeffects"]
    return ["flatpak", "run", "--command=easyeffects", "com.github.wwmm.easyeffects"]


def is_service_enabled() -> bool:
    try:
        res = subprocess.run(["systemctl", "--user", "is-enabled", "easyeffects-auto-preset.service"], capture_output=True, text=True)
        return res.stdout.strip() == "enabled"
    except Exception:
        return False


def set_service_enabled(enable: bool) -> None:
    try:
        action = "enable" if enable else "disable"
        subprocess.run(["systemctl", "--user", action, "easyeffects-auto-preset.service"], check=False)
    except Exception:
        pass


def list_available_presets() -> tuple[list[str], list[str]]:
    """Retrieve output and input presets from EasyEffects."""
    cmd = get_easyeffects_cmd() + ["-p"]
    out_presets: list[str] = []
    in_presets: list[str] = []
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        current_section = None
        for line in res.stdout.splitlines():
            line_str = line.strip()
            if "Output presets:" in line_str:
                current_section = "output"
                continue
            elif "Input presets:" in line_str:
                current_section = "input"
                continue

            if current_section and line_str and not line_str.startswith("No "):
                parts = re.split(r"^\d+[\s\t]+", line_str)
                name = parts[-1].strip() if len(parts) > 1 else line_str
                if name:
                    if current_section == "output":
                        out_presets.append(name)
                    elif current_section == "input":
                        in_presets.append(name)
    except Exception as e:
        print(f"Error listing presets: {e}", file=sys.stderr)

    # Also scan known EasyEffects preset directories on disk so newly installed files appear immediately
    for base_dir in get_easyeffects_target_preset_dirs():
        data_out = base_dir / "output"
        if data_out.is_dir():
            for p in data_out.glob("*.json"):
                if p.stem not in out_presets:
                    out_presets.append(p.stem)
        data_in = base_dir / "input"
        if data_in.is_dir():
            for p in data_in.glob("*.json"):
                if p.stem not in in_presets:
                    in_presets.append(p.stem)

    return sorted(out_presets), sorted(in_presets)


def get_current_loaded_preset() -> str:
    """Return the currently loaded output preset name."""
    cmd = get_easyeffects_cmd() + ["-s"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
        for line in res.stdout.splitlines():
            if line.startswith("output:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def apply_preset(output_preset: str, input_preset: str | None = None) -> bool:
    """Apply an output (and optionally input) preset in EasyEffects."""
    cmd_base = get_easyeffects_cmd()
    success = True
    if output_preset:
        try:
            res = subprocess.run(cmd_base + ["-l", output_preset], capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                success = False
        except Exception as e:
            print(f"Failed applying output preset {output_preset}: {e}", file=sys.stderr)
            success = False

    if input_preset:
        try:
            subprocess.run(cmd_base + ["--load-preset", input_preset], capture_output=True, text=True, timeout=5)
        except Exception:
            pass

    return success


def parse_pactl_blocks(raw_output: str, block_prefix: str) -> list[dict[str, str]]:
    """Parse block format of pactl list into list of dicts."""
    blocks = []
    current = None
    for line in raw_output.splitlines():
        if line.startswith(block_prefix):
            if current is not None:
                blocks.append(current)
            current = {"id": line.split("#")[-1].strip()}
        elif current is not None:
            stripped = line.strip()
            if "=" in stripped and "Properties:" not in stripped:
                k, v = stripped.split("=", 1)
                current[k.strip()] = v.strip().strip('"')
            elif ":" in stripped:
                k, v = stripped.split(":", 1)
                current[k.strip()] = v.strip().strip('"')
    if current is not None:
        blocks.append(current)
    return blocks


def pause_active_media_players() -> list[str]:
    """Pause any currently playing MPRIS2 media applications (browsers, Spotify, VLC, mpv, Elisa, etc.).

    Skips any MPRIS service whose name or metadata matches a live voice meeting tab/app.
    Returns a list of paused player names/titles.
    """
    paused: list[str] = []
    services: list[str] = []

    if shutil.which("busctl"):
        try:
            res = subprocess.run(
                ["busctl", "--user", "list", "--no-legend"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in res.stdout.splitlines():
                parts = line.split()
                if parts and parts[0].startswith("org.mpris.MediaPlayer2."):
                    services.append(parts[0])
        except Exception:
            pass
    elif shutil.which("qdbus6"):
        try:
            res = subprocess.run(["qdbus6"], capture_output=True, text=True, timeout=3)
            for line in res.stdout.splitlines():
                s = line.strip()
                if s.startswith("org.mpris.MediaPlayer2."):
                    services.append(s)
        except Exception:
            pass

    for svc in services:
        svc_lower = svc.lower()
        if any(m in svc_lower for m in ("zoom", "teams", "slack", "discord", "webex", "skype")):
            continue

        try:
            st_res = subprocess.run(
                [
                    "busctl",
                    "--user",
                    "get-property",
                    svc,
                    "/org/mpris/MediaPlayer2",
                    "org.mpris.MediaPlayer2.Player",
                    "PlaybackStatus",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if '"Playing"' not in st_res.stdout:
                continue

            meta_res = subprocess.run(
                [
                    "busctl",
                    "--user",
                    "get-property",
                    svc,
                    "/org/mpris/MediaPlayer2",
                    "org.mpris.MediaPlayer2.Player",
                    "Metadata",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            meta_lower = meta_res.stdout.lower()
            if any(kw in meta_lower for kw in MEETING_KEYWORDS):
                continue

            # Send MPRIS2 Pause command
            pause_res = subprocess.run(
                [
                    "busctl",
                    "--user",
                    "call",
                    svc,
                    "/org/mpris/MediaPlayer2",
                    "org.mpris.MediaPlayer2.Player",
                    "Pause",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if pause_res.returncode != 0 and shutil.which("dbus-send"):
                subprocess.run(
                    [
                        "dbus-send",
                        "--session",
                        "--type=method_call",
                        f"--dest={svc}",
                        "/org/mpris/MediaPlayer2",
                        "org.mpris.MediaPlayer2.Player.Pause",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )

            player_short = svc.replace("org.mpris.MediaPlayer2.", "").split(".")[0]
            paused.append(player_short)
        except Exception as e:
            print(f"Error pausing MPRIS service {svc}: {e}", file=sys.stderr)

    return paused


# ==============================================================================
# Dialogs: Bundled Presets Installer & System Dependency Checker
# ==============================================================================

class BundledPresetsDialog(QDialog):
    """Interactive dialog to view and install/restore bundled EasyEffects presets."""

    def __init__(self, parent: QWidget | None = None, first_launch: bool = False):
        super().__init__(parent)
        self.first_launch = first_launch
        self.installed_any = False
        self.setWindowTitle(
            "Welcome — Install Bundled EasyEffects Presets"
            if first_launch
            else "Install / Restore Bundled EasyEffects Presets"
        )
        self.resize(720, 520)
        self._init_ui()
        self._refresh_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        if self.first_launch:
            intro = QLabel(
                "<b>Welcome to EasyEffects Auto Preset!</b><br>"
                "This application includes <b>8 custom-tuned EasyEffects presets</b> for Voice Meetings "
                "(with vocal depth, mic-thump filtering, loud/soft voice leveling, and neural anti-breathing suppression) "
                "plus Media/YouTube playback.<br><br>"
                "Would you like to install these presets into EasyEffects now? "
                "<i>(You can also install or restore them anytime later from Settings or the System Tray menu.)</i>"
            )
        else:
            intro = QLabel(
                "<b>Bundled EasyEffects Presets</b><br>"
                "Install missing presets or restore all bundled presets to their factory defaults in EasyEffects:"
            )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        targets_str = ", ".join(str(p) for p in get_easyeffects_target_preset_dirs())
        lbl_dirs = QLabel(f"<span style='color: gray; font-size: 11px;'>Target directory: <code>{targets_str}</code></span>")
        lbl_dirs.setWordWrap(True)
        layout.addWidget(lbl_dirs)

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Preset Name", "Channel", "Status", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_install_missing = QPushButton("📥 Install Missing Presets", self)
        self.btn_install_missing.setStyleSheet("padding: 8px 14px; font-weight: bold;")
        self.btn_install_missing.clicked.connect(lambda: self._run_install(overwrite=False))
        btn_row.addWidget(self.btn_install_missing)

        self.btn_install_all = QPushButton("📦 Install / Update All Bundled Presets", self)
        self.btn_install_all.setStyleSheet(
            "background-color: #2e7d32; color: white; padding: 8px 16px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_install_all.clicked.connect(lambda: self._run_install(overwrite=True))
        btn_row.addWidget(self.btn_install_all)

        btn_row.addStretch()

        self.btn_close = QPushButton("Skip for Now" if self.first_launch else "Close", self)
        self.btn_close.setStyleSheet("padding: 8px 14px;")
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)

        layout.addLayout(btn_row)

    def _refresh_table(self):
        status = get_bundled_preset_status()
        self.table.setRowCount(len(BUNDLED_PRESET_DESCRIPTIONS))
        for row, (name, (channel, desc)) in enumerate(BUNDLED_PRESET_DESCRIPTIONS.items()):
            is_inst = status.get(name, False)
            name_item = QTableWidgetItem(name)
            font = name_item.font()
            font.setBold(True)
            name_item.setFont(font)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(channel))

            st_item = QTableWidgetItem("✅ Installed" if is_inst else "⚠️ Not Installed")
            st_item.setForeground(QColor("#2e7d32") if is_inst else QColor("#f57c00"))
            self.table.setItem(row, 2, st_item)

            desc_item = QTableWidgetItem(desc)
            desc_item.setToolTip(desc)
            self.table.setItem(row, 3, desc_item)

        self.table.resizeRowsToContents()

    def _run_install(self, overwrite: bool):
        count, names, targets = install_bundled_presets(overwrite=overwrite)
        self.installed_any = True
        self._refresh_table()
        self.btn_close.setText("Done")
        if count > 0:
            QMessageBox.information(
                self,
                "Bundled Presets Installed",
                f"Successfully installed {count} preset(s) into EasyEffects:\n\n"
                + "\n".join(f"  • {n}" for n in names)
                + "\n\nTarget directory:\n"
                + "\n".join(f"  {t}" for t in targets),
            )
        else:
            QMessageBox.information(
                self,
                "All Presets Already Installed",
                "All bundled presets are already installed in EasyEffects.\n\n"
                "Click 'Install / Update All Bundled Presets' if you want to overwrite them with factory defaults.",
            )


class SystemDependenciesDialog(QDialog):
    """Dialog showing EasyEffects and required package status, fix commands, and one-click install."""

    def __init__(self, parent: QWidget | None = None, startup_warning: bool = False):
        super().__init__(parent)
        self.startup_warning = startup_warning
        self.setWindowTitle(
            "Missing Required Packages — EasyEffects Auto Preset"
            if startup_warning
            else "System & Dependency Check — EasyEffects Auto Preset"
        )
        self.resize(760, 560)
        self._init_ui()
        self.refresh_status()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.lbl_header = QLabel(self)
        self.lbl_header.setWordWrap(True)
        layout.addWidget(self.lbl_header)

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Component", "Requirement", "Status", "Purpose"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        grp_fix = QGroupBox("How to Fix / Install Missing Packages", self)
        fix_layout = QVBoxLayout(grp_fix)
        self.lbl_fix_hint = QLabel("Run the following command(s) for your Linux distribution, or click <b>Install Missing Packages</b> below:")
        self.lbl_fix_hint.setWordWrap(True)
        fix_layout.addWidget(self.lbl_fix_hint)

        self.txt_commands = QTextEdit(grp_fix)
        self.txt_commands.setReadOnly(True)
        self.txt_commands.setMaximumHeight(110)
        self.txt_commands.setStyleSheet("font-family: monospace; font-size: 12px;")
        fix_layout.addWidget(self.txt_commands)

        action_row = QHBoxLayout()
        self.btn_copy_cmd = QPushButton("📋 Copy Command", grp_fix)
        self.btn_copy_cmd.clicked.connect(self._copy_commands)
        action_row.addWidget(self.btn_copy_cmd)

        self.btn_install_sys = QPushButton("🔧 Install Missing System Packages...", grp_fix)
        self.btn_install_sys.setStyleSheet(
            "background-color: #1565c0; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;"
        )
        self.btn_install_sys.clicked.connect(self._install_missing_system)
        action_row.addWidget(self.btn_install_sys)

        self.btn_install_flatpak = QPushButton("📦 Install EasyEffects (Flatpak)...", grp_fix)
        self.btn_install_flatpak.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;"
        )
        self.btn_install_flatpak.clicked.connect(self._install_easyeffects_flatpak)
        action_row.addWidget(self.btn_install_flatpak)

        action_row.addStretch()
        fix_layout.addLayout(action_row)
        layout.addWidget(grp_fix)

        bottom_row = QHBoxLayout()
        self.btn_recheck = QPushButton("🔄 Re-Check System", self)
        self.btn_recheck.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_recheck.clicked.connect(self.refresh_status)
        bottom_row.addWidget(self.btn_recheck)

        bottom_row.addStretch()
        btn_close = QPushButton("Close", self)
        btn_close.setStyleSheet("padding: 6px 16px;")
        btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(btn_close)
        layout.addLayout(bottom_row)

    def refresh_status(self):
        self._report = check_system_dependencies()
        distro_name = self._report["distro"].get("name", "Linux")
        pkg_mgr = self._report["distro"].get("pkg_mgr", "unknown")

        if self._report["all_required_ok"] and self._report["all_recommended_ok"]:
            self.lbl_header.setText(
                f"<b>✅ All Required &amp; Recommended Packages Are Installed!</b><br>"
                f"Detected System: <b>{distro_name}</b> (package manager: <code>{pkg_mgr}</code>)"
            )
        elif self._report["all_required_ok"]:
            self.lbl_header.setText(
                f"<b>⚠️ Core Requirements Met — Optional DSP Packages Missing</b><br>"
                f"Detected System: <b>{distro_name}</b> (package manager: <code>{pkg_mgr}</code>). "
                "See below for recommended audio plugin packages."
            )
        else:
            self.lbl_header.setText(
                f"<b style='color: #d32f2f;'>❌ Missing Required Packages Detected!</b><br>"
                f"Detected System: <b>{distro_name}</b> (package manager: <code>{pkg_mgr}</code>). "
                "EasyEffects Auto Preset requires <b>EasyEffects</b> and <b>pactl</b> to switch presets automatically."
            )

        items = self._report["items"]
        self.table.setRowCount(len(items))
        for row, it in enumerate(items):
            name_item = QTableWidgetItem(it["name"])
            font = name_item.font()
            font.setBold(True)
            name_item.setFont(font)
            self.table.setItem(row, 0, name_item)

            req_item = QTableWidgetItem("Required" if it["required"] else "Recommended")
            self.table.setItem(row, 1, req_item)

            st_text = f"✅ {it['status_text']}" if it["installed"] else f"❌ {it['status_text']}"
            st_item = QTableWidgetItem(st_text)
            st_item.setForeground(QColor("#2e7d32") if it["installed"] else QColor("#d32f2f"))
            self.table.setItem(row, 2, st_item)

            desc_item = QTableWidgetItem(it["description"])
            desc_item.setToolTip(it["description"])
            self.table.setItem(row, 3, desc_item)

        self.table.resizeRowsToContents()

        cmds = self._report["combined_fix_commands"]
        if cmds:
            cmd_block = "\n".join(cmds)
            if not any(i["installed"] for i in items if i["id"] == "easyeffects") and shutil.which("flatpak"):
                cmd_block += "\n\n# Or install EasyEffects via Flatpak (includes all LV2/RNNoise plugins):\nflatpak install -y flathub com.github.wwmm.easyeffects"
            self.txt_commands.setPlainText(cmd_block)
            self.btn_install_sys.setEnabled(True)
        else:
            # Show reference install commands even when everything is installed
            ref_cmds = "\n".join(dict.fromkeys(it["install_pkg_cmd"] for it in items if it["install_pkg_cmd"]))
            self.txt_commands.setPlainText(
                f"# All packages are currently installed!\n# Reference command for {distro_name}:\n{ref_cmds}"
            )
            self.btn_install_sys.setEnabled(False)

        ee_item = next((i for i in items if i["id"] == "easyeffects"), None)
        self.btn_install_flatpak.setVisible(bool(shutil.which("flatpak")) and (not ee_item or not ee_item["installed"]))

    def _copy_commands(self):
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.txt_commands.toPlainText())
            QMessageBox.information(self, "Copied", "Installation command(s) copied to clipboard.")

    def _install_missing_system(self):
        cmds = self._report.get("combined_fix_commands", [])
        if not cmds:
            return
        full_cmd = " && ".join(cmds)
        ans = QMessageBox.question(
            self,
            "Install Missing Packages",
            f"Launch terminal to install missing system packages?\n\nCommand:\n{full_cmd}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            launch_package_installation(full_cmd, parent=self)

    def _install_easyeffects_flatpak(self):
        cmd = "flatpak install -y flathub com.github.wwmm.easyeffects"
        ans = QMessageBox.question(
            self,
            "Install EasyEffects via Flatpak",
            f"Install EasyEffects from Flathub?\n\nCommand:\n{cmd}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            launch_package_installation(cmd, parent=self)


# ==============================================================================
# Background Audio Stream Monitor
# ==============================================================================

class AudioMonitorWorker(QObject):
    """Monitors PipeWire/PulseAudio sink-inputs and source-outputs."""

    state_changed = pyqtSignal(str, str, list)  # (mode, active_preset, active_streams_list)
    preset_switched = pyqtSignal(str, str)     # (new_preset, reason)
    media_paused = pyqtSignal(list)            # (list of paused media player names)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self._running = True
        self.current_mode = "unknown"  # "meeting", "youtube", "default"
        self.last_preset = ""
        self._meeting_lost_at = 0.0
        self._youtube_lost_at = 0.0

    def update_config(self, new_config: dict):
        self.config = new_config

    def stop(self):
        self._running = False

    def scan_streams(self) -> tuple[bool, bool, list[dict], str, str]:
        """Inspect sink-inputs and source-outputs to determine meeting/youtube status."""
        meeting_active = False
        youtube_playing = False
        meeting_details = ""
        youtube_details = ""
        stream_items: list[dict] = []

        # 1. Inspect source outputs (Microphone recording)
        try:
            src_res = subprocess.run(["pactl", "list", "source-outputs"], capture_output=True, text=True, timeout=3)
            source_blocks = parse_pactl_blocks(src_res.stdout, "Source Output #")
        except Exception:
            source_blocks = []

        for sc in source_blocks:
            app = sc.get("application.name", "Unknown App")
            binary = sc.get("application.process.binary", "").lower()
            media = sc.get("media.name", "")
            if "speech-dispatcher" in binary or "sd_dummy" in binary:
                continue

            stream_items.append({
                "type": "Microphone (Input)",
                "app": app,
                "media": media,
                "state": "Recording",
                "trigger": "Meeting",
            })

            if self.config.get("detect_microphone", True):
                meeting_active = True
                meeting_details = f"Microphone active: {app} ({media or binary})"

        # 2. Inspect sink inputs (Playback)
        try:
            sink_res = subprocess.run(["pactl", "list", "sink-inputs"], capture_output=True, text=True, timeout=3)
            sink_blocks = parse_pactl_blocks(sink_res.stdout, "Sink Input #")
        except Exception:
            sink_blocks = []

        for sk in sink_blocks:
            corked = sk.get("Corked", sk.get("pulse.corked", "yes")).lower()
            is_playing = (corked == "no" or corked == "false")
            app = sk.get("application.name", "")
            binary = sk.get("application.process.binary", "").lower()
            media = sk.get("media.name", "")
            role = sk.get("media.role", "").lower()

            if "speech-dispatcher" in binary or "sd_dummy" in binary:
                continue

            item_trigger = "None"
            is_sk_meeting = False

            # Check meeting conditions
            if self.config.get("detect_meeting_apps", True) and binary in KNOWN_MEETING_BINARIES:
                is_sk_meeting = True
                item_trigger = "Meeting App"
            elif self.config.get("detect_communication_role", True) and role in ("communication", "phone"):
                is_sk_meeting = True
                item_trigger = "Communication Stream"
            else:
                for kw in MEETING_KEYWORDS:
                    if kw in media.lower() or kw in app.lower():
                        is_sk_meeting = True
                        item_trigger = f"Meeting ({kw})"
                        break

            if is_sk_meeting:
                meeting_active = True
                meeting_details = f"Meeting app: {app} ({media})"

            # Check YouTube, music, movie, and video playback (only when actively playing sound)
            if not is_sk_meeting and is_playing:
                matched_media, trig_label, media_detail = detect_media_playback_stream(sk, self.config)
                if matched_media:
                    item_trigger = trig_label
                    youtube_playing = True
                    youtube_details = media_detail

            stream_items.append({
                "type": "Audio Playback",
                "app": app or binary or "Unknown",
                "media": media,
                "state": "Playing" if is_playing else "Paused",
                "trigger": item_trigger,
            })

        return meeting_active, youtube_playing, stream_items, meeting_details, youtube_details

    def run_loop(self):
        """Continuously evaluate audio state with debouncing."""
        self.last_preset = get_current_loaded_preset()

        while self._running:
            if not self.config.get("enabled", True):
                time.sleep(1.0)
                continue

            try:
                meeting_active, youtube_playing, stream_items, meet_info, yt_info = self.scan_streams()
                now = time.time()
                debounce = float(self.config.get("debounce_seconds", 2.0))

                target_mode = "default"
                reason = "Idle / Default"

                # Priority: Meeting > YouTube > Default
                if meeting_active:
                    target_mode = "meeting"
                    reason = meet_info or "Voice Meeting Active"
                    self._meeting_lost_at = 0.0
                    if self.config.get("pause_media_in_meetings", True):
                        paused_players = pause_active_media_players()
                        if paused_players:
                            print(f"Paused media application(s) during meeting: {', '.join(paused_players)}")
                            self.media_paused.emit(paused_players)
                else:
                    if self.current_mode == "meeting":
                        if self._meeting_lost_at == 0.0:
                            self._meeting_lost_at = now
                        if (now - self._meeting_lost_at) < debounce:
                            target_mode = "meeting"
                            reason = "Meeting (Grace period)"

                if target_mode != "meeting":
                    if youtube_playing:
                        target_mode = "youtube"
                        reason = yt_info or "YouTube Playback"
                        self._youtube_lost_at = 0.0
                    else:
                        if self.current_mode == "youtube":
                            if self._youtube_lost_at == 0.0:
                                self._youtube_lost_at = now
                            if (now - self._youtube_lost_at) < debounce:
                                target_mode = "youtube"
                                reason = "YouTube (Grace period)"

                # Determine target preset based on mode
                if target_mode == "meeting":
                    target_preset = self.config.get("meeting_preset", "Compressed-Max")
                    target_mic = self.config.get("meeting_mic_preset", "") if self.config.get("apply_mic_preset", False) else None
                elif target_mode == "youtube":
                    target_preset = self.config.get("youtube_preset", "Crystal more Bass")
                    target_mic = None
                else:
                    target_preset = self.config.get("default_preset", "Crystal more Bass")
                    target_mic = None

                # Check if we need to switch preset
                if target_mode != self.current_mode or (target_preset and target_preset != self.last_preset):
                    if target_preset:
                        print(f"Auto-switching preset: {target_preset} (Mode: {target_mode}, Reason: {reason})")
                        applied = apply_preset(target_preset, target_mic)
                        if applied:
                            self.last_preset = target_preset
                            self.current_mode = target_mode
                            self.preset_switched.emit(target_preset, reason)

                self.current_mode = target_mode
                self.state_changed.emit(target_mode, self.last_preset, stream_items)

            except Exception as e:
                print(f"Monitor error: {e}", file=sys.stderr)

            interval = float(self.config.get("check_interval_seconds", 1.0))
            time.sleep(max(0.5, interval))


# ==============================================================================
# Main Settings Window
# ==============================================================================

class MainWindow(QMainWindow):
    """Main Settings Window for EasyEffects Auto Preset."""

    presets_updated = pyqtSignal()
    settings_saved = pyqtSignal()

    def __init__(self, config: dict, worker: AudioMonitorWorker):
        super().__init__()
        self.config = config
        self.worker = worker
        self._output_presets: list[str] = []
        self._input_presets: list[str] = []
        self._first_minimize_tip_shown = False
        self._loading_ui = False
        self._latest_release_url = GITHUB_RELEASES_PAGE_URL
        self._latest_tarball_url = ""
        self._latest_flatpak_url = ""
        self._latest_version_tag = ""
        self._last_notified_update_version = ""

        self.setWindowTitle(f"EasyEffects Auto Preset Manager v{APP_VERSION}")
        self.resize(840, 740)
        self.setWindowIcon(QIcon(str(APP_ICON_FILE)) if APP_ICON_FILE.is_file() else build_tray_icon())

        self._init_ui()
        self._populate_presets()
        self._load_config_to_ui()
        self._connect_change_trackers()

        # Connect worker signals
        self.worker.state_changed.connect(self._on_state_changed)
        self.worker.preset_switched.connect(self._on_preset_switched)

        # Periodic 6-hour background update check timer
        self._periodic_update_timer = QTimer(self)
        self._periodic_update_timer.setInterval(6 * 60 * 60 * 1000)
        self._periodic_update_timer.timeout.connect(self._on_periodic_update_timer)
        self._periodic_update_timer.start()

    def _init_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header status banner
        self.banner = QFrame(self)
        self.banner.setFrameShape(QFrame.Shape.StyledPanel)
        self.banner.setStyleSheet(
            "QFrame { background-color: palette(alternate-base); border-radius: 8px; padding: 12px; }"
        )
        banner_layout = QHBoxLayout(self.banner)

        self.icon_label = QLabel(self)
        self.icon_label.setPixmap(
            _render_tray_pixmap(mode="default", enabled=self.config.get("enabled", True), size=48)
        )
        banner_layout.addWidget(self.icon_label)

        banner_text_layout = QVBoxLayout()
        self.status_title = QLabel(
            f"<b>EasyEffects Auto Preset</b> &nbsp;<span style='color: #38bdf8; font-size: 12px; font-weight: bold;'>v{APP_VERSION}</span>",
            self,
        )
        self.status_title.setStyleSheet("font-size: 15px;")
        self.status_detail = QLabel("Monitoring audio streams...", self)
        self.status_detail.setStyleSheet("color: palette(link); font-weight: bold;")
        banner_text_layout.addWidget(self.status_title)
        banner_text_layout.addWidget(self.status_detail)
        banner_layout.addLayout(banner_text_layout)
        banner_layout.addStretch()

        self.btn_toggle_enable = QPushButton("Auto-Switching: Active", self)
        self.btn_toggle_enable.setCheckable(True)
        self.btn_toggle_enable.setChecked(True)
        self.btn_toggle_enable.setStyleSheet("padding: 8px 16px; font-weight: bold;")
        self.btn_toggle_enable.toggled.connect(self._on_enable_toggled)
        banner_layout.addWidget(self.btn_toggle_enable)

        main_layout.addWidget(self.banner)

        # Missing dependency warning banner (shown automatically if EasyEffects or pactl is missing)
        self.dep_banner = QFrame(self)
        self.dep_banner.setFrameShape(QFrame.Shape.StyledPanel)
        self.dep_banner.setStyleSheet(
            "QFrame { background-color: #b71c1c; color: white; border-radius: 6px; padding: 8px 12px; }"
        )
        dep_banner_layout = QHBoxLayout(self.dep_banner)
        dep_banner_layout.setContentsMargins(8, 4, 8, 4)
        self.lbl_dep_banner = QLabel(
            "⚠️ Required packages (EasyEffects / pactl) are missing on this system!",
            self.dep_banner,
        )
        self.lbl_dep_banner.setStyleSheet("color: white; font-weight: bold;")
        self.btn_fix_deps = QPushButton("Fix / Install Missing Packages...", self.dep_banner)
        self.btn_fix_deps.setStyleSheet(
            "background-color: #ffffff; color: #b71c1c; font-weight: bold; border-radius: 4px; padding: 4px 12px;"
        )
        self.btn_fix_deps.clicked.connect(self.open_dependency_dialog)
        dep_banner_layout.addWidget(self.lbl_dep_banner)
        dep_banner_layout.addStretch()
        dep_banner_layout.addWidget(self.btn_fix_deps)
        self.dep_banner.setVisible(False)
        main_layout.addWidget(self.dep_banner)

        # Update available notification bar (hidden unless an update is found)
        self.update_banner = QFrame(self)
        self.update_banner.setFrameShape(QFrame.Shape.StyledPanel)
        self.update_banner.setStyleSheet(
            "QFrame { background-color: #0d47a1; color: white; border-radius: 6px; padding: 8px 12px; }"
        )
        update_banner_layout = QHBoxLayout(self.update_banner)
        update_banner_layout.setContentsMargins(8, 4, 8, 4)
        self.lbl_update_banner = QLabel("A new version of EasyEffects Auto Preset is available!", self.update_banner)
        self.lbl_update_banner.setStyleSheet("color: white; font-weight: bold;")
        self.btn_install_update = QPushButton("⬇ Install Update", self.update_banner)
        self.btn_install_update.setStyleSheet(
            "background-color: #16a34a; color: #ffffff; font-weight: bold; border-radius: 4px; padding: 4px 12px;"
        )
        self.btn_install_update.clicked.connect(self.trigger_install_update)
        self.btn_open_release = QPushButton("Release Notes", self.update_banner)
        self.btn_open_release.setStyleSheet(
            "background-color: #ffffff; color: #0d47a1; font-weight: bold; border-radius: 4px; padding: 4px 12px;"
        )
        self.btn_open_release.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._latest_release_url)))
        update_banner_layout.addWidget(self.lbl_update_banner)
        update_banner_layout.addStretch()
        update_banner_layout.addWidget(self.btn_install_update)
        update_banner_layout.addWidget(self.btn_open_release)
        self.update_banner.setVisible(False)
        main_layout.addWidget(self.update_banner)

        # Tab widget
        self.tabs = QTabWidget(self)

        # ----------------------------------------------------------------------
        # Tab 1: Presets & Triggers (wrapped in QScrollArea so nothing clips)
        # ----------------------------------------------------------------------
        scroll_presets = QScrollArea(self.tabs)
        scroll_presets.setWidgetResizable(True)
        scroll_presets.setFrameShape(QFrame.Shape.NoFrame)
        tab_presets = QWidget(scroll_presets)
        layout_presets = QVBoxLayout(tab_presets)
        layout_presets.setSpacing(14)

        grp_mapping = QGroupBox("Preset Triggers && Rules", tab_presets)
        grid = QGridLayout(grp_mapping)
        grid.setSpacing(12)

        grid.addWidget(QLabel("<b>YouTube / Music / Movie / Video Preset:</b>"), 0, 0)
        self.combo_youtube = QComboBox(grp_mapping)
        grid.addWidget(self.combo_youtube, 0, 1)

        self.btn_test_yt = QPushButton("Test", grp_mapping)
        self.btn_test_yt.clicked.connect(lambda: apply_preset(self.combo_youtube.currentText()))
        grid.addWidget(self.btn_test_yt, 0, 2)

        grid.addWidget(QLabel("<b>Voice Meeting Output Preset:</b>"), 1, 0)
        self.combo_meeting = QComboBox(grp_mapping)
        grid.addWidget(self.combo_meeting, 1, 1)

        self.btn_test_meet = QPushButton("Test", grp_mapping)
        self.btn_test_meet.clicked.connect(lambda: apply_preset(self.combo_meeting.currentText()))
        grid.addWidget(self.btn_test_meet, 1, 2)

        grid.addWidget(QLabel("<b>Default / Idle Preset:</b>"), 2, 0)
        self.combo_default = QComboBox(grp_mapping)
        grid.addWidget(self.combo_default, 2, 1)

        self.btn_test_def = QPushButton("Test", grp_mapping)
        self.btn_test_def.clicked.connect(lambda: apply_preset(self.combo_default.currentText()))
        grid.addWidget(self.btn_test_def, 2, 2)

        # Optional Mic preset
        self.chk_mic_preset = QCheckBox("Also apply input (mic) preset in meetings:", grp_mapping)
        grid.addWidget(self.chk_mic_preset, 3, 0)
        self.combo_mic = QComboBox(grp_mapping)
        grid.addWidget(self.combo_mic, 3, 1)

        # Quick Bundled Presets & Refresh bar inside Preset Triggers group
        preset_tools_row = QHBoxLayout()
        self.btn_install_presets_tab1 = QPushButton("📦 Install / Restore Bundled Presets...", grp_mapping)
        self.btn_install_presets_tab1.setToolTip(
            "Install or restore the 8 bundled Meeting-Voice and Media presets into EasyEffects"
        )
        self.btn_install_presets_tab1.clicked.connect(lambda: self.open_bundled_presets_dialog(first_launch=False))
        preset_tools_row.addWidget(self.btn_install_presets_tab1)

        self.btn_refresh_presets = QPushButton("🔄 Refresh Preset List", grp_mapping)
        self.btn_refresh_presets.clicked.connect(self._on_refresh_presets_clicked)
        preset_tools_row.addWidget(self.btn_refresh_presets)
        preset_tools_row.addStretch()
        grid.addLayout(preset_tools_row, 4, 0, 1, 3)

        layout_presets.addWidget(grp_mapping)

        # Detection toggles group
        grp_detect = QGroupBox("Detection Rules", tab_presets)
        vbox_detect = QVBoxLayout(grp_detect)

        self.chk_detect_mic = QCheckBox(
            "Detect active microphone (Google Meet, Zoom, Teams, Slack, Discord)", grp_detect
        )
        self.chk_detect_comm = QCheckBox(
            "Detect communication audio streams (media.role = phone/communication)", grp_detect
        )
        self.chk_detect_yt = QCheckBox(
            "Detect YouTube, music, movie && video playback (browsers, Spotify, VLC, mpv, Plex, Kodi, etc.)",
            grp_detect,
        )
        self.chk_pause_media = QCheckBox(
            "Pause media applications when in a meeting (ensure media remains paused during calls)",
            grp_detect,
        )

        vbox_detect.addWidget(self.chk_detect_mic)
        vbox_detect.addWidget(self.chk_detect_comm)
        vbox_detect.addWidget(self.chk_detect_yt)
        vbox_detect.addWidget(self.chk_pause_media)
        layout_presets.addWidget(grp_detect)

        # Timing group
        grp_timing = QGroupBox("Switching Behavior", tab_presets)
        timing_layout = QHBoxLayout(grp_timing)
        timing_layout.addWidget(QLabel("Debounce Delay (Grace Period):"))
        self.spin_debounce = QDoubleSpinBox(grp_timing)
        self.spin_debounce.setRange(0.5, 10.0)
        self.spin_debounce.setSingleStep(0.5)
        self.spin_debounce.setSuffix(" sec")
        timing_layout.addWidget(self.spin_debounce)
        timing_layout.addSpacing(20)

        self.chk_notify = QCheckBox("Show desktop notification on preset change", grp_timing)
        timing_layout.addWidget(self.chk_notify)
        timing_layout.addStretch()
        layout_presets.addWidget(grp_timing)

        layout_presets.addStretch()
        scroll_presets.setWidget(tab_presets)
        self.tabs.addTab(scroll_presets, "Preset Triggers")

        # ----------------------------------------------------------------------
        # Tab 2: Live Stream Monitor
        # ----------------------------------------------------------------------
        tab_streams = QWidget()
        layout_streams = QVBoxLayout(tab_streams)

        lbl_streams_info = QLabel("Real-time PipeWire / PulseAudio streams evaluated by the monitor:")
        layout_streams.addWidget(lbl_streams_info)

        self.table_streams = QTableWidget(tab_streams)
        self.table_streams.setColumnCount(5)
        self.table_streams.setHorizontalHeaderLabels(["Type", "Application", "Media Name", "State", "Trigger Rule"])
        self.table_streams.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_streams.horizontalHeader().setStretchLastSection(True)
        layout_streams.addWidget(self.table_streams)

        self.tabs.addTab(tab_streams, "Live Audio Streams")

        # ----------------------------------------------------------------------
        # Tab 3: Preset Details & Tools (wrapped in QScrollArea with scrollbar!)
        # ----------------------------------------------------------------------
        scroll_about = QScrollArea(self.tabs)
        scroll_about.setWidgetResizable(True)
        scroll_about.setFrameShape(QFrame.Shape.NoFrame)
        scroll_about.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_about.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        tab_about = QWidget(scroll_about)
        layout_about = QVBoxLayout(tab_about)
        layout_about.setContentsMargins(10, 10, 14, 10)
        layout_about.setSpacing(12)

        info_text = QLabel(
            "<b>How EasyEffects Auto Preset Works</b><br>"
            "Continuously inspects active PipeWire / PulseAudio streams and switches your EasyEffects "
            "preset automatically using a <b>3-tier priority engine</b> with grace-period debouncing:"
            "<ol style='margin-top:4px; margin-bottom:8px;'>"
            "<li><b>Priority 1 — Voice Meetings (Highest):</b> Active microphone recording or meeting stream "
            "(Google Meet, Zoom, Teams, Slack, Discord, Webex, or <code>media.role=phone/communication</code>).</li>"
            "<li><b>Priority 2 — YouTube, Music, Movies &amp; Video:</b> Active playback in browsers "
            "(YouTube, YouTube Music, Netflix, Disney+, Prime Video, Twitch, Plex, SoundCloud) or media apps "
            "(Spotify, VLC, mpv, Elisa, Haruna, Celluloid, Kodi, Jellyfin, Rhythmbox, etc.).</li>"
            "<li><b>Priority 3 — Default / Idle:</b> Restored after the debounce delay once media/calls end.</li>"
            "</ol>"
            "<b>Bundled EasyEffects Presets (Included with Application)</b>"
            "<ul style='margin-top:4px; margin-bottom:6px;'>"
            "<li><b>Meeting-Voice-Clear (Balanced Meeting Output):</b> Warm vocal depth (+2.0 dB @ 125Hz, +1.5 dB @ 250Hz) "
            "so voices never sound like a landline telephone, combined with a steep sub-75Hz mic-thump cut "
            "(-28 dB @ 32Hz, -14 dB @ 64Hz, 75Hz HPF) and <b>RNNoise (65% VAD) + Speex (-35 dB)</b> to filter out "
            "other participants' <i>\"breathing into the microphone\"</i>.</li>"
            "<li><b>Meeting-Voice-Clear-Max-Level (Aggressive Volume Leveler):</b> Same warm tone and breath filter as "
            "<code>Meeting-Voice-Clear</code>, plus <b>Speex AGC + 6:1 Compressor (-24 dB, +6 dB makeup) + Maximizer (+28 dB gain)</b> "
            "to pin whisper-quiet and booming-loud speakers to the exact same volume.</li>"
            "<li><b>Meeting-Voice-Deep (Broadcast Vocal Warmth):</b> Boosts low-chest vocal fundamentals "
            "(<b>+4.0 dB @ 125Hz, +3.0 dB @ 250Hz</b>, 65Hz HPF) for rich radio-style voices while still cutting sub-60Hz desk thumps.</li>"
            "<li><b>Meeting-Breath-Block-Max (Maximum Anti-Breathing):</b> <b>100% wet RNNoise with 80% VAD threshold (40ms release)</b>, "
            "Speex -50 dB denoise (96% VAD), 80Hz HPF, -38 dB gate floor, and tamed 4–16kHz aspiration hiss for heavy mic breathers.</li>"
            "<li><b>Meeting-Voice-Deep-Breath-Max (Deep Voice + Max Breath Block):</b> Combines the +4 dB / +3 dB deep vocal warmth "
            "of <code>Meeting-Voice-Deep</code> with the 80% neural VAD breath gating of <code>Meeting-Breath-Block-Max</code>.</li>"
            "<li><b>Crystal more Bass (Media / YouTube / Movies / Music):</b> Rich low-end punch and crystalline highs.</li>"
            "<li><b>Compressed-Max (Maximum Leveling):</b> High-ratio dynamic range compressor + +36 dB maximizer ceiling.</li>"
            "<li><b>Meeting-Mic-Clean (Input / Microphone):</b> Outbound microphone noise cancellation, dereverberation, and AGC.</li>"
            "</ul>"
        )
        info_text.setWordWrap(True)
        info_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout_about.addWidget(info_text)

        # Preset Installer & System Dependency Checker Card
        tools_frame = QFrame(tab_about)
        tools_frame.setStyleSheet(
            "QFrame { background-color: palette(alternate-base); border-radius: 8px; padding: 12px; }"
        )
        tools_layout = QHBoxLayout(tools_frame)
        lbl_tools = QLabel(
            "<b>Presets &amp; System Tools:</b><br>"
            "<span style='font-size: 12px;'>Install or restore the 8 bundled presets or verify required system packages.</span>",
            tools_frame,
        )
        lbl_tools.setWordWrap(True)
        self.btn_install_presets_tab3 = QPushButton("📦 Install / Restore Bundled Presets...", tools_frame)
        self.btn_install_presets_tab3.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_install_presets_tab3.clicked.connect(lambda: self.open_bundled_presets_dialog(first_launch=False))

        self.btn_check_deps = QPushButton("🩺 System && Dependency Check...", tools_frame)
        self.btn_check_deps.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_check_deps.clicked.connect(self.open_dependency_dialog)

        tools_layout.addWidget(lbl_tools, 1)
        tools_layout.addWidget(self.btn_install_presets_tab3)
        tools_layout.addWidget(self.btn_check_deps)
        layout_about.addWidget(tools_frame)

        # Updates section in Preset Details / About tab
        updates_frame = QFrame(tab_about)
        updates_frame.setStyleSheet(
            "QFrame { background-color: palette(alternate-base); border-radius: 8px; padding: 12px; }"
        )
        updates_layout = QHBoxLayout(updates_frame)
        self.lbl_version_status = QLabel(f"<b>Version:</b> v{APP_VERSION} — Ready", updates_frame)
        self.chk_updates_startup = QCheckBox("Check for updates automatically", updates_frame)
        self.chk_updates_startup.setChecked(self.config.get("check_updates_on_startup", True))
        self.btn_install_update_about = QPushButton("⬇ Install Update", updates_frame)
        self.btn_install_update_about.setStyleSheet(
            "background-color: #16a34a; color: white; font-weight: bold; border-radius: 4px; padding: 6px 14px;"
        )
        self.btn_install_update_about.setVisible(False)
        self.btn_install_update_about.clicked.connect(self.trigger_install_update)
        self.btn_check_updates = QPushButton("🔄 Check for Updates", updates_frame)
        self.btn_check_updates.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_check_updates.clicked.connect(lambda: self.trigger_update_check(manual=True))
        updates_layout.addWidget(self.lbl_version_status)
        updates_layout.addStretch()
        updates_layout.addWidget(self.chk_updates_startup)
        updates_layout.addWidget(self.btn_install_update_about)
        updates_layout.addWidget(self.btn_check_updates)
        layout_about.addWidget(updates_frame)

        # Support on Ko-fi frame
        support_frame = QFrame(tab_about)
        support_frame.setStyleSheet(
            "QFrame { background-color: palette(alternate-base); border-radius: 8px; padding: 12px; }"
        )
        support_layout = QHBoxLayout(support_frame)
        support_label = QLabel("<b>Enjoying EasyEffects Auto Preset?</b> Support development on Ko-fi:", support_frame)
        support_btn = QPushButton("☕ Buy Me a Coffee on Ko-fi", support_frame)
        support_btn.setStyleSheet(
            "background-color: #ff5e5b; color: white; font-weight: bold; border-radius: 4px; padding: 6px 14px;"
        )
        support_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://ko-fi.com/russellmilliner")))
        support_layout.addWidget(support_label)
        support_layout.addStretch()
        support_layout.addWidget(support_btn)
        layout_about.addWidget(support_frame)

        layout_about.addStretch()
        scroll_about.setWidget(tab_about)
        self.tabs.addTab(scroll_about, "Preset Details")

        main_layout.addWidget(self.tabs)

        # Bottom buttons
        btn_layout = QHBoxLayout()

        self.chk_autostart = QCheckBox("Start automatically on login (systemd user service)", self)
        self.chk_autostart.setChecked(is_service_enabled())
        self.chk_autostart.toggled.connect(self._on_autostart_toggled)
        btn_layout.addWidget(self.chk_autostart)

        btn_layout.addStretch()

        self.btn_kofi = QPushButton("☕ Buy Me a Coffee", self)
        self.btn_kofi.setStyleSheet(
            "background-color: #ff5e5b; color: white; font-weight: bold; border-radius: 4px; padding: 6px 14px;"
        )
        self.btn_kofi.setToolTip("Support project development on Ko-fi")
        self.btn_kofi.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://ko-fi.com/russellmilliner")))
        btn_layout.addWidget(self.btn_kofi)

        self.btn_save = QPushButton("Save Settings", self)
        self.btn_save.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.btn_save.clicked.connect(lambda: self._save_settings(show_popup=True))
        btn_layout.addWidget(self.btn_save)

        self.btn_hide = QPushButton("Minimize to Tray", self)
        self.btn_hide.clicked.connect(self._on_minimize_clicked)
        btn_layout.addWidget(self.btn_hide)

        main_layout.addLayout(btn_layout)
        self._refresh_dependency_banner()

    # --------------------------------------------------------------------------
    # Change Tracking & Unsaved Changes Prompt
    # --------------------------------------------------------------------------

    def _connect_change_trackers(self):
        for combo in (self.combo_youtube, self.combo_meeting, self.combo_default, self.combo_mic):
            combo.currentIndexChanged.connect(self._on_ui_modified)
        for chk in (
            self.chk_mic_preset,
            self.chk_detect_mic,
            self.chk_detect_comm,
            self.chk_detect_yt,
            self.chk_pause_media,
            self.chk_notify,
            self.chk_updates_startup,
        ):
            chk.toggled.connect(self._on_ui_modified)
        self.spin_debounce.valueChanged.connect(self._on_ui_modified)

    def _get_ui_config_state(self) -> dict:
        return {
            "youtube_preset": self.combo_youtube.currentText(),
            "meeting_preset": self.combo_meeting.currentText(),
            "default_preset": self.combo_default.currentText(),
            "meeting_mic_preset": self.combo_mic.currentText() if self.combo_mic.currentIndex() > 0 else "",
            "apply_mic_preset": self.chk_mic_preset.isChecked(),
            "detect_microphone": self.chk_detect_mic.isChecked(),
            "detect_communication_role": self.chk_detect_comm.isChecked(),
            "detect_youtube": self.chk_detect_yt.isChecked(),
            "pause_media_in_meetings": self.chk_pause_media.isChecked(),
            "show_notifications": self.chk_notify.isChecked(),
            "check_updates_on_startup": self.chk_updates_startup.isChecked(),
            "debounce_seconds": round(float(self.spin_debounce.value()), 2),
        }

    def _get_saved_comparable_state(self) -> dict:
        return {
            "youtube_preset": str(self.config.get("youtube_preset", "Crystal more Bass")),
            "meeting_preset": str(self.config.get("meeting_preset", "Compressed-Max")),
            "default_preset": str(self.config.get("default_preset", "Crystal more Bass")),
            "meeting_mic_preset": str(self.config.get("meeting_mic_preset", "Meeting-Mic-Clean") or ""),
            "apply_mic_preset": bool(self.config.get("apply_mic_preset", False)),
            "detect_microphone": bool(self.config.get("detect_microphone", True)),
            "detect_communication_role": bool(self.config.get("detect_communication_role", True)),
            "detect_youtube": bool(self.config.get("detect_youtube", True)),
            "pause_media_in_meetings": bool(self.config.get("pause_media_in_meetings", True)),
            "show_notifications": bool(self.config.get("show_notifications", True)),
            "check_updates_on_startup": bool(self.config.get("check_updates_on_startup", True)),
            "debounce_seconds": round(float(self.config.get("debounce_seconds", 2.0)), 2),
        }

    def has_unsaved_changes(self) -> bool:
        if self._loading_ui:
            return False
        return self._get_ui_config_state() != self._get_saved_comparable_state()

    def _on_ui_modified(self, *args):
        if self._loading_ui:
            return
        dirty = self.has_unsaved_changes()
        if dirty:
            self.setWindowTitle(f"EasyEffects Auto Preset Manager v{APP_VERSION} * (Unsaved Changes)")
            self.btn_save.setText("Save Settings *")
            self.btn_save.setStyleSheet(
                "background-color: #2e7d32; color: white; font-weight: bold; padding: 6px 16px; border-radius: 4px;"
            )
        else:
            self.setWindowTitle(f"EasyEffects Auto Preset Manager v{APP_VERSION}")
            self.btn_save.setText("Save Settings")
            self.btn_save.setStyleSheet("font-weight: bold; padding: 6px 16px;")

    def confirm_or_handle_unsaved_changes(self, action_description: str = "minimizing to tray") -> bool:
        """If there are unsaved changes in the UI, prompt the user to Save, Discard, or Cancel.

        Returns True if the caller should proceed with minimizing/closing/quitting, or False to cancel.
        """
        if not self.has_unsaved_changes():
            return True

        # Ensure window is visible and focused so the user sees the prompt clearly
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Unsaved Settings Changes")
        box.setText("<b>You have unsaved configuration changes.</b>")
        box.setInformativeText(f"Would you like to save your changes before {action_description}?")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        choice = box.exec()

        if choice == QMessageBox.StandardButton.Save:
            self._save_settings(show_popup=False)
            return True
        if choice == QMessageBox.StandardButton.Discard:
            self._load_config_to_ui()
            return True
        return False

    # --------------------------------------------------------------------------
    # Presets & Configuration Loading / Saving
    # --------------------------------------------------------------------------

    def _populate_presets(self):
        self._loading_ui = True
        try:
            self._output_presets, self._input_presets = list_available_presets()
            for combo, cfg_key, fallback in (
                (self.combo_youtube, "youtube_preset", "Crystal more Bass"),
                (self.combo_meeting, "meeting_preset", "Compressed-Max"),
                (self.combo_default, "default_preset", "Crystal more Bass"),
            ):
                current_selection = combo.currentText() or str(self.config.get(cfg_key, fallback))
                combo.clear()
                items = list(self._output_presets)
                if current_selection and current_selection not in items:
                    items.insert(0, current_selection)
                for p in items:
                    combo.addItem(p)
                idx = combo.findText(current_selection)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

            cur_mic = self.combo_mic.currentText() or str(self.config.get("meeting_mic_preset", "Meeting-Mic-Clean") or "")
            self.combo_mic.clear()
            self.combo_mic.addItem("(None)")
            mic_items = list(self._input_presets)
            if cur_mic and cur_mic != "(None)" and cur_mic not in mic_items:
                mic_items.insert(0, cur_mic)
            for ip in mic_items:
                self.combo_mic.addItem(ip)
            idx_m = self.combo_mic.findText(cur_mic) if cur_mic else 0
            if idx_m >= 0:
                self.combo_mic.setCurrentIndex(idx_m)
        finally:
            self._loading_ui = False

    def _on_refresh_presets_clicked(self):
        saved_ui = self._get_ui_config_state()
        self._populate_presets()
        self._loading_ui = True
        try:
            for combo, key in (
                (self.combo_youtube, "youtube_preset"),
                (self.combo_meeting, "meeting_preset"),
                (self.combo_default, "default_preset"),
            ):
                idx = combo.findText(saved_ui[key])
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            mic_val = saved_ui["meeting_mic_preset"]
            idx_mic = self.combo_mic.findText(mic_val) if mic_val else 0
            if idx_mic >= 0:
                self.combo_mic.setCurrentIndex(idx_mic)
        finally:
            self._loading_ui = False
        self._on_ui_modified()
        self.presets_updated.emit()

    def _load_config_to_ui(self):
        self._loading_ui = True
        try:
            self.btn_toggle_enable.setChecked(self.config.get("enabled", True))
            self._update_enable_btn_text(self.config.get("enabled", True))

            for combo, key, fallback in (
                (self.combo_youtube, "youtube_preset", "Crystal more Bass"),
                (self.combo_meeting, "meeting_preset", "Compressed-Max"),
                (self.combo_default, "default_preset", "Crystal more Bass"),
            ):
                target = str(self.config.get(key, fallback))
                if target and combo.findText(target) < 0:
                    combo.addItem(target)
                idx = combo.findText(target)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

            mic_target = str(self.config.get("meeting_mic_preset", "Meeting-Mic-Clean") or "")
            if mic_target:
                if self.combo_mic.findText(mic_target) < 0:
                    self.combo_mic.addItem(mic_target)
                idx_mic = self.combo_mic.findText(mic_target)
                if idx_mic >= 0:
                    self.combo_mic.setCurrentIndex(idx_mic)
            else:
                self.combo_mic.setCurrentIndex(0)

            self.chk_mic_preset.setChecked(bool(self.config.get("apply_mic_preset", False)))
            self.chk_detect_mic.setChecked(bool(self.config.get("detect_microphone", True)))
            self.chk_detect_comm.setChecked(bool(self.config.get("detect_communication_role", True)))
            self.chk_detect_yt.setChecked(bool(self.config.get("detect_youtube", True)))
            self.chk_pause_media.setChecked(bool(self.config.get("pause_media_in_meetings", True)))
            self.chk_notify.setChecked(bool(self.config.get("show_notifications", True)))
            self.chk_updates_startup.setChecked(bool(self.config.get("check_updates_on_startup", True)))
            self.spin_debounce.setValue(round(float(self.config.get("debounce_seconds", 2.0)), 2))
        finally:
            self._loading_ui = False
        self._on_ui_modified()

    def _save_settings(self, show_popup: bool = True):
        ui_state = self._get_ui_config_state()
        self.config["enabled"] = self.btn_toggle_enable.isChecked()
        self.config.update(ui_state)
        self.config["detect_media_apps"] = ui_state["detect_youtube"]

        save_config(self.config)
        self.worker.update_config(self.config)
        self._on_ui_modified()
        self.settings_saved.emit()
        if show_popup:
            QMessageBox.information(
                self, "Settings Saved", "EasyEffects Auto Preset configuration saved successfully."
            )

    def _on_enable_toggled(self, checked: bool):
        self._update_enable_btn_text(checked)
        self.config["enabled"] = checked
        save_config(self.config)
        self.worker.update_config(self.config)
        self.icon_label.setPixmap(
            _render_tray_pixmap(mode=self.worker.current_mode, enabled=checked, size=48)
        )
        if hasattr(self, "tray_icon"):
            self.tray_icon.setIcon(build_tray_icon(self.worker.current_mode, checked))

    def _update_enable_btn_text(self, checked: bool):
        if checked:
            self.btn_toggle_enable.setText("Auto-Switching: Active")
            self.btn_toggle_enable.setStyleSheet(
                "background-color: #2e7d32; color: white; padding: 8px 16px; font-weight: bold; border-radius: 4px;"
            )
        else:
            self.btn_toggle_enable.setText("Auto-Switching: Paused")
            self.btn_toggle_enable.setStyleSheet(
                "background-color: #c62828; color: white; padding: 8px 16px; font-weight: bold; border-radius: 4px;"
            )

    def _on_autostart_toggled(self, checked: bool):
        set_service_enabled(checked)

    # --------------------------------------------------------------------------
    # Bundled Presets & Dependency Dialog Launchers
    # --------------------------------------------------------------------------

    def open_bundled_presets_dialog(self, first_launch: bool = False):
        dlg = BundledPresetsDialog(parent=self, first_launch=first_launch)
        dlg.exec()
        if first_launch and not self.config.get("bundled_presets_prompted", False):
            self.config["bundled_presets_prompted"] = True
            save_config(self.config)
        if dlg.installed_any:
            self._on_refresh_presets_clicked()

    def _refresh_dependency_banner(self):
        rep = check_system_dependencies()
        if not rep["all_required_ok"]:
            missing_names = [it["name"] for it in rep["items"] if it["required"] and not it["installed"]]
            self.lbl_dep_banner.setText(f"⚠️ Missing required package(s): {', '.join(missing_names)}")
            self.dep_banner.setVisible(True)
        else:
            self.dep_banner.setVisible(False)

    def open_dependency_dialog(self, startup_warning: bool = False):
        dlg = SystemDependenciesDialog(parent=self, startup_warning=startup_warning)
        dlg.exec()
        self._refresh_dependency_banner()
        self._on_refresh_presets_clicked()

    # --------------------------------------------------------------------------
    # Update Checker & Auto-Installer
    # --------------------------------------------------------------------------

    def _on_periodic_update_timer(self):
        if self.config.get("check_updates_on_startup", True):
            self.trigger_update_check(manual=False)

    def trigger_update_check(self, manual: bool = False):
        self.btn_check_updates.setEnabled(False)
        self.btn_check_updates.setText("Checking...")
        self.lbl_version_status.setText(f"<b>Version:</b> v{APP_VERSION} — Checking for updates...")
        self._update_worker = UpdateCheckWorker(manual=manual, parent=self)
        self._update_worker.result_ready.connect(self._on_update_check_finished)
        self._update_worker.start()

    @pyqtSlot(dict, bool)
    def _on_update_check_finished(self, result: dict, manual: bool):
        self.btn_check_updates.setEnabled(True)
        self.btn_check_updates.setText("🔄 Check for Updates")
        msg = result.get("message", "")
        self.lbl_version_status.setText(f"<b>Version:</b> v{APP_VERSION} — {msg}")
        self._latest_release_url = result.get("release_url", GITHUB_RELEASES_PAGE_URL)
        self._latest_tarball_url = result.get("tarball_download_url", "")
        self._latest_flatpak_url = result.get("flatpak_download_url", "")
        self._latest_version_tag = result.get("latest_version", "")

        if result.get("update_available"):
            latest = self._latest_version_tag
            self.lbl_update_banner.setText(
                f"🎉 Update available: EasyEffects Auto Preset {latest} (current: v{APP_VERSION})"
            )
            self.btn_install_update.setText(f"⬇ Install {latest}")
            self.btn_install_update_about.setText(f"⬇ Install {latest}")
            self.btn_install_update_about.setVisible(True)
            self.update_banner.setVisible(True)
            if (
                hasattr(self, "tray_icon")
                and self.tray_icon.isVisible()
                and self._last_notified_update_version != latest
            ):
                self._last_notified_update_version = latest
                self.tray_icon.showMessage(
                    "EasyEffects Auto Preset Update Available",
                    f"Version {latest} is available. Open Settings to install in one click.",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
            if manual:
                ans = QMessageBox.question(
                    self,
                    "Update Available",
                    f"{msg}\n\nWould you like to download and install {latest} automatically now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ans == QMessageBox.StandardButton.Yes:
                    self.trigger_install_update()
        else:
            self.btn_install_update_about.setVisible(False)
            if manual:
                if result.get("ok"):
                    QMessageBox.information(self, "Up to Date", f"EasyEffects Auto Preset is up to date (v{APP_VERSION}).")
                else:
                    QMessageBox.warning(self, "Update Check Failed", msg)

    def trigger_install_update(self):
        self.btn_install_update.setEnabled(False)
        self.btn_install_update.setText("Installing...")
        self.btn_install_update_about.setEnabled(False)
        self.btn_install_update_about.setText("Installing...")
        self.lbl_version_status.setText(
            f"<b>Version:</b> v{APP_VERSION} — Downloading and installing {self._latest_version_tag or 'update'}..."
        )
        self._install_worker = UpdateInstallWorker(
            tarball_url=self._latest_tarball_url,
            flatpak_url=self._latest_flatpak_url,
            latest_version=self._latest_version_tag,
            parent=self,
        )
        self._install_worker.install_finished.connect(self._on_install_update_finished)
        self._install_worker.start()

    @pyqtSlot(dict)
    def _on_install_update_finished(self, res: dict):
        self.btn_install_update.setEnabled(True)
        self.btn_install_update_about.setEnabled(True)
        latest = self._latest_version_tag or "Update"
        self.btn_install_update.setText(f"⬇ Install {latest}")
        self.btn_install_update_about.setText(f"⬇ Install {latest}")

        msg = res.get("message", "")
        self.lbl_version_status.setText(f"<b>Version:</b> v{APP_VERSION} — {msg}")
        if res.get("ok") and res.get("updated"):
            QMessageBox.information(
                self,
                "Update Installed",
                f"{msg}\n\nRestarting EasyEffects Auto Preset now...",
            )
            # Restart systemd user service or re-exec
            try:
                svc = subprocess.run(
                    ["systemctl", "--user", "is-active", "easyeffects-auto-preset.service"],
                    capture_output=True,
                    text=True,
                )
                if svc.stdout.strip() == "active":
                    subprocess.Popen(["systemctl", "--user", "restart", "easyeffects-auto-preset.service"])
                    QApplication.quit()
                    return
            except Exception:
                pass
            target_bin = Path.home() / ".local" / "bin" / "easyeffects-auto-preset"
            if target_bin.is_file():
                subprocess.Popen([str(target_bin)])
                QApplication.quit()
        elif not res.get("ok"):
            QMessageBox.warning(self, "Update Installation Failed", msg)

    # --------------------------------------------------------------------------
    # Live Stream Table & Window Close / Minimize Handling
    # --------------------------------------------------------------------------

    @pyqtSlot(str, str, list)
    def _on_state_changed(self, mode: str, active_preset: str, streams: list):
        self.icon_label.setPixmap(
            _render_tray_pixmap(mode=mode, enabled=self.config.get("enabled", True), size=48)
        )
        mode_display = {
            "meeting": "🎤 Voice Meeting Active [MTG]",
            "youtube": "▶ YouTube / Media Playback Active [MED]",
            "default": "🎚 Idle / Default [DEF]",
        }.get(mode, mode.capitalize())

        status_str = f"Mode: <b>{mode_display}</b>  |  Active Preset: <b>{active_preset or 'None'}</b>"
        self.status_detail.setText(status_str)

        self.table_streams.setRowCount(len(streams))
        for row, st in enumerate(streams):
            self.table_streams.setItem(row, 0, QTableWidgetItem(st.get("type", "")))
            self.table_streams.setItem(row, 1, QTableWidgetItem(st.get("app", "")))
            self.table_streams.setItem(row, 2, QTableWidgetItem(st.get("media", "")))
            self.table_streams.setItem(row, 3, QTableWidgetItem(st.get("state", "")))
            item_trig = QTableWidgetItem(st.get("trigger", ""))
            if st.get("trigger") != "None":
                item_trig.setForeground(QColor("#2e7d32"))
                font = item_trig.font()
                font.setBold(True)
                item_trig.setFont(font)
            self.table_streams.setItem(row, 4, item_trig)

    @pyqtSlot(str, str)
    def _on_preset_switched(self, new_preset: str, reason: str):
        pass

    def _on_minimize_clicked(self):
        if not self.confirm_or_handle_unsaved_changes("minimizing to the system tray"):
            return
        self._hide_to_tray()

    def _hide_to_tray(self):
        self.hide()
        if not self._first_minimize_tip_shown:
            self._first_minimize_tip_shown = True
            if hasattr(self, "tray_icon") and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    "EasyEffects Auto Preset",
                    "Application is minimized to the system tray.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )

    def closeEvent(self, event):
        """Intercept close button to prompt for unsaved changes, then hide to tray."""
        event.ignore()
        if not self.confirm_or_handle_unsaved_changes("closing the settings window"):
            return
        self._hide_to_tray()


# ==============================================================================
# System Tray Manager
# ==============================================================================

class TrayManager(QObject):
    """Manages QSystemTrayIcon and background worker thread."""

    def __init__(self, app: QApplication, config: dict):
        super().__init__()
        self.app = app
        self.config = config

        # Background audio monitor thread
        self.worker = AudioMonitorWorker(self.config)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run_loop)

        # Main window
        self.window = MainWindow(self.config, self.worker)
        self.window.presets_updated.connect(self._populate_force_presets)
        self.window.settings_saved.connect(self._sync_tray_toggles_from_config)

        # Tray Icon setup
        self._init_tray()
        self.window.tray_icon = self.tray_icon

        # Connect signals
        self.worker.state_changed.connect(self._on_worker_state_changed)
        self.worker.preset_switched.connect(self._on_preset_switched)
        self.worker.media_paused.connect(self._on_media_paused)

        # Start background monitor thread
        self.thread.start()

        # Startup checks: dependencies, first-launch bundled presets offer, and update check
        QTimer.singleShot(600, self._run_startup_checks)

    def _run_startup_checks(self):
        # 1. Check if EasyEffects or pactl is missing
        dep_report = check_system_dependencies()
        if not dep_report["all_required_ok"]:
            self.show_window()
            self.window.open_dependency_dialog(startup_warning=True)

        # 2. First-launch offer to install bundled Meeting-Voice & Media presets
        preset_status = get_bundled_preset_status()
        any_missing = any(not inst for inst in preset_status.values())
        if not self.config.get("bundled_presets_prompted", False):
            if any_missing:
                self.show_window()
                self.window.open_bundled_presets_dialog(first_launch=True)
            else:
                self.config["bundled_presets_prompted"] = True
                save_config(self.config)

        # 3. Check for updates if enabled
        if self.config.get("check_updates_on_startup", True):
            self.window.trigger_update_check(manual=False)

    def _init_tray(self):
        icon = build_tray_icon(mode="default", enabled=self.config.get("enabled", True))
        self.tray_icon = QSystemTrayIcon(icon, self.app)
        self.tray_icon.setToolTip(f"EasyEffects Auto Preset v{APP_VERSION}: Initializing...")

        self.menu = QMenu()

        self.header_action = QAction(f"EasyEffects Auto Preset v{APP_VERSION}", self.menu)
        self.header_action.setEnabled(False)
        font = self.header_action.font()
        font.setBold(True)
        self.header_action.setFont(font)
        self.menu.addAction(self.header_action)

        self.status_action = QAction("Status: Initializing...", self.menu)
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        self.menu.addSeparator()

        self.toggle_action = QAction("Auto-Switching Enabled", self.menu)
        self.toggle_action.setCheckable(True)
        self.toggle_action.setChecked(self.config.get("enabled", True))
        self.toggle_action.triggered.connect(self._on_toggle_enabled)
        self.menu.addAction(self.toggle_action)

        self.pause_media_action = QAction("Pause Media During Meetings", self.menu)
        self.pause_media_action.setCheckable(True)
        self.pause_media_action.setChecked(self.config.get("pause_media_in_meetings", True))
        self.pause_media_action.triggered.connect(self._on_toggle_pause_media)
        self.menu.addAction(self.pause_media_action)

        # Quick preset override submenu
        self.menu_presets = self.menu.addMenu("Force Preset...")
        self._populate_force_presets()
        self.menu.addSeparator()

        # Settings, Bundled Presets, Dependency Check, and Updates
        self.settings_action = QAction("Open Settings...", self.menu)
        self.settings_action.triggered.connect(self.show_window)
        self.menu.addAction(self.settings_action)

        self.install_presets_action = QAction("📦 Install / Restore Bundled Presets...", self.menu)
        self.install_presets_action.triggered.connect(self._on_tray_install_presets)
        self.menu.addAction(self.install_presets_action)

        self.check_deps_action = QAction("🩺 System & Dependency Check...", self.menu)
        self.check_deps_action.triggered.connect(self._on_tray_check_deps)
        self.menu.addAction(self.check_deps_action)

        self.check_update_action = QAction("🔄 Check for Updates...", self.menu)
        self.check_update_action.triggered.connect(lambda: self.window.trigger_update_check(manual=True))
        self.menu.addAction(self.check_update_action)

        self.menu.addSeparator()
        self.kofi_action = QAction("☕ Buy Me a Coffee (Ko-fi)", self.menu)
        self.kofi_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl("https://ko-fi.com/russellmilliner")))
        self.menu.addAction(self.kofi_action)

        self.menu.addSeparator()
        self.quit_action = QAction("Quit", self.menu)
        self.quit_action.triggered.connect(self.quit_app)
        self.menu.addAction(self.quit_action)

        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_install_presets(self):
        self.show_window()
        self.window.open_bundled_presets_dialog(first_launch=False)

    def _on_tray_check_deps(self):
        self.show_window()
        self.window.open_dependency_dialog(startup_warning=False)

    def _populate_force_presets(self):
        self.menu_presets.clear()
        out_presets, _ = list_available_presets()
        for p in out_presets:
            act = QAction(p, self.menu_presets)
            act.triggered.connect(lambda checked, name=p: self._force_preset(name))
            self.menu_presets.addAction(act)

    def _force_preset(self, name: str):
        apply_preset(name)
        self.tray_icon.showMessage("Preset Forced", f"Applied: {name}", QSystemTrayIcon.MessageIcon.Information, 1500)

    def _on_toggle_enabled(self, checked: bool):
        self.config["enabled"] = checked
        save_config(self.config)
        self.worker.update_config(self.config)
        self.window.btn_toggle_enable.setChecked(checked)
        self.tray_icon.setIcon(build_tray_icon(self.worker.current_mode, checked))

    def _on_toggle_pause_media(self, checked: bool):
        self.config["pause_media_in_meetings"] = checked
        save_config(self.config)
        self.worker.update_config(self.config)
        self.window._loading_ui = True
        self.window.chk_pause_media.setChecked(checked)
        self.window._loading_ui = False
        self.window._on_ui_modified()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window.isVisible():
                if self.window.confirm_or_handle_unsaved_changes("minimizing to the system tray"):
                    self.window.hide()
            else:
                self.show_window()

    def show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        if self.config.get("check_updates_on_startup", True):
            self.window.trigger_update_check(manual=False)

    @pyqtSlot(str, str, list)
    def _on_worker_state_changed(self, mode: str, active_preset: str, streams: list):
        mode_str = {
            "meeting": "Meeting",
            "youtube": "YouTube / Media",
            "default": "Default",
        }.get(mode, mode.capitalize())

        tooltip = f"EasyEffects Auto Preset v{APP_VERSION}: {mode_str}\nActive: {active_preset or 'None'}"
        self.tray_icon.setToolTip(tooltip)
        self.status_action.setText(f"Active: {active_preset} ({mode_str})")
        self.tray_icon.setIcon(build_tray_icon(mode, self.config.get("enabled", True)))

    def _sync_tray_toggles_from_config(self):
        self.toggle_action.setChecked(bool(self.config.get("enabled", True)))
        self.pause_media_action.setChecked(bool(self.config.get("pause_media_in_meetings", True)))

    @pyqtSlot(list)
    def _on_media_paused(self, paused_players: list):
        if self.config.get("show_notifications", True) and paused_players:
            self.tray_icon.showMessage(
                "Media Paused for Meeting",
                f"Paused active media player(s): {', '.join(paused_players)}",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    @pyqtSlot(str, str)
    def _on_preset_switched(self, new_preset: str, reason: str):
        if self.config.get("show_notifications", True):
            self.tray_icon.showMessage(
                "EasyEffects Preset Switched",
                f"Switched to: {new_preset}\n({reason})",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def quit_app(self):
        if not self.window.confirm_or_handle_unsaved_changes("quitting the application"):
            return
        self.worker.stop()
        self.thread.quit()
        self.thread.wait(2000)
        self.app.quit()


def _is_our_app_process(pid: int) -> bool:
    """Return True if /proc/<pid> belongs to another running easyeffects-auto-preset instance."""
    if pid <= 1 or pid == os.getpid() or pid == os.getppid():
        return False
    proc_dir = Path(f"/proc/{pid}")
    try:
        if not proc_dir.exists() or proc_dir.stat().st_uid != os.getuid():
            return False
        raw = (proc_dir / "cmdline").read_bytes()
        if not raw:
            return False
        args = [a.decode("utf-8", errors="ignore") for a in raw.split(b"\x00") if a]
        if not args:
            return False

        exe_base = os.path.basename(args[0])
        target_basenames = {
            "easyeffects-auto-preset",
            "easyeffects_auto_preset.py",
            "easyeffects-auto-preset-gui",
        }

        if exe_base in target_basenames:
            is_target = True
        elif exe_base.startswith("python"):
            # Only match when Python is directly executing one of our app scripts (not -c, -m, or -)
            script_arg = next((a for a in args[1:] if not a.startswith("-")), "")
            is_target = os.path.basename(script_arg) in target_basenames
        else:
            is_target = False

        if not is_target:
            return False

        # Ignore one-shot CLI invocations
        one_shot_flags = {
            "--cli-status",
            "--status",
            "-s",
            "--switch",
            "--install-presets",
            "--check-deps",
            "--check-update",
            "-u",
            "--self-update",
            "--list-presets",
            "-l",
            "--version",
            "-V",
            "--help",
            "-h",
        }
        if any(a in one_shot_flags for a in args[1:]):
            return False

        return True
    except Exception:
        return False


def _cleanup_pid_file() -> None:
    try:
        if PID_FILE.is_file():
            recorded = int(PID_FILE.read_text(encoding="utf-8").strip())
            if recorded == os.getpid():
                PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def enforce_single_instance() -> int:
    """Ensure only one instance of easyeffects-auto-preset runs at a time.

    Finds any existing instance via PID_FILE and /proc scan, sends SIGTERM (followed by SIGKILL
    if still alive), and writes the current PID to PID_FILE.
    Returns the number of terminated previous instances.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    candidate_pids: set[int] = set()

    # 1. Check PID file
    if PID_FILE.is_file():
        try:
            old_pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            if _is_our_app_process(old_pid):
                candidate_pids.add(old_pid)
        except Exception:
            pass

    # 2. Scan /proc for any other running daemon/tray instances
    try:
        for entry in Path("/proc").iterdir():
            if entry.name.isdigit():
                pid = int(entry.name)
                if _is_our_app_process(pid):
                    candidate_pids.add(pid)
    except Exception:
        pass

    terminated = 0
    for pid in sorted(candidate_pids):
        try:
            print(f"Terminating previous easyeffects-auto-preset instance (PID {pid})...")
            os.kill(pid, signal.SIGTERM)
            terminated += 1
        except ProcessLookupError:
            continue
        except Exception as e:
            print(f"Warning: could not send SIGTERM to PID {pid}: {e}", file=sys.stderr)

    # Wait up to 1.5s for graceful termination, then SIGKILL any remaining
    if candidate_pids:
        deadline = time.time() + 1.5
        while time.time() < deadline:
            alive = [p for p in candidate_pids if Path(f"/proc/{p}").exists()]
            if not alive:
                break
            time.sleep(0.05)

        for pid in candidate_pids:
            if Path(f"/proc/{pid}").exists():
                try:
                    print(f"Force-killing unresponsive previous instance (PID {pid})...")
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass

        kill_deadline = time.time() + 0.5
        while time.time() < kill_deadline:
            if not any(Path(f"/proc/{p}").exists() for p in candidate_pids):
                break
            time.sleep(0.05)

    try:
        PID_FILE.write_text(f"{os.getpid()}\n", encoding="utf-8")
    except Exception:
        pass
    atexit.register(_cleanup_pid_file)
    return terminated


def ensure_desktop_entries():
    """Ensure desktop launcher and autostart files exist."""
    APP_DESKTOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not APP_ICON_FILE.is_file():
        generate_app_icon(APP_ICON_FILE)

    content = f"""[Desktop Entry]
Type=Application
Name=EasyEffects Auto Preset
GenericName=Audio Preset Switcher
Comment=Automatic EasyEffects preset switcher for YouTube and Voice Meetings
Exec={Path.home()}/.local/bin/easyeffects-auto-preset
Icon={APP_ICON_FILE}
Terminal=false
Categories=Audio;AudioVideo;Utility;
Keywords=easyeffects;audio;preset;youtube;meeting;
"""
    APP_DESKTOP_FILE.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=f"EasyEffects Auto Preset Manager & Tray App v{APP_VERSION}")
    parser.add_argument("-V", "--version", action="version", version=f"easyeffects-auto-preset v{APP_VERSION}")
    parser.add_argument("-m", "--minimized", action="store_true", help="Start minimized to the system tray")
    parser.add_argument("--tray", action="store_true", help="Alias for --minimized")
    parser.add_argument("--cli-status", action="store_true", help="Print current status and exit")
    parser.add_argument("--switch", type=str, help="Immediately apply an output preset and exit")
    parser.add_argument(
        "--install-presets",
        action="store_true",
        help="Install all bundled Meeting-Voice and Media presets into EasyEffects and exit",
    )
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="Check if EasyEffects and required audio packages are installed and exit",
    )
    parser.add_argument("-u", "--check-update", action="store_true", help="Check GitHub Releases for updates and exit")
    parser.add_argument(
        "--self-update",
        action="store_true",
        help="Download and install the latest release from GitHub Releases and restart the service",
    )
    args = parser.parse_args()

    if args.install_presets:
        count, names, targets = install_bundled_presets(overwrite=True)
        print(f"Installed {count} bundled preset(s) into EasyEffects:")
        for n in names:
            print(f"  • {n}")
        print("Target directories:")
        for t in targets:
            print(f"  {t}")
        sys.exit(0)

    if args.check_deps:
        rep = check_system_dependencies()
        distro = rep["distro"]
        print(f"System: {distro.get('name', 'Linux')} (package manager: {distro.get('pkg_mgr', 'unknown')})")
        print("-" * 60)
        for it in rep["items"]:
            mark = "✅" if it["installed"] else "❌"
            req = "Required" if it["required"] else "Recommended"
            print(f"{mark} {it['name']} [{req}]: {it['status_text']}")
            if not it["installed"]:
                print(f"   Fix: {it['install_pkg_cmd']}")
        sys.exit(0 if rep["all_required_ok"] else 1)

    if args.check_update:
        print(f"Checking for updates (current version: v{APP_VERSION})...")
        res = check_for_updates(APP_VERSION)
        print(res["message"])
        if res.get("update_available"):
            print(f"Release URL:  {res['release_url']}")
            print(f"Download URL: {res.get('download_url', '')}")
        sys.exit(0 if res.get("ok") else 1)

    if args.self_update:
        print(f"Checking and installing latest update (current version: v{APP_VERSION})...")
        res = install_update_from_github()
        print(res.get("message", ""))
        if res.get("ok") and res.get("updated"):
            subprocess.run(["systemctl", "--user", "restart", "easyeffects-auto-preset.service"], check=False)
        sys.exit(0 if res.get("ok") else 1)

    if args.switch:
        ok = apply_preset(args.switch)
        print(f"Applied preset '{args.switch}': {'OK' if ok else 'FAILED'}")
        sys.exit(0 if ok else 1)

    if args.cli_status:
        cur = get_current_loaded_preset()
        print(f"EasyEffects Auto Preset v{APP_VERSION} — Current loaded preset: {cur}")
        sys.exit(0)

    # Enforce single instance: quit/kill any previously running instance before starting
    enforce_single_instance()

    def _handle_sigterm(signum, frame):
        _cleanup_pid_file()
        os._exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    config = load_config()
    ensure_desktop_entries()

    app = QApplication(sys.argv)
    app.setApplicationName("EasyEffects Auto Preset")
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)

    tray_mgr = TrayManager(app, config)

    # Show window on manual launch unless --minimized / --tray was passed
    should_minimize = args.minimized or args.tray
    if not should_minimize:
        tray_mgr.show_window()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
