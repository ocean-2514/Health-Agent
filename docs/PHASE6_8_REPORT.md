# Phase 6-9 实验报告：外层 Supervisor 对话层、远程 A2A 接入、动态注册与 tool/skill/agent 三层正名

| 项目 | 内容 |
|---|---|
| 报告时间 | 2026-06-11 |
| 阶段 | Phase 6（Supervisor 对话层） + Phase 7（远程 A2A 接入） + Phase 8（动态注册） + Phase 9（三层正名 + 提示词 Skill 层） |
| 分支 | `refactor/mcp-multi-agent` |
| 提交 | （待提交） |
| 变更规模 | +2608 行（Phase 6-8） + Phase 9 三层重构（重命名 + 新增提示词 Skill 层 + 示例 SKILL.md） |
| 新增依赖 | `langchain-ollama`, `a2a-sdk`（含 starlette/uvicorn extras） |

> **术语变更（Phase 9）**：Phase 6-8 把所有 LLM 可调单元都叫 **Skill**，
> 但它名不副实——它是"LLM 直调的可调函数"，业界惯例叫 **Tool**；而 **Skill**
> 在 Claude Agent SDK / CodeWhale 里指的是"可加载的提示词/知识（SKILL.md）"。
> Phase 9 据此正名：旧 `Skill`→`Tool`，并**新增**了真正的提示词 Skill 层。
> **下文第一至六节保留 Phase 6-8 的历史叙述（仍用旧 "Skill" 称呼），
> 当前生效的命名与架构见第七节。**

## 一、实验目标

Phase 3-5 把变压器诊断流程做成了一张**确定性的 LangGraph 图**——同样输入
得到同样的执行路径，可复现、可审计。但它的入口仍然是单次函数调用
`run_diagnosis(equipment_id, ...)`，不会与用户多轮对话，也无法在不重启
进程的前提下接入新能力。本阶段在 Phase 3-5 之上加一层"对话 + 平台"
能力：

1. **分层对话**：在内层确定性图之外加一层 LLM 驱动的 Supervisor，把
   `transformer_diagnosis` 整条流水线**当成一个 Skill** 暴露给 LLM；
   再加 `history_lookup` 等横向 Skill。LLM 根据用户自然语言决定调哪个、
   先调哪个，多轮上下文沿 SQLite 持久化；
2. **远程接入**：通过 A2A 协议把别的进程里的 agent 当成 Skill 加进来，
   与本地 Skill 同地位；
3. **动态注册**：在 CLI / 程序里**运行时**增删启禁 Skill（本地类、目录
   插件、远程 URL、YAML 批量），不重启进程。

这三块合起来等价于一个**面向用户的多智能体对话平台**。内层 LangGraph
的确定性约束完全保留：Supervisor 只负责"调度 + 对话"，调度结果落到
Skill 层后仍走确定性的执行路径。

## 二、技术实现

### 2.1 总体架构

```
                        用户自然语言
                              |
                   +----------v-----------+
                   |   Supervisor (LLM)   |   ← Phase 6
                   |   create_react_agent |
                   +---+--+--+--+--+--+---+
                       |  |  |  |  |  |
            tool 调用层 (LangChain StructuredTool)
                       |  |  |  |  |  |
       +---------------+  |  |  |  |  +----------------+
       v                  v  |  |  v                   v
+-----------+  +--------------+  | +-----------+  +------------+
| 本地 Skill |  | 本地 Skill   |  | | 远程 A2A  |  | 动态注册的 |
|           |  |              |  | | Skill     |  | 任意 Skill |
| history_  |  | transformer_ |  | |           |  |            |
| lookup    |  | diagnosis    |  | | (HTTP)    |  | (运行时加) |
+-----+-----+  +------+-------+  | +-----+-----+  +------------+
      |               |          |       |
      v               v          v       v
+--------+   +-------------------+  +---------------+
|SQLite  |   |  Phase 3-5        |  | a2a_demo_     |
|sessions|   |  确定性 LangGraph  |  | server (本机) |
|+ 诊断  |   |  (build_platform_  |  | 或任意远端    |
|记录    |   |   registry +      |  | A2A endpoint  |
|        |   |   run_diagnosis)  |  |               |
+--------+   +-------------------+  +---------------+
```

四件事在同一架构里成立:

* **Phase 3-5 不动**——`transformer_diagnosis` Skill 是 Phase 3-5 图的薄
  包装。Supervisor 看不到 fusion/dga/rul 这些细节,只看到一个返回
  `health_index + RUL + verdict + report` 的工具。
* **Skill 接口统一**——本地类、本地目录、远程 A2A、运行时注入,都满足
  同一个 `Skill = (SkillCard + run)` 协议;LLM 看到的工具列表里无法
  区分谁本地谁远程。
* **Session 不绑 Skill**——chat history 与 diagnosis records 都在
  SQLite 里,不同 chat session 共享设备的历史诊断,符合"一台设备的
  历史不应只属于一个对话"的现实。
* **注册可变**——Supervisor 把 Skills 存在 `OrderedDict` 而非元组,
  每次增删启禁后**重编译 react agent**(LangGraph 没有公开的 in-place
  tool 插入 API)。

### 2.2 Skill 协议(Phase 6 基础)

定义在 [Python/Src/Supervisor/skill.py](../Python/Src/Supervisor/skill.py):

```python
@dataclass(frozen=True)
class SkillCard:
    name: str
    description: str           # LLM 读它决定何时调
    input_model: Type[BaseModel]   # → JSON Schema 喂给 tool calling
    output_model: Type[BaseModel]

@runtime_checkable
class Skill(Protocol):
    card: SkillCard
    def run(self, **kwargs) -> BaseModel: ...
```

外层 Skill 与内层 `AgentCard` 是**两套契约**:

| 维度 | 内层 AgentCard(Phase 3-5) | 外层 SkillCard(Phase 6) |
|---|---|---|
| 调用语义 | 黑板上的槽位生产/消费(`consumes`/`produces`) | 函数调用(request/response) |
| Schema | `ArtifactSpec`(key + schema_name + version) | Pydantic 模型(直接转 JSON Schema) |
| 谁来决策 | Coordinator 按规则路由 | LLM tool calling |
| 抽象层 | 共享黑板上的并发节点 | 顶层"能力包" |

不混用是因为两层服务于不同目的——内层要可复现、可审计、并行;外层要
LLM 友好、natural language 入口。

### 2.3 Supervisor 对话核心

[Python/Src/Supervisor/core.py](../Python/Src/Supervisor/core.py)。
LangChain 1.x 把 `AgentExecutor` 移除,所以我们用
`langgraph.prebuilt.create_react_agent` 编译一个 tool-calling loop:

```python
self._llm = ChatOllama(model=..., base_url=..., temperature=0)
self._tools = [skill_to_tool(s) for s in active_skills]
self._agent = create_react_agent(
    model=self._llm,
    tools=self._tools,
    prompt=_SYSTEM_PROMPT,
)
```

每个 chat 轮:

```
chat(session_id, user_input)
    ├─ history = SessionStore.get_history(session_id)        # [Human, AI, ...]
    ├─ messages = history + [HumanMessage(user_input)]
    ├─ result   = self._agent.invoke({"messages": messages})  # 可能多次 tool 调用
    ├─ answer   = _extract_final_answer(result["messages"])  # 跳过 tool frames
    └─ SessionStore.save_message(session_id, "user"/"assistant", ...)
```

系统提示把"何时调工具 / 何时直接答"的判断写明,避免 LLM 对 follow-up
问题(比如"那它的 RUL 是多少")**重复触发**昂贵的诊断流水线。

### 2.4 SQLite 会话与诊断记录

[Python/Src/Supervisor/session.py](../Python/Src/Supervisor/session.py)
带三张表:

| 表 | 作用 |
|---|---|
| `sessions` | 会话元信息(id / created_at / last_active / message_count) |
| `messages` | 每轮对话明细,role + content,按 session_id 外键级联删除 |
| `diagnosis_records` | **设备级**诊断结果(`equipment_id` 索引,**不绑 session**) |

把 `diagnosis_records` 与 chat 解耦,是为了让 `history_lookup` Skill
能在**任何新会话里**回答"tr01 上次诊断结果"——历史属于设备,不属于
对话。

CLI 暴露会话管理:`/list /switch /delete /new /id /history`,在
[chat_cli.py](../Python/Src/Supervisor/chat_cli.py) 里直接调
`SessionStore.list_sessions / session_exists / delete_session`。

### 2.5 三个本地 Skill

| Skill | 文件 | 包装的能力 |
|---|---|---|
| `transformer_diagnosis` | [skills/transformer_diagnosis.py](../Python/Src/Supervisor/skills/transformer_diagnosis.py) | Phase 3-5 整条诊断图;run 完后**写一条 `diagnosis_records`** |
| `history_lookup` | [skills/history_lookup.py](../Python/Src/Supervisor/skills/history_lookup.py) | 按 equipment_id 读 `diagnosis_records`,算 HI/RUL 变化趋势,返人话摘要 |
| `knowledge_qa` | (留给其他成员) | 缺陷知识 QA |

`TransformerDiagnosisSkill` 没有 `SKILL` 模块级单例——loader 在 YAML
里实例化它(原因见 2.6)。

### 2.6 YAML 声明式加载

[Config/skills.yaml](../Config/skills.yaml) + [Supervisor/loader.py](../Python/Src/Supervisor/loader.py):

```yaml
skills:
  - name: transformer_diagnosis
    class_path: Python.Src.Supervisor.skills.transformer_diagnosis.TransformerDiagnosisSkill
    enabled: true
    init_kwargs: {}
```

`load_skills()` 拿到一个扁平 List[Skill],Supervisor `__init__` 收下。
加一个新 Skill = 写一个类 + YAML 加一行,**Supervisor / CLI / 测试 0 改动**。

### 2.7 远程 A2A 接入(Phase 7)

[Python/Src/Supervisor/remote/](../Python/Src/Supervisor/remote/):

```
remote/
├── a2a_client.py     # 同步壳: discover_card / send_text (内部 asyncio.run)
├── remote_skill.py   # RemoteA2ASkill 适配器: SkillCard + run
└── loader.py         # YAML 驱动 + 宽松启动探活
```

**接入层选择**:RemoteA2ASkill 在 **outer skill 层**(LLM 可见),不在
inner platform 层。理由:
- A2A 的能力(知识检索、外部数据)更接近"被 LLM 主动调用"的工具,
  而不是诊断流水线里的固定步骤;
- LLM 看到的工具列表里"本地 vs 远程"无差别,便于扩展;
- 内层图保持完全确定性,不引入"对方进程随时挂"的不确定性。

**通用 IO 契约**:A2A 的 Part 只有 text / data / raw 这几种,**强行**
给每个远程 agent 造 Pydantic schema 要么 YAML 编码模型(脆弱)要么
每个远程加一个 Python 文件(boilerplate)。所以统一用:

```python
class RemoteA2AInput(BaseModel):
    instruction: str   # 给远端的指令(natural language or JSON)

class RemoteA2AOutput(BaseModel):
    text: str
    raw_json: Optional[Any]    # 自动 parse 试一下
    success: bool = True
    error: Optional[str] = None
```

**故障语义**:传输错不抛,返回 `success=False`。让 LLM 自己看
错误原因,而不是被 LangChain 抹平成 `"Tool error: ..."` 字符串。

**宽松探活**:启动时拉远端 agent-card 富化 description,拉不到只
warning + 标注 `unreachable at startup`,**仍然注册**——远程服务晚
启动是常态,不该卡住整个 CLI。

**Demo server** [a2a_demo_server/fake_search_server.py](../a2a_demo_server/fake_search_server.py)
用 `a2a-sdk` + Starlette + uvicorn 起一个最小 A2A 服务,响应固定的
缺陷知识 JSON,用作端到端联调。

### 2.8 动态注册 API(Phase 8)

`Supervisor` 把 Skills 存成 `OrderedDict[str, Skill]` + `Set[str]` 禁
用集:

| 方法 | 语义 |
|---|---|
| `register_skill(skill)` | 单注册;重名**覆盖** + **保留原位**(OrderedDict 直接赋值的行为) |
| `register_skills([...])` | 批量;**仅 1 次** `_rebuild_agent()`(否则 N 次) |
| `unregister_skill(name)` | 删除 + 清禁用标记;返 bool 表示是否存在 |
| `enable_skill / disable_skill(name)` | 软开关——禁用项保留在 registry,不暴露给 LLM |
| `register_skill_from_config(spec)` | 给一个 `{class_path, init_kwargs, ...}` 实例化并注册 |
| `register_skills_from_path(dir)` | 扫目录,见 2.9 |
| `register_remote_skill(url, name=?, description=?)` | URL 一行;`name`/`description` 缺则探 card 补 |
| `register_remote_skills_from_yaml(path?)` | 任意 YAML 路径,跳过已注册同名(idempotent) |

每个 mutator 收尾**重编译 `create_react_agent`**——LangGraph 没有
splice tool 的公开 API,只能重建。重建只是图编译,远小于一次 LLM 调用。

CLI 暴露的命令:

```
/skills                         (列出,禁用项加 [disabled] 后缀)
/register <class_path>          (本地类,无参构造)
/unregister <name>
/enable <name>  /disable <name>
/load_dir <path>                (扫目录加本地插件,见 2.9)
/register_remote <url> [name]   (一行加远程)
/load_remote_yaml [path]        (批量加远程)
```

### 2.9 目录扫描(SKILL / SKILLS 模块约定)

[discovery.py](../Python/Src/Supervisor/discovery.py) 扫
`*.py`,只看模块级:

```python
SKILL = SomeSkillInstance(...)         # 单导出
# 或
SKILLS = [Skill1(...), Skill2(...)]    # 多导出
```

为什么用模块约定而不是 `issubclass` 反射:
- Skill 是 `runtime_checkable Protocol`,`issubclass` 检查的本质也是
  属性存在,反而比显式标记更弱;
- 跟内层 PluginLoader 的 `AGENT = ...` 完全对齐;
- 同名 skill 静默跳过——与 mutator 的"重名覆盖"区分开,避免热加载
  误覆盖运行中的关键 Skill。

示例 [examples/hot_skills/](../examples/hot_skills/):`echo_skill.py` 用
`SKILL =`,`time_skill.py` 用 `SKILLS = [...]`,供烟测。

## 三、一次完整的对话执行

用户在 CLI 里这一段:

```
[xxx] you> tr01 体检一下
assistant> (调 transformer_diagnosis) HI=81.93, RUL=18.32 年, 融合判定: 放电
[xxx] you> 那它上次的诊断结果呢?
assistant> (调 history_lookup) tr01 上次 HI=82.15 (-0.22)、RUL=18.51 → 18.32 年
[xxx] you> 局部放电怎么处理?
assistant> (调 defect_kb_search 远程) GB/T 7252-2016 5.3.2 ...
[xxx] you> /load_dir examples/hot_skills
新增 3 个 skill: ['echo', 'current_time', 'current_year']
[xxx] you> 现在几点?
assistant> (调 current_time) 2026-06-05T22:14:31, Friday
```

每一轮内部:

```
load history (SQLite)
   ↓
LLM(messages + system_prompt + tool schemas) → tool_call
   ↓
StructuredTool._invoke
   ↓
Skill.run(**kwargs)            ← 本地直接跑 / 远程 A2A roundtrip
   ↓
output_model.model_dump → 回到 LLM
   ↓
LLM 整合 → AIMessage
   ↓
save_message(user) + save_message(assistant)
```

第 1 轮的 `transformer_diagnosis` 还会写一条 `diagnosis_records`,
第 2 轮 `history_lookup` 就读得到——跨 Skill 的状态在 SQLite 里。

`/load_dir` 触发 `register_skills_from_path` → `_rebuild_agent` →
新工具立即出现在 LLM 的工具列表里,第 4 轮直接可用。**没有重启进程,
也没有重连 LLM。**

## 四、烟测设计与结果

三组烟测,合计**21 个检查点全过**。LLM 部分在动态注册测里被
`unittest.mock.patch` 替换为 stub(`ChatOllama` 与 `create_react_agent`
都打桩),避免依赖 Ollama 在线;远程那组依赖真实 demo server 起本机
HTTP。

### 4.1 Phase 7 端到端([remote/_smoke.py](../Python/Src/Supervisor/remote/_smoke.py))

依赖 `python -m a2a_demo_server.fake_search_server` 在后台运行。

| # | 检查 | 结果 |
|---|---|---|
| 1 | `load_remote_skills()` 从 YAML 读到 1 个 skill,探活富化 description | ok |
| 2 | `load_skills()` 把 local + remote 合并 | `['transformer_diagnosis', 'history_lookup', 'defect_kb_search']` |
| 3 | `RemoteA2ASkill.run()` 真实 HTTP 往返,自动 parse `raw_json` | matches 3 条 |
| 4 | `skill_to_tool()` 包出 LangChain StructuredTool 可调 | ok |
| 5 | 死 URL: 仍注册 + warning + 调用返 `success=False`(不抛) | ok |

### 4.2 Phase 8 动态注册([_dynamic_smoke.py](../Python/Src/Supervisor/_dynamic_smoke.py))

| # | 检查 | 结果 |
|---|---|---|
| 1 | 初始化 1 个 skill,**1 次** rebuild | ok |
| 2 | `register_skill` 后 +1 rebuild | ok |
| 3 | `register_skills([3 个])` 后 **仅 +1** rebuild(批量) | ok |
| 4 | `disable_skill` 后 active 列表去掉,`all_skill_names` 保留 | ok |
| 5 | `enable_skill` 恢复 | ok |
| 6 | `unregister_skill` 存在/不存在 → True/False | ok |
| 7 | 重名注册 → **保留原位** | alpha 仍在第 0 位 |
| 8 | `register_skill_from_config` good path | ok |
| 9 | `register_skill_from_config` 坏 class_path → `SkillLoadError` | ok |
| 10 | `register_skills_from_path('examples/hot_skills')` 加 2 个(echo 已在则跳) | `['current_time', 'current_year']` |

### 4.3 Phase 8.7-8.10 远程动态([_remote_dynamic_smoke.py](../Python/Src/Supervisor/_remote_dynamic_smoke.py))

| # | 检查 | 结果 |
|---|---|---|
| 1 | `register_remote_skill(url)` 无 name 时探 card 用 `FakeDefectSearch` | ok |
| 2 | 描述末尾追加 `[remote A2A agent @ http://127.0.0.1:9001]` | ok |
| 3 | 死 URL + 显式 name:仍注册,描述带 `unreachable at registration` | ok |
| 4 | 显式 name 覆盖 card name,但 description 仍走探活 | `my_custom_alias` |
| 5 | `register_remote_skills_from_yaml()` idempotent | 二次返 `[]` |
| 6 | 端到端 HTTP 调用 | 3 条 matches |

## 五、重要结果

### 5.1 功能层

1. 用户可以用自然语言**多轮**驱动整个 Phase 3-5 诊断流水线;follow-up
   问题不再触发重复执行(LLM 看 chat history 自己判断)。
2. `history_lookup` 让"上次诊断 / 历史趋势"在**任何**会话里都能问到。
3. 远程 A2A agent 在 LLM 的工具列表里与本地 Skill 同名同形,LLM 无需
   感知差异。
4. CLI 里两条命令(`/register_remote <url>` 与 `/load_dir <path>`)就能
   在不重启进程的前提下扩展能力。

### 5.2 工程层

| 指标 | 数值 |
|---|---|
| 新增源代码 | 2608 行 |
| 新增文件 | 23 |
| 修改的旧源代码 | 极少(`__init__.py` 与 `chat_cli.py` 增量) |
| Phase 3-5 测试套 | 全部继续绿(本阶段未触发回归) |
| 新增烟测检查点 | 21 个 全过 |
| 新增依赖 | `langchain-ollama`, `a2a-sdk` |

### 5.3 架构层

* **分层确定性**:外层 LLM 决调度,内层图保持完全确定性。两层契约
  不同(SkillCard vs AgentCard)是有意的——服务于不同目的。
* **三类注册入口统一到一个接口**:本地类 / 本地目录 / 远程 URL / 远程
  YAML / 任意程序化 Skill 全部经过 `register_skill`,从 LLM 看是一回事。
* **状态分离**:`messages`(对话)与 `diagnosis_records`(设备级)分开
  存——"对话历史"和"设备历史"是两件事。
* **批量是 fast path**:N 个连续注册触发**1 次**重编译,不是 N 次。
* **失败语义统一**:远程传输错与 schema 不匹配都不抛,返回结构化错误
  让 LLM 看见。

## 六、局限与下一步

### 6.1 当前局限

1. **重编译开销**:每次注册 / 启禁都重编 react agent。CLI 单用户场景
   无感,高频写入下需要 batch 化(已有 `register_skills` 批量接口,
   但目前没有"事务式上下文管理器")。
2. **远程 IO 通用化**:`instruction:str` 入 / `text + raw_json` 出 ——
   牺牲了远端的强类型契约。需要强 schema 的远程 agent 仍能挂上来,
   但 LLM 的 args_schema 不会反映其细节。
3. **远程鉴权 / 多租户未做**:`A2AClient` 不带 auth header / tenant
   切换;`a2a-sdk` 的 `ClientCallContext`、`security_schemes` 字段都
   预留了,只是 Skill 层没有透传。
4. **目录扫描非递归监听**:`/load_dir` 是一次性扫描,文件变化不会自动
   重新加载;改 Skill 类后仍需重新 `/load_dir`(且需手动 unregister 旧
   版本)。
5. **system prompt 写死**:工具增加后,prompt 里写死的 `调 X / 调 Y`
   规则不会自动更新——LLM 仍靠 description 选工具,只是若 prompt 没
   提到的新工具,LLM 略保守。

### 6.2 下一步候选

* **远程 agent 类型化 schema**:支持 YAML 里给一个 `schema_module`,
  里头声明 input/output Pydantic 模型,wrap 进 RemoteA2ASkill。
* **A2A 鉴权**:把 `a2a-sdk` 的 interceptor 串到 `A2AClient`,从 YAML
  读 token / api key。
* **持久注册表**:目前动态注册的 Skill 进程结束就忘;加一张 SQLite 表
  `registrations` 在启动时回放(类似 IDE 的插件持久启用状态)。
* **System prompt 动态化**:根据当前 Skill 列表生成 prompt 而不是写死,
  避免新 Skill 被 LLM 冷落。
* **Skill 调用埋点**:把每次 tool call 的 latency / success / error
  写到 `tool_calls` 表,做观测;复用 Phase 3 的 `comm_log` 思路。

## 七、Phase 9：tool / skill / agent 三层正名与提示词 Skill 层

### 7.1 动机

Phase 6-8 把一切 LLM 可调单元都包成 "Skill",最后又过一遍
`skill_to_tool()` 变成 LangChain tool——也就是说这个 "Skill" 干的本就是
**Tool**(function-calling 目标)的活。同时,业界(Claude Agent SDK /
CodeWhale)语境里 **Skill 指的是"可加载的提示词/知识"**(一个含 `SKILL.md`
的目录),是渐进披露的指令,而不是可调函数。两个含义撞名,且本项目缺失
真正的"提示词 Skill"那一层——领域知识(DGA 判读、检修 SOP)只能写死在
system prompt 里。

Phase 9 确立**三层清晰边界**,并立一条铁律:

> **LLM 直接能调的只有 Tool。Skill(知识)和 Agent(远程委派)都"经由
> Tool 触达"。**

### 7.2 三层定义(当前生效)

| 层 | 是什么 | 契约 | 与 LLM 的关系 | 文件 |
|---|---|---|---|---|
| **Tool** | LLM 唯一直调单元 | `ToolCard + run()` | 直接 tool call | [tool.py](../Python/Src/Supervisor/tool.py) |
| **Skill** | 可加载提示词/知识(SKILL.md) | `name + description + body` | 经内置 `load_skill` 注入上下文 | [skill.py](../Python/Src/Supervisor/skill.py) |
| **Agent** | 远程 A2A 委派 | 经 Tool 触达 | 不直调,藏在 `RemoteA2ATool` 后 | [remote/](../Python/Src/Supervisor/remote/) |

另外两个辅助概念:
- **Workflow**:Phase 3-5 的确定性 LangGraph,被包成**一个 Tool**
  (`transformer_diagnosis`)。坚决不让 LLM 动态改图——可复现是护城河。
- **Primitive**:Phase 1 `Tools/` 的纯算子(本轮未改名,避免牵连 inner platform)。

```
Supervisor (LLM 编排) ── LLM 只会 tool call
   ├─ load_skill(name)      → 注入领域知识     【Skill 层 = 提示词】
   ├─ transformer_diagnosis → 触发确定性 Workflow 【Tool ← Workflow】
   ├─ history_lookup        → 查历史            【Tool ← primitive】
   └─ defect_kb_search      → 远程委派           【Tool ← Agent(A2A)】
```

### 7.3 改名映射(Skill → Tool 全线)

| 旧(Phase 6-8) | 新(Phase 9) |
|---|---|
| `skill.py`：`Skill`/`SkillCard`/`skill_to_tool` | `tool.py`：`Tool`/`ToolCard`/`to_langchain_tool` |
| `skills/` 目录、`*Skill` 类 | `tools/`、`TransformerDiagnosisTool`/`HistoryLookupTool` |
| `RemoteA2ASkill` | `RemoteA2ATool` |
| `load_skills` / `SkillLoadError` / `discover_skills_from_path` | `load_tools` / `ToolLoadError` / `discover_tools_from_path` |
| `load_remote_skills` | `load_remote_tools` |
| 目录扫描约定 `SKILL=` / `SKILLS=[...]` | `TOOL=` / `TOOLS=[...]` |
| `Supervisor.register_skill*` / `skill_names` / `all_skill_names` / `disabled_skill_names` | `register_tool*` / `tool_names` / `all_tool_names` / `disabled_tool_names` |
| `Config/skills.yaml`（键 `skills:`） | `Config/tools.yaml`（键 `tools:`） |
| `Config/remote_skills.yaml`（键 `remote_skills:`） | `Config/remote_tools.yaml`（键 `remote_tools:`） |
| `examples/hot_skills/` | `examples/hot_tools/` |

`skill.py` 这个名字腾出来后,正好留给**新的提示词 Skill 层**。

### 7.4 新增：提示词 Skill 层

[skill.py](../Python/Src/Supervisor/skill.py) 实现:

```python
@dataclass(frozen=True)
class Skill:                 # 一个 SKILL.md 的解析结果
    name: str
    description: str
    body: str               # markdown 指令正文
    path: Path
    companion_files: List[Path]

class SkillRegistry:        # 扫描目录树发现 SKILL.md
    @classmethod
    def discover(cls, dirs) -> "SkillRegistry": ...
    def catalogue_text(self) -> str:    # 一行一个 name+description, 给系统提示
```

**Skill 目录布局**(对齐 CodeWhale / agentskills 约定,首个命中优先):

```
skills/<name>/SKILL.md            ← 项目级
.agents/skills/<name>/SKILL.md    ← 项目级
~/.healthagent/skills/  /  ~/.claude/skills/   ← 全局
```

`SKILL.md` = YAML frontmatter(`name`/`description`)+ markdown 正文。

**两步渐进披露**(节省上下文预算):

1. Supervisor 启动时把每个 Skill 的**一行 name+description** 注入 system
   prompt 的 `## 可用知识技能` 段(`catalogue_text()`),**不放正文**。
2. LLM 判断相关时调内置 Tool `load_skill(name)`(`LoadSkillTool`),返回
   该 Skill 的**完整正文**作为 tool 结果 → 进入下一轮上下文。

也就是说:**Skill 的"调用" = LLM 调 `load_skill` 这个 Tool 把知识正文当
tool 结果读进来**,走的就是普通 function-calling 通道,只不过返回的是指令
文本而非计算结果。

`Supervisor._rebuild_agent()` 里,只要 registry 有 skill 就把
`LoadSkillTool` 追加到工具列表;`_build_prompt()` 动态拼接 catalogue。

**两个示例领域 Skill**:
- [skills/dga-interpretation/SKILL.md](../skills/dga-interpretation/SKILL.md)
  —— DGA 三比值法 / Duval 三角的判读流程(IEC 60599)
- [skills/maintenance-report/SKILL.md](../skills/maintenance-report/SKILL.md)
  —— 检修建议报告的五段式结构与写作规范

### 7.5 CLI 命令(Phase 9 后)

```
tools:   /tools  /register <class_path>  /unregister <name>
         /enable <name>  /disable <name>  /load_dir <path>
remote:  /register_remote <url> [name]  /load_remote_yaml [path]
skills:  /skills  /load_skill <name>  /reload_skills
```

`/tools` 列可调工具(禁用项标 `[disabled]`);`/skills` 列知识技能;
`/load_skill <name>` 预览某 Skill 正文;`/reload_skills` 重扫目录。

### 7.6 Phase 9 烟测(4 套 / 27 检查点全过)

LLM 与 `create_react_agent` 在离线测里用 `unittest.mock.patch` 打桩;
远程两套依赖本机 demo server。

| 套件 | 覆盖 | 检查点 |
|---|---|---|
| [_skill_smoke.py](../Python/Src/Supervisor/_skill_smoke.py) | SKILL.md 发现 + `load_skill` + catalogue 注入 prompt | 6 |
| [_dynamic_smoke.py](../Python/Src/Supervisor/_dynamic_smoke.py) | Tool 动态增删启禁 + 批量单次重建 | 10 |
| [remote/_smoke.py](../Python/Src/Supervisor/remote/_smoke.py) | 远程 Tool 端到端 + 宽松探活 | 5 |
| [_remote_dynamic_smoke.py](../Python/Src/Supervisor/_remote_dynamic_smoke.py) | 远程动态注册 | 6 |

关键验证:`_skill_smoke` 确认 Supervisor 把 `## 可用知识技能` 写进 prompt
且 `load_skill` 已挂入工具列表;其余三套是 Phase 7/8 同等覆盖在新命名下
继续全绿。包 `import Python.Src.Supervisor` 干净,无残留旧标识符。

### 7.7 收益

- **命名与业界对齐**:Tool=可调、Skill=知识、Agent=委派,各归其位;
  消除"tool 一词三义"与"skill 名不副实"。
- **领域知识可维护**:DGA 判读 / 报告规范从 system prompt 抽到 `SKILL.md`,
  改判读逻辑不动代码,且按需加载不占首轮预算。
- **零行为回归**:Tool 调用链、动态注册、远程 A2A 全部行为不变,仅换名 +
  补一层。

## 八、复现实验

```bash
conda activate healthAgent
pip install -r requirements.txt   # 含 langchain-ollama + a2a-sdk

# 1) 多轮对话(自动加载 Config/tools.yaml + remote_tools.yaml + skills/ 下的 SKILL.md)
python Python/Src/Supervisor/chat_cli.py

# 2) 提示词 Skill 层(离线, 不依赖 Ollama / 网络)
python -m Python.Src.Supervisor._skill_smoke

# 3) 动态 Tool 注册(LLM 已 mock)
python -m Python.Src.Supervisor._dynamic_smoke

# 4) 远程 A2A 端到端联调
#    终端 A:
python -m a2a_demo_server.fake_search_server
#    终端 B:
python -m Python.Src.Supervisor.remote._smoke
#    远程动态注册(同样需先起 demo server):
python -m Python.Src.Supervisor._remote_dynamic_smoke
```

## 九、参考

* LangGraph `create_react_agent`:<https://langchain-ai.github.io/langgraph/reference/prebuilt/>
* A2A Protocol:<https://a2a-protocol.org/>
* Claude Agent SDK / Skill(SKILL.md)约定:<https://docs.claude.com/>
* Phase 2 报告:[docs/PHASE2_REPORT.md](PHASE2_REPORT.md)
* Phase 3 报告:[docs/PHASE3_REPORT.md](PHASE3_REPORT.md)
* 参考项目(SupervisorAgent.register_expert):`D:/code/AI/project/agent`
* Phase 9 三层划分参考(Rust 实现的 Claude Code 分支,tool/skill/agent 分得很干净):`D:/code/AI/project/CodeWhale`
