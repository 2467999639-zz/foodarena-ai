# foodarena-ai

校园干饭辩论赛与美食擂台：基于敏捷方法的 AI 原生选餐决策应用。

## 三轮双 Agent 控制器

`foodarena_ai.debate` 提供与模型供应商无关的三轮辩论骨架。控制器只接受
`RUNNING` 且尚无消息的会话，按固定顺序让 `sichuan_spicy`（川辣派）与
`cantonese_wellness`（粤式养生派）各发言一次，共运行 3 轮、生成 6 条
`AgentMessage`。每条消息包含 `round`、`agent`、`argument` 和 `evidence`；
全部轮次成功后，会话一次性进入 `VALIDATING`。任一 Agent 失败时不会写入
部分消息，也不会改变会话状态。

Agent 只需实现 `DebateAgent` 协议，因此测试和本地演示可使用
`MockDebateAgent`，不访问外部模型服务。最小调用方式如下：

```python
from foodarena_ai.debate import (
    AgentArgument,
    AgentName,
    DebateController,
    DebateSession,
    MockDebateAgent,
    SessionStatus,
)

turns = [
    AgentArgument(argument=f"第 {round_number} 轮观点", evidence="Mock 证据")
    for round_number in range(1, 4)
]
session = DebateSession(status=SessionStatus.RUNNING)
controller = DebateController(
    [
        MockDebateAgent(AgentName.SICHUAN_SPICY, turns),
        MockDebateAgent(AgentName.CANTONESE_WELLNESS, turns),
    ]
)
controller.run(session)
```

## SiliconFlow 连通 Demo

项目包含一个最小的 SiliconFlow OpenAI 兼容客户端，用于验证
DeepSeek-V4-Flash 的请求连通性。客户端固定使用 30 秒超时，对 HTTP 429、
5xx、请求超时和临时网络错误最多重试 3 次，退避时间依次为 1、2、4 秒。
HTTP 200 响应会先通过最小 Pydantic Schema 校验，再返回给调用方。

### 安装

需要 Python 3.11 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### 配置与运行

复制本地配置模板并填写 API Key；`.env` 已被 Git 忽略，不会进入版本库：

```powershell
Copy-Item .env.example .env
# 编辑 .env 中的 SILICONFLOW_API_KEY

siliconflow-demo
# 或自定义提示词
siliconflow-demo "只回复：连接成功"
```

成功时命令输出经过校验的 JSON 响应并返回退出码 `0`；配置缺失、重试耗尽、
非临时 HTTP 错误或响应结构无效时返回退出码 `1`。日志只记录错误类型、HTTP
状态和退避时间，不记录 API Key、请求头或完整响应体。
已设置的进程环境变量优先于 `.env` 中的同名配置。

### 自动化验证

测试全部使用 Mock Transport，不需要真实 API Key，也不会发起外部请求：

```powershell
pytest
ruff check .
```
