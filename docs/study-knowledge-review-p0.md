# Study 知识点审核 P0

所有路径位于 `/api/v1/study`，需要登录，响应沿用 `APIResponse`，业务数据位于 `data`。

## 接口

| 方法 | 路径 | 参数 |
| --- | --- | --- |
| GET | `/knowledge-runs/{run_id}/knowledge-units` | `disposition`、`review_status`、`deleted=active/deleted/all`、`page=1`、`page_size=50`（最多 100） |
| GET | `/knowledge-units/{id}` | 包含已删除条目的详情，便于恢复 |
| PATCH | `/knowledge-units/{id}` | `{"content":"当前正文","confirm":true,"version":1}` |
| POST | `/knowledge-units/{id}/confirm` | `{"version":1}` |
| POST | `/knowledge-units/{id}/unconfirm` | `{"version":1}` |
| DELETE | `/knowledge-units/{id}?version=1` | 软删除，返回更新后的详情 |
| POST | `/knowledge-units/{id}/restore` | `{"version":1}` |
| POST | `/knowledge-runs/{run_id}/confirm` | `{"items":[{"id":"知识点ID","version":1}]}`，1–100 条，不可重复 |

列表返回 `units`、筛选后的 `total`、`page`、`page_size`，以及当前 run 未受筛选影响的 `statistics`：`active_count`、`pending_count`、`confirmed_count`、`deleted_count`。pending/confirmed 统计均排除已删除条目。

修改接口默认 `confirm=false`，正文限 1–5000 字符并拒绝纯空白；其他字段不可写。确认只允许未删除的 usable 条目。编辑非 usable 条目不会改变其机器状态，也不能同时确认。已删除条目需先恢复再编辑；恢复后为 pending。每次成功操作版本加 1。

详情保留原有来源及机器元数据，并增加 `original_content`、`review_status`、`confirmed_at`、`updated_at`、`deleted_at`、`version`、`is_edited`、`source_usage`。`is_edited` 比较当前正文与首次正文；为 true 时 `source_usage=reference_only`，引用仅表示参考位置。未编辑时为 `extraction_evidence`，不额外承诺提取结果是精确原文。

不存在或非本人资源统一 404；过期版本返回 409「内容已更新，请刷新后重试」；不可执行的状态变更返回 409；请求格式、正文或批量大小不合法返回 422。批量确认失败会回滚全部更新。

## 持久化与迁移

当前分支沿用 `database.session.init_db()` 启动迁移，新增迁移模块为 `database.study_review_migration`。历史记录回填 original_content=content、pending、version=1、updated_at=created_at；重复启动保留用户修改。新建记录通过 ORM 默认值保存首次正文及待确认状态。

重新提取使用现有 `/documents/{document_id}/knowledge-runs`，请求 `{"force":true}`；创建新 run，旧 run 的审核结果继续保留。

## 下游入口

`services.study_review.learning_knowledge_query(db, user_id, run_id=None)` 同时应用资料所有权及 `usable + confirmed + deleted_at IS NULL` 条件。未来卡片、测验生成应复用此查询。本次未新增生成流程。

## 验证

`venv/Scripts/python.exe -m pytest backend/tests/test_study_review.py -q`

覆盖 API 完整审核、落库结果、来源保留、分页统计、跨账号隔离、版本条件更新竞争、批量失败回滚、重新提取保留旧编辑，以及历史迁移和重复运行。测试使用 SQLite；PostgreSQL 实例运行和生产库迁移尚未验证。
