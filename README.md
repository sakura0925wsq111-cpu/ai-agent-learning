# iCampus：面向大学生的 AI 校园成长助手

[![CI](https://github.com/sakura0925wsq111-cpu/ai-agent-learning/actions/workflows/ci.yml/badge.svg)](https://github.com/sakura0925wsq111-cpu/ai-agent-learning/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

iCampus 是一个前后端一体的微信小程序项目：前端采用微信原生小程序技术，后端采用 FastAPI。它把课程、考试、待办等日常校园事务，与成长规划、路径比较、行动计划和长期记忆连接在同一套体验中。

当前 `master` 已包含完整的 V2 小程序 `miniprogram-v2/` 和后端 `backend/`，无需再切换前端分支即可进行本地联调。`competition-freeze-2026-08-21` 标签保留了当前竞赛演示版本的冻结快照；`frontend-v1` 仅用于查阅旧版前端历史。

## 功能概览

- **今天**：聚合课程、考试、待办、天气、日历热力图和当天时间线。
- **课程与考试导入**：上传 PDF、XLS 或 XLSX，预览解析结果后再确认写入。
- **探索与成长规划**：围绕就业、考研、考公考编、转专业四类方向进行对话式信息收集和建议生成。
- **决策沙盘**：比较多条成长路径，支持继续追问、恢复会话并生成结构化对比结果。
- **报告与行动闭环**：把成长报告中的阶段任务同步到待办，持续回看完成进度。
- **成长教练与历史**：基于已有报告、任务进度和记忆继续提供阶段性反馈。
- **长期记忆**：保存用户画像、目标、偏好和上下文，并提供可查看、修改、删除的记忆面板。
- **账号与数据隔离**：注册、登录、Bearer Token 鉴权及按用户隔离的数据访问。
- **可追溯职业数据**：独立维护升学、专业、薪资、公务员和校内转专业等官方数据的归档、解析、版本与来源链。

AI 功能是可选增强项。开发环境未配置模型密钥时，账号、课程、考试、待办、文件导入等非 AI 接口仍可使用；成长对话、沙盘推演和智能建议等功能需要可用的 OpenAI 兼容模型服务。

## 技术栈

| 层级 | 主要技术 |
| --- | --- |
| 微信小程序 | JavaScript、WXML、WXSS、原生组件与分包 |
| Web API | Python 3.11、FastAPI、Uvicorn |
| 数据与校验 | SQLAlchemy 2、Pydantic 2、SQLite；支持 PostgreSQL URL |
| AI 能力 | OpenAI 兼容 SDK、LangGraph、SQLite Checkpoint |
| 文件与数据处理 | pdfplumber、openpyxl、xlrd、jieba |
| 测试与持续集成 | pytest、Node.js 语法检查、GitHub Actions |
| 部署 | Docker、Docker Compose |

## 系统组成

```text
微信小程序 miniprogram-v2
        │  HTTP / SSE / 文件上传
        ▼
FastAPI /api/v1
        ├── Today：课程、考试、待办、天气、导入
        ├── Growth：成长对话、报告、教练、行动计划
        ├── Sandbox：路径探索与决策比较
        └── Memory：用户长期记忆
                │
                ├── SQLAlchemy → SQLite / PostgreSQL
                └── OpenAI 兼容模型服务（可选）

career_data 独立数据管道 → 官方原文、SQLite、来源链与质量记录
```

`career_data` 当前是独立的数据采集与查询模块，没有注册为 Agent 工具，也没有接入 RAG；这条边界用于保证来源审计和业务编排彼此解耦。

## 项目结构

```text
ai-agent-learning/
├── miniprogram-v2/              # 当前微信小程序 V2
│   ├── pages/                   # 今天、探索、行动、我的等主页面
│   ├── pkg-growth/              # 沙盘、规划、报告、教练与历史分包
│   ├── pkg-today/               # 课程/考试文件导入分包
│   ├── pkg-profile/             # 记忆与能力页面分包
│   ├── components/              # 基础、图表、成长、Today 与弹层组件
│   ├── services/                # API、SSE、上传等请求封装
│   ├── stores/                  # 会话、成长、Today 与 UI 状态
│   ├── normalizers/             # 后端响应兼容与展示数据标准化
│   ├── fixtures/                # 前端降级和契约测试数据
│   └── config/env.js            # develop / trial / release API 地址
├── backend/
│   ├── app/                     # FastAPI 入口和 /api/v1 路由
│   ├── core/                    # 配置、日志、异常、限流和时间工具
│   ├── database/                # 数据库引擎、会话与初始化
│   ├── models/                  # SQLAlchemy 模型
│   ├── schemas/                 # Pydantic 请求/响应模型
│   ├── crud/                    # 通用及领域数据访问
│   ├── services/                # LLM、成长、记忆与 Today 服务
│   ├── planning/                # 四类成长 Agent 与 LangGraph 编排
│   ├── sandbox/                 # 决策沙盘状态、投影与编排
│   ├── memory/                  # 记忆提取、归一化与整合
│   ├── career_data/             # 独立职业数据适配、迁移与查询模块
│   ├── scripts/                 # 数据检查、评估与演示数据脚本
│   └── tests/                   # 后端单元、契约和离线回归测试
├── tests/frontend_v2_contracts.js # 前后端共享 Fixture 的前端契约测试
├── docs/                        # PRD、设计、接口、隐私和部署文档
├── .github/workflows/ci.yml     # 持续集成
├── project.config.json          # 从仓库根目录导入 V2 的微信项目配置
├── Dockerfile
├── docker-compose.yml
├── requirements.txt             # 后端运行、测试及仓库工具依赖
└── pytest.ini
```

数据库、日志、缓存、虚拟环境和本地输出目录均由 Git 忽略；只有经过审核、列入仓库的官方数据快照会被版本控制。

## 快速开始

### 1. 准备环境

- Python 3.11
- pip
- 微信开发者工具
- Node.js 20+（运行前端契约测试和 JavaScript 语法检查时需要）
- 可选：Docker Desktop 或 Docker Engine + Compose

### 2. 安装后端依赖

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

只运行 API 时可改为安装 `backend/requirements.txt`；根目录的 `requirements.txt` 额外包含 pytest 等仓库级工具。

### 3. 配置环境变量

后端从进程环境变量和 `backend/.env` 读取配置。常用配置如下：

| 变量 | 模板值 | 用途 |
| --- | --- | --- |
| `APP_ENV` | `dev` | 运行环境：`dev`、`test` 或 `prod` |
| `DATABASE_URL` | `sqlite:///./data/icampus.db` | 本地数据库；相对路径解析到 `backend/` |
| `JWT_SECRET_KEY` | 开发占位值 | Token 签名密钥，生产环境必须替换 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek 或其他 OpenAI 兼容服务密钥 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容 API 地址 |
| `LLM_MODEL` | `deepseek-chat` | 模型名称 |
| `CORS_ORIGINS` | 本地 Web 地址 | 逗号分隔的明确来源白名单 |
| `DEMO_ACCOUNT_ENABLED` | `true` | 是否在开发环境创建演示账号 |
| `LOG_DIR` | `logs` | 日志目录，相对路径解析到 `backend/` |

不使用 AI 时保持 `DEEPSEEK_API_KEY=` 即可。模板默认会创建开发演示账号 `demo2026` / `DemoPass123!`；不要在生产环境使用该账号或密码。

### 4. 启动后端

在仓库根目录、已激活虚拟环境的终端中运行：

```powershell
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

服务启动后可访问：

- Swagger UI：<http://127.0.0.1:8000/docs>
- ReDoc：<http://127.0.0.1:8000/redoc>
- 存活检查：<http://127.0.0.1:8000/health>
- 就绪检查：<http://127.0.0.1:8000/ready>
- 版本信息：<http://127.0.0.1:8000/version>

本地 SQLite 和日志默认写入 `backend/data/`、`backend/logs/`。

### 5. 运行微信小程序

1. 打开微信开发者工具，导入仓库根目录；根目录 `project.config.json` 已把 `miniprogramRoot` 指向 `miniprogram-v2/`。
2. 启动本地后端。
3. 在开发者工具控制台临时覆盖开发 API 地址：

```javascript
wx.setStorageSync("ICAMPUS_V2_API_BASE_URL", "http://127.0.0.1:8000")
```

4. 重新编译小程序并登录。

开发、体验和正式环境地址统一配置在 `miniprogram-v2/config/env.js`。仓库中的开发地址用于阶段性联调，不保证长期有效；提交代码前应换成团队当前使用的地址。模拟器访问本机服务时可在开发者工具中关闭合法域名校验，真机调试或发布则必须使用可访问的 HTTPS 地址，并在微信公众平台配置服务器域名。

## Docker 运行

从仓库根目录启动：

```powershell
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8000/ready
docker compose logs -f api
```

停止服务但保留数据：

```powershell
docker compose down
```

容器以非 root 用户运行并监听 `0.0.0.0:8000`。SQLite 数据和日志分别由 `icampus-data`、`icampus-logs` 命名卷持久化。除非确定要删除本地数据，否则不要执行 `docker compose down -v`。

Compose 默认以开发配置启动，不需要模型密钥即可验证非 AI 接口。启用 AI 功能时通过环境变量注入密钥：

```powershell
$env:DEEPSEEK_API_KEY = "your-key"
docker compose up --build -d
```

## API 概览

| 路径 | 功能 |
| --- | --- |
| `/health`、`/ready`、`/version` | 存活、就绪和版本检查 |
| `/api/v1/users` | 注册、登录和用户资料 |
| `/api/v1/today` | 今日概览、时间线、日历、课程、考试、导入、建议和计划同步 |
| `/api/v1/todos` | 待办增删改查及完成状态 |
| `/api/v1/weather` | 城市解析与天气查询 |
| `/api/v1/growth` | 成长对话、流式响应、报告、历史、教练和行动计划 |
| `/api/v1/sandbox` | 路径选择、沙盘会话、恢复、流式推演与结果 |
| `/api/v1/memory` | 长期记忆和记忆面板 |

完整参数和响应结构以运行后的 Swagger UI 为准。受保护接口需要请求头 `Authorization: Bearer <token>`。

## 测试与质量检查

在仓库根目录、已安装 `requirements.txt` 的环境中运行：

```powershell
# Python 测试（pytest.ini 已配置 backend/tests 和 Python 路径）
python -m pytest -q

# Python 语法检查
python -m compileall -q backend

# 前后端共享 Fixture 的 V2 契约测试
node .\tests\frontend_v2_contracts.js

# 小程序全部 JavaScript 文件语法检查
Get-ChildItem miniprogram-v2 -Recurse -Filter *.js | ForEach-Object {
  node --check $_.FullName
  if ($LASTEXITCODE -ne 0) { throw "JavaScript syntax check failed: $($_.FullName)" }
}
```

GitHub Actions 会在每次 push 和 pull request 时使用 Python 3.11 与 Node.js 20 安装依赖、编译 Python、运行后端测试，并检查仓库中现有小程序目录的 JavaScript 语法。CI 使用本地占位模型地址，不访问真实大模型。

## 职业数据模块

`backend/career_data/` 提供独立 CLI，负责官方数据的原文归档、哈希去重、解析清洗、版本保留、来源链和质量问题记录。运行前需让 Python 找到后端模块；PowerShell 下初始化并查看数据源：

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
python -m career_data db init
python -m career_data sources list
python -m career_data runs list
python -m career_data quality list
```

macOS / Linux 可在命令前设置 `PYTHONPATH=backend`。详细的导入、查询和来源约束见 [Career Data 说明](backend/career_data/README.md)。

## 生产与安全边界

- 不提交 `backend/.env`、API Key、数据库、日志或包含个人数据的临时文件。
- `APP_ENV=prod` 会校验模型密钥、至少 32 位且非默认的 JWT 密钥、明确的 CORS 白名单、关闭调试以及关闭演示账号；不安全配置会拒绝启动。
- 小程序正式环境必须使用已备案并在微信公众平台配置的 HTTPS API 域名。
- AI 输出是辅助建议，不替代学校正式政策、职业、医疗或心理专业意见。
- 官方政策和岗位数据具有时效性；使用前应检查来源链、数据年份和审核状态。
- 当前仓库定位为可运行的竞赛演示与持续开发版本，不宣称未经验证的生产可用性、性能或覆盖率指标。

## 进一步阅读

- [后端运行说明](backend/README.md)
- [前端 API 对接文档](docs/frontend-api-reference.md)
- [V2 产品需求文档](docs/iCampus-PRD-v2.md)
- [前端设计规范](docs/frontend-design-spec.md)
- [部署说明](docs/deployment-week1.md)
- [隐私说明](docs/privacy.md)
- [真实模型端到端评估记录](docs/live-llm-e2e-evaluation-2026-08-20.md)

## License

[MIT](LICENSE) © 2026 iCampus contributors
