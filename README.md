# CampusPal — AI 校园成长助手

CampusPal 是一个面向大学生的 AI 智能助手，基于 FastAPI + LangGraph 构建。它能够管理日常事务（待办、天气），并通过长期记忆和沙盘推演为用户提供个性化的成长规划建议。

## 核心功能

- **今日模式**：待办管理、天气查询、日常问答
- **成长模式**：就业 / 考研 / 考公 / 转专业 四大方向的 AI 诊断与规划
- **沙盘推演**：模拟不同人生选择，可视化路径对比
- **长期记忆**：记住用户偏好和历史，提供持续陪伴式体验

## 技术栈

| 类别 | 技术 |
|---|---|
| 框架 | FastAPI + Uvicorn |
| AI | LangGraph + DeepSeek |
| 数据库 | SQLite + SQLAlchemy |
| 配置 | Pydantic Settings（.env） |
| 日志 | Loguru |

## 快速开始

### 1. 环境要求

- Python 3.11+
- pip

### 2. 克隆项目

git clone https://github.com/sakura0925wsq111-cpu/ai-agent-learning.git
cd ai-agent-learning

### 3. 安装依赖

python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS / Linux

pip install -r requirements.txt
pip install -r backend/requirements.txt

### 4. 配置环境变量

copy backend\.env.example backend\.env

编辑 ackend/.env，填入你的 DeepSeek API Key：

LLM_API_KEY=sk-xxxxxxxxxxxxxxxx

> 去 https://platform.deepseek.com/api_keys 免费申请

### 5. 启动服务

cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

启动后访问：

- API 文档：http://127.0.0.1:8000/docs
- ReDoc：http://127.0.0.1:8000/redoc

## API 路由

| 路由 | 说明 |
|---|---|
| GET / | 服务信息 |
| GET /health | 健康检查 |
| /api/v1/users | 用户管理 |
| /api/v1/memory | 长期记忆 |
| /api/v1/growth | 成长规划 |
| /api/v1/todos | 待办事项 |
| /api/v1/weather | 天气查询 |
| /sandbox | 沙盘推演 |

## 项目结构

ai-agent-learning/
├── backend/               # 后端代码
│   ├── app/main.py        # FastAPI 入口
│   ├── app/api/           # API 路由
│   ├── core/              # 配置、异常、日志
│   ├── database/          # 数据库初始化
│   ├── models/            # ORM 模型
│   ├── schemas/           # Pydantic 请求/响应模型
│   ├── services/          # 业务逻辑
│   ├── memory/            # 记忆系统
│   ├── planning/          # LangGraph 规划引擎
│   ├── sandbox/           # 沙盘推演
│   └── crud/              # 数据库操作
├── docs/                  # 产品文档
└── requirements.txt       # 全局依赖

## 文档

- [产品需求文档 (PRD)](docs/CampusPal-PRD-V1.0-正式版.md)
- [前端 API 参考](docs/frontend-api-reference.md)
- [差距分析](docs/CampusPal-差距分析.md)

## License

MIT
