# 学习知识点识别与拆分：第二轮方法调研

日期：2026-09-05。范围：官方资料/公开代码核验与方案选择；未在本轮调用模型提取用户资料，未修改业务代码。

## 结论

优先验证“结构化文档 + 原文定位的语义抽取”。新增重点是 LangExtract 的受约束原文抽取方法；
保留上轮实测 Docling 作为结构化输入基线，增加 MinerU pipeline 作为扫描课件/行内公式定位候选。
不是同时叠加所有解析器。识别层可替换，知识点层遵守同一来源与完整性契约。

目前没有证据证明任何一个候选已在本项目实现稳定的知识点拆分。此文是有来源的下一轮验证方案，不是实测成功报告。

## 1. 新查到的能力与限制

| 方法 | 有依据的能力 | 对本项目的限制/决策 |
| --- | --- | --- |
| Docling Hierarchical/HybridChunker | 利用结构生成 chunk、附加标题等元数据；Hybrid 会按 token 进一步拆分/合并 | chunk 边界不等于教学知识点；不能用 chunk 个数代替提取成功数。上轮保留为解析基线 |
| MinerU pipeline | middle.json 保留 block/line/span；span 可标为 inline_equation/interline_equation；提供坐标、列表和标题 | 值得检验行内公式隔离，官方支持某字段不代表公式检测无漏检；尚未在两份用户 PDF 实测 |
| Marker | JSON 树、ListGroup、TextInlineMath 等类型；chunks 是顶层块的平铺结果 | 也是文档转换工具；不能因有 chunks 就认为做了知识点分解，本轮不同时扩展三个解析器 |
| LangExtract（google 仓库） | LLM 根据任务例子抽取原文片段，提供 char_interval、alignment_status、JSONL 与可视化；支持自定义提供者 | 更接近知识点识别。官方明确它不是 Google 正式支持产品；对齐与语义正确性仍是两件事 |
| Dense X Retrieval 的 proposition 方法 | 将内容拆为独立、自包含的事实表达，研究与代码公开 | 研究结果是检索/QA任务，不是中文课件正确率；公开 propositionizer 基于英文 Wikipedia，且会重写语句，因此不直接作为本项目原文来源 |

## 2. 对前一轮方案的具体调整

之前把“识别文字”“拼完整段落”“知道什么是一条知识”压在确定性规则里，且要求解析器完成语义判断。
现在明确让语义模型只承担选择/分类职责：依据上下文指出哪些原文片段构成一个定义、完整特点列表或其他指定类型。
模型不能改写作为证据的文字。模型提议、代码定位、内容审查的职责不同，必须各有验收。

这需要在知识点识别阶段使用 LLM。既有约束“不要 LLM 猜公式/修复 OCR”“不生成 Card”继续成立。
本轮没有调用 API、上传课件或扩大当前已安装服务的权限。

## 3. 最小可执行路线

1. Parser 输出不可变 StructuredDocument：block ID、类型、阅读顺序、父子关系、page/bbox、原文。
2. 构造有标题路径的连续章节上下文，并建立字符偏移 → 原 block/page/bbox 映射。不能把之前过滤后剩余的 safe_text 当作完整原文。
3. LangExtract 用固定 schema + 正反例识别两种知识：definition、complete_list。原文不完整则提议 uncertain，而非补全文字。
4. 抽取的内容必须是同一上下文中的连续原文区间；词句不能重写。标题可以单独引用为上下文，但不能伪装成一条事实。
5. 程序从原文位置重建内容，继承识别层风险；任何必要片段不可靠、含不支持内容或位置不明，就拒绝整个知识点。
6. 结合完整上下文进行独立语义复核：主语、限定条件、否定、因果、枚举成员是否齐全。不通过即拒绝，不启动修复循环。
7. 输出 KnowledgeUnit 候选与证据链，供后续 Card 模块使用。这里没有 front/back、Quiz 或学习计划。

跨页策略：保留邻页只是为发现缺失依赖；第一版仍可拒绝所有跨页候选，不要求自动恢复。
窗口超长时保留结构边界和缓冲区。落在被裁断区的候选不能被判定完整；不能用固定字符数切片后隐去此事实。

## 4. LangExtract 必须额外限制的行为

核对其 `resolver.py` 发现默认 `enable_fuzzy_alignment=True`、`accept_match_lesser=True`。
`MATCH_EXACT` 表示 token 级匹配；因此本项目不能只看“有坐标”或者枚举状态。

拟采用的门槛（需要运行版本验证）：

- 关闭 fuzzy alignment 和 lesser match；只保留 exact 候选。
- char_interval 必须存在、区间合法，并额外严格检查 `source[start:end] == extraction_text`。
- 代码保存的知识内容来自原始 slice，而非重新使用模型自由文本；对重复出现的同句保留上下文和 block ID 验证位置。
- 自由生成的 attributes/description 只作候选元数据，不成为事实来源。初版使用有限标签，禁止外部知识属性。
- 字符准确匹配只证明候选来自已提取文本，不证明 OCR 忠实于图片，更不证明是完整知识点。

例如只截取“适用于……”而丢掉前面的“不”，可能仍是原文子串；这就是独立语义完整性检查必须存在的原因。
同一个模型或不同模型都可能一致犯错，复核是可评估的过滤信号，不是自动正确性证明。

## 5. 输入问题不由拆分模型修复

- 原生 PDF 保留文字层及截图来源；文字层可能有映射错误，不能自动等价于 verified。
- OCR 资料若存在漏字、公式混排、不清楚的阅读关系，保留 unknown/unsupported；不要让 LangExtract 将这些内容“整理通顺”。
- MinerU pipeline 的行内公式类型值得针对现有 F09 问题实测。关闭公式转写是否仍保留风险位置要单独核对，不能假设一个开关解决。
- 公式、图示解释、表格关系第一版继续排除。只有识别层满足要求的内容才用于衡量知识点抽取质量。

## 6. 下一次实验必须回答的问题

先固定拆分标准和人工参考，再比较：

1. 结构 chunk 基线；
2. LangExtract 原文抽取；
3. LangExtract 原文抽取 + 独立完整性复核。

这些比较使用同一份已冻结的解析输出，避免更换 OCR 和更换拆分策略同时发生，无法归因。
扫描识别能力另作 Docling 与 MinerU 的比较。

抽取单位：一个定义，或一个完整的分类/特点列表；先不要求把同一列表强行拆成若干无主语词条。

评估维度：

- 来源匹配率：可确定检查，目标 100%。
- 放行 KnowledgeUnit 精确率：人工对照原文，判定文字、条件、主语和成员完整。
- 覆盖率：相对于参考知识点，避免全拒绝伪装高准确率。
- 拆分稳定性：同一冻结输入运行三次，按 source span/type 比较，不只比输出文字。
- 公式误放行、原文外事实、遗漏否定或限定：逐条作为严重失败。
- 成本、耗时、拒绝原因分别记录。多个 Unit 来自同一文档并非统计独立样本，报告应注明文档聚类。

已有两份用户课件继续作为开发集；另取至少两份未参与调试的真实中文资料作为留出集。
现有 20 页机器结果尚不能作为完整人工金标准，必须完成标签后才可报告实测准确率。

## 7. 证据与追踪

检索日期均为 2026-09-05。官方 main/latest 页面可能变化，实际实验时应固定版本/提交。

- Docling chunking：https://docling-project.github.io/docling/concepts/chunking/
- MinerU output schema：https://opendatalab.github.io/MinerU/reference/output_files/
- MinerU CLI/backends：https://opendatalab.github.io/MinerU/usage/cli_tools/
- Marker JSON/chunks：https://github.com/datalab-to/marker/blob/master/README.md
- LangExtract 项目与限制：https://github.com/google/langextract
- LangExtract 数据类型：https://github.com/google/langextract/blob/main/langextract/core/data.py
- LangExtract 对齐实现：https://github.com/google/langextract/blob/main/langextract/resolver.py
- Dense X Retrieval：https://arxiv.org/abs/2312.06648
- 论文代码与公开模型：https://github.com/chentong0/factoid-wiki

本轮没有覆盖上一轮设计/评估结果，也没有把新组件接入业务。Docling 的本项目能力以 2026-09-04 本地实测为准；
LangExtract、MinerU、Marker 的结论是文档/代码调研，不能写成中文课件实测成功。
