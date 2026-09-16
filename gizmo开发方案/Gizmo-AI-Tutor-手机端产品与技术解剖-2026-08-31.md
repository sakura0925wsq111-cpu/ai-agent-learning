# Gizmo: AI Tutor 手机端产品与技术解剖

> 研究对象：Save All Ltd 的 **Gizmo: AI Tutor**，不是同名的小游戏创作社区。
> 研究日期：2026-08-31。
> 范围：公开商店页、官方帮助中心/隐私政策、已登录产品界面只读观察、Android 3.2.51 APK 的静态分析与 Hermes 字节码反编译。没有创建内容、没有发消息、没有购买，也没有把账户中的个人资料、卡组内容或 ID 写入本文。

## 0. 一句话结论

Gizmo 的本质不是“AI 给你做闪卡”，而是一个把 **资料转化、主动回忆、游戏化习惯、同学关系链和订阅变现** 串成一条闭环的移动学习产品：

`任意学习资料 → AI 生成可测内容 → 高频答题反馈 → XP/生命/连胜/怪物 → 同学比较与邀请 → 回来继续学或订阅解锁`

它的产品参照系不是单一 Quizlet，而是：

- 用 AI 解决“整理笔记、出题太麻烦”；
- 用间隔重复和主动回忆解决“读过但记不住”；
- 用 Duolingo 式经济系统解决“知道该学但不想学”；
- 用学校、好友、Live 和分享解决“一个人难坚持、获客贵”。

技术上，当前客户端已经是 **React Native + Expo 的原生跨端 App**，并非简单网页壳；服务端是经 Cloudflare 暴露的多服务架构，主数据面走 GraphQL + WebSocket，Live 有独立实时通道，AI/内容/练习考试/用户服务分开。旧 iOS bundle id 含 `gonative`，是历史遗留命名，不能据此判断为 WebView 壳。

---

## 1. 证据等级与边界

| 标记 | 含义 | 本文中的例子 |
|---|---|---|
| A | 直接可验证 | 已登录 App 的页面结构、官方商店/帮助文档、签名匹配的 APK 静态文件 |
| B | 官方声明 | 隐私政策、融资新闻稿、帮助中心对算法与限制的说明 |
| C | 第三方报道/评论 | TechCrunch、Google Play 用户评价 |
| 推断 | 由命名、调用关系、SDK 或架构组成的合理推断 | 资料处理流水线、服务职责划分 |

不能从客户端证明的事情，我不会当作事实写：具体数据库、服务端全部源代码、某一次 AI 请求实际用了哪一家模型、间隔重复的完整数学公式、实时服务的全部部署参数，均不可由本次证据完全确认。

---

## 2. 定位、用户与真正要解决的问题

### 定位

官方主张是“让学习上瘾”。创始人的理论底座是“学习就是记住”：新知识要进入长时记忆，才能降低理解新概念时的工作记忆压力；产品因此把重点放在回忆练习和复习时机，而不是长内容阅读。[创始人文章](https://gizmo.ai/blog/learning-is-remembering/)

它面向考试驱动的青少年和大学生，尤其是需要处理 GCSE/A-level/AP、大学课程、医学/理工课程等大量资料的人。产品里出现了学校、年级、考试委员会、专业、国家榜单和同校关系，而非企业培训常见的组织/课程管理模型。

2026 年 4 月，公司宣称拥有 120 多国、1,300 万以上学习者；2023 年时为 30 万以上用户，早期增长主要来自口碑。[2026 Series A 报道](https://techcrunch.com/2026/04/15/ai-learning-app-gizmo-levels-up-with-13m-users-and-a-22m-investment/)，[2023 早期产品报道](https://techcrunch.com/2023/09/21/ai-startup-gizmo-funding-gamified-quizzes-flashcards-make-learning-fun/)

### 四个用户痛点

| 用户痛点 | 常见替代方案的问题 | Gizmo 的回答 |
|---|---|---|
| 资料多且杂，整理成卡片太费时间 | 手抄卡片、手动建 Quizlet/Anki，启动成本高 | Magic Import 一次接收 PDF、PPT、图片、录音、笔记、YouTube、Quizlet、Anki、表格、网页 |
| 看过并不等于会 | 重读、划线产生“我懂了”的错觉 | 高亮挖空、打字、语音、选择、配对、排序；答错更快重现 |
| 临考才学，难养成日常习惯 | 传统 SRS 有效但枯燥、配置复杂 | 生命、提示、XP、等级、连胜、联赛、奖励音效、怪物收集 |
| 独自学没有压力与传播动机 | 单人闪卡工具缺少关系链 | 学校/好友、同学卡组、组内每日题、好友连胜、Gizmo Live、挑战和分享 |

### 它不是在卖什么

它并不以“权威知识内容库”作为第一卖点，也不以“最精确的自定义排程器”取胜。它卖的是一句更直接的承诺：**把你已经有的学习材料，迅速变成今天就能玩、能答、能比较的学习循环。**

这决定了它的优点是启动快、动机强；弱点也是输入质量和 AI 判分一旦出错，信任会迅速崩掉。

---

## 3. 手机端信息架构与核心用户路径

在已登录移动布局的实际界面中，主导航是：

`Home / Progress / Add / Decks / Profile`

Home 不是传统“课程首页”，而是一个意图入口：顶部直接问“想学什么”，给出上传文件、粘贴文字、YouTube 和更多导入方式；下方是继续未完成 Lesson、已有卡组、最近 AI 对话，以及“搜索 50 亿张闪卡”。这把“从资料开始”和“从问题开始”并列。

| 页面/入口 | 用户行为 | 产品目的 |
|---|---|---|
| Home | 输入题目、上传、粘贴、YouTube、接着上次学 | 缩短第一次有效学习到达时间 |
| Add / Magic Import | 选择文件、相机、录音、Quizlet、Anki、网页等 | 把已有资产接入，而不是逼用户重新录入 |
| Deck | 看 Cards、Notes、Imports、Topics、Lessons、Path、Leaderboard | 把“资料容器”变成可学习、可协作的对象 |
| Memorise / Quiz | 多种题型答题、提示、解释、速度关 | 完成主动回忆与即时反馈 |
| AI Tutor | 对话、分步 Lesson、笔记、卡片、测验 | 解决“记忆之外的理解” |
| Practice test | 选课程/卡组/主题，生成考试题与评分 | 给临考用户明确的准备度反馈 |
| Progress | 等级、XP、连胜、卡组掌握度、好友榜、组 | 把学习结果可视化、社会化 |
| Profile / Social | 关注、学校、动态、好友连胜、群组 | 提升留存与关系传播 |
| Shop / Subscribe | 用 Coin 买道具；用 Unlimited 去掉资源限制 | 把“中断”转为复习/订阅动机 |

### 最关键的激活路径

1. 新用户从 TikTok、同学链接、App Store 或搜索进入。
2. 选择资料或直接说“我想学 X”。
3. Magic Import 生成卡片/高亮词/主题，或 AI Tutor 直接开 Lesson。
4. 做一轮 Memorise，立刻看到正确/错误、XP、Coin、掌握度和连胜。
5. 将卡组分享给同学、被邀请进组，或进入 Live。
6. 当生命、AI 次数、导入冷却成为障碍时，出现道具、邀请或 Unlimited 方案。

这是典型的 **“先获得学习价值，再叠加习惯和付费摩擦”**，不是先让用户建立复杂课程计划。

---

## 4. 功能全图

### 4.1 Magic Import：把输入摩擦压到最低

官方帮助中心确认的输入包括 PDF、录音、粘贴笔记、照片、PPT、Quizlet、Anki、表格和网页；Home 还将 PDF/PPT/YouTube/照片/录音/卡组直接接入 AI Tutor Lesson。[Magic Import](https://help.gizmo.ai/en/articles/15647624-what-is-magic-import)，[从资料启动 AI Tutor](https://help.gizmo.ai/en/articles/15935404-how-do-i-use-magic-import-to-start-an-ai-tutor-lesson)

客户端还明确包含：PDF 页面选择、子卡组选择、拍照、内嵌相机、录音、照片批量上传、音频导入、Office 文档转 PDF、YouTube 导入、网页导入和 Chrome 插件导入提示。

产品意义：它不是“再造笔记”，而是吞掉学生已经存在的学习堆栈。Quizlet/Anki 导入尤其重要——它降低了迁移阻力，也把竞品的内容资产变成自己的激活资源。

### 4.2 卡片与测验

官方当前支持五种卡：文本卡、选择题、配对、排序、判断题；文本卡可包含图片和 LaTex，高亮的词/短语会成为被挖空和被测试的答案。[卡片类型说明](https://help.gizmo.ai/en/articles/16527223-what-types-of-flashcards-can-i-make)，[高亮机制](https://help.gizmo.ai/en/articles/13166301-how-does-highlighting-work)

测验模式包含：

- 仅选择题：正确项 + 三个 AI 干扰项；
- 优先打字；
- 优先语音回答；
- 翻卡自评；
- 混合模式：再加入配对、排序、判断题；
- “先隐藏选项”、10 秒 Lightning round、独立 2 分钟 Speed run。

这点很聪明：同一个卡片对象可用不同难度的“取回方式”反复消费，避免只靠翻卡造成熟悉感错觉。[题型设置](https://help.gizmo.ai/en/articles/13015455-can-i-change-the-questions-i-m-asked-when-quizzing)

### 4.3 记忆引擎

官方描述的间隔重复规则很朴素：答对后更久再出现，答错后更快重现；无需用户配置。[间隔重复说明](https://help.gizmo.ai/en/articles/15647638-what-is-spaced-repetition)

静态代码可以进一步确认 UI 掌握度不是简单“正确率”。其 `calculateMasteryPercentage` 逻辑将卡片分为 `forgotten / new / learning / mastered`：

```text
mastery = round((1 × learning + 2 × mastered)
                / (2 × (forgotten + new + learning + mastered)) × 100)
```

即 new 与 forgotten 计 0，learning 计半分，mastered 计满分。这解释了用户为什么会看到“答了一些题但卡组掌握度提升有限”。

注意：客户端没有公开完整的复习调度公式，不能据此声称它使用 FSRS、SM-2 或 Anki 算法；调度结果更可能由服务端决定，再下发到客户端。

### 4.4 AI Tutor 与 Practice Test

AI Tutor 可从主题或既有 Deck 开始，生成 Course、Cards、Notes、分步 Lesson、基于内容的 Quiz；Lesson 与 Chat 会保存在 History。[AI Tutor](https://help.gizmo.ai/en/articles/13011417-how-does-the-ai-tutor-work)

Practice Test 支持按官方课程、当前 Deck 或任意主题出题，默认 10 题，可附加难度/范围指令；题型含选择、多选、书面作答，书面题按 mark scheme 给分，错题可“Explain”或保存成卡。[Practice Test](https://help.gizmo.ai/en/articles/16310506-how-do-i-start-a-practice-test)，[答题与评分](https://help.gizmo.ai/en/articles/16310632-what-happens-during-a-practice-test)

这构成了两个层次：

- Memorise：短回路，主要解决记住；
- Tutor/Test：长回路，主要解决理解、迁移和临考模拟。

### 4.5 社交与协作

产品内不只是“分享链接”，而有一套轻社交：关注、同学/学校、公开卡组、动态、好友榜、在线状态、Wave、好友连胜、私密/公开 Study Group、群组每日题与 Live 挑战。

Study Group 可添加 Deck，系统会为成员生成每日题；成员共同答题建立群组 streak。[Study Group](https://help.gizmo.ai/en/articles/13860290-how-do-i-make-a-study-group)

Gizmo Live 是实时同题竞速：倒计时、分数、局内排行榜、对其他玩家下注、结束后复盘与再开一局。[Gizmo Live 流程](https://help.gizmo.ai/en/articles/15945296-what-happens-during-a-gizmo-live-game)

### 4.6 游戏经济：产品真正的留存机器

| 机制 | 行为设计 | 商业/留存作用 |
|---|---|---|
| XP、等级、9 个 League | 正确且答得快可获得更多 XP，周榜升降级 | 将“做题”转换成可比较进度 |
| Coin | 首次答对获得，可买道具 | 让免费用户仍有资源路径 |
| Hearts | 答错扣生命；免费用户 15 条，耗尽等待 10 分钟 | 防止无脑刷题，也是最直接的付费触发 |
| Hints | 首字母或移除错误项 | 把卡关变为可控资源消耗 |
| Super Hearts / Freeze / Repair | 连胜和生命的保险道具 | 降低断连损失，同时维持连胜焦虑 |
| Shop | Hints、Super Hearts、Freeze、Repair，甚至 Dark Mode 用 Coin 解锁 | 不把每项体验都硬锁进现金付费 |
| Eggs / Monsters / Essence | 答题捕蛋、到条件孵化、重复怪转 Essence、喂养升级、装备槽与效果 | 把“连续答题”做成收集和养成系统 |
| Focus mode | iOS 上锁定干扰 App，得到当日 streak 后解锁 | 直接对抗短视频/社交应用的注意力竞争 |

官方公开的 Hearts、Hints、Freeze、League 规则见：[Hearts](https://help.gizmo.ai/en/articles/15623061-what-are-hearts)、[Hints](https://help.gizmo.ai/en/articles/15504721-what-are-hints)、[Freeze](https://help.gizmo.ai/en/articles/15326672-what-are-streak-freezes)、[Leagues](https://help.gizmo.ai/en/articles/13844961-what-are-leagues)。

Monster 系统和 Focus mode 是当前版本最容易被低估的新增层：客户端文本显示怪物有稀有度、蛋、Essence、装备槽，以及“快速回答 XP 加成、答题连击 XP 加成、正确答题额外 Coin、黄心概率、重复孵化 Essence 加成”等效果。Focus mode 的文本写明使用 Apple Screen Time，只在 iPhone/iPad 可用；用户选择的被锁 App 留在设备侧，Gizmo 不读取该选择。

这说明 Gizmo 已经从“闪卡工具”向 **学习行为操作系统** 演化：它不只提醒你学，而是在移动系统层面减少你去刷 TikTok/Instagram 的机会。

---

## 5. 留存、增长与付费拆解

### 留存飞轮

```text
导入资料
  → 很快得到可答题卡组
  → XP / Coin / 卡组掌握度 / 连胜
  → 好友、同校、群组、Live 比较
  → 分享卡组或邀请同学
  → 新内容、新关系、新复习任务
  → 再次打开 App
```

真正关键的是它把三种“回来理由”叠在一起：

1. **认知理由**：有到期卡、有没完成的 Lesson；
2. **损失厌恶**：连胜、生命、联赛晋级；
3. **社会理由**：好友在线、群组每日题、挑战、排行榜。

已登录界面可直接看到 Deck progress、好友榜、Study Group、Follow、好友连胜、历史/Jump back in；这不是营销页的抽象承诺，而是当前产品结构。

### 增长动作

- 品牌内容与学生 UGC：产品公开强调 “As seen on TikTok and Instagram”；早期报道称主要靠 word of mouth 增长。[2023 TechCrunch](https://techcrunch.com/2023/09/21/ai-startup-gizmo-funding-gamified-quizzes-flashcards-make-learning-fun/)
- 邀请激励：每成功邀请一人获得 10 Super Hearts；客户端还包含 TikTok/Instagram/Snapchat/WhatsApp/GroupMe 分享通道、短链接与二维码。
- 学校图谱：同校用户、学校榜、课程/考试板块让“一个班有一人使用”更容易扩散到同学。
- UGC 资产：公开 Deck、共享 Deck、导入竞争产品 Deck；用户内容同时是 SEO、搜索和新用户激活供给。
- 创作者计划：客户端文本提到为 TikTok/Instagram 观看量提供奖品和素材支持，最高可到 300 美元。它不是纯广告投放，而是把学生创作者变成分发节点。

### 免费到付费的设计

Basic 并非“不能用”：可用无限 Cards、Decks 和普通 Quiz；关键限制被放在高成本和高动机时刻：

- Hearts：15 次错误后暂停 10 分钟；
- Import：免费用户两次导入之间 20 分钟；
- AI Tutor：当前帮助文档写明免费每日 5 次 session；
- Hints/AI 额外能力受限。

Unlimited 的承诺是无限 Cards、Hearts、AI Tutor、Hints、Imports。[免费 AI Tutor 限额](https://help.gizmo.ai/en/articles/15869958-how-many-ai-tutor-sessions-can-i-have-for-free)，[订阅说明](https://help.gizmo.ai/en/articles/13185488-how-do-i-sign-up-for-unlimited)

本次只读观察到的网页结算页显示：年付 US$77.22（折 US$1.48/周）或周付 US$5.99；有学生优惠开关。App Store 的同一订阅显示多个区域/渠道价格，US 页面可见 US$6.99、77.99、14.99、154.99 等档位。因此不要把一个页面的金额当全市场统一价，最终价格取决于国家、学生折扣与 Web/iOS/Android 渠道。[App Store 条目](https://apps.apple.com/us/app/gizmo-ai-tutor/id1610516671)

技术上，Android 包含 Google Play Billing 和 RevenueCat；iOS 配置了 StoreKit。这说明它做的是跨 Web、Apple、Google 的统一订阅权益，而非只依赖网页 Stripe。

---

## 6. 用户真实评价：价值与裂缝

本次抓取了 716 条近期 Google Play 英文评论；为找问题，样本刻意额外抓取了 1–3 星评论，因此下面的“出现次数”只能用于问题发现，**不能当作总体比例**。Google Play 当前公开显示 4.8 分、12 万+评分、1M+ 安装门槛；抓取到的商店元数据显示约 4.9M 实装量，后者非 Google 官方公开口径，不作为正式规模结论。[Google Play](https://play.google.com/store/apps/details?id=ai.saveall.app)

### 用户喜欢什么

- 上传笔记/图片后能快速出 75 张左右卡片，解决临考整理；
- “像游戏”、XP/进度/挑战让本来不想学的人愿意开始；
- 图片/PPT/课程资料与 Explain/Tutor 形成从资料到理解的闭环；
- 有用户明确提到成绩、信心和学习频率提升。

### 最该警惕的产品问题

| 优先级 | 问题 | 证据 | 根因判断 | 建议 |
|---|---|---|---|---|
| P0 | Android 崩溃、卡顿、导入时界面冻结 | 近期低星样本中 crash/freeze 命中 100 条；集中出现在 3.2.x | 体积大、重动画、原生迁移/频繁版本迭代、导入大文件链路复杂 | 上传分片与可恢复队列；低端机性能预算；发布前导入/登录/继续按钮冒烟测试 |
| P0 | AI 出错却扣 Hearts | 用户反馈“多答案只认一个”“数学答案不对”“重复题”；AI accuracy 相关命中 27 条 | 生成、判分、干扰项与卡片高亮没有充分区分不确定性 | 关键答案给来源片段/置信度；争议题不扣心；一键纠错反馈回流评测集 |
| P1 | 付费摩擦被理解为惩罚 | Hearts、导入冷却、取消订阅与续费投诉 | 生命经济在教育场景容易被感知为“答错就不让学” | 用“每日学习预算”替代生命语言；加强订阅前续费说明与恢复购买入口 |
| P1 | 导入质量/格式/批量能力不足 | 多图选择、多个 PDF、图像导入、上传慢等投诉 | Magic Import 承诺很强，边缘场景更多 | 上传前显示可接受格式/页数/预计时间；失败可续传、逐页预览、保留原文件 |
| P1 | 账号与深链不稳 | Google 登录循环、重复 Profile、好友链接失效 | 多端认证、社交身份、深链路由一起迁移 | 账号合并、自诊断页、深链 fallback、统一登录状态机 |
| P2 | 可迁移性/可控性不足 | 官方帮助页仍写卡片导出暂不可用；用户索要 Anki export | 数据锁定会降低高阶学习者信任 | 支持 CSV/Anki 导出；明确数据可携带性 |

官方也承认导入后应检查并编辑卡片；这是正确但不足的防线——现在的痛点不是“用户不知道可编辑”，而是“模型有错时还会连带伤害生命/连胜和信任”。[导入后检查提示](https://help.gizmo.ai/en/articles/15647624-what-is-magic-import)，[卡片导出尚未提供](https://help.gizmo.ai/en/articles/13761411-how-do-i-edit-or-manage-my-cards)

---

## 7. 竞品位势：Gizmo 赢在哪里，输在哪里

| 产品 | 核心强项 | 对 Gizmo 的压力 | Gizmo 的应对 |
|---|---|---|---|
| Quizlet | 品牌、内容库、AI Cards、Practice Tests、教材资源 | 用户已有卡组与搜索习惯 | 导入 Quizlet；更强游戏化、社交、移动手感与低摩擦资料入口 |
| Anki | 自由、离线、可导出、FSRS/深度排程控制 | 高阶/医学用户重视可靠性和数据自主权 | 用极低学习成本吸引大众；但导出、可解释调度和准确性是短板 |
| Knowt | AI 导入 + 多种免费学习模式，免费层更宽 | 直接争夺“免费 Quizlet 替代”人群 | Gizmo 以游戏、好友、Live、Focus 增强日活；免费限制更激进 |
| RemNote | 笔记—PDF—引用—知识图谱—SRS 一体，离线与深度组织 | 长期系统学习者 | Gizmo 牺牲知识管理深度，换取快、轻、适合考试冲刺 |

Quizlet 已有 AI 闪卡、Practice Test 和 Q-Chat；因此“AI 导入”本身没有护城河。[Quizlet AI Flashcard Generator](https://quizlet.com/features/ai-flashcard-generator)，[Quizlet 订阅与 Practice Test](https://quizlet.com/upgrade-web)

Knowt 的免费层提供无限卡片/笔记及多种学习模式，只对 AI 使用量设限；这对 Gizmo 的 Hearts/冷却策略是直接价格压力。[Knowt 免费/付费差异](https://help.knowt.com/en/articles/10298016-what-are-the-differences-between-free-and-paid-accounts-for-students)

Anki/RemNote 则从“深度和主权”攻击：Anki 支持可配置 FSRS；RemNote 强调笔记、PDF、离线与跨端连续性。[Anki FSRS](https://docs.ankiweb.net/deck-options)，[RemNote Mobile](https://www.remnote.com/mobile)

**我的判断：Gizmo 的护城河是中等偏弱的技术护城河、较强的行为和分发护城河。**

- 弱：LLM 出卡、PDF 转卡、普通 SRS 都易被复制；
- 中：学习状态、错题/高亮/内容图谱和海量公共 Deck 会逐渐积累；
- 强：在同学、学校、好友连胜、Live、UGC 短视频和游戏化经济之间形成的复合网络效应；
- 风险：如果准确性、稳定性或数据可携带性不能守住，习惯飞轮会反过来放大负面口碑。

---

## 8. 技术解剖：客户端

### 8.1 样本与可信性

| 项目 | 结果 |
|---|---|
| Android 包名 | `ai.saveall.app` |
| 静态样本 | Android 3.2.51，versionCode 800，2026-08-29 发布标签 |
| 最低/目标 Android | minSdk 26（Android 8），targetSdk 36 |
| 分发样本 | XAPK 253.6 MB，base APK 163.2 MB + arm64 配置包 90.1 MB |
| 签名核验 | APK 证书 SHA-1 为 `f6d7…4a47`，与 APKPure 公布的签名一致；证书主体为 Google Play App Signing 的 Google Inc. |
| iOS 公共信息 | 3.2.37，2026-08-26，180.6 MB，iOS 16.4+；bundle id `io.gonative.ios.xqdyad` |

Android 静态样本与 Google Play 当前版本一致。iOS 名称中的 `gonative` 容易误导：当前共享配置、JS bundle、原生插件和 Android 包均显示它已迁移到 React Native/Expo；包名没有随迁移改名。

### 8.2 客户端技术栈

| 层 | 可验证实现 | 含义 |
|---|---|---|
| UI | React Native 0.86.3 + TypeScript/TSX | iOS/Android 一套主要业务 UI |
| App 框架 | Expo SDK 57、Expo Router 57.0.17、EAS Build | 路由、打包、原生模块、OTA/预览能力统一 |
| JS 引擎 | Hermes bytecode v98，主 bundle 约 43.2 MB | 更快启动/更小解释开销，但源逻辑仍可反编译 |
| UI/动画 | NativeWind/Tailwind、Reanimated、Skia、Lottie、音效/触感 | 强游戏感和高反馈密度 |
| 状态 | MobX、XState、TanStack React Query（含持久化） | 局部响应式状态 + 复杂流程状态机 + 服务端缓存 |
| 数据校验 | Zod | API/状态输入的运行时验证 |
| 数学/富文本 | LaTex/KaTeX、Markdown、图片标注/遮挡 | 支持理工题、解释和图像题 |

反编译结果保留了大量原始组件名，如 `quiz-screen.tsx`、`flashcard.tsx`、`blocking-settings-page.tsx`、`egg-openable.tsx`、`practice-while-you-wait.tsx`、`friend-streaks-component.tsx`、`create-live-game.tsx`。说明业务代码主要是 TypeScript，而非大量原生 Kotlin/Swift 页面。

### 8.3 原生能力不是摆设

Android 包和 Expo 配置包含：相机、相册、文件选择、后台录音/播放、语音识别、通知、联系人、深链、Google/Apple 登录、Secure Store、媒体库、Web Browser 等。

iOS 还配置了：

- `GizmoWidget`：桌面 Widget；
- `GizmoShare`：系统分享扩展，允许从别的 App 直接导入；
- `GizmoScreenTimeMonitor` 和 Shield：Focus/应用屏蔽；
- App Clip 与 Live Activity：Live/分享场景的轻入口和实时状态；
- OneSignal 通知服务扩展。

因此“手机端”不只是把网页塞进 WebView：相机、录音、语音答题、系统分享、通知、屏幕时间控制和应用内购均是原生能力，真正适合在 App 内做。

### 8.4 权限与隐私面

Android manifest 请求网络、相机、录音、通知、联系人、存储/文件、震动、生物识别、广告 ID、后台服务和 Google Play Billing 等权限。配置文案明确写着：联系人用于在 Gizmo 找朋友，且“contacts are stored on a server so we can identify your friends”。

这与 iOS App Store 当前“Data Not Collected”标签存在明显不一致：

- App Store 页面标为“Data Not Collected”；
- Google Play 写明可能收集位置、个人信息等多类数据；
- Gizmo 官方隐私政策写明收集账户资料、教育资料（文字、消息、学习材料、照片、视频）、使用/设备/地理位置数据，并会将教育和用户生成数据披露给 AI 服务商以生成输出和改进 AI 功能；还列出 LogRocket 会话回放。[App Store](https://apps.apple.com/us/app/gizmo-ai-tutor/id1610516671)，[Google Play](https://play.google.com/store/apps/details?id=ai.saveall.app)，[Privacy Policy](https://gizmo.ai/privacy/)

这不是对其合法性的判断，但属于必须修复的 **披露一致性风险**：至少需要让 iOS Privacy Nutrition Label、应用内权限文案、官网隐私政策与实际 SDK/数据流同步。对未成年人和教育数据产品，这不是小问题。

---

## 9. 技术解剖：服务端、数据与实时链路

### 9.1 可见服务边界

客户端的生产环境配置直接列出以下域名：

| 服务 | 客户端证据 | 推断职责 |
|---|---|---|
| `proxy.gizmo.ai/v1/graphql` + `wss://…` | 主 HTTP GraphQL 与订阅地址 | BFF/主数据读写、实时订阅 |
| `auth.gizmo.ai` | Auth Worker URL | 登录、身份链接、令牌/账户流程 |
| `ai.gizmo.ai` | AI Worker URL | Tutor、解释、出题/生成编排 |
| `content.gizmo.ai` | Content Worker URL | 文件、链接、视频、文档解析与导入工作流 |
| `practice-exam.gizmo.ai` | Practice Exam Worker URL | 考试生成、评分/结果 |
| `user.gizmo.ai` | User Worker URL | 用户资料、社交关系、在线状态 |
| `coeus.gizmo.ai` | Tracking Worker URL，亦作 PostHog host | 事件采集、实验/分析代理 |
| `wss://live.gizmo.ai` | Live Game WS URL | 实时房间、竞赛状态 |
| S3/CloudFront | 图片和媒体 URL | 卡片图片、头像、资源存储/CDN |

`GET https://proxy.gizmo.ai/api/_health_check` 返回 Python 类型名 `api.messages.HealthCheckRequest/Response`，并由 Cloudflare 返回。这能证明公开 API 边缘经过 Cloudflare，后端至少有 Python 服务/消息模型；不能仅凭此断言整个后端是 FastAPI 或 Cloudflare Workers。

### 9.2 主数据模型（从路由、hooks 与 API 名称恢复）

```text
User ──< Deck ──< Card ──< Highlight / Label / Attribute
              ├──< Import ──< SourceFile / Pages / Topics / Subdecks
              ├──< Note
              ├──< Lesson / TutorChat / TutorMessage
              └──< QuizRound ──< Question / Answer / ReviewState

User ──< Follow / FriendStreak / Notification / Activity
User ──< StudyGroup ──< GroupMember / GroupDeck / DailyQuiz / GroupGame
User ──< XP / Coin / Heart / Streak / League / Monster / Inventory
User ──< Subscription / Purchase / Entitlement
```

证据包括 `useAddCardMutation`、`useDeckWithDescendantsQuery`、`useStudyNoteImportQuery`、`useFriendStreaksQuery`、`useGroupQuizQuery`、`useUserRankStatsQuery` 等 hooks，以及客户端遗留/兼容 REST 路由：`/api/add_card`、`/api/generate_deck`、`/api/log_answer`、`/api/complete_round`、`/api/get_lives_info`、`/api/start_ai_tutor_lesson`、`/api/create_group`、`/api/start_group_game` 等。

这不是“一个 LLM 聊天框 + 一张表”的产品：它有明确的内容图谱、学习状态、社交图、经济系统和订阅权益模型。

### 9.3 导入与生成流水线（推断）

```text
文件/图片/录音/URL
  → 原生采集、上传、文件类型检测
  → Content service：PDF/PPT/网页/YouTube/音频预处理与抽取
  → AI service：摘要、主题、子卡组、卡片、绿色高亮、干扰项/题目
  → Deck/Card/Import 持久化
  → Quiz engine 选择问题与复习状态
  → 客户端展示、记录答案、奖励、同步
```

支持这条推断的证据：客户端有 PDFBox Android 资源、相机/文档/音频模块、导入状态文案（上传、扫描、提取关键主题、生成子卡组/卡片）、`content.gizmo.ai`、`ai.gizmo.ai`、对象存储与大量导入 API。OCR/图像理解究竟在端侧还是服务端，不能从 APK 单独确定；ML Kit 依赖存在，但不足以证明它就是 OCR 的唯一实现。

### 9.4 AI 模型策略：不是单模型，而是实验化的路由层

静态 bundle 中有 539 个功能实验键，并且存在面向导入/解释/编排的模型变体：`gpt-luna-low/high`、`deepseek-v4-flash`、`gemini-3-5-flash-lite`、`lite-thinking-1024`、`muse-spark-1-2`、`gpt-oss`、`gemma`、`qwen` 等。还能看到 `cheap / standard / premium` 导入头、国家/地区分组、`ai-explain-model`、`create-questions-model`、`orchestrator-*` 等实验名。

正确解读是：

- Gizmo 具备按任务、成本档、用户分群和地区做模型路由/A-B 的能力；
- 资料导入、出题、解释、Tutor 不是必然使用同一个模型；
- 客户端代码中的 flag 不等于某个用户某次请求一定跑在该模型上，最终路由仍由远端实验和服务端控制；
- 官方 2023 年说“生成模型是 proprietary”，可理解为其编排、提示、评测和产品流程，而不是足以证明从零训练基础模型。[2023 报道](https://techcrunch.com/2023/09/21/ai-startup-gizmo-funding-gamified-quizzes-flashcards-make-learning-fun/)

这一层是成本控制的关键：免费用户的 20 分钟导入冷却、每日 AI 限额和 Premium/地域模型路由，很可能共同用于把大模型成本锁在可接受范围内。

### 9.5 Quiz 与 Live 的实现特点

- App 配置暴露独立 `quizEngine`：engineVersion 32、stateVersion 16；
- 客户端有游戏兼容性握手和 server/client state version 校验；
- Live 有独立 WebSocket；
- 生产文本中写着 Live room 的 game durable object 在服务端运行，强烈指向基于 Cloudflare Durable Objects 或等价房间状态服务的设计；
- 对实时竞赛而言，服务端主导状态比“纯客户端加分”更能防止抢答、计时和下注作弊。

从产品角度，这解释了为什么 Gizmo Live 可以做计时、同题、局内榜、下注、重连与连续回合，而不仅是共享一组静态题。

---

## 10. 观察、分析、实验与商业化 SDK

| 目的 | SDK/能力证据 | 风险/价值 |
|---|---|---|
| 身份 | Firebase Auth、Google Sign-In、Apple Sign-In | 降低注册摩擦，需处理多账号合并 |
| 订阅 | RevenueCat、Google Play Billing、StoreKit | 跨平台权益统一，价格/取消路径要透明 |
| 推送 | OneSignal、Firebase Messaging、Live Activity | 连胜/好友/到期卡召回能力强，也容易打扰 |
| 事件/实验 | PostHog，经 `coeus.gizmo.ai` 代理 | 539 个 flag 说明非常强的实验文化 |
| 投放归因 | Adjust、Meta/Facebook、Snapchat | 支撑学生社媒获客与归因 |
| 稳定性 | Sentry、LogRocket | 适合快速迭代，但教育内容/隐私遮罩必须严格验证 |
| 本地安全 | Expo Secure Store、生物识别 | 会话和敏感凭证应避免明文落地 |

产品不是“先做完再上线”的节奏，而是高频实验：导航、导入模型、AI Tutor、Live 时长、付费墙、怪物、Focus、好友推荐等都被 feature flag 化。优点是能快速找到有效增长机制；代价是版本复杂度和回归风险高，近期用户的“更新后卡顿/崩溃/登录失败”正是其运营代价。

---

## 11. 关键产品判断

### 做对的事

1. **把 AI 放在资料入口而非聊天入口。** 用户真正愿意付费的是“省掉整理时间”，不是多一个泛聊天机器人。
2. **把主动回忆包装成游戏。** 对大多数学生，正确的学习法不难理解，难的是持续执行；Gizmo 用反馈密度解决执行。
3. **内容、关系和状态同时沉淀。** Deck 不是孤立文件，而可以进入个人资料、学校、群组、Live、榜单和分享链接。
4. **对短视频注意力正面竞争。** 不是假装自己比 TikTok 严肃，而是借用其短回路、视觉、社交和奖励语法，甚至开始屏蔽干扰 App。
5. **把模型选择当运营杠杆。** 不同导入/解释场景走不同成本、质量与地区路由，才可能在免费层支持高频 AI。

### 最危险的事

1. **AI 判错与 Hearts 捆绑。** 普通错误令人烦，AI 错误还让用户掉生命，是双重惩罚。
2. **稳定性弱于承诺。** Magic Import 是核心价值，如果 PDF/多图上传最容易崩，产品最强的卖点会变成最强的流失点。
3. **“上瘾”越做越像付费惩罚。** 连胜/生命在语言学习中常被接受，在考试学习里若挡住用户复习，会直接伤害信任。
4. **数据披露不一致。** 教育材料、联系人、语音、位置和行为分析的组合，对未成年人产品需要更高透明度。
5. **缺少可迁移性。** 不支持导出会让高阶用户把 Gizmo 当临时工具，而不是长期学习仓库。

---

## 12. 如果复刻，应该复刻什么，不该复刻什么

### 先做的最小闭环

```text
PDF/图片/文本导入
→ 可编辑卡片 + 来源定位
→ 多题型主动回忆
→ 服务端复习状态
→ 每日待复习与单一进度指标
```

先把“导入正确率、可编辑性、答题反馈、复习到达率”做稳，再加社交和游戏化。

### 不建议一开始复刻

- 9 级联赛、怪物稀有度、经济道具、下注 Live、App Clip、Focus blocker 全部一起做；
- 任意资料一键生成后不允许审查；
- 用 Hearts 作为唯一免费限制；
- 把公开 Deck 当作天然可信内容库。

### 更健康的 v1 路线

| 阶段 | 做什么 | 验收指标 |
|---|---|---|
| 1 | 导入 + 卡片编辑 + 来源证据 | 90% 导入可完成；错误卡可在 15 秒内修正 |
| 2 | Recall + SRS + 进度 | D1 首轮答题率；7 日复习回访；不误判答案 |
| 3 | Tutor / Practice Test | 每个 AI 题可回溯到来源或标明通用知识 |
| 4 | 轻游戏化 | 奖励不妨碍继续学习；免费用户仍可完成核心复习 |
| 5 | 分享与群组 | 先 Deck 分享，再做实时竞赛与社交图谱 |

最值得借鉴的不是皮肤，而是这条原则：**让每一个增长/游戏机制都服务于一次真实的主动回忆，而不是只服务于停留时长。**

---

## 13. 最终判断

Gizmo 能火，不是因为它比别人更早有“大模型”，而是因为它非常准确地抓住了学生学习的三个摩擦：**做资料麻烦、记忆很枯燥、一个人不容易坚持。**

它用 AI 消掉资料摩擦，用测验替代被动阅读，用游戏和关系链替代意志力。其最强竞争力是把这些组合成连续行为系统；其最脆弱的地方也完全对应：生成必须可信、导入必须稳定、付费不能让用户觉得“答错就不配学习”。

从工程视角看，这是一支典型的高迭代 AI 消费产品团队：跨端原生客户端、分服务后端、实时房间、模型路由、实验平台、完整增长/订阅/观测栈都已具备。它不是一个 Demo，也不是只有前端 UI 的“套壳 AI 应用”；但服务端核心算法、模型调用与数据治理仍不公开，不能以本报告替代源码审计或安全审计。

---

## 附录：主要公开来源

- [Gizmo App Store 页面](https://apps.apple.com/us/app/gizmo-ai-tutor/id1610516671)
- [Gizmo Google Play 页面](https://play.google.com/store/apps/details?id=ai.saveall.app)
- [官方帮助中心](https://help.gizmo.ai/en/)
- [官方隐私政策](https://gizmo.ai/privacy/)
- [创始人：Learning is Remembering](https://gizmo.ai/blog/learning-is-remembering/)
- [TechCrunch：2023 年种子轮与早期产品](https://techcrunch.com/2023/09/21/ai-startup-gizmo-funding-gamified-quizzes-flashcards-make-learning-fun/)
- [TechCrunch：2026 年 1,300 万用户与 Series A](https://techcrunch.com/2026/04/15/ai-learning-app-gizmo-levels-up-with-13m-users-and-a-22m-investment/)

## 附录：本地静态分析产物

为方便复核，研究过程生成了以下中间证据（不含任何账户内容）：

- `work/analysis/apk_report.json`：manifest、权限、组件、SDK、构建配置；
- `work/analysis/AndroidManifest.xml`：解码后的 Android manifest；
- `work/analysis/google_play_reviews.json`：近期评论样本与人工关键词归类；
- `work/analysis/i18n_en-US.json`：客户端公开语言包；
- `work/apk/gizmo.decompiled.js`：Hermes 反编译结果，仅用于本次审查，不作为对外分发源码。
