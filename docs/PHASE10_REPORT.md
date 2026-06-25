# Phase 10 实验报告：自控 Agent 运行时(循环 / 上下文 / 记忆)

| 项目 | 内容 |
|---|---|
| 报告时间 | 2026-06-27 |
| 阶段 | Phase 10（弃用 LangGraph,自写 Agent 循环 + 上下文管理 + 跨会话记忆） |
| 分支 | `refactor/mcp-multi-agent` |
| 提交 | （待提交） |
| 参考实现 | `D:/code/AI/project/claude-code-from-scratch`（仿写 Claude Code 的开源教学项目） |
| 新增依赖 | `openai`（OpenAI 兼容客户端，已装 2.28.0） |

## 一、背景与目标

Phase 6-9 把外层 Supervisor 做成了基于 LangGraph `create_react_agent` 的
对话层。实测暴露两个硬伤:**工具调用不稳**(本地/小模型在黑盒循环里
tool-call 易出错)与**上下文管理薄弱**(每轮把全部历史塞给模型、巨大工具
结果直接进上下文)。

Phase 10 对标 `claude-code-from-scratch`(它逐章仿写了 Claude Code 的循环、
工具、上下文压缩、记忆等机制),**弃用 LangGraph 黑盒,自己拥有 Agent 循环**,
分三步落地:

- **P1 自控循环**:掌控工具调用,加结果防护、错误即数据、重试、迭代上限;
- **P2 上下文管理**:单轮内压缩 + 跨轮自动摘要;
- **P3 跨会话记忆**:文件式 4 类记忆 + 语义召回。

一个关键支点:**Ollama 与 DeepSeek 都提供 OpenAI 兼容端点**,所以同一套
循环用 `openai.AsyncOpenAI` 即可对接两者,切换只改配置。

## 二、总体架构

```
                         用户(CLI / 前端 HTTP)
                                  │
                    ┌─────────────▼──────────────┐
                    │   Supervisor (core.py)      │
                    │   ── 自控 async 循环编排 ──   │
                    │   chat_verbose → _achat     │
                    └─────────────┬──────────────┘
            ┌─────────────────────┼─────────────────────────┐
            ▼                     ▼                          ▼
   ┌────────────────┐   ┌──────────────────┐    ┌────────────────────┐
   │ 上下文 (P2)     │   │ 记忆 (P3)         │    │ AgentLoop (P1)      │
   │ _maybe_compact  │   │ 语义召回 + 注入    │    │ agent_loop.py       │
   │ _and_load       │   │ memory.py         │    │ openai.AsyncOpenAI  │
   │ (auto-compact)  │   │ SaveMemoryTool    │    │ → DeepSeek / Ollama │
   └───────┬────────┘   └─────────┬────────┘    └──────────┬─────────┘
           │ SQLite               │ var/memory/            │ tool-calling 循环
   ┌───────▼────────┐    ┌────────▼────────┐    ┌──────────▼─────────┐
   │ session.py      │    │ MEMORY.md 索引   │    │ Tool 注册表 + dispatch│
   │ messages /      │    │ {type}_{slug}.md │    │ ├ transformer_diag  │
   │ session_summaries│   └─────────────────┘    │ ├ history_lookup    │
   └─────────────────┘                           │ ├ remote A2A        │
                                                 │ ├ load_skill        │
                                                 │ └ save_memory       │
                                                 └─────────────────────┘
```

三层概念不变(Phase 9 确立,见 [PHASE6_8_REPORT.md](PHASE6_8_REPORT.md) 第七节):
**Tool**=LLM 唯一直调单元;**Skill**=可加载提示词(SKILL.md);**Agent**=经
Tool 触达的远程/委派。Phase 10 换的是「循环内核」与「上下文/记忆」,三层
契约与动态注册、热加载全部保留。

## 三、P1 — 自控 Agent 循环

文件 [agent_loop.py](../Python/Src/Supervisor/agent_loop.py)(369 行)。

### 3.1 循环主体

`AgentLoop.run()` 是一个我们完全掌控的 while 循环:

```
messages = [system] + history + [user]
for _ in range(MAX_TOOL_ITERATIONS):     # 上限 25, 防弱模型死循环
    压缩(messages)                        # P2 单轮内压缩
    resp = client.chat.completions.create(model, messages, tools=schemas)
    记 usage
    messages.append(assistant)
    if 无 tool_calls: answer = 文本; break
    for tc in tool_calls:
        raw = await dispatch(name, args)  # 派发到 Tool.run()
        res = persist_large_result(truncate_result(raw))
        messages.append({role: tool, content: res})
```

对比旧的 `create_react_agent`:循环可见、可插桩,这是 P2/P3 一切能力的接缝。

### 3.2 OpenAI 兼容 = 一套码接两端

`openai.AsyncOpenAI(base_url=..., api_key=...)`。`base_url` 指向
`http://localhost:11434/v1`(Ollama)或 `https://api.deepseek.com/v1`
(DeepSeek)。`Tool` 的 `ToolCard.input_model.model_json_schema()` 直接转成
OpenAI `tools=[...]` 的函数参数,无需中间层。

### 3.3 工具结果防护(借鉴参考 Level 0 / 0.5)

- `truncate_result`:超 50K 字符 → 保留头尾(头部有结构,尾部有结论/报错)。
- `persist_large_result`:超 30KB → **完整写盘**(`var/tool-results/`),上下文里
  只留预览(前 200 行)+ 文件路径,**可恢复、不丢信息**。
  解决 `transformer_diagnosis` 大报告 / 远程 JSON 撑爆上下文。

### 3.4 错误即数据 + 重试 + 中断保护

- 工具异常 → `Tool error (name): ...` 字符串回模型(在 `core._achat` 的
  `dispatch` 里 try/except),循环继续,模型可自纠;**绝不抛到上层**。
- `_with_retry`:429/5xx/超时/连接错指数退避(默认 3 次)。
- `MAX_TOOL_ITERATIONS=25`:弱模型反复调工具不收敛时兜底。
- 慢的同步工具(诊断 30–60s)用 `asyncio.to_thread` 包,不阻塞事件循环。

## 四、P2 — 上下文管理

关键判断:我们的**跨轮历史只存 user/assistant 最终文本**(无 tool 消息),
所以跨轮天然省;膨胀主要在**单轮内**(多次工具调用 + 大结果累积)。两层分治:

### 4.1 单轮内压缩(`agent_loop.py`,每次 API 调用前)

按上下文利用率 `last_input_tokens / effective_window` 触发:

| 层 | 触发 | 动作 |
|---|---|---|
| budget | 利用率 ≥ 0.5(>0.7 更狠) | tool 结果压到 30K / 15K(头尾保留) |
| snip | 利用率 ≥ 0.6 | 只留最近 3 条 tool 结果,更早的换成「[旧工具结果已省略]」 |

`effective_window` = 模型上下文窗口 − 8K 余量;窗口按模型名推断
(`deepseek→128K`,本地小模型→32K),可用 `LLM.Agent.EffectiveWindowOverride`
强制覆盖。

### 4.2 跨轮自动摘要(`core._maybe_compact_and_load`)

每轮加载历史前估算 token(char/4)。超 `effective_window × 0.85` 时:
保留最近 6 条消息,**把更早的对话摘要成一段**,持久化到新表
`session_summaries`(记 `covered_until` = 已覆盖的 message id),下次只读
「摘要 + 该 id 之后的消息」,**不重复摘要**。

摘要 prompt 专门要求保留:**设备 ID、HI/RUL/风险数值、故障判定、用户决定**。
因我们的历史是纯 user/assistant 文本,任意切片都安全(不会切断
tool_use↔tool_result 配对)。

## 五、P3 — 跨会话记忆

文件 [memory.py](../Python/Src/Supervisor/memory.py)(354 行)。

### 5.1 文件式 4 类记忆

存 `var/memory/{type}_{slug}.md`(YAML frontmatter + 正文)+ 自动维护
`MEMORY.md` 索引(注入 system prompt)。四类:

| 类型 | 记什么 |
|---|---|
| user | 用户身份 / 偏好 / 背景 |
| feedback | 对行为的纠正或肯定(正文写明 Why + 如何应用) |
| project | 进行中目标 / 决策 / 截止日期(相对日期转绝对) |
| reference | 外部系统定位(看板 / 工单 / URL) |

`_slugify` **保留 Unicode**,否则中文记忆名会全塌成同名文件互相覆盖。

### 5.2 保存:内置 `SaveMemoryTool`

参考项目用 `write_file` 存记忆;我们不是编码 agent,故做成一个**内置 Tool**
`save_memory(name, description, type, content)`,LLM 像调别的工具一样保存。
system prompt 教它何时存、4 类、什么**不该**存(能从代码/诊断数据推导的不存)。

### 5.3 召回:语义 sideQuery + 注入

每轮(`core._recall_memories`):把记忆清单(文件名+描述)发给 DeepSeek
做 `AgentLoop.side_query`,让模型选相关记忆(语义匹配,非关键词),命中的
以 `<system-reminder>` 注入。门控:单词查询跳过、会话 60KB 预算、per-session
去重。>1 天的记忆带 **freshness 警告**(时间切片,需核实)。

入口:CLI `/memory`、HTTP `GET /api/agent/memory`。

## 六、一次完整 chat 的链路

```
chat_verbose(sid, "给 tr01 做体检并记住它 9 月要检修")
  └─ asyncio.run(_achat)
       1. _maybe_compact_and_load(sid)      # 历史(必要时摘要)
       2. _recall_memories(sid, input)      # sideQuery 选相关记忆 → 注入
       3. AgentLoop.run(system+memory段, history, input, tools, dispatch)
            循环:
              compress(messages)            # budget/snip
              create() → tool_call: transformer_diagnosis
              dispatch → Tool.run() (to_thread) → 大结果存盘+预览
              create() → tool_call: save_memory(project, ...)
              create() → 最终文本
       4. save_message(user) + save_message(assistant)   # SQLite
  └─ {answer, tool_calls}
```

## 七、配置与切换

[Config/GlobalConfig.yaml](../Config/GlobalConfig.yaml) 的 `LLM.Agent` 段:

```yaml
Agent:
  BaseURL: "https://api.deepseek.com/v1"
  APIKey:  "<deepseek key>"      # 非 YOUR_ 占位才生效, 否则回退 Local(Ollama)
  ModelName: "deepseek-v4-pro"
  MaxTokens: 4096
  EffectiveWindowOverride: 0     # >0 强制上下文窗口
```

`APIKey` 是占位符或留空 → 自动回退到 `LLM.Local`(Ollama `/v1`)。

## 八、测试

5 套离线烟测(LLM 用 scripted fake client / patched openai,不依赖网络):

| 套件 | 覆盖 | 检查点 |
|---|---|---|
| [_loop_smoke.py](../Python/Src/Supervisor/_loop_smoke.py) | 结果防护、schema 生成、工具往返、错误即数据、Supervisor 端到端 | 6 |
| [_context_smoke.py](../Python/Src/Supervisor/_context_smoke.py) | 单轮 budget / snip、跨轮摘要触发+持久化+幂等 | 4 |
| [_memory_smoke.py](../Python/Src/Supervisor/_memory_smoke.py) | 保存+索引、语义召回、SaveMemoryTool、freshness | 6 |
| [_skill_smoke.py](../Python/Src/Supervisor/_skill_smoke.py) | SKILL.md 发现 + load_skill + 注入 | 6 |
| [_dynamic_smoke.py](../Python/Src/Supervisor/_dynamic_smoke.py) | Tool 动态增删启禁 + 目录热加载 | 10 |

P1 的真实 DeepSeek 端到端已由用户实测通过。FastAPI 应用 23 路由正常导入。

## 九、与参考项目对照

| 机制 | claude-code-from-scratch | 我们的适配 |
|---|---|---|
| 后端 | Anthropic + OpenAI 双后端 | 只用 OpenAI 兼容(接 Ollama / DeepSeek) |
| 循环 | 自写 while + 流式 + 早启动并发 | 自写 while(P1 非流式,够用) |
| 工具 | 编码工具(read/edit/shell) | 领域工具(诊断/历史/远程/技能/记忆) |
| 结果防护 | truncate 50K + persist 30KB | 一致 |
| 上下文 | budget/snip/microcompact/auto-compact | budget/snip(单轮)+ auto-compact(跨轮,持久化摘要) |
| 记忆保存 | write_file 工具 | 内置 SaveMemoryTool |
| 记忆召回 | sideQuery + 异步预取 | sideQuery(P3 串行,预取留作优化) |
| 子 Agent | fork-return + 7 角色 | 暂未做(P4) |

## 十、局限与下一步

1. **记忆召回是串行的**:每轮多一次 sideQuery 往返(参考用异步预取与首个
   模型调用并行)。门控已减少无谓调用,后续可上预取。
2. **未做流式输出**:最终文本一次性返回(诊断耗时在工具内,LLM 流式收益
   有限)。需要"正在调用 X"实时进度时再加 SSE。
3. **microcompact 未实装**:对我们跨轮无 tool 消息的历史无用武之地,用
   auto-compact 替代。
4. **P4(可选)**:子 Agent(fork-return,`run_once` 模式)做多设备并行
   分析 / 历史探索;危险域操作的权限确认钩子。

## 十一、复现

```bash
conda activate healthAgent
pip install -r requirements.txt        # 含 openai

# 配 LLM.Agent 的 DeepSeek key(或留占位走 Ollama)

# 离线烟测(不依赖网络)
python -m Python.Src.Supervisor._loop_smoke
python -m Python.Src.Supervisor._context_smoke
python -m Python.Src.Supervisor._memory_smoke
python -m Python.Src.Supervisor._skill_smoke
python -m Python.Src.Supervisor._dynamic_smoke

# 真实端到端
python Python/Src/Supervisor/chat_cli.py     # CLI
python Python/Main.py                          # 后端 + 前端"智能体平台"页
```

## 十二、参考

- 仿写 Claude Code 的教学项目:`D:/code/AI/project/claude-code-from-scratch`
- DeepSeek OpenAI 兼容 API:<https://api.deepseek.com/v1>
- Phase 6-9 报告(三层正名 + 前端):[docs/PHASE6_8_REPORT.md](PHASE6_8_REPORT.md)
- Phase 3 报告(确定性诊断图):[docs/PHASE3_REPORT.md](PHASE3_REPORT.md)
