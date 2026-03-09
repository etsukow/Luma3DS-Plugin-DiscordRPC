use crate::{api, config, rpc, rpc::RpcClient, ws};
use serde::Serialize;
use std::sync::Arc;
use tauri::{AppHandle, Emitter};
use tokio::sync::{watch, Mutex};

// ── App state ─────────────────────────────────────────────────────────────────

#[derive(Default)]
pub struct AppState {
    pub ws_cancel: Option<watch::Sender<bool>>,
    pub rpc: Option<RpcClient>,
    pub rpc_status_tx: Option<tokio::sync::broadcast::Sender<rpc::RpcStatus>>,
    pub ws_connected: bool,
    pub rpc_connected: bool,
    pub current_game: Option<CurrentGame>,
}

#[derive(Serialize, Clone, Default)]
pub struct CurrentGame {
    pub name: String,
    pub icon: String,
    pub title_id: String,
}

pub type SharedState = Arc<Mutex<AppState>>;

// ── Tauri commands ────────────────────────────────────────────────────────────

#[derive(Serialize, Clone)]
pub struct StatusPayload {
    pub installed: bool,
    pub token: Option<String>,
    pub server_ws: String,
    pub server_api: String,
    pub plugin_path: Option<String>,
}

#[derive(Serialize, Clone)]
pub struct LiveStatus {
    pub ws_connected: bool,
    pub ws_message: String,
    pub rpc_connected: bool,
    pub rpc_message: String,
    pub current_game: Option<CurrentGame>,
}

#[tauri::command]
pub async fn get_live_status(state: tauri::State<'_, SharedState>) -> Result<LiveStatus, String> {
    let s = state.lock().await;
    Ok(LiveStatus {
        ws_connected: s.ws_connected,
        ws_message: if s.ws_connected { "Connected".into() } else { "Disconnected".into() },
        rpc_connected: s.rpc_connected,
        rpc_message: if s.rpc_connected { "Discord connected".into() } else { "Discord not available".into() },
        current_game: s.current_game.clone(),
    })
}

#[tauri::command]
pub async fn get_status() -> Result<StatusPayload, String> {
    let cfg = config::load();
    let plugin_path = cfg.token.as_ref().map(|_| {
        config::config_dir()
            .join("plugin")
            .join("discord-rpc.3gx")
            .to_string_lossy()
            .to_string()
    });
    let plugin_exists = plugin_path
        .as_ref()
        .map(|p| std::path::Path::new(p).exists())
        .unwrap_or(false);

    Ok(StatusPayload {
        installed: cfg.token.is_some() && plugin_exists,
        token: cfg.token.map(|t| mask_token(&t)),
        server_ws: cfg.server_ws,
        server_api: cfg.server_api,
        plugin_path,
    })
}

#[tauri::command]
pub async fn install(app: AppHandle, state: tauri::State<'_, SharedState>) -> Result<(), String> {
    let mut cfg = config::load();

    // Step 1 — provision token if needed
    emit_log(&app, "info", "Requesting token from server…");
    if cfg.token.is_none() {
        let resp = api::provision(&cfg.server_api)
            .await
            .map_err(|e| e.to_string())?;
        cfg.token = Some(resp.token.clone());
        config::save(&cfg).map_err(|e| e.to_string())?;
        emit_log(&app, "success", &format!("Token received: {}", mask_token(&resp.token)));
    } else {
        emit_log(&app, "info", &format!("Existing token: {}", mask_token(cfg.token.as_ref().unwrap())));
    }

    // Step 2 — download plugin
    let token = cfg.token.as_ref().unwrap().clone();
    let plugin_path = config::config_dir().join("plugin").join("discord-rpc.3gx");
    emit_log(&app, "info", "Building personalised plugin on server…");
    let version = api::download_plugin(&cfg.server_api, &token, &plugin_path)
        .await
        .map_err(|e| e.to_string())?;
    emit_log(&app, "success", &format!("Plugin saved: {} (v{})", plugin_path.display(), version));

    // Step 3 — start daemon
    emit_log(&app, "info", "Starting Discord RPC daemon…");
    start_daemon(app.clone(), state.inner().clone(), cfg).await?;
    emit_log(&app, "success", "Installation complete ✅");

    app.emit("install_complete", plugin_path.to_string_lossy().to_string())
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn uninstall(app: AppHandle, state: tauri::State<'_, SharedState>) -> Result<(), String> {
    stop_daemon(state.inner().clone()).await;

    let mut cfg = config::load();
    cfg.token = None;
    config::save(&cfg).map_err(|e| e.to_string())?;

    // Remove plugin file
    let plugin_path = config::config_dir().join("plugin").join("discord-rpc.3gx");
    let _ = std::fs::remove_file(&plugin_path);

    emit_log(&app, "info", "Uninstalled — token and plugin removed");
    app.emit("uninstall_complete", ()).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn update_plugin(app: AppHandle) -> Result<(), String> {
    let cfg = config::load();
    let token = cfg.token.ok_or("No token — run install first")?;
    let plugin_path = config::config_dir().join("plugin").join("discord-rpc.3gx");

    emit_log(&app, "info", "Updating plugin…");
    let version = api::download_plugin(&cfg.server_api, &token, &plugin_path)
        .await
        .map_err(|e| e.to_string())?;
    emit_log(&app, "success", &format!("Plugin updated to v{}", version));
    Ok(())
}

#[tauri::command]
pub async fn start(app: AppHandle, state: tauri::State<'_, SharedState>) -> Result<(), String> {
    let cfg = config::load();
    if cfg.token.is_none() {
        return Err("Not installed — run install first".into());
    }
    start_daemon(app, state.inner().clone(), cfg).await
}

#[tauri::command]
pub async fn stop(state: tauri::State<'_, SharedState>) -> Result<(), String> {
    stop_daemon(state.inner().clone()).await;
    Ok(())
}

#[tauri::command]
pub fn get_plugin_path() -> String {
    config::config_dir()
        .join("plugin")
        .join("discord-rpc.3gx")
        .to_string_lossy()
        .to_string()
}

// ── Auto-start helper (called from lib.rs setup, no State needed) ─────────────

pub async fn try_autostart(app: AppHandle, state: SharedState) {
    let cfg = config::load();
    if cfg.token.is_some() {
        if let Err(e) = start_daemon(app, state, cfg).await {
            log::warn!("[setup] auto-start failed: {}", e);
        }
    }
}

// ── Daemon helpers ────────────────────────────────────────────────────────────

pub async fn start_daemon(
    app: AppHandle,
    state: SharedState,
    cfg: config::Config,
) -> Result<(), String> {
    stop_daemon(state.clone()).await;

    let token = cfg.token.clone().ok_or("No token")?;
    let (mut event_rx, mut status_rx, cancel_tx) =
        ws::connect_and_run(cfg.server_ws.clone(), token)
            .await
            .map_err(|e| e.to_string())?;

    // RPC status channel
    let (rpc_status_tx, mut rpc_status_rx) = tokio::sync::broadcast::channel::<rpc::RpcStatus>(8);

    let mut rpc = RpcClient::new(&cfg.discord_app_id)
        .with_status_tx(rpc_status_tx.clone());

    // Try connecting to Discord immediately so the UI shows the real status.
    rpc.try_connect();

    {
        let mut s = state.lock().await;
        s.ws_cancel = Some(cancel_tx);
        s.rpc = Some(rpc);
        s.rpc_status_tx = Some(rpc_status_tx);
    }

    let app_clone = app.clone();
    let state_clone = state.clone();
    tokio::spawn(async move {
        loop {
            tokio::select! {
                Ok(evt) = event_rx.recv() => {
                    let _ = app_clone.emit("presence_event", &evt);
                    let mut s = state_clone.lock().await;
                    match &evt {
                        ws::ServerEvent::Presence { name, icon, title_id, .. } => {
                            s.current_game = Some(CurrentGame {
                                name: name.clone(),
                                icon: icon.clone(),
                                title_id: title_id.clone(),
                            });
                            if let Some(ref mut rpc) = s.rpc {
                                rpc.update(name, icon);
                            }
                        }
                        ws::ServerEvent::Clear => {
                            s.current_game = None;
                            if let Some(ref mut rpc) = s.rpc {
                                rpc.clear();
                            }
                        }
                    }
                }
                Ok(status) = status_rx.recv() => {
                    {
                        let mut s = state_clone.lock().await;
                        s.ws_connected = status.connected;
                    }
                    let _ = app_clone.emit("ws_status", &status);
                }
                Ok(rpc_status) = rpc_status_rx.recv() => {
                    {
                        let mut s = state_clone.lock().await;
                        s.rpc_connected = rpc_status.connected;
                    }
                    let _ = app_clone.emit("rpc_status", &rpc_status);
                }
                else => break,
            }
        }
    });

    Ok(())
}

pub async fn stop_daemon(state: SharedState) {
    let mut s = state.lock().await;
    if let Some(tx) = s.ws_cancel.take() {
        let _ = tx.send(true);
    }
    if let Some(ref mut rpc) = s.rpc {
        rpc.close();
    }
    s.rpc = None;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn mask_token(t: &str) -> String {
    if t.len() <= 8 {
        return "****".to_string();
    }
    format!("{}…{}", &t[..4], &t[t.len() - 4..])
}

#[derive(Serialize, Clone)]
struct LogPayload {
    level: String,
    message: String,
}

fn emit_log(app: &AppHandle, level: &str, message: &str) {
    log::info!("[drpc] {}", message);
    let _ = app.emit("log", LogPayload {
        level: level.to_string(),
        message: message.to_string(),
    });
}
