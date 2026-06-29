---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4258827487937943_0/project_7656107528631124262-files/用户上传/未命名.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4258827487937943#1782713853341
    ReservedCode2: ""
---
技术规格说明书（SPEC）

项目一：调试助手（Debug Assistant）

一、产品定位

调试助手是一个独立的桌面工具，用于记录、管理和闭环解决代码错误。

· 它独立于任何项目，是一个全局工具
· 任何项目（Python / Rust / Tauri / 前端 / 后端 / 脚本）都可以接入
· 核心功能：记录错误 + 一键复制 + 闭环解决

二、核心功能

功能 说明
记录错误 通过 HTTP API / 命令行 / GUI 创建错误报告
存储报告 按项目组织，Markdown 格式存储，CSV 索引
一键复制 复制完整 Markdown 报告，粘贴给 AI 诊断
闭环解决 问题解决后回传解决方案，状态从"待解决"→"已解决"
全局检索 跨项目搜索错误报告

三、存储架构

3.1 存储目录结构

```
{用户指定根目录}/
├── projects/
│   ├── PaperAssistant/
│   │   ├── backend/
│   │   │   └── 2026-06-29/
│   │   │       └── ERR-143052-A3F9.md
│   │   └── frontend/
│   │       └── 2026-06-29/
│   │           └── ERR-151230-B7E2.md
│   ├── AnotherProject/
│   │   └── ...
│   └── index.csv
├── config/
│   └── debugger_config.csv
└── debugger.exe
```

3.2 错误报告格式（Markdown）

```markdown
# 🔴 错误报告

> **错误ID**：`ERR-20260629-143052-A3F9`
> **项目**：PaperAssistant
> **模块**：backend
> **状态**：🔴 待解决
> **生成时间**：2026-06-29 14:30:52
> **解决时间**：-
> **报告版本**：v1.0


## 一、错误摘要

| 项目 | 内容 |
|------|------|
| 错误类型 | `MinerUConversionTimeout` |
| 严重程度 | ⚠️ 警告 |
| 错误信息 | MinerU转换超时（300s），文件超过200页限制 |
| 用户操作 | 上传PDF文件 `文献A.pdf` |
| 当前阶段 | 文献综述 |


## 二、上下文信息

| 项目 | 内容 |
|------|------|
| Session ID | `sess-20260629-140000-xyz789` |
| 项目名称 | 数字普惠金融论文 |
| 当前阶段 | 文献综述 |
| 已读文献数 | 3篇 |
| 对话轮次 | 第5轮 |


## 三、操作路径

```

用户操作：点击「上传PDF」按钮
↓
前端调用：POST /api/file/upload
↓
后端路由：routers/file.py:upload_file()
↓
服务调用：services/mineru_client.py:convert()
↓
外部API：MinerU API（超时）
↓
❌ 错误抛出：TimeoutError

```

## 四、输入数据

```yaml
file_name: "文献A.pdf"
file_size: 45.2 MB
page_count: 230
file_path: "C:/Users/xxx/Documents/PaperAssistant/temp/monitor/文献A.pdf"
session_id: "sess-20260629-140000-xyz789"
stage: "文献综述"
```

五、日志（最近20行）

```
[14:30:50] INFO  [file_watcher] 检测到新文件：文献A.pdf
[14:30:50] INFO  [mineru_client] 开始转换：文献A.pdf
[14:30:51] INFO  [mineru_client] 文件大小：45.2MB，页数：230
[14:30:51] WARN  [mineru_client] 页数超过200页限制
[14:30:51] INFO  [mineru_client] 启动MinerU API调用
[14:30:52] ERROR [mineru_client] API超时（300s）
[14:30:52] ERROR [file_watcher] 转换失败：TimeoutError
```

六、错误栈

```python
Traceback (most recent call last):
  File "backend-python/app/services/mineru_client.py", line 78, in convert
    response = await api_client.post("/convert", files={"file": file})
  File "backend-python/app/utils/http_client.py", line 45, in post
    raise TimeoutError("请求超时（300s）")
TimeoutError: 请求超时（300s）
```

七、环境信息

项目 内容
OS Windows 11 23H2
软件版本 PaperAssistant v1.0.0
Python版本 3.11.9
Tauri版本 v2.0.0

八、解决方案

此部分在问题解决后由用户回传填写

解决状态：⬜ 待解决
解决时间：-
解决方式：-

相关修改：-

📋 一键复制

[点击复制完整报告]

```


### 四、三种使用方式

#### 4.1 HTTP API（推荐，供程序自动调用）

调试助手启动后，在后台监听本地端口（默认 `8765`）。

**创建错误报告：**

```

POST http://localhost:8765/api/report
{
"project": "PaperAssistant",
"module": "backend",
"error_type": "MinerUConversionTimeout",
"error_message": "转换超时",
"stack_trace": "...",
"context": {"stage": "文献综述"},
"logs": ["[14:30:50] INFO 检测到新文件..."]
}

```

**回传解决方案：**

```

POST http://localhost:8765/api/resolve
{
"error_id": "ERR-20260629-143052-A3F9",
"solution": "将文件拆分为两个部分后分别上传",
"related_changes": "增加超时配置到600s"
}

```

#### 4.2 命令行（适合脚本/快速记录）

```bash
debugger.exe report \
    --project PaperAssistant \
    --module backend \
    --type TimeoutError \
    --message "转换超时" \
    --context '{"stage":"文献综述"}'
```

4.3 GUI 手动填写（适合无法自动捕获的场景）

打开调试助手主界面 → 点击「新建报告」→ 填写表单 → 生成报告

五、闭环机制

```
错误发生
    ↓
调试助手记录 → 生成错误报告（状态：🔴 待解决）
    ↓
用户复制报告 → 发给AI助手诊断
    ↓
AI给出解决方案 / 用户自行解决
    ↓
用户点击「问题已解决」
    ↓
弹出回传对话框：
    - 解决方案输入区（支持 Markdown，可一键粘贴）
    - 相关修改输入区（可选）
    - 点击确认
    ↓
系统将解决方案追加到原错误报告末尾
    ↓
状态更新：🔴 待解决 → 🟢 已解决
    ↓
闭环完成
```

5.1 回传对话框

```
┌─────────────────────────────────────────────────────────────┐
│ ✅ 问题已解决                                              │
│                                                           │
│ 错误ID：ERR-20260629-143052-A3F9                          │
│                                                           │
│ 解决方案（支持 Markdown，可从任何地方复制粘贴）：          │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ [粘贴区域 - 支持纯文本 / Markdown / 代码块]        │   │
│ │                                                     │   │
│ │ 将文件拆分为两个部分（≤200页/部分）后分别上传，    │   │
│ │ MinerU转换成功。                                   │   │
│ │                                                     │   │
│ │ 相关修改：                                         │   │
│ │ - 增加超时配置到600s（config/settings.py:23）      │   │
│ │ - 增加文件页数前置校验（routers/file.py:15）       │   │
│ └─────────────────────────────────────────────────────┘   │
│                                                           │
│ [📋 一键粘贴] [确认] [取消]                               │
└─────────────────────────────────────────────────────────────┘
```

5.2 一键粘贴

· 用户点击「📋 一键粘贴」→ 系统读取剪贴板内容 → 自动填入解决方案区域
· 支持任何格式（纯文本 / Markdown / 代码 / 混合内容），原样保留
· 粘贴后仍可手动编辑

六、SDK 客户端

6.1 Python SDK

```python
from debug_assistant import Debugger

debugger = Debugger(
    project="PaperAssistant",
    module="backend",
    host="localhost",
    port=8765
)

# 自动捕获异常
@debugger.catch
def my_function():
    pass

# 手动上报
try:
    result = mineru_client.convert(file_path)
except Exception as e:
    debugger.report(
        error=e,
        context={"file_name": file_path, "page_count": 230}
    )

# 回传解决
debugger.resolve(
    error_id="ERR-20260629-143052-A3F9",
    solution="将文件拆分后上传"
)
```

6.2 TypeScript SDK（Tauri 前端）

```typescript
import { Debugger } from 'debug-assistant-sdk';

const debugger = new Debugger({
    project: 'PaperAssistant',
    module: 'frontend',
    host: 'localhost',
    port: 8765
});

// 全局错误捕获
window.addEventListener('error', (event) => {
    debugger.report({ error: event.error });
});

// 手动上报
try {
    await api.uploadFile(file);
} catch (error) {
    debugger.report({ error, context: { file_name: file.name } });
}
```

6.3 Rust SDK

```rust
use debug_assistant_sdk::Debugger;

let debugger = Debugger::new("PaperAssistant", "backend", "localhost", 8765);

if let Err(e) = mineru_client.convert(file_path) {
    debugger.report(&e, &context, &logs);
}
```

七、环境变量配置

变量 默认值
DEBUG_ASSISTANT_ENABLED true
DEBUG_ASSISTANT_HOST localhost
DEBUG_ASSISTANT_PORT 8765
DEBUG_ASSISTANT_PROJECT 空（必须）
DEBUG_ASSISTANT_MODULE 空（必须）
DEBUG_ASSISTANT_LOG_LEVEL INFO

八、技术规格

项目 规格
语言 Python 3.11+
打包 独立 EXE
数据格式 Markdown（报告）+ CSV（配置/索引）
存储路径 用户首次启动时指定
与主应用关系 完全独立
分发方式 独立 EXE

项目二：PaperAssistant（主应用）

一、产品定位

本地优先的学术写作辅助软件，覆盖从选题、文献综述、正文撰写、引用管理到格式排版的全流程。AI 扮演"文献导航员 + 总结助手 + 审计员"角色，辅助人类决策，而非替代人类写作。

开发阶段集成调试助手，所有开发/运行错误自动上报到调试助手。

二、交付形态

· 单个 EXE 安装包（Windows），用户双击安装/运行
· 无需配置任何环境（Python、LaTeX 等全部内嵌）
· 用户仅需在首次启动时输入 API Key

三、技术栈总览

层级 技术 版本/说明
前端框架 Tauri v2.x
前端语言 TypeScript + HTML + CSS —
Markdown 编辑器 Milkdown / Vditor 所见即所得，支持 LaTeX
后端语言（当前） Python 3.11+
后端框架 FastAPI —
后端打包 PyInstaller / Nuitka sidecar EXE
后端语言（未来） Rust 重构目标
通信协议 HTTP（localhost） Tauri ↔ Python sidecar
LaTeX 引擎 Tectonic 内嵌
引用格式 CSL（citeproc） 本地运行
数据存储 文件系统（Markdown + CSV） 无需数据库
调试接入 调试助手 SDK 开发/运行期错误上报

四、全局核心规则

4.1 数据格式规则

本系统所有内部数据存储与交换，仅限以下两种格式：

· CSV：结构化数据（文献卡片、知识库卡片、大类配置、自定义字段、引用选择记录）
· Markdown：非结构化/富文本数据（文献全文、课本全文、论文正文、记忆、临时知识、LaTeX模板、卡片内容）

绝对不用 JSON 作为内部永久存储格式。

4.2 AI 职责边界

AI 可以做的 AI 绝对不做的
✅ 推荐检索关键词、检索平台、期刊、课题组 ❌ 凭空给出任何具体文献内容
✅ 联网检索/爬取文献（仅供展示） ❌ 将爬取内容未经用户上传确认就存入临时知识
✅ 总结用户已上传的材料（附来源引用，经审计） ❌ 代写论文实质性内容
✅ 基于已有材料推断建议（标注"建议"） ❌ 依赖模型自身参数知识作为输出依据
✅ 语法/错别字修正 ❌ 任何没有来源的"知识提供"

4.3 事实核查规则

核心判断标准：如果 AI 输出的内容声称"来自某篇文献/某本教材的某部分"，就必须经过事实核查。如果输出是"基于已有材料的综合判断/推荐"，没有声称具体来源，则不强制审计，但需标注"建议"。

必须经事实核查：

· 总结已上传文献
· 从课本/教材提炼知识点
· 从方法论教材提取操作流程
· 从已读材料归纳对比
· 文献卡片重新生成
· 知识库卡片生成

不强制事实核查（标注"建议"）：

· 推荐选题方向
· 推荐检索关键词/平台
· 综合研究方法建议
· 框架组织建议

核查流程：

```
助手AI生成需审计内容 + 原文引用片段
    ↓
调用审阅AI，检查：
  1. 总结是否与原文一致？（无矛盾）
  2. 总结是否有原文中不存在的新增信息？
    ↓
两项都通过 → 写入临时知识/记忆/卡片
任一项不通过 → 内容丢弃 → 反馈助手AI → 重新生成 → 再次送审 → 循环直到通过（最多5次）
    ↓
审计日志写入审阅_记忆.md
```

4.4 兜底原则

当用户需要实质性使用 AI 输出时，如果 AI 缺少必要信息，不得自行补全或编造。唯一允许的行为是：告知用户缺少什么信息，以及告诉用户如何获取/补充这些信息。

4.5 四个 API 接口位

序号 角色 说明 API 配置
1 MinerU PDF→Markdown 转换 独立，必有
2 助手 主要输出 独立，必有
3 审阅 事实核查 独立，必有
4 秘书 错别字/语法修正 可选：未配置则复用助手 API

五、存储架构

5.1 运行时数据目录结构

```
%USERPROFILE%\Documents\PaperAssistant\
├── config/
│   ├── api_config.csv
│   ├── category_config.csv
│   └── custom_fields.csv
├── knowledge/                  # 知识库
│   └── {学科}/
│       ├── {课本名}.md
│       └── cards/
│           ├── {卡片名}.md
│           └── cards.csv
├── library/                    # 文献库
│   ├── fulltext/
│   │   └── {主键}.md
│   └── cards/
│       ├── {主键}.md
│       └── cards.csv
├── projects/                   # 项目
│   └── {项目名}/
│       ├── memories/
│       │   ├── assistant.md
│       │   ├── reviewer.md
│       │   └── secretary.md
│       ├── temp_knowledge.md
│       ├── paper/
│       │   ├── draft.md
│       │   └── images/
│       └── citations/
│           └── selected.csv
└── temp/
    └── monitor/                # 监控目录
```

5.2 四种存储类型

存储类型 生命周期 作用域 经事实核查 可继承 可删除 格式
知识库 持久化 跨论文/跨对话 ✅ ✅ ❌ Markdown全文 + CSV卡片
文献库 持久化 跨论文/跨对话 ✅ ✅ ❌ Markdown全文 + CSV卡片 + Markdown卡片
记忆 持久化 当前对话+可继承 视内容 ✅ ❌ Markdown（三角色分离）
临时知识 当前对话期间 仅当前对话 ✅ ✅ ✅ Markdown

六、UI/UX 布局

```
┌─────────────────────────────────────────────────────────────┐
│ 左栏（可折叠）          │     主工作区（双栏，可调宽度）    │
│                         │  ┌─────────────┬───────────────┐ │
│ 项目列表                │  │  左工作区    │   右工作区     │ │
│ ├─ 项目A               │  │  （可切换）  │   （可切换）   │ │
│ ├─ 项目B               │  │             │               │ │
│ └─ 项目C               │  │             │               │ │
│                         │  │             │               │ │
│ 阶段导航                │  │             │               │ │
│ ● 选题                  │  │             │               │ │
│ ○ 文献综述              │  │             │               │ │
│ ○ 正文撰写              │  │             │               │ │
│ ○ 引用                  │  │             │               │ │
│ ○ 排版                  │  │             │               │ │
└─────────────────────────────────────────────────────────────┘
```

可切换的内容类型：

· AI 对话（含审计状态、交互式勾选组件）
· 搜索网站（内嵌 WebView，用户可自定义）
· 知识库检索
· Markdown 编辑器（所见即所得）
· LaTeX 预览
· 文献卡片列表
· 知识库卡片列表

七、五大阶段流程

7.1 阶段一：选题

步骤 操作 AI 职责 审计
1 用户输入论文要求 + 课程/学科信息 判断学科→追溯一级学科 —
2 检查本地知识库 列出已有教材 或 推荐检索关键词 ❌（策略建议）
3 用户上传课本/教材 AI 总结提炼 → 存入临时知识 ✅（有来源）
4 AI 读知识库+论文要求 推荐选题方向 + 检索关键词 ❌（推断类，标注"建议"）
5 用户自行检索 爬取结果仅展示 —
6 用户上传文献 AI 总结 → 存入临时知识 ✅（有来源）
7 AI 结合知识库+临时知识 推荐具体选题 ❌（推断类，标注"建议"）
8 用户选择/自定选题 项目名称自动更新 —

7.2 阶段二：文献综述

步骤 操作 AI 职责 审计
1 AI 推荐检索关键词+平台 推断类建议 ❌（标注"建议"）
2 用户检索并上传文献 可监控目录自动转 —
3 AI 读取并总结文献 按话题归纳，附来源引用 ✅（有来源）
4 AI 询问勾选 "请勾选实际引用的文献" —
5 用户勾选 系统记录 —

7.3 阶段三：正文撰写

社科类默认序列： 理论 → 研究设计 → 数据 → 结果和结论
理科类默认序列： 实验 → 表征 → 机理 → 结果和结论

子阶段3.1：理论建设

步骤 操作 AI 职责 审计
1 AI 推荐理论文献（关键词+来源方向） 推断类建议 ❌（标注"建议"）
2 用户上传理论文献 — —
3 AI 总结 → 存入临时知识 附来源引用 ✅（有来源）
4 AI 询问勾选 用户勾选 —

子阶段3.2：方法论/研究设计

步骤 操作 AI 职责 审计
1 AI 从已上传文献归纳方法 附DOI+引用位置 ✅（有来源）
2 AI 从方法论教材提取流程 附来源 ✅（有来源）
3 AI 给出综合建议 "建议考虑XX方向" ❌（推断类，标注"建议"）
4 用户确认方法 提取详细流程 ✅（有来源）

子阶段3.3：数据

步骤 操作 AI 职责 审计
1 用户上传数据/分析结果 — —
2 AI 读取并理解 提供结论方向参考 ❌（参考性）

子阶段3.4：结果和结论

· 最终结论由人类自写
· AI 可提供方向参考（标注"建议"）

7.4 阶段四：引用

核心逻辑： 只有用户明确勾选的文献进入引用列表。

前置勾选（嵌入各阶段）：

每个阶段完成时，AI 在对话中自动出现交互式勾选消息。

引用阶段工作流：

步骤 左栏（AI） 右栏
1 汇总各阶段已勾选文献 显示文献卡片列表
2 警告：某阶段0勾选→"是否补勾？" —
3 用户选择引用格式 —
4 系统生成引用列表（基于CSL） 显示格式化引用
5 用户确认→生成Markdown引用标记 —

7.5 阶段五：排版

第一步：确认 LaTeX 模板

步骤 左栏（AI） 右栏（LaTeX预览）
1 用户粘贴格式要求 —
2 AI 解析→生成模板骨架 实时渲染
3 用户反馈→迭代 更新渲染
4 确认模板可用 —

第二步：Markdown ↔ LaTeX 联动

工作区 内容
左栏 Markdown 编辑器（所见即所得）
右栏 LaTeX 实时渲染预览

· 左编辑 Markdown → 系统转 LaTeX → 右栏更新
· 引用标记替换：[@doi:xxx] → 按选定格式替换
· 用户可导出 .tex 或一键编译 PDF

八、数据模型

8.1 文献卡片（CSV + Markdown 双向同步）

CSV 结构：

```
doi,title,journal,first_author,corresponding_author,keywords,abstract,category,subcategory,theory,experiment_design,data,results,policy_suggestions,experiment,characterization,mechanism,application,custom_fields,status,last_modified
```

Markdown 结构： 与 CSV 字段对应，人类可读可编辑

8.2 知识库卡片（CSV + Markdown 双向同步）

用户自定义提示词 → AI 从知识库提取 → 经事实核查 → 存入

8.3 记忆文件（三角色分离）

角色 文件 内容
助手 assistant.md 所有 AI 输出
审阅 reviewer.md 审计日志
秘书 secretary.md 秘书审阅记录

8.4 临时知识

对话过程中的工作缓存，所有写入内容必须经事实核查。

九、MinerU 处理规则

项目 规则
输入 PDF / 电子书
输出 Markdown（保留图片+公式）
限制 200页 / 100MB
大文件 自动切分
触发方式 手动上传 / 监控目录自动检测

十、技术约束

项目 约束
当前语言 Python 3.11+
未来重构 Rust
打包方式 Tauri + Python sidecar → 单个 EXE
LaTeX 引擎 Tectonic（内嵌）
数据格式 仅 CSV + Markdown（落盘存储）
监控目录 用户设置，自动转换触发点
数据存储目录 用户设置，所有数据根目录
API 4 个接口位
安装体验 傻瓜式，无需配置环境
调试集成 接入调试助手 SDK

十一、后话（预留）

项目 状态
自动更新机制 ⚠️ 后话
跨平台（macOS/Linux） ⚠️ 后话

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
