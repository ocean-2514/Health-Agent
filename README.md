# 电力变压器全寿命周期健康管控多智能体平台

一个面向电力变压器健康管控的多智能体系统:底层是**可复现、可审计的确定性诊断
内核**,外层是**大模型驱动的自控对话编排**。用户用自然语言(如"给 tr01 做体检")
即可触发完整诊断、历史分析、知识检索与多设备并行处理,整条工作流实时可见。

---

## 核心能力

- **确定性诊断内核**:时序取数 → BERT/CNN/YOLO 三源缺陷识别 → D-S 证据融合 →
  DGA 风险分析 → 物理模型 RUL(剩余寿命)→ 诊断报告。四个内层智能体在 LangGraph
  图上协同,三源识别并行执行,规则路由,**同输入同输出**,并由 golden-trace 测试焊死。
- **自控 Agent 编排(Supervisor)**:自有的工具调用循环(推理→行动→观察),
  通过 OpenAI 兼容接口对接大模型;带工具结果防护、错误兜底、重试、迭代上限。
- **三层能力 Tool / Skill / Agent**:
  - **Tool**——LLM 直接调用的可执行单元(诊断、查历史、远程协作);
  - **Skill**——可按需加载的领域知识(`SKILL.md`,如 DGA 判读、检修报告写法),
    且带**经验记忆**(越用越懂);
  - **Agent**——可派生的子智能体(explore 只读 / general 全能),支持**并发**处理
    多设备等独立子任务。
- **上下文管理**:单轮内压缩 + 跨轮自动摘要,长对话不超模型窗口。
- **跨会话记忆**:文件式四类记忆 + 语义召回,跨会话累积对用户与项目的认知。
- **动态注册 / 热加载**:工具(本地类 / 目录扫描 / 远程 A2A)可运行时增删启禁,**不重启**。
- **流式 Web 体验**:回复逐字流出 + **实时工作流可视化**(工具/技能/子智能体调用状态)
  + Markdown 富文本报告。
- **多入口**:Web 前端、HTTP API、命令行 CLI、MCP 服务。

> 详尽的系统说明见 **[docs/OVERVIEW.md](docs/OVERVIEW.md)**。

---

## 架构一览

```
用户 (Web / CLI / MCP)
        │
   Supervisor —— 自控 Agent 循环 (OpenAI 兼容, 可接 DeepSeek / 本地 Ollama)
        ├─ 上下文管理 (压缩 + 摘要, SQLite)
        ├─ 跨会话记忆 (4 类 + 语义召回)
        └─ 三层能力:
             Tool ── transformer_diagnosis ── 确定性诊断内核 (LangGraph 图)
                  ├─ history_lookup (查历史)
                  └─ 远程 A2A 工具 (跨进程协作)
             Skill ── 领域知识 (SKILL.md + 经验记忆)
             Agent ── 子智能体 (explore / general, 并发 fork-return)
```

---

## 项目结构

```
HealthAgent/
├─ Python/
│  ├─ Main.py                 # FastAPI 入口 (REST /api/assess/* + 智能体 /api/agent/*)
│  ├─ MCPMain.py              # MCP 服务入口
│  └─ Src/
│     ├─ Tools/               # 算子层:dga / fusion / rul / inference / iotdb / llm
│     ├─ Agents/              # 确定性诊断内核 (LangGraph 图 + 4 智能体 + 插件)
│     ├─ Supervisor/          # 外层自控运行时 (循环 / 上下文 / 记忆 / 三层能力 / 子Agent)
│     └─ API/                 # 路由 (含 SSE 流式)
├─ Config/                    # tools.yaml / remote_tools.yaml / GlobalConfig.yaml
├─ skills/                    # 领域知识技能 (SKILL.md + 经验记忆)
├─ golden/                    # 确定性基准快照
├─ Web/                       # React + Vite 前端 ("智能体平台"页 + 流式 + Markdown)
└─ docs/                      # 总览 + 各阶段实验报告
```

---

## 快速启动

### 环境
- **Python** 3.10+（推荐虚拟环境）
- **Node.js** 18+ / 20+
- **Apache IoTDB**(测试版本 1.3.3,默认端口 6667;诊断内核默认使用内置 mock 数据,
  联真实库时需运行)

### 后端
```bash
pip install -r requirements.txt
# 配置大模型:编辑 Config/GlobalConfig.yaml 的 LLM.Agent
#   - 云端:填 DeepSeek 等 OpenAI 兼容端点的 BaseURL/APIKey/ModelName
#   - 本地:留空占位则回退 LLM.Local 的 Ollama (http://localhost:11434/v1)
python Python/Main.py            # 启动 HTTP 服务 (默认 :8000)
```

### 前端
```bash
cd Web
npm install
npm run dev                      # 打开后选顶部"智能体平台"页
```

### 命令行
```bash
python Python/Src/Supervisor/chat_cli.py
```

---

## 配置与脱网部署

- **模型切换**:同一套循环走 OpenAI 兼容接口,只改 `Config/GlobalConfig.yaml` 即可在
  **DeepSeek 云端 API** 与 **本地 Ollama** 之间切换(`LLM.Agent` 的 `APIKey` 为占位符时
  自动回退到 `LLM.Local`)。
- **完全脱网**:面向工业内网,模型与数据均可本地化;配置已解耦,无需改核心代码。
- **能力扩展**:在 `Config/tools.yaml` / `remote_tools.yaml` 增工具,或在 `skills/` 下
  放 `SKILL.md` 增知识——支持运行时热加载,无需重启。

---

## 质量保障

- **离线烟测**(打桩大模型,不依赖网络):自控循环、上下文压缩、跨会话记忆、技能层、
  动态注册、子智能体、流式。
  ```bash
  python -m Python.Src.Supervisor._loop_smoke
  python -m Python.Src.Supervisor._subagent_smoke
  # ……(各子系统对应 _*_smoke)
  ```
- **确定性闸门**(真实诊断,验证同输入同输出):
  ```bash
  python -m Python.Src.Supervisor._golden_smoke
  ```

---

## 文档

| 文档 | 内容 |
|---|---|
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | 系统总览(架构 / 三层能力 / 各机制) |

---

## 参与贡献

欢迎提交 Issue 或 Pull Request。
