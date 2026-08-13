# iCampus 后端

iCampus 后端基于 FastAPI、SQLAlchemy、Pydantic 和 OpenAI 兼容 SDK，提供账号、今日模式、成长规划、长期记忆与决策沙盘 API。完整项目结构和小程序说明见[根目录 README](../README.md)。

## 本地运行

从仓库根目录执行：

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
$env:PYTHONPATH = (Resolve-Path backend).Path
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

macOS / Linux 使用 `source venv/bin/activate`、`cp backend/.env.example backend/.env`，并将虚拟环境解释器路径改为 `./venv/bin/python`。

服务地址：

- Swagger：<http://127.0.0.1:8000/docs>
- ReDoc：<http://127.0.0.1:8000/redoc>
- 存活检查：<http://127.0.0.1:8000/health>
- 就绪检查：<http://127.0.0.1:8000/ready>

## 配置

后端从进程环境变量和 `backend/.env` 读取配置。复制模板后重点检查：

```env
APP_NAME=iCampus
APP_ENV=dev
DATABASE_URL=sqlite:///./data/campuspal.db
JWT_SECRET_KEY=replace-with-at-least-32-random-characters
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

`DEEPSEEK_API_KEY` 为空时，dev 环境的非 AI 接口仍可使用。生产环境会校验模型密钥、JWT 密钥、CORS 白名单、调试开关和演示账号设置；配置不安全时启动失败。详见[部署说明](../docs/deployment-week1.md)。

## Docker

从仓库根目录执行：

```powershell
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8000/ready
```

镜像使用 Python 3.11 轻量基础镜像和非 root 用户。SQLite 与日志分别写入 `/app/data`、`/app/logs`，由 Compose 的 `icampus-data`、`icampus-logs` 卷持久化。默认不需要模型密钥即可启动非 AI 接口。

## 代码结构

```text
backend/
├── app/          # FastAPI 入口；API 路由位于 app/api
├── core/         # 配置、日志、异常与限流
├── database/     # SQLAlchemy 引擎、会话和初始化
├── models/       # ORM 模型
├── schemas/      # Pydantic 模型
├── crud/         # 数据访问
├── services/     # 业务服务
├── memory/       # 长期记忆
├── planning/     # 成长规划 Agent 与 LangGraph
├── sandbox/      # 决策沙盘
├── career_data/  # 职业数据适配、标准化与审计
└── tests/        # 自动化测试
```

当前生效的路由入口是 `backend/app/api`，不要再新建或引用旧式 `backend/api` 目录。

## 测试

从仓库根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
.\venv\Scripts\python.exe -m pytest backend/tests -q
.\venv\Scripts\python.exe -m compileall -q backend
```

## 数据与日志

- 本地 SQLite：`backend/data/`
- 本地日志：`backend/logs/`
- 容器数据：`/app/data`
- 容器日志：`/app/logs`
- 本地环境变量：`backend/.env`

运行时文件均被 Git 和 Docker 构建上下文忽略；经审核保留的官方职业数据快照除外。
