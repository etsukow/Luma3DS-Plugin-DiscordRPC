use anyhow::Result;
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use serde_json::json;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tokio::sync::broadcast;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum ServerEvent {
    Presence {
        event: String,
        #[serde(rename = "titleId")]
        title_id: String,
        name: String,
        icon: String,
    },
    Clear,
}

#[derive(Debug, Clone, Serialize)]
pub struct WsStatus {
    pub connected: bool,
    pub message: String,
}


/// Run the WebSocket loop — reconnects automatically until cancel_rx fires.
pub async fn run(
    server_ws: String,
    token: String,
    event_tx: broadcast::Sender<ServerEvent>,
    status_tx: broadcast::Sender<WsStatus>,
    mut cancel: tokio::sync::watch::Receiver<bool>,
) {
    let mut backoff = tokio::time::Duration::from_secs(2);

    loop {
        let _ = status_tx.send(WsStatus {
            connected: false,
            message: format!("Connecting to {}…", server_ws),
        });

        match connect_async(&server_ws).await {
            Err(e) => {
                let msg = format!("Connection failed: {}", e);
                log::warn!("[ws] {}", msg);
                let _ = status_tx.send(WsStatus { connected: false, message: msg });
            }
            Ok((ws_stream, _)) => {
                let (mut sink, mut stream) = ws_stream.split();

                // Send auth frame.
                let auth = json!({"type": "auth", "token": token}).to_string();
                if sink.send(Message::Text(auth.into())).await.is_err() {
                    continue;
                }

                let _ = status_tx.send(WsStatus {
                    connected: true,
                    message: format!("Connected to {}", server_ws),
                });
                log::info!("[ws] connected");
                backoff = tokio::time::Duration::from_secs(2);

                loop {
                    tokio::select! {
                        _ = cancel.changed() => {
                            if *cancel.borrow() {
                                let _ = sink.close().await;
                                return;
                            }
                        }
                        msg = stream.next() => {
                            match msg {
                                None => break,
                                Some(Err(e)) => {
                                    log::warn!("[ws] read error: {}", e);
                                    break;
                                }
                                Some(Ok(Message::Text(txt))) => {
                                    if let Ok(evt) = serde_json::from_str::<ServerEvent>(&txt) {
                                        let _ = event_tx.send(evt);
                                    }
                                }
                                _ => {}
                            }
                        }
                    }
                }

                let _ = status_tx.send(WsStatus {
                    connected: false,
                    message: format!("Disconnected — reconnecting in {}s…", backoff.as_secs()),
                });
            }
        }

        // Check for cancellation before sleeping.
        tokio::select! {
            _ = cancel.changed() => {
                if *cancel.borrow() { return; }
            }
            _ = tokio::time::sleep(backoff) => {}
        }

        if backoff < tokio::time::Duration::from_secs(60) {
            backoff *= 2;
        }
    }
}

pub async fn connect_and_run(server_ws: String, token: String) -> Result<(
    broadcast::Receiver<ServerEvent>,
    broadcast::Receiver<WsStatus>,
    tokio::sync::watch::Sender<bool>,
)> {
    let (event_tx, event_rx) = broadcast::channel(32);
    let (status_tx, status_rx) = broadcast::channel(16);
    let (cancel_tx, cancel_rx) = tokio::sync::watch::channel(false);

    tokio::spawn(run(server_ws, token, event_tx, status_tx, cancel_rx));

    Ok((event_rx, status_rx, cancel_tx))
}

