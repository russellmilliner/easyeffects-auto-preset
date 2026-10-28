# Changelog — easyeffects-auto-preset

All notable changes and bumped dependencies for `russellmilliner/easyeffects-auto-preset` are documented in this file.

## [v0.5.3](https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.5.3) — 2026-10-28

### Security
- **SHA-256 Checksum Verification for Self-Updater (`S1`):** Both the Rust (`install_update_from_github` in `src/main.rs`) and Python (`install_update_from_github` in `python/easyeffects_auto_preset.py`) self-updaters now download the corresponding `.tar.gz.sha256` / `.flatpak.sha256` checksum asset and verify the cryptographic SHA-256 digest (`verify_file_sha256`) before extracting or installing updates.
- **GitHub Release URL Allowlist & Strict SemVer Validation (`S1`):** Restricted update download URLs to `https://github.com/russellmilliner/easyeffects-auto-preset/releases/download/` and release page URLs to `https://github.com/russellmilliner/easyeffects-auto-preset/releases/`. Hardened `is_newer_version` so non-semver or malformed release tags return `false` instead of triggering a false update.
- **Flatpak Sandbox & Host Command Routing (`S2`):** Bundled pinned `PyQt6==6.11.0` and `PyQt6_sip==13.13.0` wheels into `/app` inside the Flatpak (`org.kde.Platform//6.11`), verified `PyQt6` import during the build, routed host `easyeffects` and `busctl` commands via `flatpak-spawn --host`, and staged Flatpak update downloads in `CONFIG_DIR` so the host `flatpak install` can access the verified bundle.
- **Exclusive Temporary Directory Creation (`S3`):** Replaced predictable `/tmp/easyeffects-auto-preset-update-<pid>` directory names in the Rust updater with `create_secure_temp_dir` using `DirBuilderExt::mode(0o700)` exclusive directory creation.
- **Single-Instance UID Verification & Unified Binary Names (`S4`):** Verified `/proc/<pid>` UID ownership before sending `SIGTERM` to previous instances, made `instance.pid` and `config.json` writes atomic via temporary file replacement, and unified binary installation across `easyeffects-auto-preset`, `easyeffects-auto-preset-gui`, and `easyeffects-auto-preset-daemon`.
- **Argument-Safe Package Installation (`S5` & `S6`):** Refactored `launch_package_installation` to split command chains with `shlex.split` and invoke `pkexec` / `flatpak` directly without `bash -c`. Respected `XDG_CONFIG_HOME` and `XDG_DATA_HOME`.

### Added
- **Desktop Notifications Toggle (`show_notifications`):** Added a quick-toggle button (`🔔 Notifications: ON` / `🔕 Notifications: OFF`) in the main window header, a checkbox in the Settings tab, and a toggle action in the System Tray context menu to enable or silence preset-switch and media-pause desktop notifications.
- **Automated Test Suite & CI Checks:** Added comprehensive Rust unit tests (`src/main.rs`) and headless Python/PyQt6 unit tests (`tests/test_easyeffects_auto_preset.py`), plus `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, and `pytest` in GitHub Actions CI.

### Fixed
- **Whole-Word Alert Keyword Matching (`B1` & `B2`):** Replaced substring alert matching with word-boundary matching so `"ding"` no longer false-matches `"Recording"` or `"Loading"` and `"ping"` no longer false-matches `"Shopping"` or `"Mapping"`. Removed `"chime"` from `ALERT_KEYWORDS` and added `"amazon chime"` to `MEETING_KEYWORDS` so Amazon Chime calls are properly detected.
- **Single-Shot Media Pause on Meeting Onset (`B3`):** Added `media_paused_for_meeting` state tracking in both Rust and Python monitors so `pause_active_media_players()` runs only once when entering meeting mode (allowing users to manually resume media during a call if desired) and resets when leaving meeting mode.
- **Config Numeric Clamping (`B4`):** Added `Config::sanitize()` (Rust) and `sanitize_config()` (Python) to clamp `debounce_seconds` (`0.0..=60.0`), `meeting_onset_seconds` (`0.0..=60.0`), and `check_interval_seconds` (`0.25..=30.0`), preventing `Duration::from_secs_f64` panics on negative or `NaN` values.
- **Command Caching & Config Live Reload (`B5`):** Cached `get_easyeffects_cmd()` (`OnceLock` in Rust, module cache in Python) and added `config.json` modification time (`mtime`) polling to the Rust daemon.
- **Locale-Independent `pactl -f json` Parsing (`B6`):** Added `parse_pactl_json` and `query_pactl_streams` using `LC_ALL=C pactl -f json list` with fallback to `LC_ALL=C pactl list` so non-English system locales parse `Corked`/`Mute` states reliably.
- **Dynamic Clap Version (`B7`):** Derived Rust CLI `--version` directly from `Cargo.toml` via `#[command(version)]`.

---

## [v0.5.2](https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.5.2) — 2026-10-23

### Added
- **Alert & Notification Sound Filtering:** Ignore short notification/event streams (`media.role=event`/`notification`) from meeting apps (Teams, Slack, Discord, Zoom) so chat pings do not pause media or switch presets.
- **Configurable Meeting Onset Delay (`meeting_onset_seconds`):** Added sustained meeting activity verification (default `3.5s` for active microphone/communication streams, `2×` for playback-only streams from meeting binaries) to filter out brief WebRTC mic probes and UI sounds.

---

## [v0.5.1](https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.5.1) — 2026-10-22

### Added
- **Periodic & Window-Restore Update Checks:** Automatic background update check every 6 hours and whenever the Settings window is restored from the system tray.
- **One-Click In-App & CLI Self-Updater (`--self-update`):** Download and install the latest GitHub Release directly from the GUI update banner, System Tray menu, or CLI (`--self-update`).

### Commits
- docs(changelog): add v0.5.0 dependency changelog (`a9aeefb`)
- docs: update v0.5.0 UI and tray badge screenshots (`b455005`)

---

## [v0.5.0](https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.5.0) — 2026-10-22

### Added
- **High-Contrast Dual-Glyph & Badge System Tray Icons:** Redesigned system tray and header status icons to render a mode-specific upper glyph (🎤 microphone for `MTG`, ▶ play triangle for `MED`, 🎚️ equalizer sliders for `DEF`, ⏸ pause bars for `OFF`) paired with a high-contrast 3-letter badge pill across all standard icon sizes (`22px`–`128px`).

---

## [v0.4.0](https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.4.0) — 2026-10-21

### Added
- **Auto-Pause Media During Meetings (`pause_media_in_meetings`):** Automatically pauses active MPRIS2 media players (browsers, Spotify, VLC, mpv, Elisa) via `busctl` / `dbus-send` when a voice meeting is active.
- **Single-Instance Enforcement (`enforce_single_instance`):** Ensures only one daemon/tray instance runs at a time via `instance.pid` and `/proc` inspection.

---

## [v0.3.0](https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.3.0) — 2026-10-21

### Added
- **Visible Version Badges:** Added version display across the main application header, window title, system tray context menu, tray hover tooltip, and CLI.

---

## [v0.2.0](https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.2.0) — 2026-10-21

### Added
- **Universal Music, Movie & Video Detection:** Expanded media detection to cover all major desktop video/music players (`vlc`, `mpv`, `spotify`, `elisa`, `haruna`, `celluloid`, `kodi`, `jellyfin`, etc.) and streaming platforms.
- **Built-in GitHub Releases Update Checker:** Added `--check-update` (`-u`) CLI flag and GUI/Tray update checking.

---

## [v0.1.0](https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.1.0) — 2026-10-20

### Added
- Initial release featuring the native Rust CLI/daemon (`src/main.rs`), PyQt6 System Tray & Settings GUI (`python/easyeffects_auto_preset.py`), 8 custom EasyEffects presets (`presets/*.json`), systemd user service, and Flatpak packaging.
