# 整批知识点选择题：后端联调说明

## 启动与接口

接口前缀 `/api/v1/study`，均沿用 Bearer 登录认证与 `APIResponse.data` 包装。

- `POST /knowledge-runs/{knowledge_run_id}/choice-question-runs`：无请求体，返回 202。仅处理该任务下 `usable` 且未删除的全部知识点，不要求 confirmed。没有有效知识点返回 409。
- `GET /choice-question-runs/{question_run_id}`：查询进度。
- `GET /choice-question-runs/{question_run_id}/questions?page=1&page_size=20`：分页获取已保存题目，page_size 上限 100。
- `GET /choice-question-runs/{question_run_id}/questions/{question_id}`：单题详情。

启动和进度响应的 data 包含 `question_run_id`、`knowledge_run_id`、`status`、`total_knowledge_count`、`processed_count`、`generated_count`、`skipped_count`、`error_count`、`first_question_id`、模型与提示词版本及时间戳。启动响应另通过 `reused` 标记是否复用。

前端轮询时，只要 `first_question_id != null` 就可进入第一题，包括任务已经 completed/partial 的情况；后续继续分页取题。`ready` 表示已有题目且后台还在处理；`completed` 表示全部处理完（可能有跳过甚至零题）；`partial` 表示有批次错误但已有题；`failed` 表示失败且没有生成题目。零题时展示无可用题提示。

`options` 是按 A、B、C、D 顺序排列的四项字符串，`correct_option` 为 A/B/C/D。按 MVP 要求直接下发正确答案，在前端本地判题。题目 position 对应输入快照位置，跳过会产生间隔，不应把 position 当成连续题号。

## 持久化和生成规则

新增 `study_choice_question_runs` 与 `study_choice_questions` 两表。应用 `init_db()` 创建新表，并调用可重复执行的 `migrate_study_choice_questions(engine)`；旧卡片表不变。

启动时保存全部输入的 content、version、source_refs 和 source_usage 快照。request_key 由知识点任务、按 ID 排序的 ID/version、提示词版本和配置模型组成，数据库唯一索引防止重复任务。每个任务的知识点 ID 也有唯一约束。

沿用项目 `llm_service` 和 `LLM_MODEL` 配置，单批最多 10 条；模型只返回候选片段和干扰项，网络/JSON错误最多重试一次。程序检查精确 offset、长度、比例、停用词、白名单角色、重复答案、剩余上下文、四选项去重、干扰项不在正文及数字格式。候选依序最多检查三条，取首条通过者。每批提交，跳过原因写入 run.audit.outcomes。

解析由正确答案、知识点原句和已有来源页码组成。用户修改后的正文仍保留 source_usage=reference_only，来源页码只作参考。

## 验证边界

出题提示词已升级为 `choice-source-v2`：模型只选择原文答案文本和干扰项，保留答案角色等元信息，不再计算 offset。程序在快照正文中精确搜索唯一出现的答案，计算并保存 answer_start/end；不存在或重复出现（含重叠匹配）则尝试下一个候选。定位不使用模糊匹配、去空格或大小写转换，其他硬校验保持执行。版本变化会创建新任务，旧版本题目保持原有快照。

自动化测试使用受控模型响应和 SQLite，覆盖 API 鉴权、分页、快照、版本复用、批次重试与部分成功、坏候选过滤和数据库唯一约束。尚未进行真实提供方调用、PostgreSQL 运行验证或人工核心信息标注验收。

“是否值得记忆”“同领域语义和语法是否匹配”“挖空后是否自然可理解”只能由提示词引导及人工验收评估，硬规则不构成语义正确性的证明。仍需按需求标注 30 条跨类型样本，检查至少 85% 挖空位置属于核心信息。

执行采用现有 FastAPI BackgroundTasks 模式：批次结果持久化，但不具备进程崩溃后的自动续跑。部署重启可能使 processing/ready 任务停留；正式需要跨重启恢复时，应接入持久任务队列和租约恢复。MVP 完成、partial 和 failed 的相同 request_key 都复用现有任务，不提供手工强制重试接口。
