// PaperAssistant Tauri 启动器（H 阶段）
//
// 职责：
// 1. 启动时 spawn Python sidecar 二进制（binaries/paperassistant-backend）
// 2. 解析 resources/tectonic/tectonic.exe 绝对路径，注入到 sidecar 的
//    PAPERASSISTANT_TECTONIC_BIN 环境变量
// 3. 异步消费 sidecar 的 stdout/stderr，前缀 [backend-out]/[backend-err]
// 4. RunEvent::ExitRequested 时 kill sidecar，释放端口

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use once_cell::sync::OnceCell;
use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

// 全局保存 sidecar 句柄；退出时 kill。
static SIDECAR: OnceCell<Mutex<Option<CommandChild>>> = OnceCell::new();

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // 1) 解析 Tectonic 资源路径（resources/tectonic/tectonic.exe）
            let tectonic_path = app
                .path()
                .resolve("resources/tectonic/tectonic.exe", tauri::path::BaseDirectory::Resource)
                .ok();

            // 2) 构造 sidecar 命令
            let shell = app.shell();
            let mut cmd = shell
                .sidecar("paperassistant-backend")
                .expect("找不到 sidecar 'paperassistant-backend'，请先运行 scripts/build_sidecar.ps1");

            if let Some(p) = tectonic_path.as_ref() {
                cmd = cmd.env("PAPERASSISTANT_TECTONIC_BIN", p.to_string_lossy().to_string());
            }

            // 3) spawn
            let (mut rx, child) = cmd.spawn().expect("启动 PaperAssistant 后端 sidecar 失败");
            // 句柄存到全局，退出时 kill
            SIDECAR.set(Mutex::new(Some(child))).ok();

            // 4) 异步消费输出
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("[backend-out] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("[backend-err] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Terminated(payload) => {
                            eprintln!("[backend-err] sidecar terminated: code={:?}", payload.code);
                            break;
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("构建 PaperAssistant Tauri 失败")
        .run(|_app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // 退出时 kill sidecar，释放端口
                if let Some(lock) = SIDECAR.get() {
                    if let Ok(mut guard) = lock.lock() {
                        if let Some(child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}
