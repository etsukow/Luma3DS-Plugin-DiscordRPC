mod api;
mod commands;
mod config;
mod rpc;
mod ws;

use commands::{AppState, SharedState};
use std::sync::Arc;
#[cfg(target_os = "macos")]
use tauri::ActivationPolicy;
use tauri::{
    Manager,
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};
use tauri_plugin_autostart::MacosLauncher;
use tokio::sync::Mutex;

fn hide_to_tray(app: &tauri::AppHandle, window: &tauri::WebviewWindow) {
    #[cfg(target_os = "macos")]
    let _ = app.set_activation_policy(ActivationPolicy::Accessory);
    let _ = window.set_skip_taskbar(true);
    let _ = window.hide();
}

fn show_from_tray(app: &tauri::AppHandle, window: &tauri::WebviewWindow) {
    #[cfg(target_os = "macos")]
    let _ = app.set_activation_policy(ActivationPolicy::Regular);
    let _ = window.set_skip_taskbar(false);
    let _ = window.show();
    let _ = window.set_focus();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_log::Builder::default()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec!["--hidden"]),
        ))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .manage(Arc::new(Mutex::new(AppState::default())) as SharedState)
        .setup(|app| {
            // Start hidden when launched via autostart
            if std::env::args().any(|a| a == "--hidden") {
                if let Some(win) = app.get_webview_window("main") {
                    hide_to_tray(app.handle(), &win);
                }
            }

            // System tray
            let show = MenuItem::with_id(app, "show", "Show", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;
            let tray_icon =
                tauri::image::Image::from_bytes(include_bytes!("../icons/tray-template.png"))?;

            TrayIconBuilder::new()
                .menu(&menu)
                .icon(tray_icon)
                .icon_as_template(true)
                .tooltip("3DS Discord RPC")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(win) = app.get_webview_window("main") {
                            show_from_tray(app, &win);
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        if let Some(win) = tray.app_handle().get_webview_window("main") {
                            show_from_tray(&tray.app_handle(), &win);
                        }
                    }
                })
                .build(app)?;

            // Auto-start daemon if already installed
            let app_handle = app.handle().clone();
            let state: SharedState = app.state::<SharedState>().inner().clone();
            tauri::async_runtime::spawn(async move {
                commands::try_autostart(app_handle, state).await;
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_status,
            commands::get_live_status,
            commands::install,
            commands::uninstall,
            commands::update_plugin,
            commands::start,
            commands::stop,
            commands::get_plugin_path,
            commands::get_full_token,
            commands::fetch_icon,
        ])
        .on_window_event(|window, event| {
            // Hide to tray instead of closing
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if let Some(win) = window.app_handle().get_webview_window("main") {
                    hide_to_tray(&window.app_handle(), &win);
                }
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
