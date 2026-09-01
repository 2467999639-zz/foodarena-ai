# foodarena-ai

校园干饭辩论赛与美食擂台：基于敏捷方法的 AI 原生选餐决策应用。

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
