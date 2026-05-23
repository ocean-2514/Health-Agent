# Phase 3 实验报告：基于 LangGraph 的多智能体协同诊断图

| 项目 | 内容 |
|---|---|
| 阶段 | Phase 3（多智能体协同层落地） |
| 分支 | `refactor/mcp-multi-agent` |
| 提交 | `9a6ebfa` |
| 变更规模 | +881 行 / 10 个文件（8 个新 Agents 源文件 + 1 个测试文件 + requirements.txt） |
| 新增依赖 | `langgraph` |

## 一、实验目标

Phase 2 把变压器健康管控能力做成了 12 个 MCP 工具，由**单个 LLM 客户端
自己决定怎么串**。Phase 3 把"取数 → 三源识别 → 证据融合 → RUL → 决策"
这条诊断流程，固化成一个**显式的多智能体协同图**，目标是：

1. **确定性可复现**：控制流不依赖 LLM 的临场判断，同样输入得到同样的
   执行路径——满足实验复现要求；
2. **智能体解耦**：任何一个 agent 不直接调用另一个 agent；
3. **协同可解释**：智能体之间的每一次"通信"都被记录成可审计的轨迹。

为此确立了**三条通信通道**的设计（详见 2.3）。

## 二、技术实现

### 2.1 总体架构

```
                          run_diagnosis()
                                |
                  +-------------v--------------+
                  |   LangGraph StateGraph     |
                  |   (graph.py / build_graph) |
                  +-------------+--------------+
                                |  在共享黑板 DiagnosisState 上运行
        +--------------+--------+-------+---------------+
        |              |                |               |
   Coordinator     Data Agent     Diagnosis Agent   Decision Agent
   (规则路由)      (取数据)       (识别+融合+DGA)   (RUL+LLM+报告)
        |              |                |               |
        +--------------+-------+--------+---------------+
                               |  复用 Phase 1 工具层
                       Python/Src/Tools/*
        （iotdb / inference / fusion / dga / rul / llm）
```

四个 agent 全部消费 Phase 1 的 [Tools/](../Python/Src/Tools/)，**不重写任何
算法**。Phase 3 只新增 [Python/Src/Agents/](../Python/Src/Agents/) 一个目录，
FastAPI 后端与 MCP server 路径零改动。

### 2.2 框架选型

| 框架 | 特点 | 取舍 |
|---|---|---|
| **LangGraph** | 显式 `StateGraph`、类型化状态、条件边、并行 fan-out、检查点 | **选用** |
| CrewAI | 角色化 agent，但偏对话驱动；Phase 1 已基本拆除其 BaseTool | 否（会与新 Tools/ 层产生漂移） |
| AutoGen | 对话式消息传递，涌现式协作 | 否（非确定性，实验数字难复现） |
| 手写编排 | 完全可控 | 否（检查点/并行/可视化都要自己造） |

变压器诊断是一条**有确定数据依赖的流水线**，不是开放式头脑风暴，所以
选了图结构最显式、最可复现的 LangGraph。

### 2.3 三层通信模型

| 通道 | 载体 | 作用 |
|---|---|---|
| **数据通道** | 类型化黑板 `DiagnosisState` | agent 读它需要的字段、写它产出的字段；没有任何 agent 直接调用另一个 agent |
| **控制通道** | Coordinator + `AgentRegistry` | Coordinator 遍历 registry 决定下一跳（规则式，不用 LLM） |
| **审计通道** | `DiagnosisState.comm_log` | 追加式记录每条智能体间消息，仅用于可解释性 |

关键点：**数据不走 `comm_log`**——数据走类型化字段。`comm_log` 是"叙事"，
和"机制"分离，可单独渲染成时序图。

### 2.4 共享状态 DiagnosisState

定义在 [Agents/state.py](../Python/Src/Agents/state.py)，是整个协同的唯一黑板：

| 分区 | 字段 | 写入方 |
|---|---|---|
| 输入 | `equipment_id` / `substation` / `raw_input` | 调用方 |
| Data 产出 | `scoring_trends` / `log_text` / `oil_values` / `image_path` | Data Agent |
| Diagnosis 产出 | `bert_result` / `cnn_result` / `yolo_result` / `fusion_result` / `dga_analysis` | Diagnosis Agent |
| Decision 产出 | `rul_result` / `final_report` | Decision Agent |
| 控制 / 通信 | `next_agent` / `comm_log` / `errors` | Coordinator / 各 agent |

`comm_log` 与 `errors` 带 **`operator.add` reducer**（`Annotated[List[...], operator.add]`）。
原因见 2.5——并行节点会在同一超步并发追加，没有 reducer 时 LangGraph 会
拒绝对同一字段的并发写。

### 2.5 图是如何构建的

这是 Phase 3 的核心。`build_graph()`（[Agents/graph.py](../Python/Src/Agents/graph.py)）
按以下步骤组装一个 LangGraph `StateGraph`：

#### 步骤 1：建注册表

`build_default_registry()` 注册三个 `AgentCard`（worker agent 的能力清单）：

| AgentCard | consumes（依赖字段） | produces（产出字段） |
|---|---|---|
| `DATA_CARD` | （无） | scoring_trends, log_text, oil_values, image_path |
| `DIAGNOSIS_CARD` | log_text, oil_values, image_path, scoring_trends | fusion_result, dga_analysis |
| `DECISION_CARD` | fusion_result, scoring_trends | rul_result, final_report |

#### 步骤 2：注册 8 个节点

```python
g = StateGraph(DiagnosisState)
g.add_node("coordinator", make_coordinator_node(registry))
g.add_node("data",  data_node)
g.add_node("bert",  bert_node)     # ┐
g.add_node("cnn",   cnn_node)      # ├ Diagnosis Agent 的并行三节点
g.add_node("yolo",  yolo_node)     # ┘
g.add_node("fusion", fusion_node)  # 三源融合（fan-in）
g.add_node("dga",   dga_node)      # DGA 趋势分析
g.add_node("decision", decision_node)
```

> 注意：逻辑上的 "Diagnosis Agent" 在图里展开成 **5 个节点**
> （bert/cnn/yolo/fusion/dga）。一个 `AgentCard` 对应一个逻辑 agent，
> 不必对应单个节点。

#### 步骤 3：连边

```
START ──> coordinator
coordinator ──(条件边 _route)──> data | [bert,cnn,yolo] | decision | END
data   ──> coordinator
bert ──┐
cnn  ──┼──> fusion          （三条入边 = fan-in，fusion 等三者都完成才跑）
yolo ──┘
fusion ──> dga
dga    ──> coordinator
decision ──> coordinator
```

完整拓扑：

```
            +-------------------------------+
            |          coordinator          |<--------------+
            +---+-------------+----------+---+               |
   _route 条件边 |             |          |                  |
        +-------v----+   +----v----+  +--v-------+           |
        |    data    |   | bert    |  | decision |           |
        +-----+------+   | cnn     |  +----+-----+           |
              |          | yolo    |       |                 |
              |          +----+----+       +-----------------+
              |               |  (并行)                      |
              |          +----v----+                         |
              |          | fusion  |                         |
              |          +----+----+                         |
              |               |                              |
              |          +----v----+                         |
              |          |  dga    |                         |
              |          +----+----+                         |
              +---------------+------------------------------+
```

#### 步骤 4：条件边 `_route`

Coordinator 是图的中枢——每个 worker 跑完都回到它。`_route` 是一个**纯映射
函数**，读 `state.next_agent`（由 coordinator 节点写入）决定去向：

```python
def _route(state):
    nxt = state.next_agent
    if nxt == "DONE" or nxt is None:  return END
    if nxt == "diagnosis":            return ["bert", "cnn", "yolo"]  # 并行 fan-out
    return nxt                        # "data" | "decision"
```

返回一个**列表**时，LangGraph 把这几个节点放进同一超步并发执行——这就是
Diagnosis Agent 的三源并行。职责切分清晰：coordinator **节点**负责决策 +
写日志，条件**边**只做映射。

#### 步骤 5：并行 fan-out / fan-in 的并发安全

- bert/cnn/yolo 在同一超步并发跑，各自写**互不相交**的字段
  （`bert_result` / `cnn_result` / `yolo_result`）——无冲突；
- 但三者都要追加 `comm_log`——这是对**同一字段的并发写**，靠 2.4 的
  `operator.add` reducer 把三次追加拼接起来；
- `fusion` 有三条入边，是 fan-in 节点，LangGraph 等 bert/cnn/yolo 全部
  完成后只跑它一次。

#### 步骤 6：编译

`g.compile()` 返回可执行图。`run_diagnosis()` 构造初始 `DiagnosisState`
并 `graph.invoke()`。

### 2.6 四个 agent 的职责

| Agent | 文件 | 图节点 | 复用的工具 |
|---|---|---|---|
| Coordinator | [coordinator.py](../Python/Src/Agents/coordinator.py) | coordinator | —（纯路由） |
| Data | [data_agent.py](../Python/Src/Agents/data_agent.py) | data | `iotdb_tool` |
| Diagnosis | [diagnosis_agent.py](../Python/Src/Agents/diagnosis_agent.py) | bert/cnn/yolo/fusion/dga | `inference_tool` / `fusion_tool` / `dga_tool` |
| Decision | [decision_agent.py](../Python/Src/Agents/decision_agent.py) | decision | `rul_tool` / `llm_tool` / `dga_tool` |

每个 agent 节点的统一约定：读 `DiagnosisState` 需要的字段 → 调 Phase 1
工具 → 返回一个**局部状态更新 dict** + 往 `comm_log` 追加一条 `AgentMessage`。

### 2.7 Coordinator 的规则路由

`decide_next_agent(state, registry)`（[coordinator.py](../Python/Src/Agents/coordinator.py)）：

```python
for card in registry.ordered():
    if card.is_runnable(state) and not card.is_satisfied(state):
        return card.name
return "DONE"
```

- `is_runnable`：该 card 的 `consumes` 字段在 state 里全部非空 → 可以跑；
- `is_satisfied`：`produces` 字段全部非空 → 没活可干了。

**遍历 registry** 而非写死 `if/elif`——这是有意为之的结构性钩子：将来注册
一个新 agent，路由逻辑零改动即可把它纳入工作流。控制路径完全不依赖 LLM，
因此确定、可复现、可单测。

## 三、图的一次完整执行

以 `run_diagnosis("tr01")` 为例，超步（superstep）序列：

```
START → coordinator → data → coordinator → [bert ‖ cnn ‖ yolo]
      → fusion → dga → coordinator → decision → coordinator → END
```

Coordinator 一共被触发 4 次，每次重新评估 registry 决定下一跳。这一趟产生
的 `comm_log`（智能体通信轨迹，共 11 条）：

| # | 发送方 → 接收方 | intent | 摘要 |
|---|---|---|---|
| 1 | coordinator → data | route | 路由 → data agent |
| 2 | data → diagnosis | result | 已拉取 tr01 的 10 个测点趋势 |
| 3 | coordinator → diagnosis | route | 路由 → diagnosis agent |
| 4 | diagnosis.bert → diagnosis.fusion | result | BERT 日志分类: 起火 (conf 0.95) |
| 5 | diagnosis.cnn → diagnosis.fusion | result | CNN 油色谱分类: 放电 (conf 0.95) |
| 6 | diagnosis.yolo → diagnosis.fusion | result | YOLO 图像检测: 0 处缺陷 |
| 7 | diagnosis.fusion → coordinator | result | 三源融合结论: 放电 (conf 0.15) |
| 8 | diagnosis.dga → coordinator | result | DGA 综合风险评分 99.0, 主要威胁 放电故障 |
| 9 | coordinator → decision | route | 路由 → decision agent |
| 10 | decision → coordinator | result | HI=81.93, RUL=18.32 年, 报告已生成 |
| 11 | coordinator → DONE | route | 全部 agent 已完成 |

该轨迹可序列化（`DiagnosisState.snapshot()`），可直接渲染成时序图。
样例输出指标：融合判定 = 放电，DGA 风险评分 = 99.0，HI = 81.93，
RUL = 18.32 年。

## 四、测试设计与结果

测试文件 [tests/integration/test_agent_graph.py](../tests/integration/test_agent_graph.py)，
10 个集成测试：

| 编号 | 测试 | 验证内容 |
|---|---|---|
| T1 | `test_graph_compiles` | `build_graph()` 能编译 |
| T2 | `test_default_registry_has_three_agents` | registry 含 3 个 worker agent |
| T3 | `test_agent_card_runnable_and_satisfied` | AgentCard 的 runnable/satisfied 判定 |
| T4 | `test_decide_next_agent_progression` | 路由在 4 个阶段的推进序列 |
| T5 | `test_registry_is_runtime_extensible` | 注册新 agent 即改变路由（动态钩子） |
| T6 | `test_data_node_produces_all_inputs` | Data 节点单独跑产出 4 个字段 |
| T7 | `test_run_diagnosis_end_to_end` | 完整图端到端：fusion/dga/rul/report 都非空 |
| T8 | `test_parallel_inference_results_present` | 并行三节点结果全部就位 |
| T9 | `test_comm_log_records_every_agent` | comm_log 含全部 agent 的消息，coordinator 路由 4 次 |
| T10 | `test_state_snapshot_is_json_serializable` | 状态快照可 JSON 序列化 |

**结果**：

```
tests/integration/test_agent_graph.py ..........  [10 passed]

全量套件：68 passed in 453s
```

合并 Phase 0/1/2 后累计：

| 阶段 | 新增测试 | 累计 |
|---|---|---|
| Phase 0 baseline | 5 | 5 |
| Phase 1 工具层 | 50 | 55 |
| Phase 2 MCP server | 8 | 63 |
| Phase 3 多智能体图 | 10 | **68** |

## 五、重要结果

### 5.1 功能层

1. 4 个 agent 在一张 LangGraph 图上协同跑通；Diagnosis Agent 的三源识别
   以真正的图级并行 fan-out 执行，在 `fusion` 节点 fan-in。
2. 端到端：`run_diagnosis("tr01")` 输出完整诊断报告，并留下 11 条可审计
   的智能体通信轨迹。

### 5.2 工程层

| 指标 | 数值 |
|---|---|
| 新增源代码 | 881 行 |
| 修改的旧源代码 | 0（仅 `requirements.txt` 增量） |
| 新增依赖 | `langgraph` |
| 测试 | 10 个集成测试，全量 68 passed |

### 5.3 架构层

- **三层通信分离**：数据走类型化黑板、控制走 registry、审计走 comm_log；
  机制与叙事解耦。
- **不变量保持**：复用 Phase 1 `Tools/`，FastAPI 与 MCP 路径零改动，
  Phase 0/1/2 的 58 个测试继续全绿。
- **前向兼容钩子**：Coordinator 遍历 `AgentRegistry` 路由（而非写死
  `if/elif`），每个 agent 带 `AgentCard`——为 Phase 4 的动态平台留好接口。

## 六、局限与下一步

### 6.1 当前局限

1. **图是静态的**：`build_graph` 手工连边，新增 agent 需改图。
2. **状态是封闭的**：`DiagnosisState` 每个产出物占一个写死字段。
3. **路由不含负载/异常分支**：规则路由只按"输入是否就绪"推进，
   尚无失败回退、重试、条件跳过。

### 6.2 Phase 4 计划

在 Phase 3 留下的 registry 钩子之上，构建**动态智能体平台**：
开放式 `artifacts` 命名空间替代封闭字段、`PluginLoader` 启动时扫描插件
目录、`build_graph` 从 registry 动态接节点；并通过 A2A 协议支持加载
**远程** agent。

## 七、复现实验

```bash
# 切到本阶段提交
git -C HealthAgent checkout 9a6ebfa

# 安装依赖
conda activate healthAgent
pip install -r requirements.txt

# 跑测试
python -m pytest tests/integration/test_agent_graph.py -v

# 直接运行多智能体诊断（打印 comm_log + 最终报告）
python Python/Src/Agents/graph.py
```

## 八、参考

- LangGraph：<https://langchain-ai.github.io/langgraph/>
- Phase 1 工具层提交：`01d2e2d`
- Phase 2 MCP server 提交：`ee67138` ・ 报告 [docs/PHASE2_REPORT.md](PHASE2_REPORT.md)
- Phase 3 提交：`9a6ebfa`
