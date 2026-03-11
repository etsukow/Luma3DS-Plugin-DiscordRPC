use anyhow::Result;
use serde::Deserialize;
use std::time::Duration;

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

/// Revoke an existing token on the server (best effort from client side).
pub async fn revoke_token(server_api: &str, token: &str) -> Result<()> {
    let client = reqwest::Client::new();
    client
        .post(format!("{}/token/revoke", server_api))
        .json(&serde_json::json!({ "token": token }))
        .send()
        .await?
        .error_for_status()?;
    Ok(())
}

/// Download a personalised .3gx plugin for the given token.
pub async fn download_plugin(
    server_api: &str,
    token: &str,
    dest: &std::path::Path,
) -> Result<String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()?;
    let url = format!("{}/plugin/build?token={}", server_api, token);

    let resp = {
        let mut last_err: Option<anyhow::Error> = None;
        let mut ok_resp: Option<reqwest::Response> = None;

        for attempt in 1..=3 {
            match client.get(&url).send().await {
                Ok(r) if r.status().is_success() => {
                    ok_resp = Some(r);
                    break;
                }
                Ok(r) if r.status() == reqwest::StatusCode::SERVICE_UNAVAILABLE => {
                    last_err = Some(anyhow::anyhow!(
                        "HTTP 503 from plugin builder (attempt {attempt}/3)"
                    ));
                    if attempt < 3 {
                        tokio::time::sleep(Duration::from_secs((attempt * 2) as u64)).await;
                        continue;
                    }
                }
                Ok(r) => {
                    let status = r.status();
                    let body = r.text().await.unwrap_or_default();
                    return Err(anyhow::anyhow!(
                        "plugin build failed with HTTP {status}: {body}"
                    ));
                }
                Err(e) => {
                    last_err = Some(e.into());
                    if attempt < 3 {
                        tokio::time::sleep(Duration::from_secs((attempt * 2) as u64)).await;
                        continue;
                    }
                }
            }
        }

        match ok_resp {
            Some(r) => r,
            None => {
                return Err(anyhow::anyhow!(
                    "plugin build service unavailable after retries (HTTP 503). \
                     Try again in a minute. Last error: {}",
                    last_err
                        .map(|e| e.to_string())
                        .unwrap_or_else(|| "unknown error".to_string())
                ));
            }
        }
    };

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
