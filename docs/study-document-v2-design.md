

## 1. 目标与非目标

目标是把用户资料转换为有结构、有来源、能明确拒绝不支持内容的学习输入。
不是把整页 OCR 字符串加更多正则后称为安全知识。

- 复用 iCampus 账号、权限、上传和存储；不另做用户系统。
- 本轮 PDF 文本/扫描件选型；PPTX 通过同一契约的适配器接入，未经实测不宣称支持。
- 不生成 Card，不调用 LLM 改写/补全/OCR 纠错，不开发前端、知识图谱或多 Agent。
- 复杂公式、表格关系、图示推理第一版不作为可生成学习内容；仍保留原图区域和类型。
- 文本忠实性与原文知识正确性是两件事，本模块不替原作者纠正知识。
## 2. 冻结与变更边界

现有代码/测试/评估归档于 `backend/evals/parser_selection/2026-09-04/baseline/`。
归档包含未提交的 Study 改动，排除 .env、密钥、数据库、原始 PDF 和模型权重。
旧 `StudyDocumentUnit` 仍然是按页记录，不静默迁移其语义。新契约本轮只在实验输出中验证。

## 3. 三层职责

```
ParserAdapter → StructuredDocument → UnitAssembler → EligibilityPolicy
```

### ParserAdapter：恢复结构，不决定内容可用

原生文字与 OCR 均输出同一 StructuredDocument。采用成熟解析器的版面、阅读顺序、列表/层级识别，
不再由业务代码根据某个字符或页号识别一种特殊课件。
保存提供者原始 JSON，适配后信息不足即 unknown，不能给缺失字段猜一个值。

### UnitAssembler：形成逻辑内容单元

一个 Unit 是一个完整定义/正文段落，或含引导语与必要条目的完整列表；不是 PDF 页、OCR 行或 token chunk。
来源可以覆盖多个页面。跨页证据不足时仅标记 uncertain，不尝试语言补全。
标题可以提供上下文，不能单独作为知识 Unit。页眉、页码、图注、公式不混入正文字符串。
只按提供者结构组合原始片段，保留所有来源引用；不删掉坏行后拼出一个新结论。

### EligibilityPolicy：对所有输入使用同一判定

- usable：受支持的类型、结构闭合、必需子项齐全、来源有效、无未解决的识别/布局风险。
- uncertain：边界/父项/阅读顺序/文字可靠性不明。下游禁止使用。
- unsupported：明确属于公式、表格推理、图片理解等未支持能力。下游禁止使用。

解析器输出的 text 标签或高置信度本身不满足 usable。数值置信度属于提供者特定信号，不是事实概率。
usable 是当前契约的机器判定，不得标为“人工核验”或宣称绝对正确。

## 4. 统一数据契约（设计，不是本轮数据库迁移）

StructuredDocument:

- revision_id、source_sha256、parser_name/version/config_hash、完整性状态。
- pages：1-based 页码、页尺寸。
- blocks：id、type、raw_text、parent_id、children、reading_order、source_spans、signals。
- type：heading / paragraph / list / list_item / table / formula / figure / caption / furniture / unknown。
- source_spans：page_number、bbox（0..1、左上原点）、block 内字符范围；OCR 来源显式标记 transcription。
- signals：文字提取方式、原始 OCR/版面置信度（可空）、边界和来源可用性。不同维度不取平均掩盖坏项。
- provider_raw：原始结果文件与 hash，避免仅保存丢失层级的 Markdown。

DocumentUnit V2:

- unit_id、revision_id、kind（paragraph/list）、context_block_ids、required_block_ids。
- content：仅由来源片段组成，顺序可审计，任何省略不得改变列表或句子完整性。
- source_spans[]：可以多页；page_number 不再唯一决定 Unit 身份。
- completeness：complete / unknown / incomplete。
- disposition：usable / uncertain / unsupported。
- reasons[]、assessment_version。丢失必需子项拒绝整个 Unit。

基本不变量：

1. usable Unit 引用的每个来源页和 block 必须存在，坐标和字符范围合法。
2. 不允许来源外的字符补全；白空格规范化必须有明确映射。
3. 列表必须保留引导语和其必需条目；不能仅保留识别成功的子项。
4. unsupported/uncertain 子项若为 Unit 必需内容，则父 Unit 不能 usable。
5. 原生 PDF、扫描 PDF、后续 PPTX 均使用相同判定，不能 native 直接 accepted。
6. 对跨页未知、缺失结构、未覆盖区域，记录并拒绝；不是悄悄忽略。
7. 原始资料里的命令文字只作为文档内容，不执行，不进入系统指令。

## 5. 候选与本轮固定实验边界

候选 A：Docling 标准 PDF pipeline + RapidOCR（中文），不用 VLM/公式补全。
候选 B：PaddleOCR PP-StructureV3 的版面/阅读顺序 + 中文 OCR，关闭公式/图表生成解释。

候选在独立虚拟环境中运行。依赖下载不等于向第三方上传课件；本轮仅本地推理。
记录 CPU、线程、版本、模型、预处理、冷启动与转换时间。不同 OCR/输入路径是配置差异，不能把速度差全归因于版面模型。
统一输出比较：类型、层级/列表、阅读顺序、来源覆盖、公式/图片隔离、完整段落和内容忠实性。
若一个候选不暴露某字段，明确缺失，不用手写推断偷偷补齐后再评分。

## 6. 样本划分和预注册检查

开发样本（已反复调试过，不作为新样本）：

- 企业战略管理：第 10–11 页，观察整合营销跨页；第 18–19 页，观察括号和列表跨页。
- 土力学：第 20 页文字+示意图，第 100 页照片+标签，第 160/400 页公式和说明混排。

额外工程留出样本：选择一个此前未用于本项目规则调试的公开 CC BY 文档，选页与期望结构在推理前登记。
这是项目层面的未调试样本，不是模型训练集排除证明；公开文档也不能代替新的真实中文用户资料。

本轮检查（先固定，再运行候选）：

- 所有输出 block 有有效页码/bbox；缺失统计，不凭空补。
- 标题、正文、列表、图/表/公式类型不能被统一压平；公式识别能力单列实测。
- 整合营销定义若合并，必须同时具备第 10、11 页来源；未合并则不得声称单页段落完整。
- 文本/图片混排的正文不应混入图内变量；检测不出时记失败，不提高阈值掩盖。
- 至少保留可对照的正文和列表，不能全拒绝而宣称准确率 100%。
- 此轮小样只筛选架构适配性，不声称达到生产准确率。

晋级要求（后续才执行）：至少 5 份不同真实资料，冻结不少于 2 份新文档作为留出集；
放行内容由独立人工按原图标注，统计完整 Unit 精确率、字符错误率、完整列表召回、公式误放行和来源覆盖。
核心错误为 0 才能继续；准确率同时报告样本量与置信区间。200 个独立放行 Unit 全对时，
Wilson 95% 区间下界仍只有约 98.1%，不能宣传未来资料 100% 正确。

## 7. 接入路径（本轮不执行）

保留当前上传/API/账号。以新解析 revision 存放 StructuredDocument 和 V2 Units，旧页记录只作基线。
先影子运行比较，不改 `/parse` 默认行为；候选达到契约后整体切换文档处理层。
全书后台处理、并发、恢复和部署性能在质量选型之后验证；本轮不把几个代表页速度外推为 429 页可用证明。

## 8. 官方依据

- DoclingDocument 结构、层级、阅读顺序、来源：https://docling-project.github.io/docling/concepts/docling_document/
- Docling 置信度维度：https://docling-project.github.io/docling/concepts/confidence_scores/
- Docling OCR/安装：https://docling-project.github.io/docling/getting_started/installation/
- PP-StructureV3 模块、结构输出与开关：https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html

这些文档支持候选能力说明，不证明在用户资料上的准确率。实测结果另存于 parser_selection 目录。

## 9. 第一轮决定

见 `backend/evals/parser_selection/2026-09-04/README.md`。两候选均完成 8 个案例、10 页。
Docling 优先进入实验适配，因为它保留完整文档树和可传递的来源/类型关系；不是认定其所有段落已完整准确。
两者的跨页闭合、中文列表层级、行内公式和转写忠实性仍有未通过项，因此不替换当前服务、不生成 usable 业务 Unit。
候选结构必须通过统一 UnitAssembler/EligibilityPolicy 进行下一阶段验证，不恢复原先 native 直通 accepted 的路径。

- 复用 iCampus 账号、权限、上传和存储；不另做用户系统。
- 本轮 PDF 文本/扫描件选型；PPTX 通过同一契约的适配器接入，未经实测不宣称支持。
- 不生成 Card，不调用 LLM 改写/补全/OCR 纠错，不开发前端、知识图谱或多 Agent。
- 复杂公式、表格关系、图示推理第一版不作为可生成学习内容；仍保留原图区域和类型。
- 文本忠实性与原文知识正确性是两件事，本模块不替原作者纠正知识。
