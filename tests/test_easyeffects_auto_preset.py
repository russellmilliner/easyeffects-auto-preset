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
