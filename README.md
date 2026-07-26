# iCampus — AI 校园成长助手

iCampus 是一个面向大学生的 AI 智能助手，基于 **FastAPI + LangGraph** 构建。它能够管理日常事务（待办、天气），并通过长期记忆和沙盘推演为用户提供个性化的成长规划建议。

## 核心功能

- **今日模式** — 待办管理、天气查询、日常问答
- **成长模式** — 就业 / 考研 / 考公 / 转专业 四大方向的 AI 诊断与规划
- **沙盘推演** — 模拟不同人生选择，可视化路径对比
- **长期记忆** — 记住用户偏好和历史，提供持续陪伴式体验

## 技术栈

| 类别   | 技术                      |
| ------ | ------------------------- |
| 框架   | FastAPI + Uvicorn         |
| AI     | LangGraph + DeepSeek      |
| 数据库 | SQLite + SQLAlchemy       |
| 配置   | Pydantic Settings (.env)  |
| 日志   | Loguru                    |

## 快速开始

### 1. 环境要求

- Python 3.11+
- pip

### 2. 克隆项目

```bash
git clone https://github.com/sakura0925wsq111-cpu/ai-agent-learning.git
cd ai-agent-learning
```

### 3. 安装依赖

```bash
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS / Linux

pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 4. 配置环境变量

```bash
copy backend\.env.example backend\.env
```

编辑 `backend/.env`，填入你的 DeepSeek API Key：

```
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
```

> 去 [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) 免费申请

### 5. 启动服务

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后访问：

- API 文档：http://127.0.0.1:8000/docs
- ReDoc：http://127.0.0.1:8000/redoc

## API 路由

| 路由               | 说明     |
| ------------------ | -------- |
| `GET /`            | 服务信息 |
| `GET /health`      | 健康检查 |
| `/api/v1/users`    | 用户管理 |
| `/api/v1/memory`   | 长期记忆 |
| `/api/v1/growth`   | 成长规划 |
| `/api/v1/todos`    | 待办事项 |
| `/api/v1/weather`  | 天气查询 |
| `/sandbox`         | 沙盘推演 |

## 项目结构

```
ai-agent-learning/
├── backend/
│   ├── app/main.py          # FastAPI 入口
│   ├── app/api/v1/          # API 路由
│   ├── core/                # 配置、异常、日志
│   ├── database/            # 数据库初始化
│   ├── models/              # ORM 模型
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── services/            # 业务逻辑
│   ├── memory/              # 记忆系统
│   ├── planning/            # LangGraph 规划引擎
│   ├── sandbox/             # 沙盘推演
│   ├── crud/                # 数据库操作
│   ├── scripts/             # 工具脚本
│   └── tests/               # 测试
├── docs/                    # 产品文档
└── requirements.txt         # 全局依赖
```

## 文档

- [产品需求文档 (PRD)](docs/iCampus-PRD-V1.0-%E6%AD%A3%E5%BC%8F%E7%89%88.md)
- [前端 API 参考](docs/frontend-api-reference.md)
- [差距分析](docs/iCampus-%E5%B7%AE%E8%B7%9D%E5%88%86%E6%9E%90.md)

## License

MIT
