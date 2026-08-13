# iCampus — 校园成长助手

[![CI](https://github.com/sakura0925wsq111-cpu/ai-agent-learning/actions/workflows/ci.yml/badge.svg)](https://github.com/sakura0925wsq111-cpu/ai-agent-learning/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

iCampus 是一款面向大学生的微信小程序，由微信原生小程序前端和 FastAPI 后端组成。项目覆盖课程与待办管理、成长规划、长期记忆和路径决策；AI 能力是可选增强项，没有配置模型密钥时，账号、课程、考试、待办、天气等非 AI 接口仍可使用。

## 核心能力

- **今日模式**：课程、考试、待办、天气、日历与时间线管理。
- **文件导入**：支持 PDF / Excel 课表和考试信息的解析、预览与确认。
- **成长规划**：支持就业、考研、考公考编、转专业等对话式诊断。
- **报告与行动计划**：输出结构化报告，并同步阶段任务到每日计划。
- **决策沙盘**：比较成长路径，支持追问、切换路径和结果回看。
- **长期记忆**：保存并管理用户画像、目标和对话上下文。
- **账号与鉴权**：注册、登录及 Bearer Token 保护的数据访问。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 微信小程序 | 原生 JavaScript / WXML / WXSS |
| Web API | Python 3.11 / FastAPI / Uvicorn |
| 数据层 | SQLAlchemy 2 / SQLite，兼容 PostgreSQL 配置 |
| 数据校验 | Pydantic 2 / Pydantic Settings |
| AI 编排 | OpenAI 兼容 SDK / LangGraph / SQLite Checkpoint |
| 文件处理 | pdfplumber / openpyxl / xlrd |
| 测试与 CI | pytest / `compileall` / `node --check` / GitHub Actions |
| 容器化 | Docker / Docker Compose |

## 项目结构

```text
ai-agent-learning/
├── miniprogram/                 # 微信原生小程序
│   ├── pages/                   # 页面及交互逻辑
│   ├── config/env.js            # 各微信发布环境的 API 地址
│   ├── utils/                   # API、日期、学期等公共工具
│   ├── app.js                   # 全局状态、请求与鉴权
│   └── app.json                 # 页面和 TabBar 配置
├── backend/
│   ├── app/                     # FastAPI 入口与 API 路由
│   ├── core/                    # 配置、日志、异常与限流
│   ├── database/                # 数据库引擎、会话与初始化
│   ├── models/                  # SQLAlchemy 模型
│   ├── schemas/                 # Pydantic 请求/响应模型
│   ├── crud/                    # 数据访问
│   ├── services/                # 业务服务
│   ├── memory/                  # 长期记忆提取与整合
│   ├── planning/                # 成长规划 Agent 与 LangGraph
│   ├── sandbox/                 # 决策沙盘
│   ├── career_data/             # 可追溯职业数据管道
│   ├── data/career_data/raw/    # 经审核保留的官方数据快照
│   └── tests/                   # 后端自动化测试
├── docs/                        # 部署、隐私、产品与接口文档
├── .github/workflows/ci.yml     # push / pull_request 持续集成
├── Dockerfile                   # 后端生产式镜像入口
├── docker-compose.yml           # 本地容器运行配置
├── project.config.json          # 微信开发者工具根项目配置
└── requirements.txt             # 后端、测试及仓库工具依赖
```

## 本地开发

### 环境要求

- Python 3.11
- pip
- Node.js 20+（仅 JavaScript 语法检查需要）
- 微信开发者工具（运行小程序时需要）
- 可选：Docker Desktop / Docker Engine + Compose

### 安装依赖

Windows PowerShell：

```powershell
git clone https://github.com/sakura0925wsq111-cpu/ai-agent-learning.git
Set-Location ai-agent-learning
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item backend/.env.example backend/.env
```

macOS / Linux：

```bash
git clone https://github.com/sakura0925wsq111-cpu/ai-agent-learning.git
cd ai-agent-learning
python3.11 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp backend/.env.example backend/.env
```

`requirements.txt` 是推荐的开发与测试入口；只部署 API 时可安装 `backend/requirements.txt`。

### 配置环境变量

后端从进程环境变量和 `backend/.env` 读取配置。不要提交真实 `.env`，模板文件 `backend/.env.example` 会保留在 Git 中。

| 变量 | 本地默认/示例 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `dev` | `dev`、`test` 或 `prod` |
| `DATABASE_URL` | `sqlite:///./data/campuspal.db` | 也支持 `postgresql+psycopg://...` |
| `JWT_SECRET_KEY` | 仅本地开发默认值 | 生产环境必须换成至少 32 位的独立随机值 |
| `DEEPSEEK_API_KEY` | 空 | AI 功能所需；非 AI 功能不需要 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容服务地址 |
| `LLM_MODEL` | `deepseek-chat` | 模型名称 |
| `CORS_ORIGINS` | 本地地址白名单 | 生产环境必须使用明确域名，不能为 `*` |
| `LOG_DIR` | `logs` | 相对 `backend/` 的日志目录，也可用绝对路径 |

不使用 AI 时，将模板中的密钥显式留空：

```env
DEEPSEEK_API_KEY=
```

### 启动后端

从仓库根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

macOS / Linux：

```bash
PYTHONPATH=backend ./venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

启动后可访问：

- Swagger：<http://127.0.0.1:8000/docs>
- ReDoc：<http://127.0.0.1:8000/redoc>
- 存活检查：<http://127.0.0.1:8000/health>
- 就绪检查：<http://127.0.0.1:8000/ready>

本地 SQLite 数据库和日志默认写入 `backend/data/`、`backend/logs/`，两者均被 Git 忽略。

### 导入微信小程序

1. 打开微信开发者工具，选择“导入项目”。
2. 选择仓库根目录；根目录 `project.config.json` 已将 `miniprogramRoot` 指向 `miniprogram/`。
3. 启动本地后端后编译运行小程序。

API 地址集中在 `miniprogram/config/env.js`。开发版、体验版和正式版分别使用 develop、trial、release 地址；真机或发布前必须替换示例域名，并在微信公众平台配置 HTTPS 业务域名。

## Docker 启动

默认 Compose 配置使用 SQLite，不要求大模型密钥即可启动后端并访问非 AI 接口：

```powershell
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8000/ready
docker compose logs -f api
```

停止服务但保留数据卷：

```powershell
docker compose down
```

容器以非 root 用户运行，监听 `0.0.0.0:8000`。运行数据位置如下：

| 内容 | 容器路径 | Compose 卷 |
| --- | --- | --- |
| SQLite 与运行数据 | `/app/data` | `icampus-data` |
| 日志 | `/app/logs` | `icampus-logs` |

Compose 项目名为 `icampus`，Docker 通常将卷显示为 `icampus_icampus-data` 和 `icampus_icampus-logs`。不要使用 `docker compose down -v`，除非确定要删除本地容器数据。

如需 AI 功能，可在启动前通过环境变量注入密钥；不要把密钥写进镜像或 Compose 文件：

```powershell
$env:DEEPSEEK_API_KEY = "your-key"
docker compose up --build -d
```

Compose 内置的 JWT 值只用于本地 `dev`。生产部署必须设置独立的 `JWT_SECRET_KEY`，同时关闭演示账号、关闭调试并配置明确的 CORS 白名单；`APP_ENV=prod` 会拒绝不安全配置。

## 测试与质量检查

后端测试：

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
.\venv\Scripts\python.exe -m pytest backend/tests -q
```

Python 语法检查：

```powershell
.\venv\Scripts\python.exe -m compileall -q backend
```

微信小程序 JavaScript 语法检查：

```powershell
Get-ChildItem miniprogram -Recurse -Filter *.js | ForEach-Object {
  node --check $_.FullName
  if ($LASTEXITCODE -ne 0) { throw "JavaScript syntax check failed: $($_.FullName)" }
}
```

GitHub Actions 会在每次 push 和 pull request 上使用 Python 3.11 与 Node.js 20 执行：

1. pip 缓存与依赖安装。
2. `python -m compileall -q backend`。
3. `PYTHONPATH=backend python -m pytest backend/tests -q`。
4. `miniprogram` 下全部 `.js` 文件的 `node --check`。

CI 使用占位密钥和仅指向本机的模型地址，不读取真实 `.env`，测试不应访问真实大模型或外部数据源。

## API 概览

| 路径前缀 | 功能 |
| --- | --- |
| `/health`、`/ready`、`/version` | 存活、就绪与版本 |
| `/api/v1/users` | 注册、登录、用户资料 |
| `/api/v1/memory` | 长期记忆与记忆面板 |
| `/api/v1/growth` | 成长对话、报告、历史与行动计划 |
| `/api/v1/today` | 课程、考试、日历、导入、建议与计划同步 |
| `/api/v1/todos` | 待办增删改查与完成状态 |
| `/api/v1/weather` | 天气查询 |
| `/api/v1/sandbox` | 决策沙盘、路径比较与结果 |

完整请求参数和响应模型以运行后的 Swagger 文档为准。受保护接口使用 `Authorization: Bearer <token>`。

## 数据与安全边界

- 不提交 `backend/.env`、数据库、日志、缓存或真实 API Key。
- `backend/data/career_data/raw/` 中列入允许清单的文件是可追溯官方数据快照，不属于运行时垃圾。
- 生产环境必须替换默认 JWT 密钥，并使用明确的 CORS 白名单。
- AI 建议仅供参考，不替代学校政策、职业、医疗或心理专业意见。
- 当前仓库没有声明未经验证的性能、覆盖率或生产可用性指标。

## 文档

- [后端运行说明](backend/README.md)
- [部署与演示说明](docs/deployment-week1.md)
- [隐私说明](docs/privacy.md)
- [产品需求文档](docs/iCampus-PRD-v2.md)
- [前端设计规范](docs/frontend-design-spec.md)
- [前端 API 对接文档](docs/frontend-api-reference.md)

## License

[MIT](LICENSE) © 2026 iCampus contributors
