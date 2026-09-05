# iCampus 文档解析器第一轮选型验证

日期：2026-09-04。**推荐 Docling 作为下一轮统一结构底座候选，但本轮不批准替换现有运行路径。**
这是能力/结构的试验性比较，不是已达 98%/100% 正确率的验收。

## 已交付

- 统一设计：仓库 `docs/study-document-v2-design.md`。
- 不可变基线：`baseline/code_and_evaluations.zip`，39 个代码、配置模板和既有评估文件。
- 基线归档 SHA-256：`d81ca03d4dc179d4af82d2bdb940d83193a7937de4aa50dce181e79099d506c7`。
- 推理前登记的案例：`corpus.json`，8 个案例、3 个来源、合计 10 个页面。
- 两候选原始 JSON、归一化结果、配置、依赖和耗时：`docling_run1/`、`paddle_run1/`。
- 输出核验：`structural_audit.json`；具体优点/缺陷与原始结果定位：`review_findings.json`。

## 样本与边界

开发样本是已经调试过的两份用户资料：企业战略管理第 10–11、18–19 页；土力学第 20、100、160、400 页。
额外第 3、5 页来自公开论文 *Docling: An Efficient Open-Source Toolkit for AI-driven Document Conversion*（Livathinos 等，2025）：
https://arxiv.org/abs/2501.17887 ，PDF：https://arxiv.org/pdf/2501.17887v1 ，CC BY 4.0。
它提供双栏、表格、图文混排的新结构样本，但由候选作者发表、可能进入其训练集，且不是中文课件；不能作为最终无偏留出验收。
公开参考 PDF 保留于 `public_reference/docling_2501.17887v1.pdf`，许可链接：https://creativecommons.org/licenses/by/4.0/ 。
原 PDF 未修改；本目录的机器提取结果是该文档的转换产物。

这些参考检查由助手对原图和输出进行核对，不是独立专家人工标注。没有完成全字符 CER 或完整 Unit 精确率统计。
两份用户 PDF 未复制进仓库、未修改，也没有上传给在线解析服务。

## 实验配置

| 项目 | Docling | Paddle PP-StructureV3 |
| --- | --- | --- |
| 包版本 | Docling 2.125.0，docling-core 2.94.1 | PaddleOCR 3.7.0，PaddlePaddle 3.3.1，PaddleX 3.7.2 |
| 结构模型 | 默认 docling-layout-heron | PP-DocLayout_plus-L |
| OCR | RapidOCR 3.9.2，实际默认 PP-OCRv6 small ONNX | PP-OCRv5 mobile |
| 原生文字处理 | 使用 PDF 文字层，必要时 OCR | 本配置逐页 200 DPI 渲染并 OCR |
| 加速配置 | CPU，Docling 4 线程 | CPU，4 线程，MKL-DNN 关闭 |
| 生成式处理 | 未启用公式/VLM/图片说明 | 未启用公式/表格/图表识别等可选子模块 |
| 业务 Unit | 均不生成 usable Unit，只输出结构候选 | 同左 |

机型为 AMD Ryzen 7 7840H（8 核/16 线程），Windows、Python 3.11.6。
两候选进程部分重叠运行，且 OCR 与输入路径不同，以下耗时只代表本轮配置的观测，不是严格同算力性能排名。

## 实测概况

| 案例 | 页数 | Docling 秒 | PP-StructureV3 秒 |
| --- | ---: | ---: | ---: |
| 中文笔记跨页定义 | 2 | 3.63 | 64.89 |
| 中文笔记跨页列表 | 2 | 2.61 | 52.04 |
| 扫描中文+示意图 | 1 | 6.08 | 8.02 |
| 照片+文字标签 | 1 | 5.08 | 6.27 |
| 显式公式 | 1 | 3.43 | 7.93 |
| 行内公式 | 1 | 5.06 | 7.74 |
| 英文双栏 | 1 | 1.74 | 53.70 |
| 表格+图形 | 1 | 5.21 | 47.18 |
| 合计（不含初始化） | 10 | 32.85 | 247.75 |

初始化分别约 72.02 秒和 71.88 秒，包含首次所需模型准备；包安装耗时未计入。
两者均完成 8/8 案例。Docling 完整树导出 290 个内容节点，Paddle 导出 169 个高层区域，粒度不同，不能比较节点数量判断质量。
已导出节点的页码/bbox 检查均通过；完整树引用检查无重复 ID、悬空引用或父链环。
这些通过只证明结构能引用，不证明结构或文字本身正确。

## 为什么优先 Docling

1. 同一 DoclingDocument 保留原生与扫描页面的内容、类型、阅读顺序、列表容器和来源坐标。
2. 图内文字、表格内部文字仍通过父节点归属于图片/表格，后续统一契约能按祖先类型排除；不需要靠 `P1` 或希腊字母猜测其身份。
3. 在土力学第 20 页，结尾两行说明成为一个完整正文区域，图内三相标签保持在 picture 子树中。这比压平成 OCR 行字符串更适合作为结构底座。
4. 原生 PDF 不必全部重新 OCR，保留原始文字层信息。

这是架构适配性选择，不是声称 Docling 已达到可靠知识提取标准。Paddle 保留作比较候选，不默认把两套解析器串联堆成更复杂的主链路。

## 尚未通过的切换门

- **跨页完整性**：两个候选都保留了跨页碎片，没有证明整个定义或列表完整。不能因标签是 paragraph/text 就放行。
- **中文层级**：Docling 的 list 容器有时把多个小节及条目放到同一个组中；存在父子树不代表逻辑层级已正确。
- **内嵌公式**：第 400 页带公式的说明在 Docling 中是 list_item，在 Paddle 中是 text，两者转写都丢失/误表示符号。仅过滤 formula 类型仍会漏。
- **文字忠实性**：Docling 第 100 页文字重复；Paddle 第 20 页正文附带多余 `i`。成熟解析器也不能自动免除质量验证。
- **新资料验证不足**：只有一份额外英文、提供者自发表文档，不构成最终真实中文留出集。
- **PPTX/完整大文件**：本轮未测试，不能外推已支持或 429 页可稳定运行。

因此当前决定为 `prefer_docling_for_next_prototype / no_production_switch`。
下一轮应按统一契约实现 UnitAssembler/EligibilityPolicy 的实验适配并做独立留出验收，不再给当前逐行过滤添加页号或短语补丁。

## 数据完整性说明

Docling 最初 `iterate_items()` 默认未遍历 picture 子节点，`normalized.json` 是初始适配结果。
检查原始 JSON 后通过完整树重新导出 `normalized_full.json` 和 `summary_full.json`；没有重跑模型或改写原始识别内容，旧文件也未覆盖。
最终 Docling 结构统计以 full 文件为准。此处修正的是实验导出器信息遗漏，不是候选算法改进。

`structural_audit.json` 已确认冻结的 39 个基线文件 hash 全部未变，主项目 venv 包版本未变。
实验环境仅在 `tmp/parser-selection/docling-venv` 和 `paddle-venv`，未更改后端 requirements 或现有服务入口。
原后端回归重新运行：160 passed、1 warning、4 subtests passed；该数字验证基线没有被实验改坏，不是候选解析准确率。
主环境及两个实验环境的 `pip check` 均通过。PDF 视觉检查的临时 PNG 已清理，原始结果和公开来源 PDF 保留。

## 复现入口

在独立环境安装对应固定包（完整依赖版本见各自 environment.json）：

```powershell
python -m pip install "docling[rapidocr]==2.125.0" --extra-index-url https://download.pytorch.org/whl/cpu
python -m pip install "paddleocr[doc-parser]==3.7.0" "paddlepaddle==3.3.1" "PyMuPDF==1.28.2"
```

用对应环境 Python 运行 `backend/evals/parser_selection/run_candidates.py`：

```text
--candidate docling|paddle
--user-source-dir <两份原课件所在目录>
--public-source <公开论文PDF路径>
--output-dir <新的不可覆盖目录>
```

`reexport_docling.py` 只对已保存的提供者输出做完整树映射；`audit_results.py` 验证结构引用和基线未改变。
原始课件依据 SHA-256 校验，文件名不是唯一身份。使用新目录重跑，禁止覆盖本轮结果。

## 官方资料

- Docling 结构：https://docling-project.github.io/docling/concepts/docling_document/
- Docling OCR 与安装：https://docling-project.github.io/docling/getting_started/installation/
- Docling 置信度：https://docling-project.github.io/docling/concepts/confidence_scores/
- PP-StructureV3：https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html

官方能力说明与本报告实测结论分别保留，不把宣传指标写成本项目实测结果。
