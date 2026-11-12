pub mod engine;

use engine::{
    check_update_impl, install_update_impl, load_and_sync_settings, run_openrouter_fallback,
    save_settings_to_disk, try_native_command, AppSettings, SidecarBridge, APP_VERSION,
};
use serde_json::{json, Value};
use std::sync::Mutex;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, LogicalSize, Manager, RunEvent, Size, State};

pub struct AppState {
    pub settings: Mutex<AppSettings>,
    pub bridge: Mutex<Option<SidecarBridge>>,
    pub mic_active: Mutex<bool>,
    pub continuous: Mutex<bool>,
}

fn emit_bridge(app: &AppHandle, payload: Value) {
    let _ = app.emit("bridge-event", payload);
}

fn send_or_fallback<F>(app: &AppHandle, state: &AppState, cmd: Value, fallback: F) -> Result<Value, String>
where
    F: FnOnce() -> Result<Value, String>,
{
    if let Ok(guard) = state.bridge.lock() {
        if let Some(ref bridge) = *guard {
            if bridge.send_cmd(cmd).is_ok() {
                return Ok(json!({ "ok": true, "mode": "python-bridge" }));
            }
        }
    }
    let _ = app;
    fallback()
}

#[tauri::command]
fn get_initial_state(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    let settings_json = {
        let s = state.settings.lock().map_err(|_| "Settings lock error")?;
        s.to_frontend_json()
    };

    if let Ok(guard) = state.bridge.lock() {
        if let Some(ref bridge) = *guard {
            let _ = bridge.send_cmd(json!({ "cmd": "get_state" }));
        }
    }

    let mic = *state.mic_active.lock().map_err(|_| "Mic lock error")?;
    let continuous = *state.continuous.lock().map_err(|_| "Continuous lock error")?;
    let bridge_connected = state
        .bridge
        .lock()
        .map(|g| g.as_ref().map(|b| b.is_alive()).unwrap_or(false))
        .unwrap_or(false);

    emit_bridge(
        &app,
        json!({
            "event": "settings",
            "data": settings_json.clone()
        }),
    );

    Ok(json!({
        "state": if mic { "listening" } else { "ready" },
        "text": if bridge_connected { "Nova Ready" } else { "Nova Standalone Ready" },
        "detail": "",
        "mic_active": mic,
        "continuous": continuous,
        "bridge_connected": bridge_connected,
        "app_version": APP_VERSION,
        "settings": settings_json,
    }))
}

#[tauri::command]
fn run_command(app: AppHandle, state: State<'_, AppState>, text: String) -> Result<Value, String> {
    let trimmed = text.trim().to_string();
    if trimmed.is_empty() {
        return Err("Command cannot be empty".to_string());
    }

    send_or_fallback(
        &app,
        &state,
        json!({ "cmd": "run_command", "text": trimmed.clone() }),
        || {
            let settings = state
                .settings
                .lock()
                .map_err(|_| "Settings lock error")?
                .clone();
            let app_bg = app.clone();
            std::thread::spawn(move || {
                emit_bridge(
                    &app_bg,
                    json!({
                        "event": "state",
                        "state": "processing",
                        "text": trimmed.clone(),
                        "detail": "Executing natively..."
                    }),
                );

                let outcome = match try_native_command(&trimmed) {
                    Some(res) => res,
                    None => run_openrouter_fallback(&trimmed, &settings),
                };

                match outcome {
                    Ok(msg) => {
                        emit_bridge(
                            &app_bg,
                            json!({ "event": "log", "line": msg.clone(), "kind": "action" }),
                        );
                        emit_bridge(
                            &app_bg,
                            json!({ "event": "state", "state": "ready", "text": msg, "detail": "" }),
                        );
                    }
                    Err(err) => {
                        emit_bridge(
                            &app_bg,
                            json!({ "event": "log", "line": err.clone(), "kind": "error" }),
                        );
                        emit_bridge(
                            &app_bg,
                            json!({ "event": "state", "state": "error", "text": err, "detail": "" }),
                        );
                    }
                }
            });
            Ok(json!({ "ok": true, "mode": "rust-native" }))
        },
    )
}

#[tauri::command]
fn toggle_mic(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    let mut mic = state.mic_active.lock().map_err(|_| "Mic lock error")?;
    *mic = !*mic;
    let active = *mic;
    drop(mic);

    send_or_fallback(
        &app,
        &state,
        json!({ "cmd": "toggle_mic" }),
        || {
            emit_bridge(
                &app,
                json!({
                    "event": "state",
                    "state": if active { "listening" } else { "ready" },
                    "text": if active { "Listening..." } else { "Ready" },
                    "detail": if active { "Python bridge offline; type a command below." } else { "" }
                }),
            );
            Ok(json!({ "ok": true, "mic_active": active }))
        },
    )
}

#[tauri::command]
fn set_continuous(
    app: AppHandle,
    state: State<'_, AppState>,
    enabled: bool,
) -> Result<Value, String> {
    if let Ok(mut c) = state.continuous.lock() {
        *c = enabled;
    }
    send_or_fallback(
        &app,
        &state,
        json!({ "cmd": "set_continuous", "enabled": enabled }),
        || Ok(json!({ "ok": true, "continuous": enabled })),
    )
}

#[tauri::command]
fn trigger_panic(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    if let Ok(mut mic) = state.mic_active.lock() {
        *mic = false;
    }
    if let Ok(mut c) = state.continuous.lock() {
        *c = false;
    }
    send_or_fallback(
        &app,
        &state,
        json!({ "cmd": "panic" }),
        || {
            emit_bridge(
                &app,
                json!({
                    "event": "log",
                    "line": "PANIC STOP triggered",
                    "kind": "error"
                }),
            );
            emit_bridge(
                &app,
                json!({
                    "event": "state",
                    "state": "ready",
                    "text": "Stopped",
                    "detail": "Emergency stop"
                }),
            );
            Ok(json!({ "ok": true }))
        },
    )
}

#[tauri::command]
fn confirm_guardrail(
    app: AppHandle,
    state: State<'_, AppState>,
    approved: bool,
) -> Result<Value, String> {
    send_or_fallback(
        &app,
        &state,
        json!({ "cmd": "confirm_guardrail", "approved": approved }),
        || {
            emit_bridge(
                &app,
                json!({
                    "event": "state",
                    "state": "ready",
                    "text": if approved { "Action approved" } else { "Action cancelled" },
                    "detail": ""
                }),
            );
            Ok(json!({ "ok": true, "approved": approved }))
        },
    )
}

#[tauri::command]
fn save_settings(
    app: AppHandle,
    state: State<'_, AppState>,
    settings: Value,
) -> Result<Value, String> {
    let updated_json = {
        let mut s = state.settings.lock().map_err(|_| "Settings lock error")?;
        save_settings_to_disk(&settings, &mut s)?;
        s.to_frontend_json()
    };

    if let Ok(guard) = state.bridge.lock() {
        if let Some(ref bridge) = *guard {
            let _ = bridge.send_cmd(json!({ "cmd": "save_settings", "settings": settings }));
        }
    }

    emit_bridge(
        &app,
        json!({
            "event": "settings",
            "data": updated_json.clone()
        }),
    );

    Ok(updated_json)
}

#[tauri::command]
fn download_model(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    send_or_fallback(
        &app,
        &state,
        json!({ "cmd": "download_model" }),
        || {
            emit_bridge(
                &app,
                json!({
                    "event": "log",
                    "line": "Offline Parakeet downloader requires Python runtime.",
                    "kind": "info"
                }),
            );
            Err("Python bridge not available for model download".to_string())
        },
    )
}

#[tauri::command]
fn cancel_download(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    send_or_fallback(
        &app,
        &state,
        json!({ "cmd": "cancel_download" }),
        || Ok(json!({ "ok": true })),
    )
}

#[tauri::command]
fn check_update() -> Result<Value, String> {
    check_update_impl()
}

#[tauri::command]
fn install_update(app: AppHandle) -> Result<String, String> {
    install_update_impl(&app)
}

#[tauri::command]
fn set_always_on_top(app: AppHandle, pinned: bool) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("main") {
        win.set_always_on_top(pinned).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn set_compact_mode(app: AppHandle, compact: bool) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("main") {
        let size = if compact {
            LogicalSize::new(420.0, 560.0)
        } else {
            LogicalSize::new(1020.0, 740.0)
        };
        win.set_size(Size::Logical(size)).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn minimize_win(app: AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("main") {
        win.minimize().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn close_win(app: AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("main") {
        win.close().map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn show_and_focus_main(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.unminimize();
        let _ = win.show();
        let _ = win.set_focus();
    }
}

fn setup_tray(app: &AppHandle) -> tauri::Result<()> {
    let show_item = MenuItem::with_id(app, "tray_show", "Show / Hide", true, None::<&str>)?;
    let mic_item = MenuItem::with_id(app, "tray_mic", "Toggle Mic", true, None::<&str>)?;
    let panic_item = MenuItem::with_id(app, "tray_panic", "Panic Stop", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "tray_quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_item, &mic_item, &panic_item, &quit_item])?;

    let mut builder = TrayIconBuilder::with_id("main-tray")
        .menu(&menu)
        .tooltip("Computer-Auto v2.0")
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "tray_show" => {
                if let Some(win) = app.get_webview_window("main") {
                    if win.is_visible().unwrap_or(false) {
                        let _ = win.hide();
                    } else {
                        show_and_focus_main(app);
                    }
                }
            }
            "tray_mic" => {
                let state = app.state::<AppState>();
                let _ = toggle_mic(app.clone(), state);
            }
            "tray_panic" => {
                let state = app.state::<AppState>();
                let _ = trigger_panic(app.clone(), state);
            }
            "tray_quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_and_focus_main(tray.app_handle());
            }
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    builder.build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let initial_settings = load_and_sync_settings();

    let app = tauri::Builder::default()
        .manage(AppState {
            settings: Mutex::new(initial_settings.clone()),
            bridge: Mutex::new(None),
            mic_active: Mutex::new(false),
            continuous: Mutex::new(false),
        })
        .setup(|app| {
            setup_tray(app.handle())?;

            let settings_snapshot = {
                let state = app.state::<AppState>();
                let s = state.settings.lock().expect("settings lock").clone();
                s
            };

            let handle = app.handle().clone();
            if let Some(bridge) = SidecarBridge::spawn(handle.clone(), &settings_snapshot) {
                let _ = bridge.send_cmd(json!({ "cmd": "get_state" }));
                let state = app.state::<AppState>();
                if let Ok(mut guard) = state.bridge.lock() {
                    *guard = Some(bridge);
                };
            }

            show_and_focus_main(&handle);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_initial_state,
            run_command,
            toggle_mic,
            set_continuous,
            trigger_panic,
            confirm_guardrail,
            save_settings,
            download_model,
            cancel_download,
            check_update,
            install_update,
            set_always_on_top,
            set_compact_mode,
            minimize_win,
            close_win,
        ])
        .build(tauri::generate_context!())
        .expect("error while building Computer-Auto Tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            let state = app_handle.state::<AppState>();
            if let Ok(guard) = state.bridge.lock() {
                if let Some(ref bridge) = *guard {
                    bridge.shutdown();
                }
            };
        }
    });
}
