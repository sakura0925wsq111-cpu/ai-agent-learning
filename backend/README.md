# CampusPal — AI 人生决策教练

帮助大学生进行日常规划和人生重大决策的 AI 助手。

> 🏗️ 第二周：数据库设计 + 用户系统 + 聊天记录 + 用户画像（Memory） + REST API

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Windows / macOS / Linux

### 1. 创建虚拟环境 & 安装依赖

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1   # Windows
# source venv/bin/activate  # macOS / Linux
pip install -r requirements.txt
```

### 2. 配置环境变量

```powershell
copy .env.example .env
```

编辑 `.env`，填入你的 API Key：

```env
LLM_API_KEY=sk-your-key-here
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

### 3. 启动服务

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. 打开 Swagger

浏览器访问: **http://127.0.0.1:8000/docs**

---

## 📁 完整目录结构

```
backend/
├── app/                        # FastAPI 应用层
│   ├── api/                    # API 路由（薄层，只做参数收/发）
│   │   ├── health.py           # GET /health, /version
│   │   ├── chat.py             # POST /chat (legacy)
│   │   └── v1/                 # ★ v1 REST API
│   │       ├── users.py        # POST/GET/PUT/DELETE /api/v1/users
│   │       ├── conversation.py # POST/GET/DELETE /api/v1/conversation
│   │       ├── memory.py       # POST/GET/PUT/DELETE /api/v1/memory
│   │       └── chat.py         # POST /api/v1/chat (memory-integrated)
│   └── main.py                 # 应用入口 + 生命周期 + 路由注册
│
├── core/                       # 核心基础设施
│   ├── config.py               # Pydantic Settings 配置管理
│   ├── logger.py               # Loguru 日志系统
│   └── exceptions.py           # 自定义异常 + 全局 handler
│
├── database/                   # 数据库层
│   ├── base.py                 # SQLAlchemy DeclarativeBase
│   └── session.py              # Engine + Session + get_db + init_db
│
├── models/                     # ★ ORM 数据库模型
│   ├── user.py                 # User 表
│   ├── conversation.py         # Conversation 表（聊天记录）
│   └── memory.py               # Memory 表（用户画像 key-value）
│
├── schemas/                    # ★ Pydantic 请求/响应模型
│   ├── response.py             # 统一响应 {code, message, data}
│   ├── chat.py                 # 对话接口模型
│   ├── user.py                 # User CRUD 模型
│   ├── conversation.py         # Conversation CRUD 模型
│   └── memory.py               # Memory CRUD 模型
│
├── crud/                       # ★ 数据访问层
│   ├── base.py                 # 通用 CRUD 基类
│   ├── user.py                 # User CRUD
│   ├── conversation.py         # Conversation CRUD
│   └── memory.py               # Memory CRUD (含 upsert)
│
├── services/                   # ★ 业务逻辑层
│   ├── llm_service.py          # LLM 调用封装（OpenAI SDK）
│   ├── memory_service.py       # Memory 服务（save/load/update/delete）
│   └── chat_service.py         # 聊天编排（读记忆→发Prompt→调LLM→存记忆）
│
├── memory/                     # ★ Memory 提取引擎
│   ├── prompts.py              # 系统 Prompt（含记忆提取规则）
│   └── extractor.py            # JSON 解析器（从 LLM 回复中提取 memory_update）
│
├── utils/                      # 通用工具
│   └── json_parser.py          # 安全 JSON 解析
│
├── prompts/                    # Prompt 模板（预留）
├── tests/                      # 测试代码（预留）
│
├── data/                       # 数据库文件（自动生成，不入 Git）
├── logs/                       # 日志文件（自动生成，不入 Git）
├── .env                        # 环境变量（不入 Git）
├── .env.example                # 环境变量模板
├── .gitignore
├── requirements.txt
├── main.py
└── README.md
```

---

## 🏛️ 架构设计

```
用户请求
  │
  ▼
┌─────────────────────────────────────────┐
│  app/api/v1/     ← 路由层（参数校验）    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  services/       ← 业务逻辑层            │
│  ├── chat_service   (记忆注入+LLM调用)   │
│  └── memory_service (记忆CRUD)          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  crud/           ← 数据访问层（DB操作）  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  models/         ← ORM 模型             │
│  database/       ← Engine + Session     │
└─────────────────────────────────────────┘
```

**依赖方向：上层 → 下层，不允许反向依赖。**

---

## 📐 API 一览

### v1 (挂载在 /api/v1)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/users | 创建用户 |
| GET | /api/v1/users/{id} | 获取用户 |
| PUT | /api/v1/users/{id} | 更新用户 |
| DELETE | /api/v1/users/{id} | 删除用户 |
| POST | /api/v1/conversation | 保存消息 |
| GET | /api/v1/conversation/{user_id} | 获取聊天记录 |
| DELETE | /api/v1/conversation/{user_id} | 清空聊天记录 |
| POST | /api/v1/memory | 保存/更新记忆 |
| POST | /api/v1/memory/batch | 批量保存记忆 |
| GET | /api/v1/memory/{user_id} | 获取用户所有记忆 |
| GET | /api/v1/memory/{user_id}/{key} | 获取指定 key 的记忆 |
| PUT | /api/v1/memory/{user_id}/{key} | 更新指定 key 的记忆 |
| DELETE | /api/v1/memory/{user_id}/{key} | 删除指定 key 的记忆 |
| POST | /api/v1/chat | ★ 带记忆的 AI 对话 |

### 统一响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

| code | 含义 |
|------|------|
| 0 | 成功 |
| 422 | 参数校验失败 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 🧠 Memory 系统工作流程

```
用户: "我是交通工程专业"
  │
  ▼
Chat Service 读取已有 Memory → 拼入系统 Prompt
  │
  ▼
LLM 返回:
  "好的，已记住你的专业是交通工程。有什么想聊的吗？"
  ```json
  {"memory_update": [{"key": "major", "value": "交通工程"}]}
  ```
  │
  ▼
Extractor 解析 JSON → Memory Service 保存到 DB
  │
  ▼
下次用户再聊天时:
  "欢迎回来！你是交通工程专业的。今天想聊什么？"
```

---

## 🧪 如何验证

### 1. 创建用户

```bash
curl -X POST http://127.0.0.1:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"nickname": "小明", "major": "交通工程", "grade": "大二", "target": "考研"}'
```

### 2. 发送带记忆的 AI 对话

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "<USER_ID>", "message": "我喜欢AI方向"}'
```

### 3. 查看记忆是否保存

```bash
curl http://127.0.0.1:8000/api/v1/memory/<USER_ID>
```

### 4. Swagger 直接测试

打开 http://127.0.0.1:8000/docs，所有接口都可以直接在页面上测试。

---

## 🔧 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.115 | Web 框架 |
| Uvicorn | 0.34 | ASGI 服务器 |
| SQLAlchemy | 2.0 | ORM (2.0 新写法) |
| Pydantic | 2.10 | 数据验证 |
| Pydantic Settings | 2.7 | 配置管理 |
| Loguru | 0.7 | 日志系统 |
| OpenAI SDK | 1.58 | LLM 客户端 |
| Alembic | 1.14 | 数据库迁移（预留） |

---

## 📋 下一步开发计划

| 周次 | 内容 |
|------|------|
| 第 1 周 ✅ | 后端基础架构 |
| 第 2 周 ✅ | 用户系统 + 聊天记录 + Memory |
| 第 3 周 | AI 连续追问（成长诊断） |
| 第 4 周 | 今日模式（课程分析/待办/日程） |
| 第 5 周 | 成长模式（考研/就业规划） |
| 第 6 周 | AI 决策沙盘 |
| 第 7 周 | 长期成长追踪 |
| 第 8 周 | 部署上线 & 性能优化 |

---

## 📄 License

MIT
