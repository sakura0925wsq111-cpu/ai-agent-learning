# iCampus V1 / V2 并列版本使用说明

仓库按分支维护两套微信小程序前端，共用向后兼容的 `/api/v1` 后端。`master` 只保留后端；切换到对应前端分支即可得到完整的可导入工程。

| 版本 | 前端目录 | 微信开发者工具项目配置 | 默认状态 |
|---|---|---|---|
| V1 原版 | `frontend-v1` 分支的 `miniprogram/` | `project.config.json` | 保持原入口、原 TabBar、原存储键 |
| V2 重构版 | `frontend-v2` 分支的 `miniprogram-v2/` | `miniprogram-v2/project.config.json` | 独立路由、四 Tab、自定义 TabBar、独立存储键 |

## 打开方式

先在仓库根目录切换分支，再在微信开发者工具中导入对应目录：

```powershell
git switch frontend-v1
# 导入 D:\ai-agent-learning，使用根目录的 project.config.json

git switch frontend-v2
# 导入 D:\ai-agent-learning\miniprogram-v2，使用该目录内的 project.config.json
```

`frontend-v2` 分支同时保留根目录的 `project.v2.config.json`，供支持指定配置文件的脚本使用；微信开发者工具日常开发推荐直接导入 V2 目录。

## 本地联调

后端仍按原方式运行：

```powershell
& .\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

V2 开发版默认请求 `http://127.0.0.1:8000`。也可以在 V2 的“我的 → 设置 → 开发调试”中单独修改地址。该值写入 `ICAMPUS_V2_API_BASE_URL`，不会覆盖 V1 使用的 `API_BASE_URL`。

V2 的 token、用户、城市、设置与沙盘/规划恢复状态全部使用 `ICAMPUS_V2_*` 存储键，不会清除或覆盖 V1 登录状态。

## 兼容后端改动

- Today 天气与独立天气接口共用城市解析和天气映射；城市解析失败时 Today 返回 `weather=null`。
- `POST /api/v1/today/sync-plan` 新增可选 `start_date`。旧前端不传时保持原行为。
- 未新增 `/api/v2`，未修改数据库表，未删除旧接口。

## 验证命令

```powershell
& .\venv\Scripts\python.exe -m pytest -q
node .\tests\frontend_v2_contracts.js
```

前端契约测试读取与后端相同的正式 Fixture，重点检查信封/原始响应差异、文字时间推演、1–10 分矩阵、0–1 完成率和旧报告降级。
