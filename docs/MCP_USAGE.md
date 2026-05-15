# HealthAgent MCP Server

把变压器健康管控的全部能力以 MCP 工具形式暴露给任意 MCP 客户端
（Claude Desktop / Claude Code / 其它）。所有数据保留在本地，LLM 客户端
通过 stdio 传输调用工具。

## 一、前置条件

- Python 3.12+ 在 conda 环境 `healthAgent` 中（含 torch、fastmcp 等依赖）
- Ollama 在 `http://localhost:11434` 监听，模型 `gpt-oss:120b-cloud` 已 pull
  （或修改 [Config/GlobalConfig.yaml](../Config/GlobalConfig.yaml) 改成你自己的本地模型）
- IoTDB 可选；不开也能跑（自动回落 mock 模式）

## 二、Claude Desktop 配置

编辑 `%APPDATA%\Claude\claude_desktop_config.json`（macOS：
`~/Library/Application Support/Claude/claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "healthagent": {
      "command": "D:\\Users\\mingj\\anaconda3\\envs\\healthAgent\\python.exe",
      "args": ["D:\\code\\AI\\project\\HealthAgent\\Python\\MCPMain.py"]
    }
  }
}
```

把两个路径改成你自己机器上的实际位置。重启 Claude Desktop，左下角应该出现
"healthagent" 服务，包含 12 个工具、2 个资源模板、3 个 prompts。

## 三、本地手动启动（调试用）

```bash
conda run -n healthAgent python Python/MCPMain.py
```

stdio 模式下进程会等待 MCP 客户端连接，无可见输出是正常的。

## 四、暴露的能力

### Tools（12 个）

#### 数据获取
| 工具 | 用途 |
|---|---|
| `get_sensor_trend` | 取单个测点（如 H2、oil_bdv）的历史趋势 |
| `get_dga_trends` | 取 7 个 DGA 气体的完整趋势 |
| `get_scoring_data` | 取健康评估全套测点（10 个）|

#### 单源识别
| 工具 | 模型 | 输入 |
|---|---|---|
| `classify_inspection_log` | BERT | 巡检日志文本 |
| `classify_oil_chromatogram` | CNN | 油色谱 7 维数值 |
| `detect_image_defects` | YOLO | 图像本地路径 |

#### 综合分析
| 工具 | 用途 |
|---|---|
| `analyze_dga` | DGA 趋势综合风险评分（iTransformer + CATCH 风格）|
| `get_dga_expert_advice` | 一句话维护建议（确定性模板）|
| `fuse_three_sources` | D-S Murphy 三源证据融合 |
| `compute_remaining_useful_life` | 物理 RUL 计算（含缺陷叠加）|

#### 一键流水线
| 工具 | 用途 |
|---|---|
| `assess_full_health` | 完整健康评估（等价于 /api/assess/health）|
| `assess_defect_only` | 仅缺陷识别（等价于 /api/assess/defect）|

### Resources（2 个）

| URI 模板 | 内容 |
|---|---|
| `iotdb://{equipment_id}/scoring` | 全部 10 个评分测点 7 天趋势的 JSON 快照 |
| `iotdb://{equipment_id}/dga` | 7 个 DGA 气体 7 天趋势的 JSON 快照 |

### Prompts（3 个）

| Prompt | 适用场景 |
|---|---|
| `diagnose_transformer(equipment_id)` | 完整故障诊断决策树，让 LLM 按顺序串起所有工具 |
| `quick_health_screen(equipment_id)` | 30 秒快速健康筛查，一次工具调用 |
| `explain_dga_anomaly(equipment_id)` | 聚焦 DGA 气体异常的成因分析 |

## 五、典型对话示例

在 Claude Desktop 里直接打：

> "用 healthagent 帮我快速筛查 tr01 的健康状态。"

Claude 会自动调用 `quick_health_screen` prompt，里面要求它调用
`assess_full_health(equipment_id="tr01")`，最后给出健康指数 / 剩余寿命 /
主要威胁 / 维护建议四行汇报。

更细粒度：

> "看一下 tr01 最近 7 天的 H2 趋势，并解释是不是有放电风险。"

Claude 会先调 `get_sensor_trend`，然后调 `get_dga_trends` + `analyze_dga`
做对比分析。

## 六、和 FastAPI 后端的关系

MCP server 与 [FastAPI 后端](../Python/Main.py) **共用同一套 [Tools/](../Python/Src/Tools/)
工具层**——前端继续通过 `/api/assess/*` 调用 [AssessmentService](../Python/Src/Services/AssessmentService.py)，
LLM 客户端通过 MCP 调用同样的工具。两条路径不会互相影响。

## 七、运行测试

```bash
conda run -n healthAgent python -m pytest tests/integration/test_mcp_server.py -v
```

8 个测试覆盖工具/资源/prompt 注册和端到端调用。
