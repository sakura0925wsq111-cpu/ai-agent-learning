# iCampus：让 AI 规划进入真实执行闭环

[![CI](https://github.com/sakura0925wsq111-cpu/ai-agent-learning/actions/workflows/ci.yml/badge.svg)](https://github.com/sakura0925wsq111-cpu/ai-agent-learning/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 路径比较 → 四阶段规划 → 报告持久化 → 同步为待办 → 用户完成任务 → 进度回写 → AI 教练读取真实执行状态

iCampus 是一个微信小程序 + FastAPI 的 AI 校园成长系统。项目重点不是堆叠“四种 Agent”，而是把一次模型建议变成可确认、可执行、可追踪、可反馈的行动闭环。

**当前定位：可运行的 AI 全栈作品集 / 竞赛演示系统，不宣称已经达到多租户生产 SaaS 水平。**

[真实 LLM 全链路评估](docs/live-llm-e2e-evaluation-2026-08-20.md) · [后端运行说明](backend/README.md) · [API 对接文档](docs/frontend-api-reference.md) · [产品需求文档](docs/iCampus-PRD-v2.md)

## 已用真实模型跑通的黄金闭环

2026-08-20 使用 `deepseek-chat`、隔离业务数据库和隔离 LangGraph checkpoint 完成了一次真实服务调用评估。它验证的不是单轮回答质量，而是跨模块状态能否连续传递。

```text
选择「就业 + 考研」两条路径
  → 沙盘收集约束并生成路径对比
  → 用户选择「就业」方向
  → 生成并持久化 phase_1 ~ phase_4 四阶段规划
  → 用户确认同步第一阶段，创建 3 个 Todo
  → 用户完成其中 1 项
  → 聚合进度更新为 1 / 3 = 33%
  → AI 教练读取报告、同步任务和最新完成状态后给出建议
```

| 验收点 | 真实评估结果 | 证据落点 |
| --- | --- | --- |
| 路径比较 | `career` 与 `graduate` 被锁定，对话未擅自改写选择 | Sandbox session / projection |
| 四阶段规划 | 成功生成 `phase_1` 至 `phase_4` | `GrowthReport` |
| 报告持久化 | 规划结果写入业务数据库，可从历史报告恢复 | Growth API + SQLAlchemy |
| 同步待办 | 第一阶段同步 3 项，Today 再次读取到 3 项 | `PlanTask` + `Todo` |
| 进度回写 | 完成 1 项后聚合为 `1 / 3`、`33%` | `get_plan_progress` |
| 教练闭环 | 教练读取最新完成状态后给出下一步建议 | Growth Coach context |

完整输入、隔离方式与结果见 [真实 LLM 全链路评估记录](docs/live-llm-e2e-evaluation-2026-08-20.md)。

## 核心界面

以下为 `deliverables/complete-design-v1-bento/` 中与黄金闭环对应的高保真 UI 设计稿，**用于说明信息架构和交互目标，不冒充实机运行截图**。

<table>
  <tr>
    <td width="50%" align="center"><img src="deliverables/complete-design-v1-bento/08-path-comparison.png" alt="路径模拟对比 UI 设计稿"><br><strong>路径比较</strong>：展示同轮相对评分、不确定性和用户最终选择</td>
    <td width="50%" align="center"><img src="deliverables/complete-design-v1-bento/10-growth-report.png" alt="四阶段成长报告 UI 设计稿"><br><strong>四阶段报告</strong>：报告、同步状态与执行进度在同一页面汇合</td>
  </tr>
  <tr>
    <td width="50%" align="center"><img src="deliverables/complete-design-v1-bento/09-action-plan.png" alt="行动计划 UI 设计稿"><br><strong>行动计划</strong>：任务完成状态反向聚合为阶段进度</td>
    <td width="50%" align="center"><img src="deliverables/complete-design-v1-bento/04-ai-coach.png" alt="AI 成长教练 UI 设计稿"><br><strong>AI 教练</strong>：读取执行事实，建议新增任务仍需用户确认</td>
  </tr>
</table>

这组设计稿与真实接口的对应关系见 [后端能力矩阵](deliverables/complete-design-v1-bento/backend-capability-matrix.md)。

## 为什么不是普通聊天机器人

| 普通 LLM Chat Demo | iCampus |
| --- | --- |
| 输入一段文本，返回一段文本 | 读取用户画像、路径选择、历史报告、长期记忆和 Todo 状态 |
| 模型自由决定流程何时结束 | 代码控制 LangGraph 状态、追问上限、退出条件和确认门 |
| 输出仅存在聊天记录中 | 输出校验为结构化 `GrowthReport` 并持久化 |
| 建议与真实行动脱节 | 用户确认后同步为 `PlanTask + Todo` |
| 下一轮不知道用户是否执行 | Todo 状态回写为阶段进度，Coach 再读取最新事实 |
| 很难解释模型做了什么 | Session、Checkpoint、Report、PlanTask、Todo 形成来源链 |

模型负责理解用户和生成建议；代码负责状态机、结构校验、持久化、幂等同步、权限隔离与人工确认。这个边界让系统即使出现模型超时或格式错误，也不会静默修改用户计划。

## 核心运行链路

```text
微信小程序
  pages / services / stores / normalizers
                │ HTTP / SSE / 文件上传
                ▼
FastAPI /api/v1
  ├─ Sandbox：多路径探索、比较、方向选择
  ├─ Growth：LangGraph 规划、报告、历史、Coach
  ├─ Today：课程、考试、Todo、计划同步、进度聚合
  └─ Memory：长期记忆提取、冲突与过期治理
                │
                ├─ SQLAlchemy → SQLite / PostgreSQL URL
                ├─ AsyncSqliteSaver → 对话 checkpoint
                └─ OpenAI-compatible LLM（可选）
```

黄金闭环在数据层的主链路：

```text
SandboxResult
  → GrowthSession
  → GrowthReport
  → TodayService.sync_growth_plan
  → PlanTask（来源与阶段映射）
  → Todo（用户实际执行）
  → get_plan_progress
  → Coach / Today suggestion
```

`PlanTask` 是 Growth 与 Today 之间的桥接表：它保留 `report/session/phase/task` 来源，支持阶段级幂等同步和进度聚合。用户删除 AI 计划任务时记录为 `cancelled`，避免执行证据直接消失。

## LangGraph 状态、退出条件与人工确认

规划主分支：

```text
router
  → planning_turn_analysis
  → [planning_knowledge]
  → planning_follow_up
  → planning_await_trigger
  → planning_analyze
  → END（展示初步分析，等待明确批准）

用户批准生成报告
  → router
  → planning_build_report
  → END
```

路径沙盘分支：

```text
sandbox_discovery
  → sandbox_projection
  → 用户选择最终方向
  → planning_follow_up
```

| 机制 | 当前实现 |
| --- | --- |
| 状态 | `GrowthState` 保存用户、会话、规划、沙盘、报告请求和错误状态 |
| 追问退出 | turn analysis 判断信息是否足够；`MAX_FOLLOW_UP_ROUNDS = 5` 只是硬安全上限 |
| 沙盘退出 | 沙盘到达 `completed`，生成 projection；用户选定方向后才 handoff |
| 报告确认 | 初步分析后图先 `END`；只有显式 `approve` 才进入 `build_report` |
| 会话持久化 | `AsyncSqliteSaver` 保存 LangGraph checkpoint，支持中断、恢复和服务重启 |
| 业务持久化 | 最终报告进入 `GrowthReport`；执行映射进入 `PlanTask` 和 `Todo` |

人工确认点包括：选择 2–4 条比较路径、选定最终方向、批准生成完整报告、选择阶段与开始日期后同步、接受 Coach 建议后创建 Todo。AI 不自动替用户改计划。

## 模型成本、延迟与失败回退

这里区分“代码已经具备的控制”与“真实评估已经记录的数字”，不把 timeout 当成真实延迟，也不猜测模型账单。

| 维度 | 当前状态 |
| --- | --- |
| 模型 | 默认 `deepseek-chat`，通过 OpenAI-compatible SDK 接入，可替换兼容服务 |
| 超时与重试 | 全局默认 timeout `30s`、SDK retry `1`；路径对比 `15s/0 retry`；单路径报告 `18s/0 retry`；Today 建议 `10s` |
| Token 上限 | 不同调用按用途设置 `300 / 512 / 1024 / 2048` 等 `max_tokens`，限制最坏输出规模 |
| 调用观测 | `LLMService` 采集功能名、模型、耗时、成功状态、错误类型和 token usage，不记录 prompt、响应正文或密钥 |
| 本次真实 eval 延迟 | 2026-08-20 记录未汇总端到端耗时、P50/P95，不能把配置的 timeout 写成实测延迟 |
| 本次真实 eval 成本 | 当次记录未保存可审计的 token 汇总，因此不公开猜测单次人民币成本 |
| 下一轮基准要求 | 按 feature 汇总调用次数、input/output token、单调用 P50/P95、整条链路 wall time，并用评估当日供应商单价计算成本 |

失败回退策略：

- 流式 SSE 没有收到事件时，小程序回退普通非流式接口，不重复已经成功的 mutation。
- 结构化 JSON 校验失败时，用 repair prompt 修复一次；仍失败则返回明确错误。
- 单路径模拟或比较超时、解析失败时，返回标记清楚的最小结构化 fallback，不伪装成真实模型评分。
- 未配置模型密钥时，课程、考试、Todo、导入等非 AI 能力仍可运行；AI 接口明确报错。
- Today 单个模块失败不会让整页数据不可用；Todo 乐观更新失败会回滚。
- Coach 只提出变更建议，创建新 Todo 必须由用户点击确认。

## 测试与评估

当前完整本地快照验证（2026-08-25）：`132 passed, 1 warning, 4 subtests passed`；前端契约、Python 编译和全部 `miniprogram-v2` JavaScript 语法检查通过。干净 CI checkout 不包含可选的山东公务员原始快照，对应 2 项数据集集成测试会明确标记为 skipped，其余 130 项照常执行。

```powershell
# 后端单元、契约与回归测试
.\venv\Scripts\python.exe -m pytest -q

# Python 编译检查
.\venv\Scripts\python.exe -m compileall -q backend

# 前后端共享 Fixture 契约
node .\tests\frontend_v2_contracts.js

# 小程序 JavaScript 语法
Get-ChildItem miniprogram-v2 -Recurse -Filter *.js | ForEach-Object {
  node --check $_.FullName
  if ($LASTEXITCODE -ne 0) { throw "JavaScript syntax check failed: $($_.FullName)" }
}
```

GitHub Actions 在 push 和 pull request 时运行 Python 3.11 测试、Python 编译检查及小程序 JavaScript 语法检查。CI 使用本地占位模型地址，不把“测试通过”伪装成真实模型验证；真实 LLM 评估单独记录。

## 快速开始

### 1. 安装后端

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

### 2. 配置模型（可选）

`backend/.env`：

```dotenv
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
LLM_TIMEOUT=30
LLM_MAX_RETRIES=1
```

不使用 AI 时保持 `DEEPSEEK_API_KEY=`。开发模板可创建演示账号 `demo2026` / `DemoPass123!`；生产环境必须关闭演示账号并替换 JWT 密钥。

### 3. 启动 API

```powershell
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

- Swagger UI：<http://127.0.0.1:8000/docs>
- 存活检查：<http://127.0.0.1:8000/health>
- 就绪检查：<http://127.0.0.1:8000/ready>

### 4. 运行微信小程序

1. 使用微信开发者工具导入仓库根目录；`project.config.json` 已指向 `miniprogram-v2/`。
2. 启动本地 API。
3. 开发环境默认请求 `http://127.0.0.1:8000`；如需临时覆盖，在控制台执行：

```javascript
wx.setStorageSync("ICAMPUS_V2_API_BASE_URL", "http://127.0.0.1:8000")
```

4. 重新编译并登录。模拟器可关闭合法域名校验；真机调试与发布必须使用设备可访问、已配置服务器域名的 HTTPS 地址。

### Docker

```powershell
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8000/ready
docker compose logs -f api
```

停止但保留数据：`docker compose down`。除非明确要删除本地数据，不要执行 `docker compose down -v`。

邀请制 Beta 使用 PostgreSQL 编排，迁移成功后 API 才会启动：

```powershell
$env:POSTGRES_PASSWORD = "replace-with-a-strong-password"
$env:DATABASE_URL = "postgresql+psycopg://icampus:replace-with-a-strong-password@postgres:5432/icampus"
$env:JWT_SECRET_KEY = "replace-with-at-least-32-random-characters"
$env:DEEPSEEK_API_KEY = "your-model-key"
$env:CORS_ORIGINS = "https://beta.example.com"
docker compose -f docker-compose.postgres.yml up --build -d
Invoke-RestMethod http://127.0.0.1:8000/ready
```

实际部署应从 Secret Manager 注入变量，不把上面的示例值写入仓库。完整范围与门禁见[邀请制 Beta 发布范围](docs/beta-release-scope.md)。

## 项目结构

```text
ai-agent-learning/
├─ miniprogram-v2/          # 当前微信原生小程序
│  ├─ pages/                # 今天、探索、行动、我的
│  ├─ pkg-growth/           # 沙盘、规划、报告、教练、历史
│  ├─ services/             # HTTP、SSE、上传封装
│  ├─ stores/               # 会话和领域状态
│  └─ normalizers/          # API → UI 数据契约适配
├─ backend/
│  ├─ app/api/v1/           # FastAPI 路由、鉴权、响应边界
│  ├─ services/             # Growth、Today、Memory、LLM 编排
│  ├─ planning/             # LangGraph 和四类规划策略
│  ├─ sandbox/              # 路径发现、模拟、比较、handoff
│  ├─ models/ + crud/       # SQLAlchemy 持久化
│  └─ career_data/          # 独立官方数据归档/解析管道
├─ tests/                   # 前端契约测试
├─ docs/                    # PRD、接口、部署、评估记录
└─ deliverables/            # UI 设计交付物
```

## 诚实的工程边界

- `career_data` 具备官方原文归档、哈希去重、版本和来源审计，但目前没有注册为 Agent 工具，也没有接入 RAG；不能声称规划建议已经使用该数据。
- `AsyncSqliteSaver` 适合当前单机演示；多实例部署需要共享 checkpoint 存储。
- OpenAI-compatible 客户端主体仍是同步调用，部分异步链路需要进一步隔离阻塞。
- 限流是进程内实现，不适合多实例全局配额。
- 生产主业务库已建立 PostgreSQL + Alembic 基线；开发/测试仍保留 SQLite 兼容启动逻辑。
- 有后端测试、契约测试和 JavaScript 语法检查，但没有完整的小程序 UI/E2E 自动化套件。
- 本 README 展示的是高保真设计稿；60 秒实机录屏尚未随仓库发布。
- 当次真实 LLM eval 没有形成可审计的成本和延迟分位数，下一轮应先补测量再做性能宣称。

## 30 秒面试介绍

> iCampus 是一个微信小程序和 FastAPI 组成的 AI 成长执行系统。我没有把重点放在四种 Agent，而是用 LangGraph、业务数据库和 Todo 系统串起一条闭环：用户先比较路径，再生成四阶段报告，确认后把任务同步到待办；真实完成状态会聚合成进度，再交给 AI 教练读取。真实模型评估跑通过“同步 3 项、完成 1 项、进度 33%、教练读取最新状态”。模型负责理解与文案，代码负责状态、退出条件、结构校验、持久化和人工确认。

## 仓库维护约定

现有 `master`、历史分支和 `backup-main-*` / `competition-freeze-*` 标签保留，不重写历史。完成默认分支迁移后只保留 `main`、`develop` 和语义化 Release（`vX.Y.Z`）；提交信息使用 `feat:`、`fix:`、`docs:`、`test:`、`refactor:` 等明确前缀，不再使用 `Backup updates` 一类不可追踪描述。

## 进一步阅读

- [真实模型端到端评估](docs/live-llm-e2e-evaluation-2026-08-20.md)
- [后端运行与 API](backend/README.md)
- [前端 API 对接](docs/frontend-api-reference.md)
- [V2 产品需求](docs/iCampus-PRD-v2.md)
- [邀请制 Beta 发布范围](docs/beta-release-scope.md)
- [部署与数据库迁移](docs/deployment-week1.md)
- [部署说明](docs/deployment-week1.md)
- [隐私说明](docs/privacy.md)
- [UI 与后端能力矩阵](deliverables/complete-design-v1-bento/backend-capability-matrix.md)

## License

[MIT](LICENSE) © 2026 iCampus contributors
