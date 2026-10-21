//! EasyEffects Auto Preset Daemon & CLI (Rust Engine)
//!
//! High-performance, lightweight automated preset switcher for EasyEffects.
//! Monitors PipeWire / PulseAudio streams in real-time and dynamically
//! applies presets for YouTube playback and Voice Meetings.

use clap::Parser;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread::sleep;
use std::time::{Duration, Instant};

const DEFAULT_CONFIG_JSON: &str = r#"{
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
  "detect_media_apps": true,
  "pause_media_in_meetings": true,
  "check_updates_on_startup": true
}"#;

pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
pub const GITHUB_RELEASES_API_URL: &str =
    "https://api.github.com/repos/russellmilliner/easyeffects-auto-preset/releases/latest";
pub const GITHUB_RELEASES_PAGE_URL: &str =
    "https://github.com/russellmilliner/easyeffects-auto-preset/releases";

const KNOWN_MEETING_BINARIES: &[&str] = &[
    "zoom",
    "zoom.real",
    "teams",
    "slack",
    "discord",
    "discord-canary",
    "webex",
    "skype",
    "skypeforlinux",
    "signal-desktop",
    "telegram-desktop",
];

const MEETING_KEYWORDS: &[&str] = &[
    "meet.google.com",
    "google meet",
    "zoom meeting",
    "teams call",
    "slack huddle",
    "discord call",
    "webex",
    "gotomeeting",
    "chime",
];

/// Native music, movie, and video player binaries that should switch to `youtube_preset`.
const KNOWN_MEDIA_BINARIES: &[&str] = &[
    // Video & movie players / media centers
    "vlc",
    "mpv",
    "celluloid",
    "totem",
    "haruna",
    "dragon",
    "kaffeine",
    "smplayer",
    "mplayer",
    "parole",
    "clapper",
    "showtime",
    "bomi",
    "qmplay2",
    "kodi",
    "kodi.bin",
    "plex",
    "plexmediaplayer",
    "plex-htpc",
    "jellyfinmediaplayer",
    "jellyfin-mpv-shim",
    "stremio",
    "freetube",
    "newpipe",
    "pipeline",
    "tubefeeder",
    "hypnotix",
    "ffplay",
    // Music players & audio streaming apps
    "spotify",
    "nuclear",
    "tidal-hifi",
    "high-tide",
    "qobuz",
    "deezer",
    "cider",
    "apple-music",
    "youtube-music",
    "pear-desktop",
    "spotube",
    "psst",
    "ncspot",
    "spotifyd",
    "elisa",
    "strawberry",
    "clementine",
    "rhythmbox",
    "amberol",
    "lollypop",
    "g4music",
    "gapless",
    "audacious",
    "deadbeef",
    "qmmp",
    "cmus",
    "mpd",
    "cantata",
    "amarok",
    "pragha",
    "sayonara",
    "quodlibet",
    "fooyin",
    "tauonmb",
    "tauon",
    "feishin",
    "supersonic",
    "finamp",
    "sonixd",
    "harmony",
    "plexamp",
    "radiotray-ng",
    "shortwave",
    "goodvibes",
    "gradio",
];

/// Flatpak / desktop portal application IDs for music, movie, and video applications.
const KNOWN_MEDIA_APP_IDS: &[&str] = &[
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
];

/// Keywords in `media.name` or `application.name` for web & desktop music, movie, and video streams.
const MEDIA_KEYWORDS: &[&str] = &[
    // Video & movie streaming / players
    "youtube",
    "youtu.be",
    "netflix",
    "disney+",
    "disneyplus",
    "prime video",
    "amazon video",
    "hulu",
    "hbomax",
    "max.com",
    "peacock",
    "paramount+",
    "apple tv",
    "crunchyroll",
    "twitch",
    "vimeo",
    "dailymotion",
    "nebula",
    "curiositystream",
    "plex",
    "jellyfin",
    "emby",
    "kodi",
    "vlc",
    "mpv",
    "celluloid",
    "haruna",
    "totem",
    "clapper",
    "stremio",
    "freetube",
    "smplayer",
    "dragon player",
    // Music streaming & desktop players
    "spotify",
    "soundcloud",
    "tidal",
    "deezer",
    "qobuz",
    "bandcamp",
    "pandora",
    "apple music",
    "amazon music",
    "iheart",
    "tunein",
    "mixcloud",
    "audiomack",
    "pocket casts",
    "overcast",
    "elisa",
    "strawberry",
    "rhythmbox",
    "clementine",
    "amberol",
    "lollypop",
    "audacious",
    "deadbeef",
    "plexamp",
    "feishin",
    "supersonic",
];

/// PipeWire / PulseAudio `media.role` values that denote music, movie, or video playback.
const MEDIA_ROLES: &[&str] = &["music", "video", "movie"];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default = "default_youtube_preset")]
    pub youtube_preset: String,
    #[serde(default = "default_meeting_preset")]
    pub meeting_preset: String,
    #[serde(default = "default_youtube_preset")]
    pub default_preset: String,
    #[serde(default)]
    pub meeting_mic_preset: String,
    #[serde(default)]
    pub apply_mic_preset: bool,
    #[serde(default = "default_debounce")]
    pub debounce_seconds: f64,
    #[serde(default = "default_interval")]
    pub check_interval_seconds: f64,
    #[serde(default = "default_true")]
    pub detect_microphone: bool,
    #[serde(default = "default_true")]
    pub detect_communication_role: bool,
    #[serde(default = "default_true")]
    pub detect_meeting_apps: bool,
    #[serde(default = "default_true")]
    pub detect_youtube: bool,
    #[serde(default = "default_true")]
    pub detect_media_apps: bool,
    #[serde(default = "default_true")]
    pub pause_media_in_meetings: bool,
    #[serde(default = "default_true")]
    pub check_updates_on_startup: bool,
}

fn default_true() -> bool {
    true
}
fn default_youtube_preset() -> String {
    "Crystal more Bass".to_string()
}
fn default_meeting_preset() -> String {
    "Compressed-Max".to_string()
}
fn default_debounce() -> f64 {
    2.0
}
fn default_interval() -> f64 {
    1.0
}

impl Default for Config {
    fn default() -> Self {
        serde_json::from_str(DEFAULT_CONFIG_JSON).unwrap()
    }
}

pub fn get_config_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    PathBuf::from(home)
        .join(".config")
        .join("easyeffects-auto-preset")
        .join("config.json")
}

pub fn load_config() -> Config {
    let path = get_config_path();
    if let Ok(contents) = fs::read_to_string(&path) {
        if let Ok(cfg) = serde_json::from_str(&contents) {
            return cfg;
        }
    }
    Config::default()
}

pub fn get_easyeffects_cmd() -> (String, Vec<String>) {
    if Command::new("which")
        .arg("easyeffects")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
    {
        ("easyeffects".to_string(), vec![])
    } else {
        (
            "flatpak".to_string(),
            vec![
                "run".to_string(),
                "--command=easyeffects".to_string(),
                "com.github.wwmm.easyeffects".to_string(),
            ],
        )
    }
}

pub fn apply_preset(output_preset: &str, input_preset: Option<&str>) -> bool {
    let (cmd, base_args) = get_easyeffects_cmd();
    let mut args = base_args.clone();
    args.push("-l".to_string());
    args.push(output_preset.to_string());

    let status = Command::new(&cmd)
        .args(&args)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    let success = status.map(|s| s.success()).unwrap_or(false);

    if let Some(in_preset) = input_preset {
        if !in_preset.is_empty() && in_preset != "(None)" {
            let mut in_args = base_args;
            in_args.push("--load-preset".to_string());
            in_args.push(in_preset.to_string());
            let _ = Command::new(&cmd).args(&in_args).status();
        }
    }

    success
}

pub fn get_current_loaded_preset() -> String {
    let (cmd, mut args) = get_easyeffects_cmd();
    args.push("-s".to_string());
    if let Ok(out) = Command::new(&cmd).args(&args).output() {
        let text = String::from_utf8_lossy(&out.stdout);
        for line in text.lines() {
            if line.starts_with("output:") {
                return line.replace("output:", "").trim().to_string();
            }
        }
    }
    String::new()
}

pub fn list_available_presets() -> (Vec<String>, Vec<String>) {
    let (cmd, mut args) = get_easyeffects_cmd();
    args.push("-p".to_string());
    let mut outputs = Vec::new();
    let mut inputs = Vec::new();

    if let Ok(out) = Command::new(&cmd).args(&args).output() {
        let text = String::from_utf8_lossy(&out.stdout);
        let mut section = "";
        for line in text.lines() {
            let trimmed = line.trim();
            if trimmed.contains("Output presets:") {
                section = "output";
                continue;
            } else if trimmed.contains("Input presets:") {
                section = "input";
                continue;
            }

            if !trimmed.is_empty() && !trimmed.starts_with("No ") {
                let parts: Vec<&str> = trimmed.split('\t').collect();
                let name = if parts.len() > 1 {
                    parts[1].trim()
                } else {
                    let sp: Vec<&str> = trimmed.split_whitespace().collect();
                    if sp.len() > 1 && sp[0].parse::<u32>().is_ok() {
                        &trimmed[sp[0].len()..].trim()
                    } else {
                        trimmed
                    }
                };
                if !name.is_empty() {
                    if section == "output" {
                        outputs.push(name.to_string());
                    } else if section == "input" {
                        inputs.push(name.to_string());
                    }
                }
            }
        }
    }

    // Fallback directly to Flatpak directory
    if outputs.is_empty() {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        let p = Path::new(&home).join(".var/app/com.github.wwmm.easyeffects/data/easyeffects/output");
        if let Ok(entries) = fs::read_dir(p) {
            for entry in entries.flatten() {
                if let Some(stem) = entry.path().file_stem() {
                    outputs.push(stem.to_string_lossy().to_string());
                }
            }
        }
    }

    outputs.sort();
    inputs.sort();
    (outputs, inputs)
}

fn parse_pactl_blocks(raw: &str, block_prefix: &str) -> Vec<HashMap<String, String>> {
    let mut blocks = Vec::new();
    let mut current: Option<HashMap<String, String>> = None;

    for line in raw.lines() {
        if line.starts_with(block_prefix) {
            if let Some(b) = current.take() {
                blocks.push(b);
            }
            let mut map = HashMap::new();
            if let Some(id) = line.split('#').last() {
                map.insert("id".to_string(), id.trim().to_string());
            }
            current = Some(map);
        } else if let Some(ref mut map) = current {
            let trimmed = line.trim();
            if trimmed.contains('=') && !trimmed.contains("Properties:") {
                let parts: Vec<&str> = trimmed.splitn(2, '=').collect();
                let k = parts[0].trim().to_string();
                let v = parts[1].trim().trim_matches('"').to_string();
                map.insert(k, v);
            } else if trimmed.contains(':') {
                let parts: Vec<&str> = trimmed.splitn(2, ':').collect();
                let k = parts[0].trim().to_string();
                let v = parts[1].trim().trim_matches('"').to_string();
                map.insert(k, v);
            }
        }
    }
    if let Some(b) = current {
        blocks.push(b);
    }
    blocks
}

#[derive(Debug)]
pub struct AudioEvaluation {
    pub meeting_active: bool,
    pub youtube_playing: bool,
    pub meeting_info: String,
    pub youtube_info: String,
}

/// Inspects a single PipeWire / PulseAudio sink-input property map to determine whether
/// it represents active YouTube, music, movie, or video playback.
pub fn detect_media_playback_stream(sk: &HashMap<String, String>, config: &Config) -> Option<String> {
    if !config.detect_youtube && !config.detect_media_apps {
        return None;
    }

    let app = sk.get("application.name").cloned().unwrap_or_default();
    let binary = sk
        .get("application.process.binary")
        .cloned()
        .unwrap_or_default()
        .to_lowercase();
    let media = sk.get("media.name").cloned().unwrap_or_default();
    let role = sk
        .get("media.role")
        .cloned()
        .unwrap_or_default()
        .to_lowercase();
    let app_id = sk
        .get("pipewire.access.portal.app_id")
        .or_else(|| sk.get("application.id"))
        .cloned()
        .unwrap_or_default()
        .to_lowercase();

    let app_lower = app.to_lowercase();
    let media_lower = media.to_lowercase();

    // Ignore speech-dispatcher dummy or EasyEffects internal streams
    if binary.contains("speech-dispatcher")
        || binary.contains("sd_dummy")
        || binary.contains("easyeffects")
        || app_lower.contains("speech-dispatcher")
        || app_lower.contains("easyeffects")
    {
        return None;
    }

    let display_label = if !media.is_empty() && !app.is_empty() {
        format!("{} ({})", media, app)
    } else if !app.is_empty() {
        app.clone()
    } else if !media.is_empty() {
        media.clone()
    } else {
        binary.clone()
    };

    // 1. Check native music / movie / video binaries and Flatpak app IDs
    if config.detect_media_apps || config.detect_youtube {
        if KNOWN_MEDIA_BINARIES.contains(&binary.as_str()) {
            return Some(format!("Media App: {}", display_label));
        }
        if !app_id.is_empty() && KNOWN_MEDIA_APP_IDS.iter().any(|id| app_id.contains(id)) {
            return Some(format!("Media App: {}", display_label));
        }
        if MEDIA_ROLES.contains(&role.as_str()) {
            return Some(format!("Media ({}): {}", role, display_label));
        }
    }

    // 2. Check YouTube, music, movie, and video streaming keywords in media.name or application.name
    if config.detect_youtube || config.detect_media_apps {
        if media_lower.contains("youtube") || app_lower.contains("youtube") {
            return Some(format!("YouTube: {}", display_label));
        }
        for kw in MEDIA_KEYWORDS {
            if media_lower.contains(kw) || app_lower.contains(kw) {
                return Some(format!("Media ({}): {}", kw, display_label));
            }
        }
    }

    None
}

pub fn evaluate_audio_streams(config: &Config) -> AudioEvaluation {
    let mut eval = AudioEvaluation {
        meeting_active: false,
        youtube_playing: false,
        meeting_info: String::new(),
        youtube_info: String::new(),
    };

    // 1. Check microphone recording (source-outputs)
    if let Ok(out) = Command::new("pactl").args(["list", "source-outputs"]).output() {
        let text = String::from_utf8_lossy(&out.stdout);
        let sources = parse_pactl_blocks(&text, "Source Output #");
        for sc in sources {
            let app = sc.get("application.name").cloned().unwrap_or_default();
            let binary = sc.get("application.process.binary").cloned().unwrap_or_default().to_lowercase();
            let media = sc.get("media.name").cloned().unwrap_or_default();

            if binary.contains("speech-dispatcher") || binary.contains("sd_dummy") {
                continue;
            }

            if config.detect_microphone {
                eval.meeting_active = true;
                eval.meeting_info = format!("Microphone in use by {} ({})", app, media);
                break;
            }
        }
    }

    // 2. Check playback streams (sink-inputs)
    if let Ok(out) = Command::new("pactl").args(["list", "sink-inputs"]).output() {
        let text = String::from_utf8_lossy(&out.stdout);
        let sinks = parse_pactl_blocks(&text, "Sink Input #");
        for sk in sinks {
            let corked = sk
                .get("Corked")
                .or_else(|| sk.get("pulse.corked"))
                .cloned()
                .unwrap_or_else(|| "yes".to_string())
                .to_lowercase();
            let is_playing = corked == "no" || corked == "false";

            let app = sk.get("application.name").cloned().unwrap_or_default();
            let binary = sk.get("application.process.binary").cloned().unwrap_or_default().to_lowercase();
            let media = sk.get("media.name").cloned().unwrap_or_default();
            let role = sk.get("media.role").cloned().unwrap_or_default().to_lowercase();

            if binary.contains("speech-dispatcher") || binary.contains("sd_dummy") {
                continue;
            }

            let mut is_sk_meeting = false;

            // Meeting detection via playback role or application
            if config.detect_meeting_apps && KNOWN_MEETING_BINARIES.contains(&binary.as_str()) {
                eval.meeting_active = true;
                is_sk_meeting = true;
                eval.meeting_info = format!("Meeting app: {} ({})", app, media);
            } else if config.detect_communication_role && (role == "communication" || role == "phone") {
                eval.meeting_active = true;
                is_sk_meeting = true;
                eval.meeting_info = format!("Communication audio stream ({})", app);
            } else {
                for kw in MEETING_KEYWORDS {
                    if media.to_lowercase().contains(kw) || app.to_lowercase().contains(kw) {
                        eval.meeting_active = true;
                        is_sk_meeting = true;
                        eval.meeting_info = format!("Meeting detected: {}", kw);
                        break;
                    }
                }
            }

            // YouTube, Music, Movie & Video playback detection (only when actively playing sound)
            if !is_sk_meeting && is_playing {
                if let Some(info) = detect_media_playback_stream(&sk, config) {
                    eval.youtube_playing = true;
                    eval.youtube_info = info;
                }
            }
        }
    }

    eval
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UpdateCheckResult {
    pub checked: bool,
    pub update_available: bool,
    pub current_version: String,
    pub latest_version: String,
    pub release_url: String,
    pub release_notes: String,
    pub message: String,
}

#[derive(Debug, Deserialize)]
struct GithubReleaseResponse {
    tag_name: String,
    #[serde(default)]
    html_url: String,
    #[serde(default)]
    body: Option<String>,
}

pub fn parse_semver(version: &str) -> Option<(u32, u32, u32)> {
    let trimmed = version.trim().trim_start_matches('v').trim_start_matches('V');
    let core = trimmed.split(['-', '+']).next().unwrap_or(trimmed);
    let mut parts = core.split('.');
    let major = parts.next()?.parse::<u32>().ok()?;
    let minor = parts.next().unwrap_or("0").parse::<u32>().ok()?;
    let patch = parts.next().unwrap_or("0").parse::<u32>().ok()?;
    Some((major, minor, patch))
}

pub fn is_newer_version(current: &str, latest: &str) -> bool {
    match (parse_semver(current), parse_semver(latest)) {
        (Some(cur), Some(lat)) => lat > cur,
        _ => {
            let cur_clean = current.trim().trim_start_matches(['v', 'V']);
            let lat_clean = latest.trim().trim_start_matches(['v', 'V']);
            !lat_clean.is_empty() && lat_clean != cur_clean
        }
    }
}

pub fn parse_github_release_json(body: &str, current_version: &str) -> Result<UpdateCheckResult, String> {
    let parsed: GithubReleaseResponse =
        serde_json::from_str(body).map_err(|e| format!("Invalid GitHub release JSON: {e}"))?;

    let latest_clean = parsed
        .tag_name
        .trim()
        .trim_start_matches(['v', 'V'])
        .to_string();
    let current_clean = current_version
        .trim()
        .trim_start_matches(['v', 'V'])
        .to_string();
    let latest_tag = if latest_clean.is_empty() {
        format!("v{current_clean}")
    } else {
        format!("v{latest_clean}")
    };
    let current_tag = format!("v{current_clean}");
    let update_available = is_newer_version(&current_clean, &latest_clean);
    let release_url = if parsed.html_url.trim().is_empty() {
        GITHUB_RELEASES_PAGE_URL.to_string()
    } else {
        parsed.html_url
    };
    let release_notes = parsed.body.unwrap_or_default();
    let message = if update_available {
        format!("Update available: {latest_tag} (current: {current_tag})")
    } else {
        format!("Up to date ({current_tag})")
    };

    Ok(UpdateCheckResult {
        checked: true,
        update_available,
        current_version: current_tag,
        latest_version: latest_tag,
        release_url,
        release_notes,
        message,
    })
}

pub fn check_for_updates(current_version: &str) -> Result<UpdateCheckResult, String> {
    let output = Command::new("curl")
        .args([
            "-fsSL",
            "--max-time",
            "8",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            &format!("User-Agent: EasyEffectsAutoPreset/{current_version}"),
            GITHUB_RELEASES_API_URL,
        ])
        .output()
        .map_err(|e| format!("Failed to invoke curl for update check: {e}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("GitHub API request failed: {}", stderr.trim()));
    }

    let body = String::from_utf8_lossy(&output.stdout);
    parse_github_release_json(&body, current_version)
}

pub fn pause_active_media_players() -> Vec<String> {
    let mut paused = Vec::new();
    let mut services = Vec::new();

    if let Ok(out) = Command::new("busctl").args(["--user", "list", "--no-legend"]).output() {
        let text = String::from_utf8_lossy(&out.stdout);
        for line in text.lines() {
            if let Some(svc) = line.split_whitespace().next() {
                if svc.starts_with("org.mpris.MediaPlayer2.") {
                    services.push(svc.to_string());
                }
            }
        }
    }

    for svc in services {
        let svc_lower = svc.to_lowercase();
        if ["zoom", "teams", "slack", "discord", "webex", "skype"]
            .iter()
            .any(|m| svc_lower.contains(m))
        {
            continue;
        }

        let is_playing = Command::new("busctl")
            .args([
                "--user",
                "get-property",
                &svc,
                "/org/mpris/MediaPlayer2",
                "org.mpris.MediaPlayer2.Player",
                "PlaybackStatus",
            ])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).contains("\"Playing\""))
            .unwrap_or(false);

        if !is_playing {
            continue;
        }

        let is_meeting_tab = Command::new("busctl")
            .args([
                "--user",
                "get-property",
                &svc,
                "/org/mpris/MediaPlayer2",
                "org.mpris.MediaPlayer2.Player",
                "Metadata",
            ])
            .output()
            .map(|o| {
                let meta = String::from_utf8_lossy(&o.stdout).to_lowercase();
                MEETING_KEYWORDS.iter().any(|kw| meta.contains(kw))
            })
            .unwrap_or(false);

        if is_meeting_tab {
            continue;
        }

        let ok = Command::new("busctl")
            .args([
                "--user",
                "call",
                &svc,
                "/org/mpris/MediaPlayer2",
                "org.mpris.MediaPlayer2.Player",
                "Pause",
            ])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);

        if !ok {
            let _ = Command::new("dbus-send")
                .args([
                    "--session",
                    "--type=method_call",
                    &format!("--dest={}", svc),
                    "/org/mpris/MediaPlayer2",
                    "org.mpris.MediaPlayer2.Player.Pause",
                ])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }

        let short_name = svc
            .trim_start_matches("org.mpris.MediaPlayer2.")
            .split('.')
            .next()
            .unwrap_or(&svc)
            .to_string();
        paused.push(short_name);
    }

    paused
}

pub fn enforce_single_instance_rust() {
    let my_pid = std::process::id();
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let cfg_dir = PathBuf::from(home).join(".config").join("easyeffects-auto-preset");
    let _ = fs::create_dir_all(&cfg_dir);
    let pid_file = cfg_dir.join("instance.pid");

    let mut candidate_pids = Vec::new();
    if let Ok(content) = fs::read_to_string(&pid_file) {
        if let Ok(old_pid) = content.trim().parse::<u32>() {
            if old_pid > 1 && old_pid != my_pid {
                candidate_pids.push(old_pid);
            }
        }
    }

    if let Ok(entries) = fs::read_dir("/proc") {
        for entry in entries.flatten() {
            if let Ok(pid) = entry.file_name().to_string_lossy().parse::<u32>() {
                if pid <= 1 || pid == my_pid {
                    continue;
                }
                let cmdline_path = entry.path().join("cmdline");
                if let Ok(raw) = fs::read(&cmdline_path) {
                    let args: Vec<String> = raw
                        .split(|&b| b == 0)
                        .filter(|s| !s.is_empty())
                        .map(|s| String::from_utf8_lossy(s).to_string())
                        .collect();
                    if args.is_empty() {
                        continue;
                    }
                    let joined = args.join(" ");
                    let is_target = joined.contains("easyeffects-auto-preset")
                        || joined.contains("easyeffects_auto_preset.py");
                    let is_one_shot = args.iter().skip(1).any(|a| {
                        matches!(
                            a.as_str(),
                            "--status"
                                | "-s"
                                | "--cli-status"
                                | "--switch"
                                | "--list-presets"
                                | "-l"
                                | "--install-presets"
                                | "--check-deps"
                                | "--check-update"
                                | "-u"
                                | "--version"
                                | "-V"
                                | "--help"
                                | "-h"
                        )
                    });
                    if is_target && !is_one_shot && !candidate_pids.contains(&pid) {
                        candidate_pids.push(pid);
                    }
                }
            }
        }
    }

    for pid in &candidate_pids {
        println!("[*] Terminating previous easyeffects-auto-preset instance (PID {})...", pid);
        let _ = Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }

    if !candidate_pids.is_empty() {
        for _ in 0..30 {
            let any_alive = candidate_pids
                .iter()
                .any(|p| Path::new(&format!("/proc/{}", p)).exists());
            if !any_alive {
                break;
            }
            sleep(Duration::from_millis(50));
        }
        for pid in &candidate_pids {
            if Path::new(&format!("/proc/{}", pid)).exists() {
                let _ = Command::new("kill")
                    .args(["-KILL", &pid.to_string()])
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .status();
            }
        }
    }

    let _ = fs::write(&pid_file, format!("{}\n", my_pid));
}

fn run_daemon(config: Config) {
    enforce_single_instance_rust();
    println!("EasyEffects Auto Preset Rust Daemon v{} starting...", APP_VERSION);
    println!("  YouTube Preset: {}", config.youtube_preset);
    println!("  Meeting Preset: {}", config.meeting_preset);
    println!("  Default Preset: {}", config.default_preset);
    println!("  Debounce:       {}s", config.debounce_seconds);

    if config.check_updates_on_startup {
        std::thread::spawn(|| {
            if let Ok(res) = check_for_updates(APP_VERSION) {
                if res.update_available {
                    println!(
                        "[*] Update available: {} -> {} ({})",
                        res.current_version, res.latest_version, res.release_url
                    );
                } else {
                    println!("[*] Update check: {}", res.message);
                }
            }
        });
    }

    let mut current_mode = "unknown".to_string();
    let mut last_preset = get_current_loaded_preset();
    let mut meeting_lost_at: Option<Instant> = None;
    let mut youtube_lost_at: Option<Instant> = None;

    let debounce = Duration::from_secs_f64(config.debounce_seconds);
    let interval = Duration::from_secs_f64(config.check_interval_seconds.max(0.5));

    loop {
        let eval = evaluate_audio_streams(&config);
        let now = Instant::now();

        let mut target_mode = "default".to_string();
        let mut reason = "Default / Idle".to_string();

        if eval.meeting_active {
            target_mode = "meeting".to_string();
            reason = eval.meeting_info;
            meeting_lost_at = None;
            if config.pause_media_in_meetings {
                let paused = pause_active_media_players();
                if !paused.is_empty() {
                    println!(
                        "[*] Paused active media application(s) during meeting: {}",
                        paused.join(", ")
                    );
                }
            }
        } else {
            if current_mode == "meeting" {
                let lost = meeting_lost_at.get_or_insert(now);
                if lost.elapsed() < debounce {
                    target_mode = "meeting".to_string();
                    reason = "Meeting (Grace period)".to_string();
                }
            }
        }

        if target_mode != "meeting" {
            if eval.youtube_playing {
                target_mode = "youtube".to_string();
                reason = eval.youtube_info;
                youtube_lost_at = None;
            } else {
                if current_mode == "youtube" {
                    let lost = youtube_lost_at.get_or_insert(now);
                    if lost.elapsed() < debounce {
                        target_mode = "youtube".to_string();
                        reason = "YouTube (Grace period)".to_string();
                    }
                }
            }
        }

        let target_preset = match target_mode.as_str() {
            "meeting" => &config.meeting_preset,
            "youtube" => &config.youtube_preset,
            _ => &config.default_preset,
        };

        let target_mic = if target_mode == "meeting" && config.apply_mic_preset {
            Some(config.meeting_mic_preset.as_str())
        } else {
            None
        };

        if target_mode != current_mode || target_preset != &last_preset {
            println!(
                "[*] Switching preset -> {} (Mode: {}, Reason: {})",
                target_preset, target_mode, reason
            );
            if apply_preset(target_preset, target_mic) {
                last_preset = target_preset.clone();
                current_mode = target_mode;
            }
        }

        sleep(interval);
    }
}

#[derive(Parser, Debug)]
#[command(
    name = "easyeffects-auto-preset",
    author = "Russell Milliner <russell.milliner@gmail.com>",
    version = "0.5.0",
    about = "Automated EasyEffects preset switcher for Voice Meetings, YouTube, Music, Movies, and Video on Linux (PipeWire / KDE Plasma)"
)]
struct Args {
    /// Run daemon in background mode
    #[arg(short, long)]
    daemon: bool,

    /// Print current loaded preset and audio state
    #[arg(short, long)]
    status: bool,

    /// Switch output preset immediately
    #[arg(short, long)]
    switch: Option<String>,

    /// List all available EasyEffects output and input presets
    #[arg(short, long)]
    list_presets: bool,

    /// Install all bundled Meeting-Voice and Media presets into EasyEffects and exit
    #[arg(long)]
    install_presets: bool,

    /// Check if EasyEffects and required audio packages are installed and exit
    #[arg(long)]
    check_deps: bool,

    /// Check GitHub Releases for a newer version and exit
    #[arg(short = 'u', long)]
    check_update: bool,
}

const BUNDLED_OUTPUT_PRESETS: &[(&str, &str)] = &[
    ("Meeting-Voice-Clear", include_str!("../presets/Meeting-Voice-Clear.json")),
    ("Meeting-Voice-Clear-Max-Level", include_str!("../presets/Meeting-Voice-Clear-Max-Level.json")),
    ("Meeting-Voice-Deep", include_str!("../presets/Meeting-Voice-Deep.json")),
    ("Meeting-Breath-Block-Max", include_str!("../presets/Meeting-Breath-Block-Max.json")),
    ("Meeting-Voice-Deep-Breath-Max", include_str!("../presets/Meeting-Voice-Deep-Breath-Max.json")),
    ("Crystal more Bass", include_str!("../presets/Crystal more Bass.json")),
    ("Compressed-Max", include_str!("../presets/Compressed-Max.json")),
];

const BUNDLED_INPUT_PRESETS: &[(&str, &str)] = &[
    ("Meeting-Mic-Clean", include_str!("../presets/Meeting-Mic-Clean.json")),
];

fn which_exists(bin: &str) -> bool {
    Command::new("which")
        .arg(bin)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

pub fn install_bundled_presets_rust() -> usize {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let flatpak_dir = Path::new(&home).join(".var/app/com.github.wwmm.easyeffects/data/easyeffects");
    let xdg_data = std::env::var("XDG_DATA_HOME").unwrap_or_else(|_| format!("{}/.local/share", home));
    let native_dir = Path::new(&xdg_data).join("easyeffects");

    let mut targets = Vec::new();
    if flatpak_dir.parent().map(|p| p.exists()).unwrap_or(false) {
        targets.push(flatpak_dir.clone());
    }
    if which_exists("easyeffects") || native_dir.exists() {
        targets.push(native_dir.clone());
    }
    if targets.is_empty() {
        targets.push(flatpak_dir);
        targets.push(native_dir);
    }

    let mut count = 0;
    for (name, content) in BUNDLED_OUTPUT_PRESETS {
        for base in &targets {
            let out_dir = base.join("output");
            let _ = fs::create_dir_all(&out_dir);
            let _ = fs::write(out_dir.join(format!("{}.json", name)), content);
        }
        count += 1;
    }
    for (name, content) in BUNDLED_INPUT_PRESETS {
        for base in &targets {
            let in_dir = base.join("input");
            let _ = fs::create_dir_all(&in_dir);
            let _ = fs::write(in_dir.join(format!("{}.json", name)), content);
        }
        count += 1;
    }
    count
}

pub fn check_dependencies_rust() -> bool {
    let native_ee = which_exists("easyeffects");
    let flatpak_ee = Command::new("flatpak")
        .args(["info", "com.github.wwmm.easyeffects"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false);
    let ee_ok = native_ee || flatpak_ee;
    let pactl_ok = which_exists("pactl");
    let pw_ok = which_exists("pw-cli") || which_exists("pipewire");

    println!("EasyEffects Auto Preset — System Dependency Check");
    println!("------------------------------------------------------------");
    println!(
        "{} EasyEffects [Required]: {}",
        if ee_ok { "✅" } else { "❌" },
        if flatpak_ee && native_ee {
            "Installed (Native + Flatpak)"
        } else if flatpak_ee {
            "Installed (Flatpak: com.github.wwmm.easyeffects)"
        } else if native_ee {
            "Installed (Native: easyeffects)"
        } else {
            "MISSING — Install via package manager or `flatpak install flathub com.github.wwmm.easyeffects`"
        }
    );
    println!(
        "{} pactl (PulseAudio/PipeWire CLI) [Required]: {}",
        if pactl_ok { "✅" } else { "❌" },
        if pactl_ok { "Installed" } else { "MISSING — Install `libpulse` or `pulseaudio-utils`" }
    );
    println!(
        "{} PipeWire [Recommended]: {}",
        if pw_ok { "✅" } else { "⚠️" },
        if pw_ok { "Installed" } else { "Not found in PATH" }
    );
    ee_ok && pactl_ok
}

fn main() {
    let args = Args::parse();
    let config = load_config();

    if args.install_presets {
        let count = install_bundled_presets_rust();
        println!("Successfully installed {} bundled presets into EasyEffects:", count);
        for (name, _) in BUNDLED_OUTPUT_PRESETS {
            println!("  • {} (Output)", name);
        }
        for (name, _) in BUNDLED_INPUT_PRESETS {
            println!("  • {} (Input)", name);
        }
        std::process::exit(0);
    }

    if args.check_deps {
        let ok = check_dependencies_rust();
        std::process::exit(if ok { 0 } else { 1 });
    }

    if args.check_update {
        println!("Checking for updates (current version: v{})...", APP_VERSION);
        match check_for_updates(APP_VERSION) {
            Ok(res) => {
                println!("{}", res.message);
                if res.update_available {
                    println!("Release URL: {}", res.release_url);
                }
                std::process::exit(0);
            }
            Err(err) => {
                eprintln!("Update check failed: {}", err);
                std::process::exit(1);
            }
        }
    }

    if let Some(ref preset) = args.switch {
        let ok = apply_preset(preset, None);
        if ok {
            println!("Successfully applied preset: {}", preset);
            std::process::exit(0);
        } else {
            eprintln!("Failed to apply preset: {}", preset);
            std::process::exit(1);
        }
    }

    if args.status {
        let cur = get_current_loaded_preset();
        let eval = evaluate_audio_streams(&config);
        println!("EasyEffects Auto Preset: v{}", APP_VERSION);
        println!("Current Loaded Preset:   {}", cur);
        println!("Meeting Active:          {} ({})", eval.meeting_active, eval.meeting_info);
        println!("YouTube / Media Playing: {} ({})", eval.youtube_playing, eval.youtube_info);
        std::process::exit(0);
    }

    if args.list_presets {
        let (out, inp) = list_available_presets();
        println!("Output Presets:");
        for p in out {
            println!("  • {}", p);
        }
        println!("\nInput Presets:");
        for p in inp {
            println!("  • {}", p);
        }
        std::process::exit(0);
    }

    if args.daemon {
        run_daemon(config);
    } else {
        println!("EasyEffects Auto Preset Rust CLI v{}", APP_VERSION);
        println!("Run with --daemon to start the background engine, --status to view audio state, or --check-update to check for new releases.");
        println!("Use --help for full options.");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_semver_comparison() {
        assert_eq!(parse_semver("v0.1.0"), Some((0, 1, 0)));
        assert_eq!(parse_semver("0.1.0"), Some((0, 1, 0)));
        assert!(is_newer_version("0.1.0", "v0.2.0"));
        assert!(is_newer_version("v0.1.0", "v0.1.1"));
        assert!(!is_newer_version("v0.1.0", "v0.1.0"));
        assert!(!is_newer_version("v0.2.0", "v0.1.9"));
    }

    #[test]
    fn test_parse_github_release_json() {
        let raw = r#"{
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/russellmilliner/easyeffects-auto-preset/releases/tag/v0.2.0",
            "body": "Release notes"
        }"#;
        let res = parse_github_release_json(raw, "0.1.0").expect("valid json");
        assert!(res.update_available);
        assert_eq!(res.current_version, "v0.1.0");
        assert_eq!(res.latest_version, "v0.2.0");

        let current = parse_github_release_json(raw, "0.2.0").expect("valid json");
        assert!(!current.update_available);
    }

    #[test]
    fn test_detect_music_movie_and_video_applications() {
        let cfg = Config::default();

        // 1. Native video player binary (VLC / mpv)
        let mut vlc = HashMap::new();
        vlc.insert("application.name".to_string(), "VLC media player".to_string());
        vlc.insert("application.process.binary".to_string(), "vlc".to_string());
        vlc.insert("media.name".to_string(), "Interstellar.mkv".to_string());
        let vlc_res = detect_media_playback_stream(&vlc, &cfg);
        assert!(vlc_res.is_some());
        assert!(vlc_res.unwrap().contains("Interstellar.mkv"));

        // 2. Native music player binary (Spotify / Elisa)
        let mut spotify = HashMap::new();
        spotify.insert("application.name".to_string(), "Spotify".to_string());
        spotify.insert("application.process.binary".to_string(), "spotify".to_string());
        spotify.insert("media.name".to_string(), "Daft Punk - Harder, Better, Faster, Stronger".to_string());
        assert!(detect_media_playback_stream(&spotify, &cfg).is_some());

        // 3. PipeWire media.role = "music" or "video" or "movie"
        let mut role_video = HashMap::new();
        role_video.insert("application.name".to_string(), "CustomPlayer".to_string());
        role_video.insert("media.role".to_string(), "video".to_string());
        role_video.insert("media.name".to_string(), "Movie Stream".to_string());
        assert!(detect_media_playback_stream(&role_video, &cfg).is_some());

        // 4. Web streaming movie / video in browser (Netflix / Plex / Twitch)
        let mut browser_movie = HashMap::new();
        browser_movie.insert("application.name".to_string(), "Zen".to_string());
        browser_movie.insert("application.process.binary".to_string(), "zen".to_string());
        browser_movie.insert("media.name".to_string(), "Netflix".to_string());
        assert!(detect_media_playback_stream(&browser_movie, &cfg).is_some());

        // 5. Speech dispatcher dummy should be ignored
        let mut dummy = HashMap::new();
        dummy.insert("application.name".to_string(), "speech-dispatcher-dummy".to_string());
        dummy.insert("application.process.binary".to_string(), "sd_dummy".to_string());
        dummy.insert("media.role".to_string(), "music".to_string());
        assert!(detect_media_playback_stream(&dummy, &cfg).is_none());
    }
}
