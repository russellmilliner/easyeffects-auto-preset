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
  "detect_youtube": true
}"#;

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

            // Meeting detection via playback role or application
            if config.detect_meeting_apps && KNOWN_MEETING_BINARIES.contains(&binary.as_str()) {
                eval.meeting_active = true;
                eval.meeting_info = format!("Meeting app: {} ({})", app, media);
            } else if config.detect_communication_role && (role == "communication" || role == "phone") {
                eval.meeting_active = true;
                eval.meeting_info = format!("Communication audio stream ({})", app);
            } else {
                for kw in MEETING_KEYWORDS {
                    if media.to_lowercase().contains(kw) || app.to_lowercase().contains(kw) {
                        eval.meeting_active = true;
                        eval.meeting_info = format!("Meeting detected: {}", kw);
                        break;
                    }
                }
            }

            // YouTube playback detection (only when actively playing sound)
            if config.detect_youtube && is_playing {
                if media.to_lowercase().contains("youtube") || app.to_lowercase().contains("youtube") {
                    eval.youtube_playing = true;
                    eval.youtube_info = format!("YouTube: {} ({})", media, app);
                }
            }
        }
    }

    eval
}

pub fn run_daemon(config: Config) {
    println!("EasyEffects Auto Preset Rust Daemon starting...");
    println!("  YouTube Preset: {}", config.youtube_preset);
    println!("  Meeting Preset: {}", config.meeting_preset);
    println!("  Default Preset: {}", config.default_preset);
    println!("  Debounce:       {}s", config.debounce_seconds);

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
    version = "0.1.0",
    about = "Automated EasyEffects preset switcher for YouTube and Voice Meetings on Linux (PipeWire / KDE Plasma)"
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
}

fn main() {
    let args = Args::parse();
    let config = load_config();

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
        println!("Current Loaded Preset: {}", cur);
        println!("Meeting Active:        {} ({})", eval.meeting_active, eval.meeting_info);
        println!("YouTube Playing:       {} ({})", eval.youtube_playing, eval.youtube_info);
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
        println!("EasyEffects Auto Preset Rust CLI");
        println!("Run with --daemon to start the background engine, or --status to view audio state.");
        println!("Use --help for full options.");
    }
}
