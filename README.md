# EasyEffects Auto Preset

[![Version](https://img.shields.io/badge/Version-v0.1.0-0284c7?style=for-the-badge&logo=github)](https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.1.0)
[![Flatpak Bundle](https://img.shields.io/badge/Flatpak-Download_v0.1.0-4a90d9?style=for-the-badge&logo=flatpak&logoColor=white)](https://github.com/russellmilliner/easyeffects-auto-preset/releases/download/v0.1.0/easyeffects-auto-preset-v0.1.0-x86_64.flatpak)
[![Platform: Linux x86_64](https://img.shields.io/badge/Platform-Linux%20x86__64-fcc624?style=for-the-badge&logo=linux&logoColor=black)](https://www.kernel.org/)
[![Desktop: KDE Plasma 6](https://img.shields.io/badge/Desktop-KDE%20Plasma%206%20%2F%20Qt%206-1d99f3?style=for-the-badge&logo=kde&logoColor=white)](https://kde.org/plasma-desktop/)
[![Audio: PipeWire](https://img.shields.io/badge/Audio-PipeWire%20%2F%20PulseAudio-e05d44?style=for-the-badge&logo=soundcharts&logoColor=white)](https://pipewire.org/)
[![Built with Rust](https://img.shields.io/badge/Rust-2021_Edition-dea584?style=for-the-badge&logo=rust&logoColor=black)](https://www.rust-lang.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge)](https://www.apache.org/licenses/LICENSE-2.0)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Buy%20Me%20a%20Coffee-ff5e5b?logo=ko-fi&logoColor=white&style=for-the-badge)](https://ko-fi.com/russellmilliner)

> **Automated, intelligent audio preset switcher and system tray manager for EasyEffects on Linux (PipeWire / KDE Plasma).**  
> Seamlessly detects active YouTube playback, voice meetings, and microphone streams to switch audio presets in real time.

---

## 📥 Release & Downloads (`v0.1.0`)

| Asset | Download Link | Description |
| :--- | :--- | :--- |
| **Flatpak Bundle (`x86_64`)** | [**`easyeffects-auto-preset-v0.1.0-x86_64.flatpak`**](https://github.com/russellmilliner/easyeffects-auto-preset/releases/download/v0.1.0/easyeffects-auto-preset-v0.1.0-x86_64.flatpak) ([SHA-256](https://github.com/russellmilliner/easyeffects-auto-preset/releases/download/v0.1.0/easyeffects-auto-preset-v0.1.0-x86_64.flatpak.sha256)) | Self-contained Flatpak bundle (`org.kde.Platform//6.11`) with Rust daemon, PyQt6 GUI & bundled presets |
| **Linux Release Archive (`x86_64`)** | [**`easyeffects-auto-preset-v0.1.0-linux-x86_64.tar.gz`**](https://github.com/russellmilliner/easyeffects-auto-preset/releases/download/v0.1.0/easyeffects-auto-preset-v0.1.0-linux-x86_64.tar.gz) ([SHA-256](https://github.com/russellmilliner/easyeffects-auto-preset/releases/download/v0.1.0/easyeffects-auto-preset-v0.1.0-linux-x86_64.tar.gz.sha256)) | Native Rust daemon binary, PyQt6 GUI & tray script, custom EasyEffects presets, systemd user service & desktop entry |
| **Standalone Rust Daemon (`x86_64`)** | [**`easyeffects-auto-preset-v0.1.0-x86_64`**](https://github.com/russellmilliner/easyeffects-auto-preset/releases/download/v0.1.0/easyeffects-auto-preset-v0.1.0-x86_64) ([SHA-256](https://github.com/russellmilliner/easyeffects-auto-preset/releases/download/v0.1.0/easyeffects-auto-preset-v0.1.0-x86_64.sha256)) | Standalone compiled Rust CLI/daemon binary |

### Quick Flatpak Install (from GitHub Release)

```bash
curl -LO https://github.com/russellmilliner/easyeffects-auto-preset/releases/download/v0.1.0/easyeffects-auto-preset-v0.1.0-x86_64.flatpak
flatpak install --user -y easyeffects-auto-preset-v0.1.0-x86_64.flatpak
flatpak run io.github.russellmilliner.easyeffects_auto_preset
```

---

## ☕ Support the Project

If you find EasyEffects Auto Preset helpful for your audio workflow and meetings, consider supporting continued development:

[![Buy Me a Coffee](https://img.shields.io/badge/Ko--fi-Buy%20Me%20a%20Coffee-ff5e5b?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/russellmilliner)

👉 **[Support Russell Milliner on Ko-fi](https://ko-fi.com/russellmilliner)**

---

## ✨ Features

- 🎧 **Automatic YouTube Detection:** Switches to **`Crystal more Bass`** when YouTube or YouTube Music is actively playing audio in your browser (Zen, Firefox, Chrome, Edge) or web applications.
- 🎤 **Voice Meeting Detection:** Switches to **`Compressed-Max`** or **`Meeting-Voice-Clear`** whenever a voice meeting is active (Google Meet, Zoom, Microsoft Teams, Slack huddle, Discord, or any microphone recording stream).
- 🔄 **Smart Debouncing:** A configurable grace period (default: 2.0s) prevents abrupt preset flapping during audio buffering, track changes, or speaking pauses.
- 🦀 **Dual Architecture (Rust + Python/Qt6):**
  - **Native Rust Daemon:** Memory-safe, zero-overhead background engine consuming **<4MB RSS** and 0% CPU.
  - **PyQt6 Settings & Tray Manager:** Full graphical settings UI with live PipeWire stream inspector and dynamic status badges.
- 🎨 **Distinctive Dynamic System Tray Icon:**
  - 🔵 **Blue pip:** YouTube playback active
  - 🟢 **Green pip:** Voice meeting / call active
  - ⚪ **Slate pip:** System idle / default preset
  - 🔴 **Red pip:** Auto-switching paused
- 📦 **Flatpak Ready:** Complete Flatpak manifest (`io.github.russellmilliner.easyeffects_auto_preset.yml`) and Flathub AppStream metadata.
- 🎚️ **Bundled Custom EasyEffects Presets:** Includes custom meeting presets tuned specifically for speech clarity and background noise filtration.

---

## 🎛️ Bundled EasyEffects Presets

The repository includes curated presets ready to install into EasyEffects:

| Preset | Channel | Purpose & Audio Characteristics |
|---|---|---|
| **`Meeting-Voice-Clear`** | Output | **Voice Meeting Optimization:** Aggressive low-frequency high-pass cut (-32 dB at 32Hz, -24 dB at 64Hz, -10 dB at 125Hz) to remove table thumps, HVAC drone, and proximity rumble. +4dB presence boost in the 1.5–4kHz speech clarity range, Speex denoiser (-70 dB) and dereverberation to kill room echo, plus fast dynamic compression to equalize loud and quiet speakers. |
| **`Meeting-Mic-Clean`** | Input | **Microphone Cleanliness:** Speex noise suppression, room dereverberation, and Automatic Gain Control (AGC) for your outbound microphone. |
| **`Crystal more Bass`** | Output | **Media & Music:** Rich, punchy low-end response with crystalline highs, tuned for music, videos, and YouTube. |
| **`Compressed-Max`** | Output | **Maximum Leveling:** High-ratio dynamic compression + maximizer ceiling. |

To install the presets into EasyEffects:
```bash
chmod +x presets/install-presets.sh
./presets/install-presets.sh
```

---

## 🏗️ Architecture & Platform Integration

### 1. Platform
- **Target Platform:** Linux x86_64 with PipeWire or PulseAudio audio server.
- **Desktop Environments:** KDE Plasma 6 (native Tray and StatusNotifier integration), GNOME, and any standard X11/Wayland desktop.
- **EasyEffects:** Compatible with both Flathub Flatpak (`com.github.wwmm.easyeffects`) and native distribution packages.

### 2. Rust Engine (`easyeffects-auto-preset`)
The core engine is implemented in **Rust (2021 Edition)**. It interfaces directly with PipeWire's PulseAudio layer via `pactl` stream inspection:
- Inspects `source-outputs` to detect active microphone recording hooks from browser tabs (WebRTC) and native meeting clients.
- Inspects `sink-inputs` to identify active playback streams, media properties, and playback roles (`phone` / `communication`).
- Enforces state priority: `Meeting > YouTube > Default`.
- Implements state transition debouncing using monotonic `Instant` timestamps.

### 3. PyQt6 Tray Application
- Provides an intuitive settings manager with live stream inspection.
- Allows real-time preset testing and quick manual overrides via the tray context menu.
- Direct Ko-fi donation shortcuts embedded in the tray menu and settings dialog.

---

## 🚀 Building & Installation

### Option 1: Native Rust Daemon

```bash
# Build release binary
cargo build --release

# Check status of audio streams and active preset
./target/release/easyeffects-auto-preset --status

# List available presets
./target/release/easyeffects-auto-preset --list-presets

# Run background daemon
./target/release/easyeffects-auto-preset --daemon
```

### Option 2: PyQt6 Tray & GUI App

```bash
# Launch directly from repository
python3 python/easyeffects_auto_preset.py

# Launch minimized to system tray
python3 python/easyeffects_auto_preset.py --minimized
```

### Option 3: Systemd User Service

To enable automated startup with your graphical desktop session:

```bash
mkdir -p ~/.config/systemd/user/
cp systemd/easyeffects-auto-preset.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now easyeffects-auto-preset.service
```

---

## 📦 Building the Flatpak

```bash
chmod +x scripts/build-flatpak.sh

# Build the .flatpak bundle
./scripts/build-flatpak.sh

# Build and immediately install into user environment
./scripts/build-flatpak.sh --install
```

---

## ⚙️ Configuration

Settings are saved in `~/.config/easyeffects-auto-preset/config.json`:

```json
{
  "enabled": true,
  "youtube_preset": "Crystal more Bass",
  "meeting_preset": "Compressed-Max",
  "default_preset": "Crystal more Bass",
  "meeting_mic_preset": "Meeting-Mic-Clean",
  "apply_mic_preset": false,
  "debounce_seconds": 2.0,
  "check_interval_seconds": 1.0,
  "detect_microphone": true,
  "detect_communication_role": true,
  "detect_meeting_apps": true,
  "detect_youtube": true,
  "show_notifications": true,
  "minimize_on_startup": true
}
```

---

## 📄 License

Licensed under the Apache License, Version 2.0 (the "License");  
you may not use this file except in compliance with the License.  
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software  
distributed under the License is distributed on an "AS IS" BASIS,  
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
See the [LICENSE](LICENSE) and [NOTICE](NOTICE) files for details.

---

## 👤 Author

**Russell Milliner**
- GitHub: [@russellmilliner](https://github.com/russellmilliner)
- Ko-fi: [Buy Me a Coffee](https://ko-fi.com/russellmilliner)
