# 📚 PaperAssistant

本地优先的学术写作辅助软件，覆盖**选题 → 文献综述 → 正文撰写 → 引用 → 排版**全流程。

## 核心理念

AI 扮演 **"文献导航员 + 总结助手 + 审计员"** 角色，辅助人类决策，**不替代人类写作**。

所有 AI 声称"来自具体文献"的内容必须经事实核查；不依赖模型自身参数知识作为输出依据。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Tauri v2 |
| 前端语言 | TypeScript + React |
| Markdown 编辑器 | Milkdown / Vditor（所见即所得，支持 LaTeX） |
| 后端语言 | Python 3.11+（未来重构为 Rust） |
| 后端框架 | FastAPI（sidecar） |
| 通信协议 | HTTP（localhost） |
| LaTeX 引擎 | Tectonic（内嵌） |
| 引用格式 | CSL（citeproc，本地运行） |
| 数据存储 | 文件系统（**仅 CSV + Markdown，绝不使用 JSON**） |
| 调试接入 | [debug-assistant](https://github.com/Nikki-SU/debug-assistant) SDK |

## 四个 API 接口位

| 角色 | 用途 |
|------|------|
| MinerU | PDF → Markdown |
| 助手 | 主要输出 |
| 审阅 | 事实核查 |
| 秘书 | 错别字 / 语法修正（可选，未配置则复用助手） |

## 五大阶段

1. **选题**：学科判断 → 知识库 / 教材上传 → AI 推荐选题方向
2. **文献综述**：检索 → 上传文献 → AI 按话题归纳（经审计）→ 用户勾选实际引用
3. **正文撰写**：理论 → 研究设计 → 数据 → 结果（社科序列）/ 实验 → 表征 → 机理 → 结果（理科序列）
4. **引用**：仅用户明确勾选的文献进入引用列表，CSL 格式化
5. **排版**：LaTeX 模板迭代 → Markdown ↔ LaTeX 实时预览 → 一键编译 PDF

## 交付形态

- 单个 Windows EXE 安装包，双击运行
- Python、LaTeX 等全部内嵌，**无需配置环境**
- 用户仅首次启动时输入 API Key

## 项目状态

🚧 **正在从零搭建中**（2026-06-29 启动）

详细技术规格见 [`docs/SPEC.md`](docs/SPEC.md)。

## License

[AGPL-3.0](LICENSE)
