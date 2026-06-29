// PaperAssistant Tauri 主入口
// 关键职责：启动 Python sidecar (backend-python) 并管理其生命周期

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .setup(|_app| {
            // TODO: 启动 Python sidecar
            //   1) 通过 tauri::api::process::Command::new_sidecar("paperassistant-backend")
            //   2) 监听 stdout/stderr 写入日志
            //   3) 应用退出时 kill sidecar
            //
            // 对应 SPEC：项目二 §三. 技术栈 - "Tauri ↔ Python sidecar"
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
