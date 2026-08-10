# iCampus 前端 API 对接文档

## 鉴权约定

登录和注册成功后保存响应中的 `token`。除登录、注册、天气和健康检查外，涉及用户私有数据的请求必须携带：

```http
Authorization: Bearer <token>
```

接口会校验 Token 中的用户 ID 与路径、查询参数或请求体里的 `user_id` 是否一致：缺少或过期返回 `401`，访问其他用户数据返回 `403`。

## 一、按钮/可点击控件（共 14 个）

### 1. 用户相关

| 按钮 | API | 请求体 | 响应体 | 位置建议 |
|---|---|---|---|---|
| 登录 | `POST /api/v1/users/login` | `{ student_id, password }` | `{ token, user_id, user }` | 登录页 |
| 注册 | `POST /api/v1/users` | `{ student_id, name, password, school, college, major, enroll_year }` | `{ token, user_id, user }` | 注册页 |
| 编辑资料 | `PUT /api/v1/users/{user_id}` | `{ name?, school?, college?, major?, enroll_year? }` | `UserResponse` | 个人页 |
| 注销账号 | `DELETE /api/v1/users/{user_id}` | — | `{ deleted }` | 设置页 |

### 2. 决策沙盘

| 按钮 | API | 请求体 | 响应体 | 位置建议 |
|---|---|---|---|---|
| 开始分析 | `POST /sandbox/start` | `{ user_id, paths? }` | `SandboxChatResponse` | 首页 CTA |
| 继续上次分析 | `POST /sandbox/resume` | `{ session_id, message?, state? }` | `SandboxChatResponse` | 首页/沙盘入口 |

### 3. 规划 Agent（沙盘结束后）

| 按钮 | API | 请求体 | 响应体 | 位置建议 |
|---|---|---|---|---|
| 就业规划 | `POST /api/v1/growth/start` | `{ user_id, agent: "career" }` | `GrowthChatResponse` | 沙盘结果页 |
| 考研规划 | 同上 | `{ user_id, agent: "graduate" }` | 同上 | 沙盘结果页 |
| 考公规划 | 同上 | `{ user_id, agent: "civil" }` | 同上 | 沙盘结果页 |
| 转专业规划 | 同上 | `{ user_id, agent: "major" }` | 同上 | 沙盘结果页 |
| 确认生成报告 | `POST /api/v1/growth/approve` | `{ session_id, user_id }` | `GrowthChatResponse` | Agent 对话中 |
| 重新分析 | `POST /api/v1/growth/correct` | `{ session_id, user_id, correction }` | `GrowthChatResponse` | Agent 对话中 |
| 查看报告 | `GET /api/v1/growth/report/{session_id}` | — | `GrowthReportResponse` | 历史记录/会话结束 |

### 4. 记忆面板

| 按钮 | API | 请求体 | 响应体 | 位置建议 |
|---|---|---|---|---|
| 编辑记忆 | `PATCH /api/v1/memory/panel/{user_id}/{key}` | `{ value, memory_type? }` | `MemoryResponse` | 每条记忆右侧 |
| 删除记忆 | `DELETE /api/v1/memory/panel/{user_id}/{key}` | — | `{ deleted }` | 每条记忆右侧（长按） |

---

## 二、页面加载自动调用（8 个）

| 页面 | API | 说明 |
|---|---|---|
| 首页 | `GET /api/v1/weather?city=xxx` | 天气卡片 |
| 个人页 | `GET /api/v1/users/{user_id}` | 加载用户信息 |
| 记忆面板 | `GET /api/v1/memory/panel/{user_id}` | 加载 AI 记住的画像 |
| 沙盘入口 | `GET /sandbox/paths` | 加载可选路径列表 |
| 历史记录 | `GET /api/v1/growth/history/{user_id}` | 加载历史规划 |
| 对话历史 | `GET /api/v1/conversation/{user_id}` | 加载历史对话 |
| 会话详情 | `GET /api/v1/growth/state/{user_id}` | 加载当前会话进度 |
| Agent 入口 | `GET /api/v1/growth/agents` | 加载可选 Agent 列表 |

---

## 三、输入框发送（3 个）

| 场景 | API | 请求体 | 说明 |
|---|---|---|---|
| 沙盘对话 | `POST /sandbox/chat` | `{ session_id, user_id, message }` | 输入框发送消息 |
| Agent 对话 | `POST /api/v1/growth/chat` | `{ user_id, agent, message, session_id? }` | 输入框发送消息 |
| Agent SSE 流式 | `GET /api/v1/growth/stream/{session_id}?user_id=xxx&message=xxx` | — | 建立 EventSource 连接，逐 token 推送 |

---

## 四、请求/响应 Schema 速查

### 通用响应信封

所有 `/api/v1/*` 接口统一包裹在：

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

> 沙盘接口（`/sandbox/*`）不经过此信封，直接返回数据。

### 用户

```
POST /api/v1/users/login
→ { "student_id": "2023123456", "password": "123456" }
← { "token": "xxx", "user_id": "uuid", "user": { "id", "student_id", "name", "nickname", "school", "college", "major", "grade", "enroll_year", "created_at", "updated_at" } }

POST /api/v1/users
→ { "student_id", "name", "password", "school?", "college?", "major?", "enroll_year?", "nickname?", "grade?" }
← 同上 { token, user_id, user }

GET /api/v1/users/{user_id}
← UserResponse

PUT /api/v1/users/{user_id}
→ { "name?", "school?", "college?", "major?", "enroll_year?", "grade?" }
← UserResponse

DELETE /api/v1/users/{user_id}
← { "deleted": "user_id" }
```

### 沙盘

```
POST /sandbox/start
→ { "user_id", "paths?": ["career", "graduate", "civil", "major"] }
← { "session_id", "user_id", "phase", "finished", "message", "discovery_round", "max_discovery_rounds", "path_selections", "projection_result?" }

POST /sandbox/chat
→ { "session_id", "user_id", "message" }
← 同上结构

POST /sandbox/resume
→ { "session_id", "user_id", "message?", "state?" }
← 同上

GET /sandbox/result/{session_id}
← { "session_id", "user_id", "finished", "path_selections", "path_reports?", "projection_result?" }

GET /sandbox/paths
← { "paths": [{ "type", "name", "description" }] }

GET /sandbox/handoff?session_id=xxx&path_type=career
← { "agent_type", "agent_label", "initial_question", "handoff_context", "agent_state" }
```

### 成长 Agent

```
POST /api/v1/growth/start
→ { "user_id", "agent": "career|graduate|civil|major" }
← { "session_id", "agent", "stage", "finished", "current_step", "total_steps", "next_question?", "message" }

POST /api/v1/growth/chat
→ { "user_id", "agent", "message", "session_id?" }
← 同上 GrowthChatResponse

POST /api/v1/growth/correct
→ { "session_id", "user_id", "correction": "我想调整方向，更关注就业..." }
← GrowthChatResponse

POST /api/v1/growth/approve
→ { "session_id", "user_id" }
← GrowthChatResponse

GET /api/v1/growth/report/{session_id}
← { "session_id", "agent", "report": { "summary", "sections": [...] }, "created_at" }

GET /api/v1/growth/history/{user_id}
← { "user_id", "sessions": [{ "session_id", "agent", "status", "finished", "created_at", "message_count" }] }

GET /api/v1/growth/state/{user_id}
← { "session_id?", "agent?", "stage?", "finished", "current_step", "total_steps", "answers", "has_report" }

GET /api/v1/growth/agents
← { "agents": [{ "type", "name", "description" }] }

GET /api/v1/growth/stream/{session_id}?user_id=xxx&message=xxx
← SSE: {"step":"analyze","status":"done","data":{...}}
```

### 记忆面板

```
GET /api/v1/memory/panel/{user_id}
← { "user_id", "total", "max_capacity": 50, "type_counts": {"profile": 3, "goal": 1}, "memories": [...] }
  每个记忆: { "key", "value", "memory_type": "profile|goal|action|fact", "confidence", "source", "importance", "updated_at" }

PATCH /api/v1/memory/panel/{user_id}/{key}
→ { "value": "新值", "memory_type?": "profile" }
← MemoryResponse

DELETE /api/v1/memory/panel/{user_id}/{key}
← { "deleted": { "user_id", "key" } }
```

### 其他

```
GET /api/v1/weather?city=青岛
← { "temp": 25, "condition": "多云", "icon": "/images/weather-cloudy.png", "humidity": 65, "wind": "南风 3级", "location": "青岛", "advice": "天气舒适..." }

GET /api/v1/conversation/{user_id}
← { "user_id", "total": 12, "messages": [{ "id", "user_id", "role": "user|assistant", "content", "created_at" }] }
```

---

## 五、核心用户流程

```
启动页
  ├─ 注册 ── POST /api/v1/users
  └─ 登录 ── POST /api/v1/users/login
       │
       ▼
首页（天气自动加载）
  ├─ 开始分析 ── POST /sandbox/start
  │    │
  │    ▼
  │  沙盘对话（多轮）
  │    ├─ 发送消息 ── POST /sandbox/chat
  │    └─ 查看结果 ── GET /sandbox/result/{id}
  │         │
  │         ▼
  │  选择方向 ── POST /api/v1/growth/start（四选一）
  │         │
  │         ▼
  │  Agent 对话（多轮 + SSE 流式）
  │    ├─ 发送消息 ── POST /api/v1/growth/chat
  │    ├─ 流式接收 ── GET /api/v1/growth/stream/{id} (SSE)
  │    ├─ 纠正方向 ── POST /api/v1/growth/correct
  │    └─ 生成报告 ── POST /api/v1/growth/approve
  │         │
  │         ▼
  │  查看报告 ── GET /api/v1/growth/report/{id}
  │
  ├─ 个人页
  │    ├─ 查看资料 ── GET /api/v1/users/{id}
  │    └─ 编辑资料 ── PUT /api/v1/users/{id}
  │
  ├─ 记忆面板
  │    ├─ 查看画像 ── GET /api/v1/memory/panel/{id}
  │    ├─ 编辑记忆 ── PATCH /api/v1/memory/panel/{id}/{key}
  │    └─ 删除记忆 ── DELETE /api/v1/memory/panel/{id}/{key}
  │
  └─ 历史记录
       ├─ 规划历史 ── GET /api/v1/growth/history/{id}
       └─ 对话历史 ── GET /api/v1/conversation/{id}
```

---

## 六、API 速查表

### 用户（5 个）

```
POST   /api/v1/users/login         # 🆕 登录
POST   /api/v1/users               # 注册
GET    /api/v1/users/{id}          # 查询
PUT    /api/v1/users/{id}          # 更新
DELETE /api/v1/users/{id}          # 注销
```

### 沙盘（6 个）

```
GET    /sandbox/paths              # 路径列表
POST   /sandbox/start              # 开始会话
POST   /sandbox/chat               # 发送消息
POST   /sandbox/resume             # 恢复会话
GET    /sandbox/result/{id}        # 对比结果
GET    /sandbox/handoff            # 交接 Agent
```

### 规划 Agent（9 个）

```
GET    /api/v1/growth/agents              # Agent 列表
POST   /api/v1/growth/start               # 开始会话
POST   /api/v1/growth/chat                # 发送消息
GET    /api/v1/growth/stream/{id}         # SSE 流式
POST   /api/v1/growth/correct             # 纠正方向
POST   /api/v1/growth/approve             # 确认生成报告
GET    /api/v1/growth/state/{id}          # 会话状态
GET    /api/v1/growth/report/{id}         # 查看报告
GET    /api/v1/growth/history/{id}        # 历史记录
```

### 记忆面板（3 个）

```
GET    /api/v1/memory/panel/{id}          # 画像列表
PATCH  /api/v1/memory/panel/{id}/{key}    # 编辑记忆
DELETE /api/v1/memory/panel/{id}/{key}    # 删除记忆
```

### 其他（2 个）

```
GET    /api/v1/weather?city=xxx           # 天气
GET    /api/v1/conversation/{id}          # 对话历史
```

---

> 共 25 个用户端 API（14 个按钮/点击 + 8 个页面加载 + 3 个输入触发），完整覆盖后端全部用户端端点。
