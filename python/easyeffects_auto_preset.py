#!/usr/bin/env python3
"""easyeffects-auto-preset: Automated preset switcher and tray manager for EasyEffects.

Automatically switches EasyEffects presets based on active audio activity:
- "Crystal more Bass" when YouTube / media is playing
- "Compressed-Max" (or "Meeting-Voice-Clear") when in any voice meeting (Meet, Zoom, Teams, Discord, mic active)
- Restores default preset when audio is idle
Provides a system tray icon, background daemon, and settings GUI (PyQt6).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QObject, QRectF, Qt, QThread, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QBrush, QColor, QDesktopServices, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

CONFIG_DIR = Path.home() / ".config" / "easyeffects-auto-preset"
CONFIG_FILE = CONFIG_DIR / "config.json"
APP_ICON_FILE = CONFIG_DIR / "app-icon.png"
AUTOSTART_FILE = Path.home() / ".config" / "autostart" / "easyeffects-auto-preset.desktop"
APP_DESKTOP_FILE = Path.home() / ".local" / "share" / "applications" / "easyeffects-auto-preset.desktop"

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
    "show_notifications": True,
    "minimize_on_startup": True,
}

KNOWN_MEETING_BINARIES = {
    "zoom", "zoom.real", "teams", "slack", "discord", "discord-canary",
    "webex", "skype", "skypeforlinux", "signal-desktop", "telegram-desktop",
}

MEETING_KEYWORDS = [
    "meet.google.com", "google meet", "zoom meeting", "teams call",
    "slack huddle", "discord call", "webex", "gotomeeting", "chime",
]


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


def build_tray_icon(mode: str = "default", enabled: bool = True, size: int = 64) -> QIcon:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    scale = size / 64.0
    bar_color = QColor(220, 225, 235, 230) if enabled else QColor(130, 135, 145, 150)
    knob_color = QColor(255, 255, 255) if enabled else QColor(160, 160, 160)

    pen = QPen(bar_color, 4.0 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    xs = [16 * scale, 32 * scale, 48 * scale]
    if mode == "youtube":
        knob_ys = [18 * scale, 36 * scale, 22 * scale]
        badge_color = QColor(0, 168, 255)   # Cyan / Blue for YouTube
    elif mode == "meeting":
        knob_ys = [44 * scale, 18 * scale, 28 * scale]
        badge_color = QColor(46, 204, 113)  # Vibrant Green for Meetings
    else:
        knob_ys = [24 * scale, 32 * scale, 20 * scale]
        badge_color = QColor(185, 195, 210) # Clean Slate for Default

    if not enabled:
        badge_color = QColor(231, 76, 60)   # Red / Paused

    for i, x in enumerate(xs):
        painter.drawLine(int(x), int(12 * scale), int(x), int(52 * scale))
        painter.setBrush(QBrush(knob_color))
        painter.setPen(QPen(QColor(25, 28, 35, 190), 1.5 * scale))
        painter.drawRoundedRect(
            QRectF(x - 5.5 * scale, knob_ys[i] - 3.5 * scale, 11 * scale, 7 * scale),
            2 * scale,
            2 * scale,
        )

    # Status pip badge at bottom-right
    painter.setBrush(QBrush(badge_color))
    painter.setPen(QPen(QColor(20, 22, 28, 240), 2.2 * scale))
    painter.drawEllipse(QRectF(40 * scale, 40 * scale, 20 * scale, 20 * scale))

    painter.end()
    return QIcon(QPixmap.fromImage(img))


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
    """Find the best command to invoke EasyEffects CLI."""
    if shutil.which("easyeffects"):
        return ["easyeffects"]
    return ["flatpak", "run", "--command=easyeffects", "com.github.wwmm.easyeffects"]


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
                # Format is usually: "1\tPreset Name" or "1  Preset Name"
                parts = re.split(r"^\d+[\s\t]+", line_str)
                name = parts[-1].strip() if len(parts) > 1 else line_str
                if name:
                    if current_section == "output":
                        out_presets.append(name)
                    elif current_section == "input":
                        in_presets.append(name)
    except Exception as e:
        print(f"Error listing presets: {e}", file=sys.stderr)

    # Fallback to inspecting Flatpak directory directly if CLI failed
    if not out_presets:
        data_out = Path.home() / ".var/app/com.github.wwmm.easyeffects/data/easyeffects/output"
        if data_out.is_dir():
            out_presets = [p.stem for p in data_out.glob("*.json")]

    if not in_presets:
        data_in = Path.home() / ".var/app/com.github.wwmm.easyeffects/data/easyeffects/input"
        if data_in.is_dir():
            in_presets = [p.stem for p in data_in.glob("*.json")]

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


class AudioMonitorWorker(QObject):
    """Monitors PipeWire/PulseAudio sink-inputs and source-outputs."""

    state_changed = pyqtSignal(str, str, list)  # (mode, active_preset, active_streams_list)
    preset_switched = pyqtSignal(str, str)     # (new_preset, reason)

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
            # Filter internal speech dispatcher dummy or echo cancel loops if any
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

            item_trigger = "None"
            is_sk_meeting = False
            is_sk_youtube = False

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

            # Check YouTube conditions (only when actively playing sound)
            if self.config.get("detect_youtube", True) and is_playing:
                if "youtube" in media.lower() or "youtube" in app.lower():
                    is_sk_youtube = True
                    item_trigger = "YouTube Playing"
                    youtube_playing = True
                    youtube_details = f"YouTube: {media or app}"

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
                else:
                    if self.current_mode == "meeting":
                        # Apply debounce when leaving a meeting
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
                            # Apply debounce when pausing YouTube
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


class MainWindow(QMainWindow):
    """Main Settings Window for EasyEffects Auto Preset."""

    def __init__(self, config: dict, worker: AudioMonitorWorker):
        super().__init__()
        self.config = config
        self.worker = worker
        self._output_presets: list[str] = []
        self._input_presets: list[str] = []
        self._first_minimize_tip_shown = False

        self.setWindowTitle("EasyEffects Auto Preset Manager")
        self.resize(720, 560)
        self.setWindowIcon(QIcon(str(APP_ICON_FILE)) if APP_ICON_FILE.is_file() else build_tray_icon())

        self._init_ui()
        self._populate_presets()
        self._load_config_to_ui()

        # Connect worker signals
        self.worker.state_changed.connect(self._on_state_changed)
        self.worker.preset_switched.connect(self._on_preset_switched)

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
        if APP_ICON_FILE.is_file():
            self.icon_label.setPixmap(QPixmap(str(APP_ICON_FILE)).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.icon_label.setPixmap(build_tray_icon().pixmap(48, 48))
        banner_layout.addWidget(self.icon_label)

        banner_text_layout = QVBoxLayout()
        self.status_title = QLabel("<b>EasyEffects Auto Preset</b>", self)
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

        # Tab widget
        self.tabs = QTabWidget(self)

        # Tab 1: Presets & Triggers
        tab_presets = QWidget()
        layout_presets = QVBoxLayout(tab_presets)
        layout_presets.setSpacing(16)

        grp_mapping = QGroupBox("Preset Triggers & Rules", tab_presets)
        grid = QGridLayout(grp_mapping)
        grid.setSpacing(12)

        grid.addWidget(QLabel("<b>YouTube Playback Preset:</b>"), 0, 0)
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

        layout_presets.addWidget(grp_mapping)

        # Detection toggles group
        grp_detect = QGroupBox("Detection Rules", tab_presets)
        vbox_detect = QVBoxLayout(grp_detect)

        self.chk_detect_mic = QCheckBox("Detect active microphone (Google Meet, Zoom, Teams, Slack, Discord)", grp_detect)
        self.chk_detect_comm = QCheckBox("Detect communication audio streams (media.role = phone/communication)", grp_detect)
        self.chk_detect_yt = QCheckBox("Detect active YouTube playback in browser tabs and web apps", grp_detect)

        vbox_detect.addWidget(self.chk_detect_mic)
        vbox_detect.addWidget(self.chk_detect_comm)
        vbox_detect.addWidget(self.chk_detect_yt)
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
        self.tabs.addTab(tab_presets, "Preset Triggers")

        # Tab 2: Live Stream Monitor
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

        # Tab 3: Presets Reference
        tab_about = QWidget()
        layout_about = QVBoxLayout(tab_about)
        info_text = QLabel(
            "<h3>EasyEffects Presets Overview</h3>"
            "<ul>"
            "<li><b>Crystal more Bass:</b> Tuned for music, gaming, and YouTube video playback with rich low-end punch and crystalline highs.</li>"
            "<li><b>Compressed-Max:</b> Extreme dynamic range compressor + maximizer to level out volume spikes.</li>"
            "<li><b>Meeting-Voice-Clear (New):</b> Custom designed for voice meetings:"
            "  <ul>"
            "    <li><b>Tones down bass:</b> Aggressive high-pass shelf (-32 dB at 32Hz, -24 dB at 64Hz) to eliminate table bumps, HVAC drone, and proximity rumble.</li>"
            "    <li><b>Levels out people:</b> Fast-attack compressor + 24 dB maximizer to bring quiet whisperers and loud talkers to the same comfortable level.</li>"
            "    <li><b>Noise & Reverb Suppression:</b> Speex denoiser (-70 dB) and automatic dereverberation to clean up echoey rooms and background hiss.</li>"
            "  </ul>"
            "</li>"
            "<li><b>Meeting-Mic-Clean (Input):</b> Noise cancellation and AGC specifically tuned for your microphone stream.</li>"
            "</ul>"
            "<p><i>Presets are stored in <code>~/.var/app/com.github.wwmm.easyeffects/data/easyeffects/</code></i></p>"
        )
        info_text.setWordWrap(True)
        layout_about.addWidget(info_text)

        # Support on Ko-fi frame
        support_frame = QFrame(tab_about)
        support_frame.setStyleSheet("QFrame { background-color: palette(alternate-base); border-radius: 8px; padding: 12px; }")
        support_layout = QHBoxLayout(support_frame)
        support_label = QLabel("<b>Enjoying EasyEffects Auto Preset?</b> Support development on Ko-fi:", support_frame)
        support_btn = QPushButton("☕ Buy Me a Coffee on Ko-fi", support_frame)
        support_btn.setStyleSheet("background-color: #ff5e5b; color: white; font-weight: bold; border-radius: 4px; padding: 6px 14px;")
        support_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://ko-fi.com/russellmilliner")))
        support_layout.addWidget(support_label)
        support_layout.addStretch()
        support_layout.addWidget(support_btn)
        layout_about.addWidget(support_frame)

        layout_about.addStretch()
        self.tabs.addTab(tab_about, "Preset Details")

        main_layout.addWidget(self.tabs)

        # Bottom buttons
        btn_layout = QHBoxLayout()

        self.chk_autostart = QCheckBox("Start automatically on login (systemd user service)", self)
        self.chk_autostart.setChecked(is_service_enabled())
        self.chk_autostart.toggled.connect(self._on_autostart_toggled)
        btn_layout.addWidget(self.chk_autostart)

        btn_layout.addStretch()

        self.btn_kofi = QPushButton("☕ Buy Me a Coffee", self)
        self.btn_kofi.setStyleSheet("background-color: #ff5e5b; color: white; font-weight: bold; border-radius: 4px; padding: 6px 14px;")
        self.btn_kofi.setToolTip("Support project development on Ko-fi")
        self.btn_kofi.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://ko-fi.com/russellmilliner")))
        btn_layout.addWidget(self.btn_kofi)

        self.btn_save = QPushButton("Save Settings", self)
        self.btn_save.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.btn_save.clicked.connect(self._save_settings)
        btn_layout.addWidget(self.btn_save)

        self.btn_hide = QPushButton("Minimize to Tray", self)
        self.btn_hide.clicked.connect(self.hide)
        btn_layout.addWidget(self.btn_hide)

        main_layout.addLayout(btn_layout)

    def _populate_presets(self):
        self._output_presets, self._input_presets = list_available_presets()
        for combo in (self.combo_youtube, self.combo_meeting, self.combo_default):
            combo.clear()
            for p in self._output_presets:
                combo.addItem(p)

        self.combo_mic.clear()
        self.combo_mic.addItem("(None)")
        for ip in self._input_presets:
            self.combo_mic.addItem(ip)

    def _load_config_to_ui(self):
        self.btn_toggle_enable.setChecked(self.config.get("enabled", True))
        self._update_enable_btn_text(self.config.get("enabled", True))

        # Select saved preset values
        idx_yt = self.combo_youtube.findText(self.config.get("youtube_preset", "Crystal more Bass"))
        if idx_yt >= 0:
            self.combo_youtube.setCurrentIndex(idx_yt)

        idx_meet = self.combo_meeting.findText(self.config.get("meeting_preset", "Compressed-Max"))
        if idx_meet >= 0:
            self.combo_meeting.setCurrentIndex(idx_meet)

        idx_def = self.combo_default.findText(self.config.get("default_preset", "Crystal more Bass"))
        if idx_def >= 0:
            self.combo_default.setCurrentIndex(idx_def)

        idx_mic = self.combo_mic.findText(self.config.get("meeting_mic_preset", "Meeting-Mic-Clean"))
        if idx_mic >= 0:
            self.combo_mic.setCurrentIndex(idx_mic)

        self.chk_mic_preset.setChecked(self.config.get("apply_mic_preset", False))
        self.chk_detect_mic.setChecked(self.config.get("detect_microphone", True))
        self.chk_detect_comm.setChecked(self.config.get("detect_communication_role", True))
        self.chk_detect_yt.setChecked(self.config.get("detect_youtube", True))
        self.chk_notify.setChecked(self.config.get("show_notifications", True))
        self.spin_debounce.setValue(float(self.config.get("debounce_seconds", 2.0)))

    def _save_settings(self):
        self.config["enabled"] = self.btn_toggle_enable.isChecked()
        self.config["youtube_preset"] = self.combo_youtube.currentText()
        self.config["meeting_preset"] = self.combo_meeting.currentText()
        self.config["default_preset"] = self.combo_default.currentText()
        self.config["meeting_mic_preset"] = self.combo_mic.currentText() if self.combo_mic.currentIndex() > 0 else ""
        self.config["apply_mic_preset"] = self.chk_mic_preset.isChecked()
        self.config["detect_microphone"] = self.chk_detect_mic.isChecked()
        self.config["detect_communication_role"] = self.chk_detect_comm.isChecked()
        self.config["detect_youtube"] = self.chk_detect_yt.isChecked()
        self.config["show_notifications"] = self.chk_notify.isChecked()
        self.config["debounce_seconds"] = self.spin_debounce.value()

        save_config(self.config)
        self.worker.update_config(self.config)
        QMessageBox.information(self, "Settings Saved", "EasyEffects Auto Preset configuration saved successfully.")

    def _on_enable_toggled(self, checked: bool):
        self._update_enable_btn_text(checked)
        self.config["enabled"] = checked
        save_config(self.config)
        self.worker.update_config(self.config)

    def _update_enable_btn_text(self, checked: bool):
        if checked:
            self.btn_toggle_enable.setText("Auto-Switching: Active")
            self.btn_toggle_enable.setStyleSheet("background-color: #2e7d32; color: white; padding: 8px 16px; font-weight: bold; border-radius: 4px;")
        else:
            self.btn_toggle_enable.setText("Auto-Switching: Paused")
            self.btn_toggle_enable.setStyleSheet("background-color: #c62828; color: white; padding: 8px 16px; font-weight: bold; border-radius: 4px;")

    def _on_autostart_toggled(self, checked: bool):
        set_service_enabled(checked)

    @pyqtSlot(str, str, list)
    def _on_state_changed(self, mode: str, active_preset: str, streams: list):
        # Update banner
        mode_display = {
            "meeting": "🎤 Voice Meeting Active",
            "youtube": "▶ YouTube Playback Active",
            "default": "🎵 Idle / Default",
        }.get(mode, mode.capitalize())

        status_str = f"Mode: <b>{mode_display}</b>  |  Active Preset: <b>{active_preset or 'None'}</b>"
        self.status_detail.setText(status_str)

        # Update table
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

    def closeEvent(self, event):
        """Intercept close button to hide to tray instead of quitting."""
        event.ignore()
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

        # Tray Icon setup
        self._init_tray()
        self.window.tray_icon = self.tray_icon

        # Connect signals
        self.worker.state_changed.connect(self._on_worker_state_changed)
        self.worker.preset_switched.connect(self._on_preset_switched)

        # Start background monitor thread
        self.thread.start()

    def _init_tray(self):
        icon = build_tray_icon(mode="default", enabled=self.config.get("enabled", True))
        self.tray_icon = QSystemTrayIcon(icon, self.app)
        self.tray_icon.setToolTip("EasyEffects Auto Preset: Initializing...")

        self.menu = QMenu()

        self.header_action = QAction("EasyEffects Auto Preset", self.menu)
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

        # Quick preset override submenu
        self.menu_presets = self.menu.addMenu("Force Preset...")
        self._populate_force_presets()
        self.menu.addSeparator()

        # Settings and Quit
        self.settings_action = QAction("Open Settings...", self.menu)
        self.settings_action.triggered.connect(self.show_window)
        self.menu.addAction(self.settings_action)

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

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window.isVisible():
                self.window.hide()
            else:
                self.show_window()

    def show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    @pyqtSlot(str, str, list)
    def _on_worker_state_changed(self, mode: str, active_preset: str, streams: list):
        mode_str = {
            "meeting": "Meeting",
            "youtube": "YouTube",
            "default": "Default",
        }.get(mode, mode.capitalize())

        tooltip = f"EasyEffects Auto Preset: {mode_str}\nActive: {active_preset or 'None'}"
        self.tray_icon.setToolTip(tooltip)
        self.status_action.setText(f"Active: {active_preset} ({mode_str})")
        self.tray_icon.setIcon(build_tray_icon(mode, self.config.get("enabled", True)))

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
        self.worker.stop()
        self.thread.quit()
        self.thread.wait(2000)
        self.app.quit()


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
    parser = argparse.ArgumentParser(description="EasyEffects Auto Preset Manager & Tray App")
    parser.add_argument("-m", "--minimized", action="store_true", help="Start minimized to the system tray")
    parser.add_argument("--tray", action="store_true", help="Alias for --minimized")
    parser.add_argument("--cli-status", action="store_true", help="Print current status and exit")
    parser.add_argument("--switch", type=str, help="Immediately apply an output preset and exit")
    args = parser.parse_args()

    if args.switch:
        ok = apply_preset(args.switch)
        print(f"Applied preset '{args.switch}': {'OK' if ok else 'FAILED'}")
        sys.exit(0 if ok else 1)

    if args.cli_status:
        cur = get_current_loaded_preset()
        print(f"Current EasyEffects loaded preset: {cur}")
        sys.exit(0)

    config = load_config()
    ensure_desktop_entries()

    app = QApplication(sys.argv)
    app.setApplicationName("EasyEffects Auto Preset")
    app.setQuitOnLastWindowClosed(False)

    tray_mgr = TrayManager(app, config)

    # Determine whether to show window on start
    should_minimize = args.minimized or args.tray or config.get("minimize_on_startup", True)
    if not should_minimize:
        tray_mgr.show_window()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
