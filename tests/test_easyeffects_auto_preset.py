#!/usr/bin/env python3
"""Unit and integration tests for EasyEffects Auto Preset (Python GUI & Tray daemon)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_MODULE_PATH = REPO_ROOT / "python" / "easyeffects_auto_preset.py"

spec = importlib.util.spec_from_file_location("easyeffects_auto_preset", PY_MODULE_PATH)
assert spec is not None and spec.loader is not None
ee_mod = importlib.util.module_from_spec(spec)
sys.modules["easyeffects_auto_preset"] = ee_mod
spec.loader.exec_module(ee_mod)


def test_b1_b2_alert_keyword_word_boundaries():
    """Verify 'ding'/'ping' do not match substrings like 'Recording'/'Shopping' and 'Amazon Chime' is not an alert."""
    assert not ee_mod.is_alert_or_notification_stream(
        {
            "media.name": "Audio Recording Stream",
            "node.name": "webrtc-loading-stream",
            "media.filename": "shopping_cart_mapping.ogg",
        }
    )
    assert not ee_mod.is_alert_or_notification_stream(
        {
            "media.name": "Amazon Chime Voice Call",
            "node.name": "chime-meeting",
        }
    )
    assert ee_mod.is_alert_or_notification_stream(
        {
            "media.name": "Teams Notification Ding",
            "node.name": "audio-stream",
        }
    )
    assert ee_mod.is_alert_or_notification_stream(
        {
            "media.name": "Slack Ping Sound",
            "node.name": "audio-stream",
        }
    )
    assert ee_mod.is_alert_or_notification_stream(
        {
            "media.role": "event",
            "media.name": "Normal Stream",
        }
    )


def test_s1_semver_and_url_allowlist(tmp_path: Path):
    """Verify semver comparison rejects non-semver tags and URL allowlist + SHA-256 verification work."""
    assert ee_mod.parse_semver("v0.5.2") == (0, 5, 2)
    assert ee_mod.parse_semver("0.5.3-rc1") == (0, 5, 3)
    assert ee_mod.parse_semver("1.2.3.4") is None
    assert ee_mod.parse_semver("nightly-build") is None

    assert ee_mod.is_newer_version("0.5.2", "0.5.3")
    assert not ee_mod.is_newer_version("0.5.2", "0.5.2")
    assert not ee_mod.is_newer_version("0.5.2", "0.5.1")
    assert not ee_mod.is_newer_version("0.5.2", "nightly-test")
    assert not ee_mod.is_newer_version("0.5.2", "")

    assert ee_mod.is_allowed_download_url(
        "https://github.com/russellmilliner/easyeffects-auto-preset/releases/download/v0.5.3/easyeffects-auto-preset-v0.5.3-linux-x86_64.tar.gz"
    )
    assert not ee_mod.is_allowed_download_url("https://evil.example.com/payload.tar.gz")
    assert ee_mod.is_allowed_release_url(
        "https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.5.3"
    )
    assert not ee_mod.is_allowed_release_url("https://evil.example.com/releases/tag/v0.5.3")

    sample_file = tmp_path / "artifact.tar.gz"
    sample_bytes = b"easyeffects-auto-preset-test-payload"
    sample_file.write_bytes(sample_bytes)
    expected_hash = hashlib.sha256(sample_bytes).hexdigest()

    ok, digest = ee_mod.verify_file_sha256(sample_file, f"{expected_hash}  artifact.tar.gz\n")
    assert ok
    assert digest == expected_hash

    ok_bad, msg_bad = ee_mod.verify_file_sha256(sample_file, f"{'0' * 64}  artifact.tar.gz\n")
    assert not ok_bad
    assert "mismatch" in msg_bad.lower()


def test_b4_s6_config_sanitization_and_atomic_save(tmp_path: Path, monkeypatch):
    """Verify negative/NaN debounce/onset/interval values are clamped and config saves atomically."""
    monkeypatch.setattr(ee_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(ee_mod, "CONFIG_FILE", tmp_path / "config.json")

    raw_cfg = {
        "debounce_seconds": -15.0,
        "meeting_onset_seconds": float("nan"),
        "check_interval_seconds": 0.01,
        "show_notifications": False,
    }
    ee_mod.save_config(raw_cfg)
    loaded = ee_mod.load_config()

    assert loaded["debounce_seconds"] == 0.0
    assert loaded["meeting_onset_seconds"] == 3.5
    assert loaded["check_interval_seconds"] == 0.25
    assert loaded["show_notifications"] is False


def test_b6_parse_pactl_json_and_blocks():
    """Verify locale-independent pactl JSON parsing and text fallback."""
    sample_json = json.dumps(
        [
            {
                "index": 77,
                "corked": False,
                "mute": False,
                "properties": {
                    "application.name": "Firefox",
                    "application.process.binary": "firefox",
                    "media.name": "YouTube - Music Video",
                    "media.role": "video",
                },
            }
        ]
    )
    blocks = ee_mod.parse_pactl_json(sample_json)
    assert blocks is not None
    assert len(blocks) == 1
    assert blocks[0]["id"] == "77"
    assert blocks[0]["Corked"] == "no"
    assert blocks[0]["Mute"] == "no"
    assert blocks[0]["application.name"] == "Firefox"

    is_media, trig, reason = ee_mod.detect_media_playback_stream(blocks[0], ee_mod.DEFAULT_CONFIG)
    assert is_media
    assert "Media" in trig or "YouTube" in trig


def test_headless_icon_generation(tmp_path: Path):
    """Verify tray and app icon rendering works under offscreen Qt."""
    from PyQt6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    assert app is not None

    icon_path = tmp_path / "app.png"
    ee_mod.generate_app_icon(icon_path, size=64)
    assert icon_path.is_file() and icon_path.stat().st_size > 100

    for mode in ("default", "meeting", "youtube"):
        tray_icon = ee_mod.build_tray_icon(mode=mode, enabled=True, size=32)
        assert not tray_icon.isNull()


def test_kde_plasma_volume_meter_and_mixer_streams_ignored():
    """Verify KDE Plasma volume tray applet (PlasmaPA-VolumeMeter) and mixer VU meters never trigger meeting mode."""
    # KDE Plasma 6 system tray volume popup VU meter stream
    assert ee_mod.is_ignored_internal_or_meter_source_stream(
        {
            "application.name": "plasmashell",
            "application.process.binary": "plasmashell",
            "application.id": "org.kde.plasma.pa",
            "media.name": "PlasmaPA-VolumeMeter",
        }
    )
    # Stream with only PlasmaPA-VolumeMeter media.name
    assert ee_mod.is_ignored_internal_or_meter_source_stream(
        {
            "application.name": "PulseAudio Volume Meter",
            "media.name": "PlasmaPA-VolumeMeter",
        }
    )
    # KDE System Settings audio page VU meter
    assert ee_mod.is_ignored_internal_or_meter_source_stream(
        {
            "application.name": "System Settings",
            "application.process.binary": "systemsettings",
            "media.name": "RecordStream",
        }
    )
    # PipeWire explicit monitor / peak-detect stream properties
    assert ee_mod.is_ignored_internal_or_meter_source_stream(
        {
            "application.name": "CustomMixer",
            "media.name": "Input Level",
            "stream.monitor": "true",
        }
    )
    # Real microphone streams from Teams, browsers, and Discord must NOT be ignored
    assert not ee_mod.is_ignored_internal_or_meter_source_stream(
        {
            "application.name": "Teams for Linux",
            "application.process.binary": "teams-for-linux",
            "media.name": "RecordStream",
        }
    )
    assert not ee_mod.is_ignored_internal_or_meter_source_stream(
        {
            "application.name": "Zen",
            "application.process.binary": "zen",
            "media.name": "AudioCallbackDriver",
        }
    )
    assert not ee_mod.is_ignored_internal_or_meter_source_stream(
        {
            "application.name": "WEBRTC VoiceEngine",
            "application.process.binary": "Discord",
            "media.name": "recStream",
        }
    )


def test_sidetone_mapping_sanitization_and_cli_one_shot():
    """Verify sidetone percent-to-raw mapping, config clamping, and --sidetone one-shot exclusion."""
    assert ee_mod.percent_to_headsetcontrol_sidetone(False, 40) == 0
    assert ee_mod.percent_to_headsetcontrol_sidetone(True, 0) == 0
    assert ee_mod.percent_to_headsetcontrol_sidetone(True, 1) == 1
    assert ee_mod.percent_to_headsetcontrol_sidetone(True, 40) == 51
    assert ee_mod.percent_to_headsetcontrol_sidetone(True, 100) == 128

    cfg_low = ee_mod.sanitize_config({"sidetone_enabled": True, "sidetone_percent": -20})
    assert cfg_low["sidetone_enabled"] is True
    assert cfg_low["sidetone_percent"] == 1
    assert cfg_low["sidetone_restore_on_connect"] is True

    cfg_high = ee_mod.sanitize_config({"sidetone_percent": 250, "sidetone_restore_on_connect": False})
    assert cfg_high["sidetone_percent"] == 100
    assert cfg_high["sidetone_restore_on_connect"] is False

    assert ee_mod.is_one_shot_cli_args(["--sidetone", "toggle"])
    assert ee_mod.is_one_shot_cli_args(["--sidetone=40"])
    assert not ee_mod.is_one_shot_cli_args(["--minimized"])


def test_headless_mainwindow_sidetone_controls_and_dirty_state(tmp_path: Path, monkeypatch):
    """Verify MainWindow initializes sidetone controls cleanly without triggering unsaved-changes dirty state."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert app is not None

    monkeypatch.setattr(ee_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(ee_mod, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(ee_mod, "list_available_presets", lambda: (["Crystal more Bass", "Compressed-Max"], ["Meeting-Mic-Clean"]))
    monkeypatch.setattr(
        ee_mod,
        "check_system_dependencies",
        lambda: {"all_required_ok": True, "all_recommended_ok": True, "distro": {"name": "Test", "pkg_mgr": "pacman"}, "items": [], "combined_fix_commands": []},
    )
    monkeypatch.setattr(ee_mod, "is_service_enabled", lambda: True)
    monkeypatch.setattr(
        ee_mod,
        "query_headset_status",
        lambda: {"available": True, "device_name": "Arctis 1 Wireless", "connected": True, "battery_percent": 94, "sidetone_capable": True, "status_text": "Arctis 1 Wireless — Online (Battery: 94%)"},
    )
    applied_calls: list[tuple[bool, int]] = []
    monkeypatch.setattr(
        ee_mod,
        "apply_headset_sidetone",
        lambda enabled, pct: (applied_calls.append((enabled, pct)) or True, "OK"),
    )

    cfg = ee_mod.DEFAULT_CONFIG.copy()
    cfg["sidetone_enabled"] = False
    cfg["sidetone_percent"] = 40
    worker = ee_mod.AudioMonitorWorker(cfg)
    win = ee_mod.MainWindow(cfg, worker)

    assert not win.has_unsaved_changes()
    assert not win.chk_sidetone_enabled.isChecked()
    assert win.slider_sidetone.value() == 40
    assert win.lbl_sidetone_pct.text() == "40%"

    win._set_sidetone_quick_level(60)
    assert win.chk_sidetone_enabled.isChecked()
    assert win.slider_sidetone.value() == 60
    assert win.lbl_sidetone_pct.text() == "60%"
    assert applied_calls == [(True, 60)]
    assert not win.has_unsaved_changes()

    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["sidetone_enabled"] is True
    assert saved["sidetone_percent"] == 60
    win.close()


def test_gaming_detection_and_keeps_crystal_preset_on_call(monkeypatch):
    """Verify gaming streams/processes are detected and keep preset on Crystal even while on a voice call."""
    cfg = ee_mod.DEFAULT_CONFIG.copy()
    cfg["gaming_preset"] = "Crystal"
    cfg["meeting_preset"] = "Meeting-Voice-Clear-Max-Level"
    cfg["default_preset"] = "Crystal"
    cfg["meeting_onset_seconds"] = 0.0
    assert cfg["detect_games"] is True

    # 1. Native CS2 stream
    is_game, trig, reason = ee_mod.detect_game_playback_stream(
        {
            "application.name": "Counter-Strike 2",
            "application.process.binary": "cs2",
            "media.name": "SDLAudio",
        },
        cfg,
    )
    assert is_game
    assert "Crystal" in trig
    assert "cs2" in reason.lower()

    # 2. Proton/Wine .exe stream vs ignored Wine system daemon
    is_proton_game, _, _ = ee_mod.detect_game_playback_stream(
        {
            "application.name": "Cyberpunk 2077",
            "application.process.binary": "Cyberpunk2077.exe",
        },
        cfg,
    )
    assert is_proton_game
    is_wine_daemon, _, _ = ee_mod.detect_game_playback_stream(
        {
            "application.name": "winedevice.exe",
            "application.process.binary": "winedevice.exe",
        },
        cfg,
    )
    assert not is_wine_daemon

    # 3. Steam /steamapps/common/<Game> extraction
    assert (
        ee_mod.extract_steam_common_game_from_args(
            ["/home/millinr/.local/share/Steam/steamapps/common/Counter-Strike Global Offensive/game/bin/linuxsteamrt64/cs2"]
        )
        == "Counter-Strike Global Offensive"
    )
    assert (
        ee_mod.extract_steam_common_game_from_args(
            ["/home/millinr/.local/share/Steam/steamapps/common/SteamLinuxRuntime_sniper/pressure-vessel/bin/pv-adverb"]
        )
        is None
    )

    # 4. Tray icon renders gaming badge ("GAM")
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    assert _app is not None
    tray_icon = ee_mod.build_tray_icon(mode="gaming", enabled=True, size=32)
    assert not tray_icon.isNull()

    # 5. Simulate active call (microphone recording) + active game simultaneously in AudioMonitorWorker
    def fake_query_pactl(stream_type: str, _prefix: str):
        if stream_type == "source-outputs":
            return [
                {
                    "id": "10",
                    "Corked": "no",
                    "Mute": "no",
                    "application.name": "Discord",
                    "application.process.binary": "discord",
                    "media.name": "WEBRTC VoiceEngine",
                }
            ]
        return [
            {
                "id": "20",
                "Corked": "no",
                "Mute": "no",
                "application.name": "Discord",
                "application.process.binary": "discord",
                "media.name": "Voice Call",
                "media.role": "communication",
            },
            {
                "id": "21",
                "Corked": "no",
                "Mute": "no",
                "application.name": "Counter-Strike 2",
                "application.process.binary": "cs2",
                "media.name": "SDLAudio",
            },
        ]

    monkeypatch.setattr(ee_mod, "query_pactl_streams", fake_query_pactl)
    monkeypatch.setattr(ee_mod, "detect_running_game_process", lambda _c: "Counter-Strike 2")
    monkeypatch.setattr(ee_mod, "get_current_loaded_preset", lambda: "Meeting-Voice-Clear-Max-Level")
    applied_presets: list[tuple[str, str | None]] = []

    def fake_apply_preset(out_p: str, in_p: str | None = None) -> bool:
        applied_presets.append((out_p, in_p))
        worker.stop()
        return True

    monkeypatch.setattr(ee_mod, "apply_preset", fake_apply_preset)

    worker = ee_mod.AudioMonitorWorker(cfg)
    raw_meeting, _yt, stream_items, _m_info, _y_info, strong = worker.scan_streams()
    assert raw_meeting is True
    assert strong is True
    assert worker._last_gaming_active is True

    worker.run_loop()
    assert worker.current_mode == "gaming"
    assert worker.last_preset == "Crystal"
    assert applied_presets == [("Crystal", None)]


