use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

pub const DEFAULT_SERVER_WS: &str = "wss://api.etsukow.com";
pub const DEFAULT_SERVER_API: &str = "https://api.etsukow.com";
pub const DISCORD_APP_ID: &str = "1480019559606911057";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub server_ws: String,
    pub server_api: String,
    pub token: Option<String>,
    pub discord_app_id: String,
    pub fallback_icon: String,
    pub rpc_min_interval: u64,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            server_ws: DEFAULT_SERVER_WS.to_string(),
            server_api: DEFAULT_SERVER_API.to_string(),
            token: None,
            discord_app_id: DISCORD_APP_ID.to_string(),
            fallback_icon: "nintendo_3ds".to_string(),
            rpc_min_interval: 15,
        }
    }
}

pub fn config_dir() -> PathBuf {
    let base = dirs::config_dir().unwrap_or_else(|| PathBuf::from("."));
    let dir = base.join("luma3ds-drpc");
    let _ = fs::create_dir_all(&dir);
    dir
}

pub fn config_path() -> PathBuf {
    config_dir().join("config.json")
}

pub fn load() -> Config {
    let path = config_path();
    if let Ok(data) = fs::read_to_string(&path) {
        if let Ok(cfg) = serde_json::from_str(&data) {
            return cfg;
        }
    }
    Config::default()
}

pub fn save(cfg: &Config) -> anyhow::Result<()> {
    let path = config_path();
    let tmp = path.with_extension("json.tmp");
    let data = serde_json::to_string_pretty(cfg)?;
    fs::write(&tmp, data)?;
    fs::rename(tmp, path)?;
    Ok(())
}

