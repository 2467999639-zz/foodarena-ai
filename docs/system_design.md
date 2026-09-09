# FoodArena AI — 系统设计规约（三大模型 · 六图体系）

> 校园干饭辩论赛与美食擂台：基于敏捷方法的 AI 原生选餐决策应用。
> 本文件按《工程实践指导书》的「系统级三大模型 6 大架构图」要求绘制并维护
> 系统顶层设计。图用 Mermaid 编写，可直接在 GitHub 渲染。

- 图 1 系统顶层用例图（功能模型）
- 图 2 系统数据流图 DFD（功能模型）
- 图 3 系统领域类图（数据模型）
- 图 4 数据库实体关系图 ER（数据模型）
- 图 5 端到端核心时序图（动态模型）
- 图 6 会话生命周期状态机图（动态模型）

---

## 图 1 · 系统顶层用例图

```mermaid
flowchart LR
    subgraph System[FoodArena 系统边界]
        UC1[创建选餐会话<br/>US01]
        UC2[观看三轮双 Agent 辩论<br/>US02]
        UC3[获取结构化战报<br/>US03]
        UC4[重连恢复会话状态]
    end

    Actor(校园用户) --> UC1
    Actor --> UC2
    Actor --> UC3
    Actor --> UC4

    UC2 -.SSE 事件流.-> LLM(SiliconFlow<br/>DeepSeek 模型)
    UC3 -.裁决请求.-> LLM
    UC1 -.持久化.-> DB[(SQLite)]
    UC2 -.消息持久化.-> DB
```

---

## 图 2 · 系统数据流图（DFD）

```mermaid
flowchart LR
    U(用户) -->|口味/预算/天气/人数| FORM[偏好表单]
    FORM -->|POST /sessions| API[FastAPI 会话接口]
    API --> SVC[DebateService]

    SVC -->|校验| MENU[(合成菜品菜单)]
    SVC -->|辩论上下文| CHEF_A[川辣派 Agent]
    SVC -->|辩论上下文| CHEF_B[粤式养生派 Agent]
    SVC -->|6 条消息| JUDGE[裁决 Agent]
    SVC -->|persist| DB[(sessions<br/>preferences<br/>messages<br/>recommendations)]

    LLMAPI[SiliconFlow API] -->|回复| CHEF_A
    LLMAPI -->|回复| CHEF_B
    LLMAPI -->|回复| JUDGE

    DB -->|report| SVC
    SVC -->|SSE/JSON| UI[React 前端]
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
        +run_debate(session_id) (view, events)
        +get_session(session_id) SessionView
    }

    class ChefProvider <<interface>> {
        +argument(ctx) AgentMessage
        +report(...) DebateReport
    }

    class SiliconFlowChefProvider
    class MockChefProvider
    class MockReasoner

    DebateSession "1" --> "0..*" AgentMessage
    DebateSession "1" --> "0..1" DebateReport
    DebateService ..> ChefProvider
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

约束：`preferences.session_id` 唯一（每个会话一份偏好）；`recommendations.session_id`
唯一（最终战报仅一份）；`messages` 按 `id` 排序即发言顺序。

---

## 图 5 · 端到端核心时序图

```mermaid
sequenceDiagram
    participant UI as React 前端
    participant API as FastAPI /api/v1
    participant SVC as DebateService
    participant LLM as SiliconFlow DeepSeek
    participant DB as SQLite

    UI->>API: POST /sessions {偏好}
    API->>SVC: create_session(prefs)
    SVC->>DB: INSERT session(PENDING) + preferences
    API-->>UI: 201 {session_id, PENDING}

    UI->>API: GET /sessions/{id}/events (SSE)
    API->>SVC: run_debate(session_id)
    SVC->>DB: status -> RUNNING

    loop 3 轮 × 2 Agent
        SVC->>SVC: 依序选川辣派 / 粤式养生派
        SVC->>LLM: 轮次 prompt（人设 + 隔离的用户偏好）
        LLM-->>SVC: 结构化 JSON (argument, evidence)
        SVC->>DB: INSERT message (round, agent, ...)
        SVC-->>UI: SSE event:message
    end

    SVC->>DB: status -> VALIDATING
    SVC->>LLM: 裁决 prompt（6 条消息 + 用户偏好）
    LLM-->>SVC: 结构化 JSON (dish, reason, ...)
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
    RUNNING --> VALIDATING : 6 条消息全部成功
    VALIDATING --> SUCCESS : 裁决成功并持久化战报
    RUNNING --> FAILED : Agent/模型/Schema 失败
    VALIDATING --> FAILED : 裁决失败
    FAILED --> RUNNING : 用户重试（重新辩论）
    SUCCESS --> [*]
    FAILED --> [*]
```

补充说明

- 只有 `PENDING` 允许启动辩论；重复启动/已完成会话再次调用返回当前状态，
  绝不产生第二条执行链（图 5 中 `run_debate` 的幂等语义）。
- `FAILED` 会话永不返回伪造的成功战报：`GET /report` 仅对 `SUCCESS` 开放，
  否则返回 `409`。
