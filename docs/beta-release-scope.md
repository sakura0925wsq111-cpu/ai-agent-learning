# iCampus 邀请制 Beta 发布范围

## 发布目标

本分支只交付一条可审计的用户闭环：

```text
注册/登录
→ 成长规划对话
→ 用户确认并生成报告
→ 阶段任务同步为 Todo
→ 用户完成任务
→ 进度回写
→ AI 教练读取真实执行状态
```

## 范围冻结

Beta 期间允许：

- 修复黄金链路中的缺陷、安全问题和数据一致性问题。
- 增加部署、迁移、备份、监控和验收能力。
- 优化失败提示，但不改变已有 API 契约。

Beta 期间不允许：

- 合入 Study 文档、卡片生成或新的 Agent。
- 扩展新的业务页面、路径类型或自动执行动作。
- 将独立 `career_data` 管道宣传为当前 Agent 的 RAG/工具来源。
- 用本地 Mock、SQLite 单测或历史截图代替真实环境验收。

范围变化必须先更新本文档，再单独评估测试、迁移和发布风险。

## 数据库发布门禁

- `prod` 只接受 PostgreSQL URL。
- 生产应用启动不执行 `create_all` 或手写 DDL，只核对 Alembic revision。
- 发布任务必须先单独运行 `alembic upgrade head`，成功后才允许 API 接流量。
- 每次迁移在空库和临时数据库完成 upgrade/downgrade/upgrade 回归。
- 旧 SQLite 数据库不能直接执行初始迁移；必须先备份、核对结构，再决定迁移数据或人工 `stamp`。

## 当前仍未解决的生产边界

这次改造只完成主业务 PostgreSQL 和 Alembic 基线。以下项目完成前，不得宣称为多实例公开生产服务：

- LangGraph checkpoint 仍是持久卷上的 SQLite，只适合单 API 实例。
- 登录和 AI 限流仍是进程内状态。
- LLM 客户端仍可能阻塞异步请求路径。
- 监控告警、备份恢复、账号删除覆盖 checkpoint、真实 HTTPS 真机验收仍待完成。

## Beta 验收

1. CI 后端、前端契约和 PostgreSQL migration job 全绿。
2. 部署镜像只来自已提交的 release commit。
3. `/health`、`/ready` 成功，数据库 revision 为 Alembic head。
4. 两个独立账号完成黄金链路，不能读取彼此数据。
5. 重启 API 后报告、Todo、进度及对话恢复符合预期。
6. 备份恢复演练成功后，才开放给邀请成员。
