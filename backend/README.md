# iCampus 后端

iCampus 后端基于 FastAPI、SQLAlchemy、LangGraph 和 OpenAI 兼容 SDK，提供账号、今日模式、成长规划、长期记忆与决策沙盘 API。项目完整说明见 [根目录 README](../README.md)。

## 本地运行

从仓库根目录执行：

```powershell
python -m venv venv
./venv/Scripts/Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

macOS / Linux 使用 `source venv/bin/activate` 和 `cp backend/.env.example backend/.env`。

服务地址：

- Swagger：<http://127.0.0.1:8000/docs>
- ReDoc：<http://127.0.0.1:8000/redoc>
- 健康检查：<http://127.0.0.1:8000/health>

## 配置

后端从 `backend/.env` 读取配置。复制 `.env.example` 后，重点设置：

```env
APP_NAME=iCampus
DATABASE_URL=sqlite:///./data/campuspal.db
JWT_SECRET_KEY=replace-with-a-long-random-secret
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=your-model-name
```

`LLM_API_KEY` 为空时，非 AI 接口仍可使用。生产环境不得使用默认 JWT 密钥。

## 代码结构

```text
backend/
├── app/          # FastAPI 入口和 API 路由
├── core/         # 配置、日志、异常
├── database/     # SQLAlchemy 引擎、会话和初始化
├── models/       # ORM 模型
├── schemas/      # Pydantic 模型
├── crud/         # 数据访问
├── services/     # 业务服务
├── memory/       # 长期记忆
├── planning/     # 成长规划 Agent 与 LangGraph
├── sandbox/      # 决策沙盘
├── evals/        # 对话评估数据
├── scripts/      # 辅助脚本
└── tests/        # 自动化测试
```

## API 分组

| 路径前缀 | 功能 |
| --- | --- |
| `/api/v1/users` | 注册、登录和用户资料 |
| `/api/v1/memory` | 长期记忆 |
| `/api/v1/growth` | 成长规划、报告和历史 |
| `/api/v1/today` | 课程、考试、日历、导入和计划同步 |
| `/api/v1/todos` | 待办管理 |
| `/api/v1/weather` | 天气查询 |
| `/api/v1/sandbox` | 决策沙盘 |

具体参数和模型以 Swagger 为准。受保护接口使用 `Authorization: Bearer <token>`。

## 测试

从仓库根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
python -m pytest backend/tests -q
```

只做语法检查：

```powershell
python -m compileall -q backend
```

## 数据与日志

- SQLite 数据库：`backend/data/`
- 运行日志：`backend/logs/`
- 环境变量：`backend/.env`

这些运行时文件均不应提交到 Git。
