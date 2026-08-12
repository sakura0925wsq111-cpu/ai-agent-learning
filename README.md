# iCampus — AI 校园成长助手

iCampus 是一款面向大学生的微信小程序，覆盖日常管理、成长决策和长期规划。项目由微信小程序前端与 FastAPI 后端组成，通过长期记忆、四类成长规划 Agent 和决策沙盘，为用户提供持续、可回顾的校园成长支持。

## 核心能力

- **今日模式**：课程、考试、待办、天气、日历与时间线管理。
- **课表导入**：支持 PDF 和 Excel 解析、预览、确认导入及学期设置。
- **成长规划**：支持就业、考研、考公考编、转专业四类对话式诊断。
- **报告与行动计划**：生成结构化报告，并可同步为阶段任务和每日计划。
- **决策沙盘**：比较不同成长路径，支持继续追问、切换路径和结果回看。
- **长期记忆**：保存用户画像、目标与上下文，支持用户查看、修改和删除。
- **账号与鉴权**：提供注册、登录和 Bearer Token 保护的用户数据访问。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | 微信小程序原生 JavaScript / WXML / WXSS |
| API | FastAPI + Uvicorn |
| 数据与校验 | SQLAlchemy 2 + SQLite + Pydantic 2 |
| AI | OpenAI 兼容 SDK + LangGraph + SQLite Checkpoint |
| 文件导入 | pdfplumber + openpyxl + python-multipart |
| 日志与配置 | Loguru + Pydantic Settings + `.env` |
| 测试 | pytest + unittest |

## 项目结构

```text
ai-agent-learning/
├── Ver3 - 副本 (5)/        # 微信小程序前端
│   ├── pages/              # 页面
│   ├── utils/              # API、日期、学期等工具
│   ├── app.js              # 全局状态、请求与鉴权
│   └── app.json            # 页面和 TabBar 配置
├── backend/
│   ├── app/                # FastAPI 入口与 API 路由
│   ├── core/               # 配置、日志、异常
│   ├── database/           # 数据库初始化与会话
│   ├── models/             # SQLAlchemy 模型
│   ├── schemas/            # Pydantic 请求/响应模型
│   ├── crud/               # 数据访问
│   ├── services/           # 业务服务
│   ├── memory/             # 长期记忆提取与整合
│   ├── planning/           # 成长规划 Agent 与 LangGraph
│   ├── sandbox/            # 决策沙盘
│   ├── evals/              # 对话评估数据
│   ├── scripts/            # 辅助和评估脚本
│   └── tests/              # 后端测试
├── docs/                   # PRD、设计和接口文档
├── project.config.json     # 微信开发者工具项目配置
├── requirements.txt        # 项目统一依赖入口
└── generate_gifs.py        # 可选 GIF 生成工具
```

## 快速开始

### 1. 环境要求

- Python 3.11+
- pip
- 微信开发者工具（运行小程序时需要）
- 可选：OpenAI 兼容的大模型 API（默认配置以 DeepSeek 接口为例）

### 2. 克隆并创建虚拟环境

```powershell
git clone https://github.com/sakura0925wsq111-cpu/ai-agent-learning.git
cd ai-agent-learning
python -m venv venv
./venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

macOS / Linux 激活命令：

```bash
source venv/bin/activate
```

只运行后端时，也可以安装 `backend/requirements.txt`。

### 3. 配置后端

Windows PowerShell：

```powershell
Copy-Item backend/.env.example backend/.env
```

macOS / Linux：

```bash
cp backend/.env.example backend/.env
```

至少检查以下配置：

```env
APP_NAME=iCampus
DATABASE_URL=sqlite:///./data/campuspal.db
JWT_SECRET_KEY=replace-with-a-long-random-secret
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=your-model-name
```

如果暂时不使用 AI 能力，可以保留空的 `LLM_API_KEY`；课程、待办、天气、账号等非 AI 接口仍可运行。生产环境必须替换默认 JWT 密钥。

### 4. 启动后端

```powershell
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后可访问：

- API 文档：<http://127.0.0.1:8000/docs>
- ReDoc：<http://127.0.0.1:8000/redoc>
- 健康检查：<http://127.0.0.1:8000/health>

SQLite 数据库和日志会分别生成在 `backend/data/` 与 `backend/logs/`，默认不会提交到 Git。

### 5. 启动微信小程序

1. 打开微信开发者工具并选择“导入项目”。
2. 选择仓库根目录；`project.config.json` 已配置小程序目录为 `Ver3 - 副本 (5)/`。
3. 确认后端已启动，然后编译运行。

前端 API 地址集中在 `Ver3 - 副本 (5)/config/env.js`。开发版、体验版和正式版
分别选择 develop、trial、release 地址；真机测试前请把示例域名替换为已加入微信业务域名的 HTTPS 地址。

## API 概览

| 路径前缀 | 功能 |
| --- | --- |
| `/health`、`/ready`、`/version` | 存活、就绪与版本 |
| `/api/v1/users` | 注册、登录、用户资料 |
| `/api/v1/memory` | 长期记忆与记忆面板 |
| `/api/v1/growth` | 成长对话、报告、历史和行动计划 |
| `/api/v1/today` | 课程、考试、日历、导入、建议和计划同步 |
| `/api/v1/todos` | 待办增删改查与完成状态 |
| `/api/v1/weather` | 天气查询 |
| `/api/v1/sandbox` | 决策沙盘对话、路径和结果 |

登录成功后，前端会在需要鉴权的请求中发送：

```http
Authorization: Bearer <token>
```

业务接口通常使用统一响应结构：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

完整请求参数和响应模型以运行后的 Swagger 文档为准。

## 测试与检查

Windows PowerShell：

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
python -m pytest backend/tests -q
```

macOS / Linux：

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
```

常用静态检查：

```powershell
python -m compileall -q backend
Get-ChildItem 'Ver3 - 副本 (5)' -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
```

## 依赖清单说明

- `requirements.txt`：推荐的统一安装入口，包含后端、测试与 GIF 工具依赖。
- `backend/requirements.txt`：后端运行时依赖，适用于只部署 API 服务的环境。

依赖按当前开发与测试环境锁定；升级核心框架后应重新运行完整测试。

## 文档

- [第一周部署与演示说明](docs/deployment-week1.md)
- [隐私说明（测试版）](docs/privacy.md)
- [产品需求文档](docs/iCampus-PRD-v2.md)
- [前端设计规范](docs/frontend-design-spec.md)
- [前端 API 对接文档](docs/frontend-api-reference.md)
- [教师端开发计划](docs/teacher-dev-plan.md)
- [历史差距分析](docs/CampusPal-%E5%B7%AE%E8%B7%9D%E5%88%86%E6%9E%90.md)

## 安全与部署提示

- 不要提交 `backend/.env`、数据库、日志或真实 API Key。
- 生产环境必须设置高强度 `JWT_SECRET_KEY`。
- CORS 来源由 `CORS_ORIGINS` 白名单控制，生产环境禁止使用通配符。
- AI 生成的成长建议仅供参考，不替代学校政策、职业或心理专业意见。

## License

MIT
