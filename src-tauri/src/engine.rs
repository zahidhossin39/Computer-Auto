use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::{AppHandle, Emitter};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

pub const APP_VERSION: &str = "2.3.0";
pub const CREATE_NO_WINDOW: u32 = 0x08000000;
const DEPRECATED_MODEL: &str = "google/gemini-3.1-flash-lite";
const DEFAULT_MODEL: &str = "google/gemini-2.5-flash";
const DEFAULT_API_BASE: &str = "https://openrouter.ai/api/v1";
const GITHUB_LATEST_RELEASE_URL: &str =
    "https://api.github.com/repos/zahidhossin39/Computer-Auto/releases/latest";

/// Create a `std::process::Command` that NEVER opens a console window on Windows.
pub fn no_window_cmd(program: &str) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    cmd
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct AppSettings {
    pub vision_model: String,
    pub vision_api_base: String,
    pub vision_api_key: String,
    pub stt_cloud_model: String,
    pub theme: String,
    pub max_vision_steps: u32,
    pub use_jev: bool,
    pub minimize_to_tray: bool,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            vision_model: DEFAULT_MODEL.to_string(),
            vision_api_base: DEFAULT_API_BASE.to_string(),
            vision_api_key: String::new(),
            stt_cloud_model: String::new(),
            theme: "dark".to_string(),
            max_vision_steps: 8,
            use_jev: true,
            minimize_to_tray: false,
        }
    }
}

impl AppSettings {
    pub fn migrate(&mut self) {
        if self.vision_model.trim().is_empty() || self.vision_model == DEPRECATED_MODEL {
            self.vision_model = DEFAULT_MODEL.to_string();
        }
        if self.stt_cloud_model == DEPRECATED_MODEL {
            self.stt_cloud_model = DEFAULT_MODEL.to_string();
        }
        if self.vision_api_base.trim().is_empty() {
            self.vision_api_base = DEFAULT_API_BASE.to_string();
        }
        if self.max_vision_steps == 0 {
            self.max_vision_steps = 8;
        }
    }

    pub fn to_frontend_json(&self) -> Value {
        let key = self.vision_api_key.trim();
        let has_local_model = locate_bridge_root()
            .map(|r| r.join("models").join("parakeet-tdt-0.6b-int8").exists())
            .unwrap_or(false);
        json!({
            "vision_model": self.vision_model,
            "vision_api_base": self.vision_api_base,
            "stt_cloud_model": self.stt_cloud_model,
            "theme": self.theme,
            "max_vision_steps": self.max_vision_steps,
            "use_jev": self.use_jev,
            "minimize_to_tray": self.minimize_to_tray,
            "has_api_key": !key.is_empty(),
            "masked_key": mask_api_key(key),
            "has_local_model": has_local_model,
            "app_version": APP_VERSION,
        })
    }
}

pub fn mask_api_key(key: &str) -> String {
    let trimmed = key.trim();
    if trimmed.is_empty() {
        return String::new();
    }
    if trimmed.len() <= 10 {
        return "****".to_string();
    }
    let prefix = &trimmed[..6];
    let suffix = &trimmed[trimmed.len() - 4..];
    format!("{prefix}...{suffix}")
}

pub fn appdata_dir() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Computer-Auto")
}

pub fn appdata_settings_path() -> PathBuf {
    appdata_dir().join("settings.json")
}

pub fn parse_env_key(contents: &str, key_name: &str) -> Option<String> {
    for raw_line in contents.lines() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let line = line.strip_prefix("export ").unwrap_or(line).trim();
        if let Some((k, v)) = line.split_once('=') {
            if k.trim() == key_name {
                let val = v.trim().trim_matches('"').trim_matches('\'').trim();
                if !val.is_empty() {
                    return Some(val.to_string());
                }
            }
        }
    }
    None
}

fn read_env_openrouter_key() -> Option<String> {
    if let Ok(env_val) = std::env::var("OPENROUTER_API_KEY") {
        let trimmed = env_val.trim();
        if !trimmed.is_empty() {
            return Some(trimmed.to_string());
        }
    }

    let mut candidates = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join(".env"));
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join(".env"));
    }
    candidates.push(appdata_dir().join(".env"));
    candidates.push(PathBuf::from(r"D:\Vibe-coding\Computer-Auto\.env"));

    for path in candidates {
        if let Ok(contents) = fs::read_to_string(&path) {
            if let Some(key) = parse_env_key(&contents, "OPENROUTER_API_KEY") {
                return Some(key);
            }
        }
    }
    None
}

fn read_settings_file(path: &Path) -> Option<AppSettings> {
    let raw = fs::read_to_string(path).ok()?;
    let mut parsed: AppSettings = serde_json::from_str(&raw).ok()?;
    parsed.migrate();
    Some(parsed)
}

pub fn load_and_sync_settings() -> AppSettings {
    let appdata_path = appdata_settings_path();
    let mut candidates = vec![appdata_path.clone()];
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("settings.json"));
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("settings.json"));
    }
    candidates.push(PathBuf::from(r"D:\Vibe-coding\Computer-Auto\settings.json"));

    let mut settings = candidates
        .iter()
        .find_map(|p| read_settings_file(p))
        .unwrap_or_default();

    let mut changed = false;
    if let Some(env_key) = read_env_openrouter_key() {
        if settings.vision_api_key.trim().is_empty() {
            settings.vision_api_key = env_key;
            changed = true;
        }
    }

    let old_model = settings.vision_model.clone();
    settings.migrate();
    if settings.vision_model != old_model {
        changed = true;
    }

    if changed || !appdata_path.exists() {
        let _ = write_settings_file(&appdata_path, &settings);
    }

    settings
}

fn write_settings_file(path: &Path, settings: &AppSettings) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Failed to create dir: {e}"))?;
    }
    let mut base_obj = fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Map<String, Value>>(&s).ok())
        .unwrap_or_default();

    base_obj.insert("vision_model".into(), json!(settings.vision_model));
    base_obj.insert("vision_api_base".into(), json!(settings.vision_api_base));
    if !settings.vision_api_key.trim().is_empty() {
        base_obj.insert("vision_api_key".into(), json!(settings.vision_api_key));
        base_obj.insert("openrouter_api_key".into(), json!(settings.vision_api_key));
    }
    base_obj.insert("stt_cloud_model".into(), json!(settings.stt_cloud_model));
    base_obj.insert("theme".into(), json!(settings.theme));
    base_obj.insert("max_vision_steps".into(), json!(settings.max_vision_steps));
    base_obj.insert("use_jev".into(), json!(settings.use_jev));
    base_obj.insert("minimize_to_tray".into(), json!(settings.minimize_to_tray));

    let serialized =
        serde_json::to_string_pretty(&base_obj).map_err(|e| format!("Serialize error: {e}"))?;
    fs::write(path, serialized).map_err(|e| format!("Write error: {e}"))
}

pub fn apply_settings_patch(patch: &Value, current: &mut AppSettings) {
    if let Some(obj) = patch.as_object() {
        if let Some(v) = obj.get("vision_model").and_then(|v| v.as_str()) {
            current.vision_model = v.to_string();
        }
        if let Some(v) = obj
            .get("vision_api_base")
            .or_else(|| obj.get("base_url"))
            .and_then(|v| v.as_str())
        {
            current.vision_api_base = v.to_string();
        }
        if let Some(v) = obj
            .get("vision_api_key")
            .or_else(|| obj.get("openrouter_api_key"))
            .and_then(|v| v.as_str())
        {
            let trimmed = v.trim();
            if !trimmed.is_empty() && !trimmed.contains("...") {
                current.vision_api_key = trimmed.to_string();
            }
        }
        if let Some(v) = obj.get("stt_cloud_model").and_then(|v| v.as_str()) {
            current.stt_cloud_model = v.to_string();
        }
        if let Some(v) = obj.get("theme").and_then(|v| v.as_str()) {
            current.theme = v.to_string();
        }
        if let Some(v) = obj.get("max_vision_steps").and_then(|v| v.as_u64()) {
            current.max_vision_steps = v as u32;
        }
        if let Some(v) = obj.get("use_jev").and_then(|v| v.as_bool()) {
            current.use_jev = v;
        }
        if let Some(v) = obj.get("minimize_to_tray").and_then(|v| v.as_bool()) {
            current.minimize_to_tray = v;
        }
    }
    current.migrate();
}

pub fn save_settings_to_disk(patch: &Value, current: &mut AppSettings) -> Result<(), String> {
    apply_settings_patch(patch, current);
    write_settings_file(&appdata_settings_path(), current)?;
    let repo_settings = PathBuf::from(r"D:\Vibe-coding\Computer-Auto\settings.json");
    if repo_settings.exists() {
        let _ = write_settings_file(&repo_settings, current);
    }
    Ok(())
}

pub fn locate_bridge_root() -> Option<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        let mut cur = exe.parent().map(|p| p.to_path_buf());
        for _ in 0..4 {
            if let Some(dir) = cur {
                candidates.push(dir.clone());
                cur = dir.parent().map(|p| p.to_path_buf());
            }
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.clone());
        if let Some(parent) = cwd.parent() {
            candidates.push(parent.to_path_buf());
        }
    }
    candidates.push(PathBuf::from(r"D:\Vibe-coding\Computer-Auto"));

    candidates
        .into_iter()
        .find(|dir| dir.join("src").join("bridge.py").is_file())
}

pub struct SidecarBridge {
    stdin: Arc<Mutex<Option<ChildStdin>>>,
    child: Arc<Mutex<Option<Child>>>,
}

impl SidecarBridge {
    pub fn spawn(app: AppHandle, settings: &AppSettings) -> Option<Self> {
        let root = locate_bridge_root()?;
        let mut cmd = no_window_cmd("python");
        cmd.args(["-u", "-m", "src.bridge"])
            .current_dir(&root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUNBUFFERED", "1");

        if !settings.vision_api_key.trim().is_empty() {
            cmd.env("OPENROUTER_API_KEY", settings.vision_api_key.trim());
        }

        let mut child = cmd.spawn().ok()?;
        let stdin = child.stdin.take();
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();

        let stdin_arc = Arc::new(Mutex::new(stdin));
        let child_arc = Arc::new(Mutex::new(Some(child)));

        if let Some(out) = stdout {
            let app_clone = app.clone();
            thread::spawn(move || {
                let reader = BufReader::new(out);
                for line in reader.lines().map_while(Result::ok) {
                    let trimmed = line.trim();
                    if trimmed.is_empty() {
                        continue;
                    }
                    if let Ok(val) = serde_json::from_str::<Value>(trimmed) {
                        let _ = app_clone.emit("bridge-event", val);
                    }
                }
            });
        }

        if let Some(err) = stderr {
            thread::spawn(move || {
                let reader = BufReader::new(err);
                for _line in reader.lines().map_while(Result::ok) {
                    // Drain stderr so child never blocks on a full pipe.
                }
            });
        }

        Some(Self {
            stdin: stdin_arc,
            child: child_arc,
        })
    }

    pub fn is_alive(&self) -> bool {
        let mut guard = match self.child.lock() {
            Ok(g) => g,
            Err(_) => return false,
        };
        if let Some(ref mut ch) = *guard {
            matches!(ch.try_wait(), Ok(None))
        } else {
            false
        }
    }

    pub fn send_cmd(&self, payload: Value) -> Result<(), String> {
        if !self.is_alive() {
            return Err("Python bridge is not running".to_string());
        }
        let mut guard = self
            .stdin
            .lock()
            .map_err(|_| "Bridge stdin lock poisoned".to_string())?;
        let stdin = guard
            .as_mut()
            .ok_or_else(|| "Bridge stdin closed".to_string())?;
        let line = serde_json::to_string(&payload).map_err(|e| e.to_string())?;
        stdin
            .write_all(line.as_bytes())
            .and_then(|_| stdin.write_all(b"\n"))
            .and_then(|_| stdin.flush())
            .map_err(|e| format!("Bridge write failed: {e}"))
    }

    pub fn shutdown(&self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut ch) = guard.take() {
                let _ = ch.kill();
                let _ = ch.wait();
            }
        }
    }
}

// ============================================================================
// Layer 2: Native Windows Command & OpenRouter Fallback (Zero Python Needed)
// ============================================================================

#[cfg(windows)]
mod win32_input {
    const KEYEVENTF_KEYUP: u32 = 0x0002;
    const MOUSEEVENTF_WHEEL: u32 = 0x0800;

    #[link(name = "user32")]
    extern "system" {
        fn keybd_event(bVk: u8, bScan: u8, dwFlags: u32, dwExtraInfo: usize);
        fn mouse_event(dwFlags: u32, dx: u32, dy: u32, dwData: i32, dwExtraInfo: usize);
    }

    pub fn tap_vk(vk: u8) {
        unsafe {
            keybd_event(vk, 0, 0, 0);
            keybd_event(vk, 0, KEYEVENTF_KEYUP, 0);
        }
    }

    pub fn send_hotkey(vks: &[u8]) {
        unsafe {
            for &vk in vks {
                keybd_event(vk, 0, 0, 0);
            }
            for &vk in vks.iter().rev() {
                keybd_event(vk, 0, KEYEVENTF_KEYUP, 0);
            }
        }
    }

    pub fn scroll_wheel(delta: i32) {
        unsafe {
            mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0);
        }
    }
}

#[cfg(not(windows))]
mod win32_input {
    pub fn tap_vk(_vk: u8) {}
    pub fn send_hotkey(_vks: &[u8]) {}
    pub fn scroll_wheel(_delta: i32) {}
}

fn spawn_shell_open(target: &str) -> Result<(), String> {
    #[cfg(windows)]
    {
        no_window_cmd("cmd")
            .args(["/c", "start", "", target])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map(|_| ())
            .map_err(|e| format!("Failed to launch {target}: {e}"))
    }
    #[cfg(not(windows))]
    {
        Err(format!("Unsupported OS for launching {target}"))
    }
}

fn url_encode(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    for b in input.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char);
            }
            b' ' => out.push('+'),
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

fn key_name_to_vk(name: &str) -> Option<u8> {
    match name.trim().to_lowercase().as_str() {
        "ctrl" | "control" => Some(0x11),
        "alt" | "menu" => Some(0x12),
        "shift" => Some(0x10),
        "win" | "super" | "meta" => Some(0x5B),
        "enter" | "return" => Some(0x0D),
        "esc" | "escape" => Some(0x1B),
        "tab" => Some(0x09),
        "space" => Some(0x20),
        "backspace" => Some(0x08),
        "delete" | "del" => Some(0x2E),
        "left" => Some(0x25),
        "up" => Some(0x26),
        "right" => Some(0x27),
        "down" => Some(0x28),
        "printscreen" | "prtsc" => Some(0x2C),
        "f4" => Some(0x73),
        "f5" => Some(0x74),
        "f11" => Some(0x7A),
        s if s.len() == 1 => {
            let ch = s.chars().next()?.to_ascii_uppercase();
            if ch.is_ascii_alphanumeric() {
                Some(ch as u8)
            } else {
                None
            }
        }
        _ => None,
    }
}

pub fn type_text_native(text: &str) -> Result<(), String> {
    #[cfg(windows)]
    {
        let escaped = text.replace('\'', "''");
        let ps_script = format!("Set-Clipboard -Value '{escaped}'");
        let status = no_window_cmd("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command", &ps_script])
            .status()
            .map_err(|e| format!("Clipboard error: {e}"))?;
        if !status.success() {
            return Err("Failed to set clipboard text".to_string());
        }
        std::thread::sleep(std::time::Duration::from_millis(40));
        win32_input::send_hotkey(&[0x11, b'V']);
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = text;
        Err("Native typing only supported on Windows".to_string())
    }
}

pub fn map_app_alias(name: &str) -> Option<&'static str> {
    match name.trim().to_lowercase().as_str() {
        "notepad" => Some("notepad.exe"),
        "calc" | "calculator" => Some("calc.exe"),
        "mspaint" | "paint" => Some("mspaint.exe"),
        "explorer" | "file explorer" | "files" => Some("explorer.exe"),
        "chrome" | "google chrome" => Some("chrome"),
        "msedge" | "edge" | "microsoft edge" => Some("msedge"),
        "code" | "vscode" | "vs code" => Some("code"),
        "spotify" => Some("spotify:"),
        "discord" => Some("discord:"),
        "cmd" | "command prompt" => Some("cmd.exe"),
        "powershell" | "terminal" => Some("powershell.exe"),
        "settings" | "ms-settings:" | "windows settings" => Some("ms-settings:"),
        _ => None,
    }
}

fn find_chrome_exe() -> String {
    let candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ];
    for c in candidates {
        if Path::new(c).is_file() {
            return c.to_string();
        }
    }
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        let p = PathBuf::from(local).join(r"Google\Chrome\Application\chrome.exe");
        if p.is_file() {
            return p.to_string_lossy().to_string();
        }
    }
    "chrome".to_string()
}

pub fn resolve_chrome_profile_from_json(lower: &str, data: &Value) -> Option<(String, bool)> {
    if lower.contains(" and ") || lower.contains(" then ") {
        return None;
    }
    let is_gmail = ["gmail", "g mail", "mail", "email", "inbox"]
        .iter()
        .any(|k| lower.contains(k));
    let is_profile = ["profile", "account"].iter().any(|k| lower.contains(k));
    if !is_gmail && !is_profile {
        return None;
    }

    let profile_obj = data.get("profile")?;
    let info_cache = profile_obj.get("info_cache")?.as_object()?;

    let mut ordered_dirs: Vec<String> = Vec::new();
    if let Some(arr) = profile_obj.get("profiles_order").and_then(|v| v.as_array()) {
        for item in arr {
            if let Some(d) = item.as_str() {
                if info_cache.contains_key(d) && !ordered_dirs.iter().any(|x| x == d) {
                    ordered_dirs.push(d.to_string());
                }
            }
        }
    }
    let mut remaining: Vec<String> = info_cache
        .keys()
        .filter(|k| !ordered_dirs.contains(k))
        .cloned()
        .collect();
    remaining.sort_by_key(|k| {
        if k == "Default" {
            (0usize, 0usize, k.clone())
        } else if let Some(num_str) = k.strip_prefix("Profile ") {
            if let Ok(n) = num_str.trim().parse::<usize>() {
                return (1usize, n, k.clone());
            }
            (2usize, 0usize, k.clone())
        } else {
            (2usize, 0usize, k.clone())
        }
    });
    ordered_dirs.extend(remaining);

    if ordered_dirs.is_empty() {
        return None;
    }

    let ordinal_pairs: &[(&[&str], usize)] = &[
        (&["1st", "first", "number 1", "1 number", "default", "primary"], 1),
        (&["2nd", "second", "number 2", "2 number"], 2),
        (&["3rd", "third", "number 3", "3 number"], 3),
        (&["4th", "fourth", "number 4", "4 number"], 4),
        (&["5th", "fifth", "number 5", "5 number"], 5),
        (&["6th", "sixth", "number 6", "6 number"], 6),
        (&["7th", "seventh", "number 7", "7 number"], 7),
        (&["8th", "eighth", "number 8", "8 number"], 8),
        (&["9th", "ninth", "number 9", "9 number"], 9),
        (&["10th", "tenth", "number 10", "10 number"], 10),
    ];

    let mut matched_idx: Option<usize> = None;
    for (tokens, idx) in ordinal_pairs {
        if tokens.iter().any(|t| lower.contains(t)) {
            matched_idx = Some(*idx);
            break;
        }
    }
    if matched_idx.is_none() {
        for word in lower.split_whitespace() {
            let trimmed = word.trim_matches(|c: char| !c.is_alphanumeric());
            if let Ok(n) = trimmed.parse::<usize>() {
                if (1..=10).contains(&n) {
                    matched_idx = Some(n);
                    break;
                }
            }
        }
    }

    let stop_words = [
        "open", "launch", "start", "go", "to", "switch", "use", "check", "in", "on", "from",
        "with", "for", "the", "my", "this", "chrome", "google", "browser", "gmail", "mail",
        "email", "inbox", "profile", "account", "number", "please",
    ];
    let query_tokens: Vec<&str> = lower
        .split(|c: char| !c.is_alphanumeric() && c != '@' && c != '.' && c != '_' && c != '-')
        .filter(|w| !w.is_empty() && !stop_words.contains(w))
        .collect();

    let target_dir = if let Some(idx) = matched_idx {
        ordered_dirs.get(idx - 1)?.clone()
    } else if query_tokens.contains(&"last") {
        ordered_dirs.last()?.clone()
    } else {
        if query_tokens.is_empty() {
            return None;
        }
        let mut found: Option<String> = None;
        for dir in &ordered_dirs {
            if let Some(meta) = info_cache.get(dir) {
                let email = meta
                    .get("user_name")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_lowercase();
                let name = meta
                    .get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_lowercase();
                let handle = email.split('@').next().unwrap_or("");
                if (!handle.is_empty() && query_tokens.iter().any(|t| *t == handle || handle.contains(t) && t.len() >= 4))
                    || (!name.is_empty() && name != "zaid" && query_tokens.iter().any(|t| *t == name))
                {
                    found = Some(dir.clone());
                    break;
                }
                for part in handle.split(['.', '_', '-']) {
                    if part.len() >= 3 && part != "zaid" && query_tokens.contains(&part) {
                        found = Some(dir.clone());
                        break;
                    }
                }
                if found.is_some() {
                    break;
                }
            }
        }
        found?
    };

    Some((target_dir, is_gmail))
}

pub fn try_chrome_profile_command(lower: &str) -> Option<Result<String, String>> {
    let local_app_data = std::env::var("LOCALAPPDATA").ok()?;
    let state_path = PathBuf::from(local_app_data)
        .join("Google")
        .join("Chrome")
        .join("User Data")
        .join("Local State");
    let raw = fs::read_to_string(state_path).ok()?;
    let data: Value = serde_json::from_str(&raw).ok()?;
    let (target_dir, is_gmail) = resolve_chrome_profile_from_json(lower, &data)?;

    let chrome_exe = find_chrome_exe();
    let mut cmd = no_window_cmd(&chrome_exe);
    cmd.arg(format!("--profile-directory={target_dir}"));
    if is_gmail {
        cmd.arg("https://mail.google.com");
    }
    Some(
        cmd.spawn()
            .map(|_| {
                if is_gmail {
                    format!("Opened Gmail in Chrome ({target_dir})")
                } else {
                    format!("Opened Chrome ({target_dir})")
                }
            })
            .map_err(|e| format!("Failed to launch Chrome profile {target_dir}: {e}")),
    )
}

pub fn try_native_command(raw_text: &str) -> Option<Result<String, String>> {
    let text = raw_text.trim();
    if text.is_empty() {
        return Some(Err("Empty command".to_string()));
    }
    let lower = text.to_lowercase();

    if let Some(res) = try_chrome_profile_command(&lower) {
        return Some(res);
    }

    // Volume & Media
    if matches!(
        lower.as_str(),
        "volume up" | "turn up volume" | "increase volume" | "louder"
    ) {
        win32_input::tap_vk(0xAF);
        return Some(Ok("Volume increased".into()));
    }
    if matches!(
        lower.as_str(),
        "volume down" | "turn down volume" | "decrease volume" | "lower volume" | "softer"
    ) {
        win32_input::tap_vk(0xAE);
        return Some(Ok("Volume decreased".into()));
    }
    if matches!(
        lower.as_str(),
        "mute" | "mute audio" | "mute volume" | "unmute" | "silence"
    ) {
        win32_input::tap_vk(0xAD);
        return Some(Ok("Toggled mute".into()));
    }
    if matches!(
        lower.as_str(),
        "play" | "pause" | "resume" | "play music" | "pause music" | "play pause"
    ) {
        win32_input::tap_vk(0xB3);
        return Some(Ok("Toggled media playback".into()));
    }
    if matches!(
        lower.as_str(),
        "next track" | "next song" | "skip" | "skip song"
    ) {
        win32_input::tap_vk(0xB0);
        return Some(Ok("Skipped to next track".into()));
    }
    if matches!(
        lower.as_str(),
        "previous track" | "previous song" | "restart song"
    ) {
        win32_input::tap_vk(0xB1);
        return Some(Ok("Previous track".into()));
    }

    // Window management
    if matches!(lower.as_str(), "minimize" | "minimize window" | "hide window") {
        win32_input::send_hotkey(&[0x5B, 0x28]);
        return Some(Ok("Minimized active window".into()));
    }
    if matches!(lower.as_str(), "maximize" | "maximize window") {
        win32_input::send_hotkey(&[0x5B, 0x26]);
        return Some(Ok("Maximized active window".into()));
    }
    if matches!(lower.as_str(), "restore" | "restore window") {
        win32_input::send_hotkey(&[0x5B, 0x28]);
        return Some(Ok("Restored window".into()));
    }
    if matches!(lower.as_str(), "close window" | "close app") {
        win32_input::send_hotkey(&[0x12, 0x73]);
        return Some(Ok("Closed active window".into()));
    }
    if matches!(lower.as_str(), "snap left" | "snap window left") {
        win32_input::send_hotkey(&[0x5B, 0x25]);
        return Some(Ok("Snapped window left".into()));
    }
    if matches!(lower.as_str(), "snap right" | "snap window right") {
        win32_input::send_hotkey(&[0x5B, 0x27]);
        return Some(Ok("Snapped window right".into()));
    }

    // Browser controls
    if matches!(lower.as_str(), "new tab" | "new browser tab" | "open new tab") {
        win32_input::send_hotkey(&[0x11, b'T']);
        return Some(Ok("Opened new tab".into()));
    }
    if matches!(lower.as_str(), "close tab" | "close current tab") {
        win32_input::send_hotkey(&[0x11, b'W']);
        return Some(Ok("Closed tab".into()));
    }
    if matches!(lower.as_str(), "next tab" | "switch tab") {
        win32_input::send_hotkey(&[0x11, 0x09]);
        return Some(Ok("Switched to next tab".into()));
    }
    if matches!(lower.as_str(), "refresh" | "reload" | "refresh page") {
        win32_input::tap_vk(0x74);
        return Some(Ok("Refreshed page".into()));
    }

    // Scroll & Screenshot
    if matches!(lower.as_str(), "scroll up" | "page up") {
        win32_input::scroll_wheel(360);
        return Some(Ok("Scrolled up".into()));
    }
    if matches!(lower.as_str(), "scroll down" | "page down") {
        win32_input::scroll_wheel(-360);
        return Some(Ok("Scrolled down".into()));
    }
    if matches!(
        lower.as_str(),
        "take screenshot" | "screenshot" | "capture screen"
    ) {
        win32_input::send_hotkey(&[0x5B, 0x2C]);
        return Some(Ok("Screenshot captured".into()));
    }

    // Type / Dictate
    for prefix in ["type ", "dictate "] {
        if let Some(rest) = lower.strip_prefix(prefix) {
            let original = &text[text.len() - rest.len()..];
            return Some(
                type_text_native(original.trim()).map(|_| format!("Typed: {}", original.trim())),
            );
        }
    }

    // Search Google / YouTube
    for prefix in ["search youtube for ", "youtube search ", "youtube "] {
        if let Some(q) = lower.strip_prefix(prefix) {
            let query = text[text.len() - q.len()..].trim();
            if !query.is_empty() {
                let url = format!(
                    "https://www.youtube.com/results?search_query={}",
                    url_encode(query)
                );
                return Some(spawn_shell_open(&url).map(|_| format!("Searching YouTube for {query}")));
            }
        }
    }
    for prefix in ["search google for ", "search for ", "google "] {
        if let Some(q) = lower.strip_prefix(prefix) {
            let query = text[text.len() - q.len()..].trim();
            if !query.is_empty() {
                let url = format!("https://www.google.com/search?q={}", url_encode(query));
                return Some(spawn_shell_open(&url).map(|_| format!("Searching Google for {query}")));
            }
        }
    }

    // Open URL or App
    for prefix in ["open ", "launch ", "start ", "go to "] {
        if let Some(target_lower) = lower.strip_prefix(prefix) {
            let target = text[text.len() - target_lower.len()..].trim();
            let clean_lower = target_lower
                .trim()
                .trim_start_matches("my ")
                .trim_start_matches("this ")
                .trim_start_matches("the ")
                .trim();
            if target.starts_with("http://") || target.starts_with("https://") {
                return Some(spawn_shell_open(target).map(|_| format!("Opened {target}")));
            }
            let site_url = match clean_lower {
                "gmail" | "g mail" | "email" | "inbox" => Some("https://mail.google.com"),
                "youtube" => Some("https://www.youtube.com"),
                "github" => Some("https://github.com"),
                "chatgpt" => Some("https://chatgpt.com"),
                "reddit" => Some("https://www.reddit.com"),
                _ => None,
            };
            if let Some(url) = site_url {
                return Some(spawn_shell_open(url).map(|_| format!("Opened {clean_lower}")));
            }
            if let Some(alias) = map_app_alias(clean_lower) {
                let resolved = if alias == "chrome" {
                    find_chrome_exe()
                } else {
                    alias.to_string()
                };
                return Some(spawn_shell_open(&resolved).map(|_| format!("Opened {target}")));
            }
            if target.contains('.') && !target.contains(' ') {
                let url = format!("https://{target}");
                return Some(spawn_shell_open(&url).map(|_| format!("Opened {url}")));
            }
        }
    }

    None
}

pub fn run_openrouter_fallback(text: &str, settings: &AppSettings) -> Result<String, String> {
    let api_key = settings.vision_api_key.trim();
    if api_key.is_empty() {
        return Err("No OpenRouter API key configured and command did not match built-in actions.".into());
    }

    let endpoint = format!(
        "{}/chat/completions",
        settings.vision_api_base.trim_end_matches('/')
    );
    let system_prompt = concat!(
        "You are Computer-Auto's Windows command router. ",
        "Return ONLY valid JSON with one of these actions:\n",
        "- {\"action\":\"open_app\",\"target\":\"notepad|calc|mspaint|explorer|chrome|msedge|code|spotify|discord|cmd|powershell|ms-settings:\"}\n",
        "- {\"action\":\"open_url\",\"target\":\"https://...\"}\n",
        "- {\"action\":\"hotkey\",\"keys\":[\"ctrl\",\"t\"]}\n",
        "- {\"action\":\"type_text\",\"text\":\"...\"}\n",
        "- {\"action\":\"reply\",\"message\":\"...\"}"
    );

    let body = json!({
        "model": settings.vision_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "max_tokens": 200,
        "temperature": 0.1
    });

    let resp: Value = ureq::post(&endpoint)
        .set("Authorization", &format!("Bearer {api_key}"))
        .set("Content-Type", "application/json")
        .send_json(body)
        .map_err(|e| format!("OpenRouter request failed: {e}"))?
        .into_json()
        .map_err(|e| format!("Invalid OpenRouter JSON: {e}"))?;

    let content = resp["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("")
        .trim();
    let cleaned = content
        .trim_start_matches("```json")
        .trim_start_matches("```")
        .trim_end_matches("```")
        .trim();

    let parsed: Value = serde_json::from_str(cleaned)
        .map_err(|_| format!("AI replied: {cleaned}"))?;

    match parsed["action"].as_str().unwrap_or("reply") {
        "open_app" => {
            let t = parsed["target"].as_str().unwrap_or("");
            let mapped = map_app_alias(t).unwrap_or(t);
            spawn_shell_open(mapped)?;
            Ok(format!("Opened {t}"))
        }
        "open_url" => {
            let u = parsed["target"].as_str().unwrap_or("");
            spawn_shell_open(u)?;
            Ok(format!("Opened {u}"))
        }
        "hotkey" => {
            let vks: Vec<u8> = parsed["keys"]
                .as_array()
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().and_then(key_name_to_vk))
                        .collect()
                })
                .unwrap_or_default();
            if vks.is_empty() {
                return Err("AI returned empty hotkey".into());
            }
            win32_input::send_hotkey(&vks);
            Ok("Executed hotkey".into())
        }
        "type_text" => {
            let t = parsed["text"].as_str().unwrap_or("");
            type_text_native(t)?;
            Ok(format!("Typed: {t}"))
        }
        _ => Ok(parsed["message"]
            .as_str()
            .unwrap_or("Command processed")
            .to_string()),
    }
}

// ============================================================================
// Built-in GitHub Releases Self-Updater
// ============================================================================

pub fn parse_semver(tag: &str) -> (u32, u32, u32) {
    let cleaned = tag.trim().trim_start_matches(['v', 'V']);
    let core = cleaned.split('-').next().unwrap_or(cleaned);
    let mut parts = core.split('.').filter_map(|p| p.parse::<u32>().ok());
    (
        parts.next().unwrap_or(0),
        parts.next().unwrap_or(0),
        parts.next().unwrap_or(0),
    )
}

pub fn is_newer_version(latest_tag: &str, current_version: &str) -> bool {
    parse_semver(latest_tag) > parse_semver(current_version)
}

pub fn select_best_windows_asset(assets: &[Value]) -> Option<(String, String)> {
    let mut setup_match: Option<(String, String)> = None;
    let mut exe_match: Option<(String, String)> = None;

    for asset in assets {
        let name = asset["name"].as_str().unwrap_or("");
        let url = asset["browser_download_url"].as_str().unwrap_or("");
        if name.is_empty() || url.is_empty() {
            continue;
        }
        let lower = name.to_lowercase();
        if lower.ends_with(".exe") {
            if lower.contains("setup") || lower.contains("installer") {
                setup_match = Some((name.to_string(), url.to_string()));
                break;
            } else if exe_match.is_none() {
                exe_match = Some((name.to_string(), url.to_string()));
            }
        }
    }
    setup_match.or(exe_match)
}

pub fn check_update_impl() -> Result<Value, String> {
    let resp: Value = ureq::get(GITHUB_LATEST_RELEASE_URL)
        .set("User-Agent", &format!("Computer-Auto/{APP_VERSION}"))
        .set("Accept", "application/vnd.github+json")
        .call()
        .map_err(|e| format!("Update check failed: {e}"))?
        .into_json()
        .map_err(|e| format!("Invalid GitHub JSON: {e}"))?;

    let tag = resp["tag_name"].as_str().unwrap_or(APP_VERSION);
    let latest_version = tag.trim().trim_start_matches(['v', 'V']).to_string();
    let update_available = is_newer_version(&latest_version, APP_VERSION);
    let assets = resp["assets"].as_array().map(|a| a.as_slice()).unwrap_or(&[]);
    let best = select_best_windows_asset(assets);

    Ok(json!({
        "update_available": update_available,
        "current_version": APP_VERSION,
        "latest_version": latest_version,
        "asset_name": best.as_ref().map(|(n, _)| n.clone()),
        "download_url": best.as_ref().map(|(_, u)| u.clone()),
        "release_notes": resp["body"].as_str().unwrap_or("").to_string(),
    }))
}

pub fn install_update_impl(app: &AppHandle) -> Result<String, String> {
    let info = check_update_impl()?;
    let url = info["download_url"]
        .as_str()
        .ok_or_else(|| "No Windows .exe asset found in latest release".to_string())?;
    let name = info["asset_name"]
        .as_str()
        .unwrap_or("Computer-Auto-Update.exe");

    let temp_path = std::env::temp_dir().join(name);
    let resp = ureq::get(url)
        .set("User-Agent", &format!("Computer-Auto/{APP_VERSION}"))
        .call()
        .map_err(|e| format!("Download failed: {e}"))?;

    let mut reader = resp.into_reader();
    let mut file =
        fs::File::create(&temp_path).map_err(|e| format!("Failed to create temp file: {e}"))?;
    let mut buf = [0u8; 65536];
    loop {
        let n = reader.read(&mut buf).map_err(|e| format!("Read error: {e}"))?;
        if n == 0 {
            break;
        }
        file.write_all(&buf[..n])
            .map_err(|e| format!("Write error: {e}"))?;
    }
    drop(file);

    no_window_cmd(&temp_path.to_string_lossy())
        .spawn()
        .map_err(|e| format!("Failed to launch updater: {e}"))?;

    app.exit(0);
    Ok(format!("Launched installer: {name}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_env_key_strips_quotes_and_comments() {
        let env_text = r#"
# comment
FOO=bar
OPENROUTER_API_KEY="sk-or-v1-test123456"
"#;
        assert_eq!(
            parse_env_key(env_text, "OPENROUTER_API_KEY").as_deref(),
            Some("sk-or-v1-test123456")
        );
        assert_eq!(parse_env_key(env_text, "MISSING"), None);
    }

    #[test]
    fn test_deprecated_model_migrates_to_gemini_2_5_flash() {
        let mut s = AppSettings {
            vision_model: "google/gemini-3.1-flash-lite".into(),
            stt_cloud_model: "google/gemini-3.1-flash-lite".into(),
            ..Default::default()
        };
        s.migrate();
        assert_eq!(s.vision_model, "google/gemini-2.5-flash");
        assert_eq!(s.stt_cloud_model, "google/gemini-2.5-flash");
    }

    #[test]
    fn test_mask_api_key() {
        assert_eq!(mask_api_key(""), "");
        assert_eq!(mask_api_key("short"), "****");
        assert_eq!(mask_api_key("sk-or-v1-abcdef1234"), "sk-or-...1234");
    }

    #[test]
    fn test_semver_comparison() {
        assert!(is_newer_version("v2.0.1", "2.0.0"));
        assert!(is_newer_version("2.1.0", "2.0.0"));
        assert!(!is_newer_version("2.0.0", "2.0.0"));
        assert!(!is_newer_version("v1.9.9", "2.0.0"));
    }

    #[test]
    fn test_select_best_windows_asset_prefers_setup() {
        let assets = vec![
            json!({"name": "Computer-Auto.exe", "browser_download_url": "https://example.com/app.exe"}),
            json!({"name": "Computer-Auto-Setup.exe", "browser_download_url": "https://example.com/setup.exe"}),
        ];
        let picked = select_best_windows_asset(&assets).unwrap();
        assert_eq!(picked.0, "Computer-Auto-Setup.exe");
    }

    #[test]
    fn test_map_app_alias() {
        assert_eq!(map_app_alias("Calculator"), Some("calc.exe"));
        assert_eq!(map_app_alias("Notepad"), Some("notepad.exe"));
        assert_eq!(map_app_alias("unknown-app"), None);
    }

    #[test]
    fn test_save_settings_accepts_frontend_aliases() {
        let mut s = AppSettings::default();
        let patch = json!({
            "base_url": "https://example.com/v1",
            "openrouter_api_key": "sk-or-v1-newkey123456"
        });
        apply_settings_patch(&patch, &mut s);
        assert_eq!(s.vision_api_base, "https://example.com/v1");
        assert_eq!(s.vision_api_key, "sk-or-v1-newkey123456");
    }

    #[test]
    fn test_resolve_chrome_profile_from_json() {
        let state = json!({
            "profile": {
                "profiles_order": ["Default", "Profile 2", "Profile 5", "Profile 8"],
                "info_cache": {
                    "Default": {"name": "Zaid hossain", "user_name": "zahidhossin39@gmail.com"},
                    "Profile 2": {"name": "Zaid", "user_name": "zahidhossin509@gmail.com"},
                    "Profile 5": {"name": "Zaid", "user_name": "zahidhosson28@gmail.com"},
                    "Profile 8": {"name": "Zaid.W", "user_name": "work.zaid.business@gmail.com"}
                }
            }
        });
        assert_eq!(
            resolve_chrome_profile_from_json("open 3rd gmail", &state),
            Some(("Profile 5".into(), true))
        );
        assert_eq!(
            resolve_chrome_profile_from_json("open third number profile", &state),
            Some(("Profile 5".into(), false))
        );
        assert_eq!(
            resolve_chrome_profile_from_json("open work gmail", &state),
            Some(("Profile 8".into(), true))
        );
        assert_eq!(
            resolve_chrome_profile_from_json("open last chrome profile", &state),
            Some(("Profile 8".into(), false))
        );
        // Plain "open gmail" without a specific profile should return None so site launcher handles it
        assert_eq!(resolve_chrome_profile_from_json("open gmail", &state), None);
        assert_eq!(resolve_chrome_profile_from_json("open my gmail", &state), None);
        // Out-of-bounds ordinal returns None
        assert_eq!(resolve_chrome_profile_from_json("open 9th gmail", &state), None);
    }
}
