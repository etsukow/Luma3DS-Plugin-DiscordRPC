use anyhow::Result;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub struct TokenResponse {
    pub token: String,
    pub udp_host: String,
    pub udp_port: u16,
}

/// Provision a new token from the server.
pub async fn provision(server_api: &str) -> Result<TokenResponse> {
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{}/token", server_api))
        .send()
        .await?
        .error_for_status()?
        .json::<TokenResponse>()
        .await?;
    Ok(resp)
}

/// Download a personalised .3gx plugin for the given token.
pub async fn download_plugin(server_api: &str, token: &str, dest: &std::path::Path) -> Result<String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()?;

    let resp = client
        .get(format!("{}/plugin/build?token={}", server_api, token))
        .send()
        .await?
        .error_for_status()?;

    let version = resp
        .headers()
        .get("x-plugin-version")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("unknown")
        .to_string();

    if let Some(parent) = dest.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let bytes = resp.bytes().await?;
    let tmp = dest.with_extension("3gx.tmp");
    std::fs::write(&tmp, &bytes)?;
    std::fs::rename(&tmp, dest)?;

    Ok(version)
}

