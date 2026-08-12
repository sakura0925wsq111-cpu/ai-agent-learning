PRAGMA foreign_keys = ON;

CREATE TABLE data_sources (
 id INTEGER PRIMARY KEY, code VARCHAR(64) NOT NULL UNIQUE, name VARCHAR(200) NOT NULL,
 publisher VARCHAR(200) NOT NULL, base_url TEXT NOT NULL, source_type VARCHAR(50) NOT NULL,
 acquisition_method VARCHAR(100) NOT NULL, update_frequency VARCHAR(100), terms_note TEXT,
 enabled BOOLEAN NOT NULL DEFAULT 1, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ingestion_runs (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES data_sources(id),
 started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at DATETIME,
 status VARCHAR(32) NOT NULL CHECK(status IN ('running','succeeded','partial','failed','requires_manual_review')),
 records_discovered INTEGER NOT NULL DEFAULT 0, records_inserted INTEGER NOT NULL DEFAULT 0,
 records_updated INTEGER NOT NULL DEFAULT 0, records_skipped INTEGER NOT NULL DEFAULT 0,
 error_count INTEGER NOT NULL DEFAULT 0, error_message TEXT, parser_version VARCHAR(50) NOT NULL,
 trigger_type VARCHAR(32) NOT NULL CHECK(trigger_type IN ('automatic','manual_upload','local_fixture')),
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE source_documents (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES data_sources(id),
 ingestion_run_id INTEGER NOT NULL REFERENCES ingestion_runs(id), title TEXT NOT NULL,
 source_url TEXT NOT NULL, publisher VARCHAR(200) NOT NULL, document_type VARCHAR(50) NOT NULL,
 published_at DATETIME, retrieved_at DATETIME NOT NULL, applicable_year INTEGER,
 valid_from DATE, valid_to DATE, content_hash VARCHAR(64) NOT NULL UNIQUE,
 local_path TEXT NOT NULL, mime_type VARCHAR(150), file_size INTEGER NOT NULL,
 parser_version VARCHAR(50) NOT NULL,
 review_status VARCHAR(32) NOT NULL CHECK(review_status IN ('pending','approved','rejected','needs_review')),
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE postgraduate_programs (
 id INTEGER PRIMARY KEY, institution_code VARCHAR(20), institution_name VARCHAR(200) NOT NULL,
 region VARCHAR(100), discipline_category_code VARCHAR(20), discipline_category_name VARCHAR(100),
 first_level_discipline_code VARCHAR(20), first_level_discipline_name VARCHAR(100),
 program_code VARCHAR(30) NOT NULL, program_name VARCHAR(200) NOT NULL, degree_type VARCHAR(100),
 study_mode VARCHAR(100), special_direction TEXT, admission_year INTEGER NOT NULL,
 source_document_id INTEGER NOT NULL REFERENCES source_documents(id), source_url TEXT NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(institution_code, program_code, admission_year, study_mode, special_direction)
);

CREATE TABLE undergraduate_majors (
 id INTEGER PRIMARY KEY, catalog_year INTEGER NOT NULL, discipline_code VARCHAR(10) NOT NULL,
 discipline_name VARCHAR(100) NOT NULL, major_category_code VARCHAR(10) NOT NULL,
 major_category_name VARCHAR(100) NOT NULL, major_code VARCHAR(20) NOT NULL, major_name VARCHAR(200) NOT NULL,
 is_basic BOOLEAN NOT NULL, is_special BOOLEAN NOT NULL, is_state_controlled BOOLEAN NOT NULL,
 degree_category VARCHAR(200), source_document_id INTEGER NOT NULL REFERENCES source_documents(id),
 source_url TEXT NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(catalog_year, major_code)
);

CREATE TABLE salary_benchmarks (
 id INTEGER PRIMARY KEY, survey_year INTEGER NOT NULL, occupation_code VARCHAR(30) NOT NULL,
 occupation_name VARCHAR(200) NOT NULL, salary_unit VARCHAR(100) NOT NULL,
 percentile_10 NUMERIC, percentile_25 NUMERIC, percentile_50 NUMERIC, percentile_75 NUMERIC, percentile_90 NUMERIC,
 statistical_scope TEXT NOT NULL, statistical_definition TEXT NOT NULL,
 source_document_id INTEGER NOT NULL REFERENCES source_documents(id), source_url TEXT NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(survey_year, occupation_code, statistical_scope)
);

CREATE TABLE civil_service_positions (
 id INTEGER PRIMARY KEY, exam_year INTEGER NOT NULL, department_code VARCHAR(50), department_name VARCHAR(200) NOT NULL,
 employing_department VARCHAR(200), organization_level VARCHAR(100), position_code VARCHAR(50) NOT NULL,
 position_name VARCHAR(200) NOT NULL, position_description TEXT, position_category VARCHAR(100),
 recruitment_count INTEGER, major_requirement_raw TEXT, education_requirement TEXT, degree_requirement TEXT,
 political_status_requirement TEXT, grassroots_experience_requirement TEXT, target_group TEXT,
 work_location VARCHAR(200), settlement_location VARCHAR(200), interview_ratio VARCHAR(50), remarks TEXT,
 source_document_id INTEGER NOT NULL REFERENCES source_documents(id), source_url TEXT NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(exam_year, position_code)
);

CREATE TABLE qut_transfer_policies (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL,
 policy_type VARCHAR(32) NOT NULL CHECK(policy_type IN ('university_regulation','annual_notice','receiving_plan','supplementary_notice')),
 academic_year VARCHAR(20), published_at DATETIME, valid_from DATE, valid_to DATE, applicable_grade TEXT,
 applicable_campus TEXT, source_department TEXT, eligibility_text TEXT, restriction_text TEXT,
 grade_requirement_text TEXT, process_text TEXT, assessment_text TEXT, quota_text TEXT, timeline_text TEXT,
 full_clean_text TEXT NOT NULL, is_current BOOLEAN, review_status VARCHAR(32) NOT NULL
 CHECK(review_status IN ('pending','approved','rejected','needs_review')),
 source_document_id INTEGER NOT NULL UNIQUE REFERENCES source_documents(id), source_url TEXT NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE data_quality_issues (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES data_sources(id),
 source_document_id INTEGER REFERENCES source_documents(id), ingestion_run_id INTEGER REFERENCES ingestion_runs(id),
 issue_type VARCHAR(100) NOT NULL, severity VARCHAR(20) NOT NULL, field_name VARCHAR(100),
 description TEXT NOT NULL, raw_value TEXT, resolution_status VARCHAR(32) NOT NULL DEFAULT 'open',
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, resolved_at DATETIME
);

CREATE INDEX ix_runs_source_started ON ingestion_runs(source_id, started_at);
CREATE INDEX ix_docs_source_year ON source_documents(source_id, applicable_year);
CREATE INDEX ix_postgraduate_search ON postgraduate_programs(admission_year, region, program_name);
CREATE INDEX ix_undergraduate_search ON undergraduate_majors(catalog_year, major_code, major_name);
CREATE INDEX ix_salary_search ON salary_benchmarks(survey_year, occupation_code, occupation_name);
CREATE INDEX ix_civil_search ON civil_service_positions(exam_year, work_location, education_requirement);
CREATE INDEX ix_qut_policy_year ON qut_transfer_policies(academic_year, is_current);

INSERT INTO data_sources(code,name,publisher,base_url,source_type,acquisition_method,update_frequency,terms_note) VALUES
 ('postgraduate','研招网硕士专业目录','中国研究生招生信息网','https://yz.chsi.com.cn/','official_catalog','low-frequency/manual upload','annual','无稳定公开批量接口时仅人工导入官方文件，不遍历受限页面'),
 ('undergraduate-majors','普通高等学校本科专业目录','中华人民共和国教育部','https://www.moe.gov.cn/','official_document','official PDF','annual','仅使用教育部公开附件'),
 ('salary','企业薪酬调查信息','中华人民共和国人力资源和社会保障部','https://www.mohrss.gov.cn/','official_survey','official attachment/manual upload','annual','保留工资单位、调查范围和统计口径'),
 ('civil-service','中央机关及其直属机构考试录用公务员职位表','国家公务员局','https://www.scs.gov.cn/','official_spreadsheet','official XLSX/manual upload','annual','按年度追加，保留专业要求原文'),
 ('qut-transfer','青岛理工大学转专业政策','青岛理工大学','https://www.qut.edu.cn/','official_policy','official page/manual upload','per notice','只允许 qut.edu.cn 官方来源，拒绝结果名单和个人信息');
