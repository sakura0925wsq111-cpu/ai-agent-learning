# iCampus 版本导航

## 日常 Gizmo 开发

- 分支：`codex/gizmo-dev`
- 本地目录：`D:\ai-agent-learning`
- 默认小程序：`miniprogram-v2/`，由根目录 `project.config.json` 指定。

这里持续开发 Study/Gizmo，包括资料上传、知识点提取、审核和选择题生成。

## 竞赛冻结版

- 分支：`release/competition-2026-08-21`
- 固定标签：`competition-freeze-2026-08-21`
- 本地目录：`D:\ai-agent-learning-competition`

竞赛提交从这个目录取，不在该目录进行日常开发。

## 前端 V1

- 分支：`frontend-v1`
- 固定标签：`frontend-v1-preserved-2026-09-16`

V1 保留用于回溯。当前默认入口仍是 V2，不应修改根目录项目配置来切换默认前端。

## Beta 部署线

- 分支：`codex/launch-p0-batch1`
- 本地目录：`D:\ai-agent-learning-beta`

Beta 部署和安全修复独立维护，不能混入竞赛冻结版或 Gizmo 开发提交。
