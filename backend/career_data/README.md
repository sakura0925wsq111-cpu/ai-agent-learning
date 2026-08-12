# Career Data 独立数据模块

该模块只负责官方公开职业/升学参考数据的采集、原文归档、解析、清洗、版本管理和查询验证。它使用独立 SQLite 数据库，不导入或注册任何 Agent、Prompt、工作流、Tool Calling、Embedding 或 RAG 代码。

## 设计与存储

- 默认数据库：`backend/data/career_data/career_data.db`。
- 原始文件：`backend/data/career_data/raw/<source>/`；数据库保存相对路径和 SHA-256。
- 迁移：`migrations/*.sql` 按文件名排序执行，执行记录保存在 `schema_migrations`，可重复初始化。
- 数据访问：所有写入和查询集中在 `CareerDataRepository`，适配器不散落业务 SQL；后续迁移 PostgreSQL 时只需替换数据库/迁移实现，不影响调用方接口。
- 幂等规则：原始内容按 SHA-256 去重，业务记录按“来源自然键 + 年份”增量写入，旧年份不会被新年份覆盖。

核心表及关系：

```text
data_sources 1 ── n ingestion_runs
      │                  │
      └── 1 ── n source_documents 1 ── n postgraduate_programs
                           │          ├── n undergraduate_majors
                           │          ├── n salary_benchmarks
                           │          ├── n civil_service_positions
                           │          ├── n civil_service_positions_v2
                           │          │       └── n civil_service_position_major_requirements
                           │          └── 1 qut_transfer_policies
                           ├── n source_document_origins
                           └── n data_quality_issues

civil_service_exam_batches 1 ── n civil_service_positions_v2
```

## CLI

从仓库根目录执行（PowerShell）：

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
$python = '.\venv\Scripts\python.exe'  # 也可使用已安装依赖的 python

& $python -m career_data db init
& $python -m career_data sources list

& $python -m career_data ingest postgraduate
& $python -m career_data ingest undergraduate-majors
& $python -m career_data ingest salary
& $python -m career_data ingest civil-service
& $python -m career_data ingest qut-transfer
& $python -m career_data ingest all

& $python -m career_data import postgraduate <file> --source-url <研招网官方附件URL> --year 2026
& $python -m career_data import undergraduate-majors <file> --source-url <教育部官方附件URL> --year 2026
& $python -m career_data import salary <file> --source-url <人社部官方附件URL> --year 2025
& $python -m career_data import civil-service <file> --source-url <国家公务员局官方附件URL> --year 2026
& $python -m career_data import qut-transfer <file> --source-url <青岛理工大学官方页面URL> --year 2026 --title <标题>

& $python -m career_data import-directory shandong-civil-service `
    backend/data/career_data/raw/shandong-civil-service/2026 `
    --manifest backend/data/career_data/raw/shandong-civil-service/2026/manifest.json `
    --dry-run
& $python -m career_data import-directory shandong-civil-service `
    backend/data/career_data/raw/shandong-civil-service/2026 `
    --manifest backend/data/career_data/raw/shandong-civil-service/2026/manifest.json

& $python -m career_data runs list
& $python -m career_data quality list
```

人工导入强制要求精确的官方 `--source-url`；不在对应官方域名白名单内的文件会被拒绝。支持 CSV/TSV/XLS/XLSX（含多工作表）；教育部本科目录支持 PDF；青岛理工大学政策还支持 HTML/PDF/TXT。表头发生变化、必填字段缺失、数据类型异常或无法判断政策有效性时会写入运行记录和质量问题，不会猜补。

真实网络更新是可选命令，测试和 CI 完全不访问网络。当前只有教育部本科目录配置了稳定的低频官方 PDF；其余来源没有稳定公开批量入口时返回 `requires_manual_review`，应下载官方附件后使用 `import`，不会高频遍历、绕过登录或验证码。

## 查询接口

`CareerDataRepository` 提供后续 RAG/工具封装可复用、但当前未注册为工具的方法：

- `search_postgraduate(keyword, region, year)`
- `search_undergraduate(query, year)`
- `search_salary(query, year)`
- `search_civil_service(major_text=..., education=..., region=..., year=...)`
- `get_qut_policies(current_only=False)`
- `get_shandong_civil_service_summary(year=2026)`
- `get_source_chain(entity_type, entity_id)`

CLI 也可用于人工验证，例如：

```powershell
& $python -m career_data query undergraduate-majors --text 计算机 --year 2026
& $python -m career_data query source-chain --entity-type undergraduate-majors --id 411
```

## 测试

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
.\venv\Scripts\python.exe -m pytest backend/tests/test_career_data.py -q
```

离线测试覆盖六类解析器、空文件、缺失/变化表头、重复导入、哈希去重、跨年度保留、数据类型异常、部分失败、批事务回滚、青岛理工大学新旧政策共存、有效性待审核，以及山东职位表 Manifest 全量校验、来源链和幂等导入。

## 当前真实数据

- 教育部《普通高等学校本科专业目录（2026年）》官方 PDF 已保存在 `raw/undergraduate-majors/`。
- 官方附件 URL：`https://www.moe.gov.cn/srcsite/A08/moe_1034/s3882/202604/W020260427440749576927.pdf`。
- 目录发布日期：2026-04-07；已解析 883 个专业，重复导入不会新增记录。
- 青岛理工大学教务处 2024、2025、2026 年三份本科生转专业年度通知已保存并导入；均来自 `https://jw.qut.edu.cn/`，未下载申请/拟录取名单附件。由于页面没有给出可机器确认的失效日期，三条记录均保守标记为 `needs_review`，不会猜测 `is_current`。
- 校级《青岛理工大学学生转专业实施办法（修订）》官方页面为 `https://jw.qut.edu.cn/info/1015/2318.htm`，正文 DOCX 的官方下载要求验证码；自动程序不会绕过，需由人工在浏览器完成官方下载后按上面的 `qut-transfer import` 命令导入。
- 国家公务员局 2026 年度招考简章 ZIP 和其中的官方 XLS 已归档；4 个工作表共导入 20,714 个职位，计划招录 38,119 人。职位自然键使用“年度 + 部门代码 + 职位代码”，避免跨部门重复职位代码互相覆盖。
- 山东省 2026 年度省级机关及除德州外 15 市共 16 份职位表已归档并通过 Manifest 校验，共 5,842 个职位、计划招录 7,685 人。每份文档保留官方信息页和文件传输来源；当前批次覆盖状态为 `partial`，文档审核状态为 `needs_review`。德州加密工作簿和选调生数据不在本批次范围内。
- 研招网、人社部两类当前仅包含解析器测试 fixtures，未把合成测试记录写入正式数据库；应在获得对应年度官方公开附件或可复核网页快照后导入。
