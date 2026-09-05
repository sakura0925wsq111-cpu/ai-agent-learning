# 段落级放行修复验收

日期：2026-09-04。范围仅为 OCR 原始行分组与整段放行，不包含 Card/LLM/前端开发。

## 基线与方法

- 原始文件：土质土力学2026st.pdf，429 页，162131977 字节。
- PDF SHA-256：`e5d7c7dcb4b291be5cb279760b9907062bbf0247cdcea99428d655a56a69ade9`。
- 原始机器评估：`../soil_mechanics_2026_20_page/machine_pages.jsonl`，未覆盖。
- 基线 JSONL SHA-256：`ac4f4cb1daeae7ddd4f76d2919c5501e3ca5f085d8e945d1c7377e8d09e938f1`。
- 本目录 `comparison.jsonl` 是对冻结的逐行决定追加段落规则，不重新 OCR、不升级原先已拒绝的行。
- 旧基线未保存未匹配的第二次 OCR 文字框，因此回放不等同于当前完整流水线重跑。
- 新的完整流水线实测另存于 `../paragraph_gate_v1_live/`，只重跑第 160、400 页。

## 修复规则

1. 基于未删减的 OCR 框，先连接同一文字行的相邻片段，再按字号、行距、列对齐和列表/句末边界组成来源段落。
2. 低置信度、公式、噪声行都参与分组；不能先删掉它们再组合好行。
3. 第二次 OCR 独有的行保留为拒绝记录，防止主识别遗漏关键行后剩余部分通过。
4. 同段任意来源行被拒绝，整段拒绝，记录 `paragraph_member_rejected`；括号和上下文起始检查改在完整段落上执行。
5. 保留原始行及 `line_decision`、`line_reasons`、`paragraph_id`、`paragraph_decision`、`paragraph_reasons`。
6. 不同通过段落之间使用空行分隔，不补字、不修公式。

## 冻结基线回放结果

| 指标 | 修复前 | 追加段落规则后 |
| --- | ---: | ---: |
| 放行 OCR 块 | 74 | 47 |
| 拒绝 OCR 块 | 210 | 237 |
| partial 页 | 16 | 14 |
| rejected 页 | 3 | 5 |
| 原基线识别失败页 | 1 | 1 |

数量下降是更保守的筛选结果，不是准确率提升的量化证明。附近的噪声也可能使正确段落一起被拒绝。

## 第 160、400 页重新识别

实测使用 200/240 DPI 双次 PP-OCRv5 mobile，CPU，总耗时 35.449 秒，含首次模型加载。

- 第 160 页：`基底压力呈梯形分布时，基底附加` 与后续 `压力pomax，P0min为` 同组，整段拒绝；不再单独放行第一行。
- 第 400 页：上部跨行、混有公式的说明段整体拒绝；`破坏振` 与后续 `次1gNf` 同组拒绝。
- 两页原始 OCR 文本仍保留；最终仅保留独立标题/图中阶段名称等其他通过来源组。
- 本轮对这两页进行了助手视觉核验，确认上述续行关系；不是用户或领域专家的独立人工准确率标注。

## 边界

- 分组是保守版面启发式，不是已证明的语义完整性判定。
- 未解决两次 OCR 都漏掉同一行、稳定漏字、单独的变量误识别等问题；例如旧第 40 页疑似漏字仍需另行核对。
- 标题和图示标签过滤不是本次修改范围；保留它们不代表可以生成有用 Card。
- 本轮未重新跑完整 20 页 OCR，也未完成 20 页逐页独立人工标注，不报告 98% 或 100% 准确率。

## 复现

在仓库根目录设置 `PYTHONPATH=backend` 后：

```powershell
.\venv\Scripts\python.exe -m pytest backend/tests/test_study_extraction_quality.py backend/tests/test_study_foundation.py -q

.\venv\Scripts\python.exe -m evals.study_paragraph_replay --source <原始PDF路径> --baseline-dir backend/evals/study_ocr/soil_mechanics_2026_20_page --output-dir <新的回放目录>

.\venv\Scripts\python.exe -m evals.study_ocr_evaluation --source <原始PDF路径> --pages 160,400 --output-dir <新的实测目录>
```

评估输出目录不可复用覆盖；新实测 manifest 保留质量规则版本和相关源代码 SHA-256。
