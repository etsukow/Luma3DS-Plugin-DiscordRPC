use discord_rich_presence::{activity, DiscordIpc, DiscordIpcClient};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Clone, serde::Serialize)]
pub struct RpcStatus {
    pub connected: bool,
    pub message: String,
}

pub struct RpcClient {
    inner: Option<DiscordIpcClient>,
    app_id: String,
    last_game: Option<String>,
    game_start: i64,
    status_tx: Option<tokio::sync::broadcast::Sender<RpcStatus>>,
}

impl RpcClient {
    pub fn new(app_id: &str) -> Self {
        Self {
            inner: None,
            app_id: app_id.to_string(),
            last_game: None,
            game_start: 0,
            status_tx: None,
        }
    }

    pub fn with_status_tx(mut self, tx: tokio::sync::broadcast::Sender<RpcStatus>) -> Self {
        self.status_tx = Some(tx);
        self
    }

    fn emit_status(&self, connected: bool, message: &str) {
        if let Some(ref tx) = self.status_tx {
            let _ = tx.send(RpcStatus {
                connected,
                message: message.to_string(),
            });
        }
    }

    /// Try to connect immediately — useful to show status at startup.
    pub fn try_connect(&mut self) {
        self.ensure_connected();
    }

    fn ensure_connected(&mut self) -> bool {
        if self.inner.is_some() {
            return true;
        }
        match DiscordIpcClient::new(&self.app_id) {
            Ok(mut client) => match client.connect() {
                Ok(_) => {
                    log::info!("[rpc] Discord IPC connected");
                    self.inner = Some(client);
                    self.emit_status(true, "Discord connected");
                    true
                }
                Err(e) => {
                    log::warn!("[rpc] connect failed: {}", e);
                    self.emit_status(false, &format!("Discord not available: {}", e));
                    false
                }
            },
            Err(e) => {
                log::warn!("[rpc] client create failed: {}", e);
                self.emit_status(false, &format!("Discord IPC error: {}", e));
                false
            }
        }
    }

    pub fn update(&mut self, name: &str, icon: &str) {
        if !self.ensure_connected() {
            return;
        }

        if self.last_game.as_deref() != Some(name) {
            self.game_start = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|d| d.as_secs() as i64)
                .unwrap_or(0);
            self.last_game = Some(name.to_string());
        }

        let large_image = if icon.is_empty() {
            "nintendo_3ds"
        } else {
            icon
        };

        let act = activity::Activity::new()
            .details(name)
            .state("Nintendo 3DS")
            .assets(
                activity::Assets::new()
                    .large_image(large_image)
                    .large_text(name),
            )
            .timestamps(activity::Timestamps::new().start(self.game_start));

        if let Some(ref mut client) = self.inner {
            if let Err(e) = client.set_activity(act) {
                log::warn!("[rpc] set_activity failed: {} — reconnecting", e);
                let _ = client.close();
                self.inner = None;
                self.emit_status(false, "Discord disconnected");
            } else {
                log::info!("[rpc] presence → {}", name);
            }
        }
    }

    pub fn clear(&mut self) {
        if let Some(ref mut client) = self.inner {
            if let Err(e) = client.clear_activity() {
                log::warn!("[rpc] clear_activity failed: {}", e);
                let _ = client.close();
                self.inner = None;
                self.emit_status(false, "Discord disconnected");
            } else {
                log::info!("[rpc] presence cleared");
                self.last_game = None;
            }
        }
    }

    pub fn close(&mut self) {
        if let Some(ref mut client) = self.inner {
            let _ = client.close();
        }
        self.inner = None;
        self.last_game = None;
        self.emit_status(false, "Discord disconnected");
    }
}
