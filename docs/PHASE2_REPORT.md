# Phase 2 实验报告：基于 FastMCP 的变压器健康管控工具服务化

| 项目 | 内容 |
|---|---|
| 报告时间 | 2026-05-16 |
| 阶段 | Phase 2（MCP Server 落地） |
| 分支 | `refactor/mcp-multi-agent` |
| 提交 | `ee67138` |
| 变更规模 | +719 行 / 10 个新文件 / 0 个旧文件破坏性修改 |

## 一、实验目标

把 Phase 1 沉淀到 [Tools/](../Python/Src/Tools/) 的全部健康管控能力，以
**Model Context Protocol（MCP）** 服务的形式开放给任意 MCP 客户端
（Claude Desktop、Claude Code、Cursor、Cline 等），实现：

1. **协议级解耦**：诊断能力不再绑死在自研 FastAPI / 自研前端，任何
   兼容 MCP 的 LLM 宿主都能调用；
2. **零回归**：原有 `/api/assess/*` REST 接口的请求/响应 schema 完全
   不变，前端无需任何改动；
3. **可对话式诊断**：把"取数据→单源识别→证据融合→RUL→建议"的
   决策树以 prompts 形式预置，让 LLM 一句话即可触发完整流水线。

## 二、技术实现

### 2.1 总体架构

```
+----------------------------+        +-----------------------------+
|  Claude Desktop / Code /   |        |   Web 前端（Vue）           |
|  Cursor 等 MCP 客户端       |        |                             |
+--------------+-------------+        +--------------+--------------+
               |                                     |
        stdio (JSON-RPC)                       HTTP /api/assess/*
               |                                     |
+--------------v-------------+        +--------------v--------------+
|  Python/MCPMain.py          |        |  Python/Main.py (FastAPI)   |
|  └─ Src/MCP/server.py       |        |  └─ Routes/AssessRoutes.py  |
|     ├─ tools.py  (12 tool)  |        |     └─ Services/            |
|     ├─ resources.py (2)     |        |        AssessmentService    |
|     └─ prompts.py (3)       |        |                             |
+--------------+--------------+        +--------------+--------------+
               \                                      /
                \           共享同一套工具层           /
                 \                                  /
                  +-> Python/Src/Tools/ <----------+
                       ├─ iotdb.py
                       ├─ inference/{bert,cnn,yolo,dga}.py
                       ├─ fusion/ds_murphy.py
                       ├─ rul/physics.py
                       └─ llm/dga_advice.py
```

**关键设计**：MCP server 与 FastAPI 后端是**两条对等的访问路径**，
都消费同一套 `Tools/`，互不影响。这意味着：
- LLM 通过 MCP 调用 `assess_full_health` 与前端调用
  `POST /api/assess/health` 走的是相同的物理代码路径；
- 任一侧改 schema 都不会污染另一侧；
- 单元/契约测试同时为两侧把关。

### 2.2 FastMCP 选型

候选 SDK 对比：

| 库 | 优点 | 缺点 | 选型 |
|---|---|---|---|
| `mcp`（官方） | 协议参考实现 | API 偏底层，需要手写 Server / Tool 描述 | 否 |
| `fastmcp` | 装饰器式注册（`@mcp.tool()`），自动从 type hints + docstring 生成 schema | 第三方维护，但作者后来贡献回官方 | **是** |
| 自研 | 完全可控 | 浪费时间 | 否 |

`fastmcp` 在 [Python/Src/MCP/server.py](../Python/Src/MCP/server.py) 仅需：

```python
from fastmcp import FastMCP
mcp = FastMCP("HealthAgent")
from . import tools, resources, prompts  # side-effect 注册
```

### 2.3 Tools 注册（12 个）

按职责分四组，全部以装饰器形式挂载到全局 `mcp` 实例
（[Python/Src/MCP/tools.py](../Python/Src/MCP/tools.py)）：

| 分组 | Tool | 委托给的 Tools/ 模块 |
|---|---|---|
| **数据获取** | `get_sensor_trend` | `Tools.iotdb.query_sensor_trend` |
| | `get_dga_trends` | `Tools.iotdb.query_dga_trends` |
| | `get_scoring_data` | `Tools.iotdb.query_scoring_data` |
| **单源识别** | `classify_inspection_log` | `Tools.inference.bert.classify` |
| | `classify_oil_chromatogram` | `Tools.inference.cnn.classify` |
| | `detect_image_defects` | `Tools.inference.yolo.detect` |
| **综合分析** | `analyze_dga` | `Tools.inference.dga.analyze` |
| | `get_dga_expert_advice` | `Tools.llm.dga_advice.suggest` |
| | `fuse_three_sources` | `Tools.fusion.ds_murphy.fuse` |
| | `compute_remaining_useful_life` | `Tools.rul.physics.compute` |
| **一键流水线** | `assess_full_health` | `Services.AssessmentService.assess_full_health` |
| | `assess_defect_only` | `Services.AssessmentService.assess_defect_only` |

每个工具的入参类型与返回 schema 由 Python type hints + Pydantic 自动推导，
LLM 客户端在 `tools/list` 阶段即可看到完整描述，无需额外 OpenAPI 定义。

### 2.4 Resources（2 个）

资源（resource）是 MCP 中"被 LLM 主动加载到上下文"的只读数据，区别于
"被 LLM 主动调用产生副作用"的 tool。我们暴露两个 IoTDB 数据快照模板
（[Python/Src/MCP/resources.py](../Python/Src/MCP/resources.py)）：

| URI 模板 | 内容 | 典型用途 |
|---|---|---|
| `iotdb://{equipment_id}/scoring` | 10 个评分测点 7 天趋势 JSON | LLM 在做综合判断前预加载 |
| `iotdb://{equipment_id}/dga` | 7 个 DGA 气体 7 天趋势 JSON | 解释气体异常时引用 |

### 2.5 Prompts（3 个）

Prompts 是预置的对话模板，LLM 客户端可一键唤起
（[Python/Src/MCP/prompts.py](../Python/Src/MCP/prompts.py)）：

| Prompt | 引导动作 |
|---|---|
| `diagnose_transformer(equipment_id)` | 完整决策树：先取数 → 三源识别 → DS 融合 → RUL → 维护建议 |
| `quick_health_screen(equipment_id)` | 30 秒筛查：直接调 `assess_full_health` 汇报四行结论 |
| `explain_dga_anomaly(equipment_id)` | 聚焦 DGA：取趋势 → 调 `analyze_dga` → 调 `get_dga_expert_advice` |

Prompt 让人用自然语言"用 healthagent 帮我筛查 tr01"即可触发整条链路，
对终端用户屏蔽了底层 12 个工具的存在。

## 三、测试设计与结果

### 3.1 测试框架

- 框架：`pytest` + `pytest-asyncio`（`asyncio_mode = auto`）
- 文件：[tests/integration/test_mcp_server.py](../tests/integration/test_mcp_server.py)
- 命令：`conda run -n healthAgent python -m pytest tests/integration/test_mcp_server.py -v`

### 3.2 测试矩阵

| 编号 | 测试名 | 验证内容 |
|---|---|---|
| T1 | `test_server_instance_exists` | `mcp` 单例可被导入且非空 |
| T2 | `test_tools_registered` | 12 个工具全部出现在 `mcp.list_tools()` 返回中 |
| T3 | `test_resources_registered` | 2 个 resource 模板已注册 |
| T4 | `test_prompts_registered` | 3 个 prompt 已注册 |
| T5 | `test_call_get_sensor_trend` | 端到端调用：模拟 client → MCP → IoTDB tool → 返回 JSON |
| T6 | `test_call_assess_full_health` | 端到端调用流水线 tool（含三源识别 + 融合 + RUL）|
| T7 | `test_read_resource_scoring` | 读取 `iotdb://tr01/scoring` 返回非空 JSON |
| T8 | `test_render_prompt_quick_screen` | 渲染 `quick_health_screen` 返回包含设备 ID 的字符串 |

### 3.3 运行结果

```
tests/integration/test_mcp_server.py::test_server_instance_exists PASSED
tests/integration/test_mcp_server.py::test_tools_registered PASSED
tests/integration/test_mcp_server.py::test_resources_registered PASSED
tests/integration/test_mcp_server.py::test_prompts_registered PASSED
tests/integration/test_mcp_server.py::test_call_get_sensor_trend PASSED
tests/integration/test_mcp_server.py::test_call_assess_full_health PASSED
tests/integration/test_mcp_server.py::test_read_resource_scoring PASSED
tests/integration/test_mcp_server.py::test_render_prompt_quick_screen PASSED

============== 8 passed ==============
```

合并 Phase 0/1 后，仓库累积测试通过情况：

| 阶段 | 新增测试数 | 累计 | 全绿 |
|---|---|---|---|
| Phase 0 baseline | 5 | 5 | √ |
| Phase 1 工具层 | 50（40 单测 + 10 契约） | 55 | √ |
| Phase 2 MCP server | 8 | **63** | √ |

### 3.4 契约保护

Phase 1 写下的 10 个契约测试持续运行，证明 `/api/assess/health` 与
`/api/assess/defect` 的请求/响应 JSON 在 Phase 2 改造后**字节级一致**。
即原 Vue 前端不需要任何改动即可继续工作。

## 四、重要结果

### 4.1 功能层

1. **12 个工具 / 2 个资源 / 3 个 prompts** 全部在 `mcp.list_tools()`、
   `list_resources()`、`list_prompts()` 中可见且可调用。
2. **端到端走通**：在 Claude Desktop 中配置一行 stdio command 后，
   只用一句"用 healthagent 帮我筛查 tr01"即可触发
   `quick_health_screen` → `assess_full_health` →（IoTDB 取数 + BERT/CNN/YOLO
   推理 + DS 融合 + 物理 RUL 计算 + LLM 建议）→ 一段中文报告。
3. **多客户端兼容**：同一份 server 同时通过验证 Claude Desktop 与
   Claude Code（CLI 与 VSCode 扩展）。

### 4.2 工程层

| 指标 | 数值 |
|---|---|
| 新增源代码行 | 719 |
| 修改的旧源代码行 | 0（仅 `requirements.txt`、`pytest.ini` 配置增量） |
| 新增依赖 | `fastmcp`、`pytest-asyncio` |
| 测试覆盖 MCP 路径 | 8 个集成测试，包括端到端调用与 schema 注册 |
| 启动方式 | `python Python/MCPMain.py`（stdio）|
| 平均冷启动时间 | ≈ 4.2 s（含 torch、transformers、ultralytics 全部 import） |

### 4.3 架构层

- **能力解耦**：诊断算法 / 业务流水线 / 协议传输三层彻底分离，未来想
  接入新的 LLM 宿主只需在客户端注册 stdio command，0 改动后端。
- **共享工具层**：MCP 与 REST 共消费 `Tools/`，避免双份实现产生漂移；
  这条不变量由契约测试守门。
- **可演进**：当前为 stdio 传输；后续若需要远程访问，仅需把
  `mcp.run()` 切到 `transport="streamable-http"`，业务代码不动。

## 五、局限与下一步

### 5.1 当前局限

1. **MCP 端无身份认证**：stdio 传输天然只本机可访问；若切换到 HTTP，
   需补 token 校验。
2. **流式输出未启用**：长任务（YOLO 推理 + DGA 趋势分析）当前一次性
   返回，没有用 MCP 的 progress notification 边算边推。
3. **资源粒度较粗**：目前的 resource 是"全 7 天快照"，未来可加
   `iotdb://{equipment_id}/scoring?since=...` 之类的查询参数。

### 5.2 Phase 3 计划（多智能体协同）

把当前由 LLM 自己串工具的流程，升级为 **LangGraph 多 Agent 编排**：

| Agent | 职责 |
|---|---|
| Coordinator | 接收用户问题，分发任务 |
| Data Agent | 专管 IoTDB 取数（消费 MCP `get_*` 工具）|
| Diagnosis Agent | 三源识别 + DS 融合 |
| Decision Agent | 出 RUL + 维护建议 + 工单 |

MCP server 在 Phase 3 仍然是 Diagnosis / Decision Agent 的工具供给方，
不会被替换。

## 六、复现实验

```bash
# 1. 切到本阶段提交
git -C HealthAgent checkout ee67138

# 2. 安装依赖
conda activate healthAgent
pip install -r requirements.txt

# 3. 跑测试
python -m pytest tests/integration/test_mcp_server.py -v

# 4. 在 Claude Desktop / Claude Code 中按 docs/MCP_USAGE.md 接入
```

## 七、参考

- MCP 规范：<https://modelcontextprotocol.io/>
- FastMCP：<https://github.com/jlowin/fastmcp>
- 本项目用法手册：[docs/MCP_USAGE.md](MCP_USAGE.md)
- Phase 1 工具层提交：`01d2e2d`
- Phase 2 提交：`ee67138`
