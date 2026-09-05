# 第一周部署与演示说明

## 1. 配置约定

后端只从进程环境变量和 `backend/.env` 读取配置。先复制模板：

```powershell
Copy-Item backend/.env.example backend/.env
```

三种环境使用相同代码，通过 `APP_ENV` 区分：

- `dev`：本机 SQLite、允许调试、可启用演示账号。
- `test`：测试服务器，建议 PostgreSQL，使用测试域名 CORS 白名单，可启用演示账号。
- `prod`：生产环境。必须使用 PostgreSQL；`JWT_SECRET_KEY`、`DEEPSEEK_API_KEY`、明确的 `CORS_ORIGINS` 必填；`DEBUG` 和演示账号必须关闭，否则进程启动失败。

不要把 `backend/.env`、数据库文件、密钥或密码提交到 Git。

## 2. 本地启动（dev）

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
Set-Location backend
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

默认模板启用本地演示账号 `demo2026 / DemoPass123!`。账号只会在 dev/test 首次启动时创建，生产配置会拒绝启用它。

微信小程序根据微信版本自动选择 `miniprogram/config/env.js` 中的地址：开发版使用本地地址，体验版使用 test 地址，正式版使用 release 地址。体验/正式版部署前必须替换示例 HTTPS 域名，并在微信公众平台配置 request/uploadFile 合法域名。开发者可通过微信存储键 `API_BASE_URL` 临时覆盖开发版地址。

## 3. Docker 本地运行

仓库根目录的 Compose 配置默认使用 SQLite，无需大模型密钥即可启动并访问非 AI 接口：

```powershell
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8000/ready
```

镜像以非 root 用户运行。SQLite 与运行数据写入 `/app/data`，日志写入 `/app/logs`，分别由 `icampus-data` 和 `icampus-logs` 卷持久化。`docker compose down` 会保留卷；不要在仍需数据时执行 `docker compose down -v`。

如需 AI 功能，在启动前通过进程环境变量注入 `DEEPSEEK_API_KEY`。镜像和 Compose 文件均不保存真实密钥。Compose 的默认 JWT 值仅用于本地 dev，生产环境必须设置独立的高强度 `JWT_SECRET_KEY`。

## 4. 测试环境（test）

建议使用 PostgreSQL，最小配置示例：

```env
APP_ENV=test
DEBUG=false
DATABASE_URL=postgresql+psycopg://icampus:strong-password@postgres:5432/icampus_test
JWT_SECRET_KEY=<至少32位随机值>
DEEPSEEK_API_KEY=<测试环境密钥>
CORS_ORIGINS=https://test.example.com
DEMO_ACCOUNT_ENABLED=true
```

启动：

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
Set-Location backend
..\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

探针：负载均衡存活检查使用 `GET /health`；接流量前使用 `GET /ready`。`/ready` 会执行数据库 `SELECT 1` 并核对关键配置。`REDIS_URL` 当前仅为可选配置，不会因 Redis 未部署而阻止就绪。

## 5. 生产环境（prod）

```env
APP_ENV=prod
DEBUG=false
DATABASE_URL=postgresql+psycopg://icampus:<password>@postgres:5432/icampus
JWT_SECRET_KEY=<至少32位、独立生成的随机值>
DEEPSEEK_API_KEY=<生产密钥>
LLM_MODEL=deepseek-chat
CORS_ORIGINS=https://app.example.com
DEMO_ACCOUNT_ENABLED=false
```

推荐在进程管理器或容器中注入变量，不生成含密钥的镜像层。首次启动 API 前必须先执行迁移：

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini current
```

生产 API 启动时只核对数据库是否位于 Alembic head，不自动建表或修改表。如果迁移未执行，启动会直接失败。

## 6. 数据库与迁移边界

SQLAlchemy URL 支持 SQLite 和 PostgreSQL（`psycopg` 驱动已列入依赖）。开发和测试环境暂时保留 `Base.metadata.create_all()` 与旧 SQLite 兼容逻辑；生产环境的结构变更只允许通过 `backend/alembic/` 中的版本迁移完成。

新 PostgreSQL 数据库直接执行 `upgrade head`。已有 SQLite 数据库不能直接运行初始迁移，否则会因表已存在而失败；必须先备份并核对实际表、列、索引和约束。只有确认结构与 `20260905_0001` 完全一致时才能人工 `stamp`，否则应编写数据迁移脚本导入一个由 Alembic 创建的空 PostgreSQL 数据库。

仓库提供 `docker-compose.postgres.yml`，其 `migrate` 服务成功后 API 才会启动。运行前必须从环境或 Secret Manager 提供 `POSTGRES_PASSWORD`、`DATABASE_URL`、`JWT_SECRET_KEY`、`DEEPSEEK_API_KEY` 和 `CORS_ORIGINS`。

## 7. 演示验收顺序

1. `/health` 与 `/ready` 均返回成功。
2. 使用演示账号登录。
3. 上传不超过 10 MB 的 PDF 课表或 `.xlsx` 考试表，预览并确认；重复点确认不会重复写入。
4. 今日页确认课程、考试、待办可见。
5. 完成成长规划或路径比较，生成报告，把阶段任务同步到今日待办。
6. 完成一项待办，再请求今日 AI 建议，确认建议包含成长执行进度。

## 8. 回滚与观测

- 代码回滚不删除数据库；导入只覆盖当前用户同来源的导入记录，不碰手工课程/考试。
- AI 日志包含 `user_id`、功能、模型、耗时、成功状态、错误类型和可用的 token 用量，不记录提示词、密钥或完整响应。
- 进程内登录/AI 限流适合单实例测试环境。多 worker/多实例生产部署应把 `core/rate_limit.py` 的存储替换为 Redis；接口边界已独立保留。
