# FoodArena AI — 系统设计规约（三大模型 · 六图体系）

> 校园干饭辩论赛与美食擂台：基于敏捷方法的 AI 原生选餐决策应用。
> 基于 `main` 提交 `496eb9d82c`（2026-09-11）校核，图用 Mermaid 编写，可直接在 GitHub 渲染。
> 本文以代码现状为准：默认最多三轮六条消息；若配置提前结束，实际可为一至三轮、两至六条消息。

- 图 1 系统顶层用例图（功能模型）
- 图 2 系统数据流图 DFD（功能模型）
- 图 3 系统领域类图（数据模型）
- 图 4 数据库实体关系图 ER（数据模型）
- 图 5 端到端核心时序图（动态模型）
- 图 6 会话生命周期状态机图（动态模型）

系统边界：React/Vite 单页应用经 REST/SSE 调用 FastAPI；`DebateService` 组织 Mock 或 SiliconFlow 提供方，SQLAlchemy 将四类业务记录持久化到 SQLite。菜单是运行时校验的 JSON 或内置样例，并非数据库表。外部模型输出须经 Pydantic 校验后落库。`FAILED` 当前是终态，用户须创建新会话才能再试。

---

## 图 1 · 系统顶层用例图

```mermaid
flowchart LR
    subgraph System[FoodArena 系统边界]
        UC1[创建选餐会话<br/>US01]
        UC2[观看双 Agent 辩论<br/>US02]
        UC3[获取结构化战报<br/>US03]
        UC4[重连恢复会话状态]
    end

    Actor(校园用户) --> UC1
    Actor --> UC2
    Actor --> UC3
    Actor --> UC4

    UC2 -.real 模式模型调用.-> LLM(SiliconFlow<br/>DeepSeek 模型)
    UC3 -.real 模式裁决请求.-> LLM
    UC1 -.持久化.-> DB[(SQLite)]
    UC2 -.消息持久化.-> DB
```

---

## 图 2 · 系统数据流图（DFD）

```mermaid
flowchart LR
    U(用户) -->|口味 预算 天气 人数 人设 规则| P1[1 创建与校验会话]
    P1 -->|会话与偏好| D1[(SQLite 会话与偏好)]
    D1 -->|会话上下文| P2[2 轮次编排]
    MENU[(样例或 JSON 菜单)] -->|候选菜品| P2
    P2 -->|real 模式提示词| LLM[SiliconFlow API]
    LLM -->|原始回复| P3[3 Pydantic 校验]
    P2 -->|Mock 论据| P3
    P3 -->|有效消息| D2[(SQLite 消息)]
    D2 -->|辩论记录| P4[4 裁决与评分]
    D1 -->|偏好| P4
    MENU -->|菜单| P4
    P4 -->|real 模式裁决请求| LLM
    P4 -->|有效战报| D3[(SQLite 推荐)]
    P2 -->|状态和消息 SSE| U
    D3 -->|战报 JSON 或 SSE| U
```

---

## 图 3 · 系统领域类图

```mermaid
classDiagram
    class PreferenceInput {
        +str taste
        +int budget_yuan
        +Weather weather
        +int companions
    }

    class PersonaInput {
        +AgentName agent
        +str label
        +PersonaStyle style
        +str flavour
    }

    class DebateSettings {
        +int min_rounds
        +int max_rounds
        +bool early_stop
    }

    class DebateSession {
        +UUID session_id
        +SessionStatus status
        +list AgentMessage messages
        +DebateReport report
    }

    class AgentMessage {
        +int round
        +AgentName agent
        +str argument
        +str evidence
    }

    class DebateReport {
        +str dish
        +str reason
        +float confidence
        +dict score_breakdown
    }

    class DebateService {
        +create_session(prefs) SessionView
        +stream_debate(session_id) events
        +replay_events(session_id) events
        +get_session(session_id) SessionView
    }

    class ChefProvider <<interface>> {
        +argument(ctx) AgentMessage
        +report(...) DebateReport
    }

    class SiliconFlowChefProvider
    class MockChefProvider
    class MockReasoner

    DebateSession "1" --> "0..6" AgentMessage
    DebateSession "1" --> "0..1" DebateReport
    DebateService ..> ChefProvider
    DebateService ..> PersonaInput
    DebateService ..> DebateSettings
    DebateService ..> MenuItem
    ChefProvider <|-- SiliconFlowChefProvider
    ChefProvider <|-- MockChefProvider
    MockChefProvider ..> MockReasoner
    MockReasoner ..> MenuItem
```

---

## 图 4 · 数据库实体关系图（ER）

```mermaid
erDiagram
    SESSIONS ||--o| PREFERENCES : has
    SESSIONS ||--o{ MESSAGES : contains
    SESSIONS ||--o| RECOMMENDATIONS : produces

    SESSIONS {
        int id PK
        string session_id UK
        string status "PENDING|RUNNING|VALIDATING|SUCCESS|FAILED"
        string provider "mock|real"
        text personas_json
        text settings_json
        datetime created_at
        datetime updated_at
        text failure_reason
    }

    PREFERENCES {
        int id PK
        int session_id FK
        string taste
        int budget_yuan
        string weather
        int companions
    }

    MESSAGES {
        int id PK
        int session_id FK
        int round
        string agent
        text argument
        text evidence
        datetime created_at
    }

    RECOMMENDATIONS {
        int id PK
        int session_id FK
        string dish
        string cuisine
        text reason
        float confidence
        json score_breakdown_json
        datetime created_at
    }
```

约束：`preferences.session_id` 唯一（每个会话一份偏好）；`recommendations.session_id` 唯一（最终战报仅一份）；`messages` 按 `id` 排序即发言顺序。`personas_json` 和 `settings_json` 记录可选自定义配置；`MenuCatalog` 不是数据库实体。

---

## 图 5 · 端到端核心时序图

```mermaid
sequenceDiagram
    participant UI as React 前端
    participant API as FastAPI /api/v1
    participant SVC as DebateService
    participant P as Mock 或 SiliconFlow
    participant DB as SQLite

    UI->>API: POST /sessions {偏好}
    API->>SVC: create_session(prefs)
    SVC->>DB: INSERT session(PENDING) + preferences
    API-->>UI: 201 {session_id, PENDING}

    UI->>API: GET /sessions/{id}/events (SSE)
    API->>SVC: stream_debate(session_id)
    SVC->>DB: 条件更新 PENDING -> RUNNING

    loop 1 至 max_rounds 轮，每轮 2 Agent
        SVC->>SVC: 依序选川辣派 / 粤式养生派
        SVC->>P: 轮次上下文（人设 + 偏好 + 上轮论据）
        P-->>SVC: 论据 (argument, evidence)
        SVC->>SVC: Pydantic 校验与安全处理
        SVC->>DB: INSERT message (round, agent, ...)
        SVC-->>UI: SSE event:message
    end

    opt 达到最少轮数且双方同提一道菜单菜品
        SVC-->>UI: SSE event:info 提前结束
    end

    SVC->>DB: status -> VALIDATING
    SVC->>P: 裁决请求（已持久化消息 + 用户偏好）
    P-->>SVC: 结构化战报 (dish, reason, ...)
    SVC->>DB: INSERT recommendation + status -> SUCCESS
    SVC-->>UI: SSE event:report + event:status(SUCCESS)
    UI->>API: GET /sessions/{id}/report
    API-->>UI: 200 战报
```

---

## 图 6 · 会话生命周期状态机图

```mermaid
stateDiagram-v2
    [*] --> PENDING : POST /sessions
    PENDING --> RUNNING : POST /debate 或 SSE 连接
    RUNNING --> VALIDATING : 达到 max_rounds 或满足提前结束条件
    VALIDATING --> SUCCESS : 裁决成功并持久化战报
    RUNNING --> FAILED : Agent/模型/Schema 失败
    VALIDATING --> FAILED : 裁决失败
    SUCCESS --> [*]
    FAILED --> [*]
```

补充说明

- 只有 `PENDING` 允许启动辩论；重复启动/已完成会话再次调用返回当前状态，
  按 PENDING 条件认领设计，不应产生第二条执行链（图 5 中 `stream_debate` 的幂等语义）。
- `FAILED` 会话永不返回伪造的成功战报：`GET /report` 仅对 `SUCCESS` 开放，
  否则返回 `409`。
- 当前前端失败页“重试”只是刷新页面；后端会重放 `FAILED` 状态，不能将同一会话重新置为 `RUNNING`。需新建会话，或另行设计重试接口。该文案与行为不一致，列为后续改进。
- API 另提供 `GET /api/v1/menu`；菜单由 `menu_store.py` 装载并经 `MenuCatalog` 校验。`real` 模式依赖外部网络及密钥，默认 `mock` 模式可离线演示。

## 实现可追溯性

| 设计点 | 代码与验收依据 |
| --- | --- |
| 输入、配置、输出契约 | `src/foodarena_ai/domain.py`；`tests/test_domain_contracts.py` |
| 状态认领、轮次、提前结束、事件重放 | `src/foodarena_ai/service.py`；`tests/test_service.py` |
| 四表与唯一约束 | `src/foodarena_ai/db.py` |
| REST/SSE 与错误状态 | `src/foodarena_ai/main.py`；`tests/test_api.py` |
| US01–US03 基础 BDD | `tests/features/` |

基线：[GitHub 仓库 `496eb9d82c`](https://github.com/wujiade-2005/foodarena-ai/tree/496eb9d82c)。图为实现抽象；类图中的 `DebateSession` 表示领域会话概念，在代码中由 `SessionView`/`SessionRow` 分别承担对外契约和持久化职责。

## 推导边界

六图是当前源码的静态抽象，不是原始设计会议记录，也不证明部署、性能或运行成功。每项结论应返回上述固定基线源码核对；测试文件只表明存在断言，测试是否通过须查看独立执行结果。用户故事、Sprint 报告和本文均为新增分析，不能互作事实证据。
