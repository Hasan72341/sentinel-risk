use std::fs;
use std::path::Path;

use base64::{engine::general_purpose::STANDARD, Engine};
use serde::Serialize;
use tauri::{window::Color, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct FileBuffer {
    buffer: String,
    name: String,
    mime_type: String,
}

fn mime_type_for(path: &Path) -> &'static str {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| e.to_ascii_lowercase())
        .unwrap_or_default();
    match ext.as_str() {
        "csv" => "text/csv",
        "xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls" => "application/vnd.ms-excel",
        "pdf" => "application/pdf",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "tiff" => "image/tiff",
        "bmp" => "image/bmp",
        _ => "application/octet-stream",
    }
}

#[tauri::command]
fn read_file_buffer(file_path: String) -> Result<FileBuffer, String> {
    let path = Path::new(&file_path);
    let bytes = fs::read(path).map_err(|e| format!("Failed to read file: {e}"))?;
    Ok(FileBuffer {
        buffer: STANDARD.encode(bytes),
        name: path
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default(),
        mime_type: mime_type_for(path).to_string(),
    })
}

#[tauri::command]
fn write_file_buffer(file_path: String, buffer: String) -> Result<(), String> {
    let bytes = STANDARD
        .decode(buffer)
        .map_err(|e| format!("Failed to decode file contents: {e}"))?;
    fs::write(&file_path, bytes).map_err(|e| format!("Failed to write file: {e}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![read_file_buffer, write_file_buffer])
        .setup(|app| {
            let handle = app.handle().clone();
            WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title("Sentinel Risk")
                .inner_size(1400.0, 900.0)
                .min_inner_size(1024.0, 680.0)
                .decorations(false)
                .background_color(Color(0xf5, 0xf5, 0xf4, 0xff))
                // Keep HTML5 drag & drop working for the upload dropzone
                .disable_drag_drop_handler()
                // Prevent external navigation
                .on_navigation(move |url| {
                    let internal = url.scheme() == "tauri"
                        || matches!(url.host_str(), Some("localhost") | Some("tauri.localhost"));
                    if !internal {
                        let _ = handle.opener().open_url(url.as_str(), None::<&str>);
                    }
                    internal
                })
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Sentinel Risk");
}
