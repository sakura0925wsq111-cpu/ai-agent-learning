CREATE TABLE civil_service_exam_batches (
 id INTEGER PRIMARY KEY,
 exam_type VARCHAR(32) NOT NULL CHECK(exam_type IN ('national','provincial','selection')),
 exam_year INTEGER NOT NULL,
 province_code VARCHAR(20),
 province_name VARCHAR(100),
 batch_code VARCHAR(50) NOT NULL,
 title TEXT NOT NULL,
 publisher VARCHAR(200) NOT NULL,
 official_entry_url TEXT NOT NULL,
 coverage_status VARCHAR(32) NOT NULL CHECK(coverage_status IN ('complete','partial')),
 coverage_note TEXT,
 review_status VARCHAR(32) NOT NULL CHECK(review_status IN ('pending','approved','rejected','needs_review')),
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(exam_type, exam_year, province_code, batch_code)
);

CREATE TABLE civil_service_positions_v2 (
 id INTEGER PRIMARY KEY,
 exam_batch_id INTEGER NOT NULL REFERENCES civil_service_exam_batches(id),
 natural_key VARCHAR(200) NOT NULL,
 province_name VARCHAR(100),
 city_name VARCHAR(100),
 recruitment_authority TEXT NOT NULL,
 employing_unit TEXT NOT NULL,
 department_code VARCHAR(50),
 position_code VARCHAR(50) NOT NULL,
 position_name TEXT NOT NULL,
 position_nature VARCHAR(100),
 position_category VARCHAR(100),
 position_attribute VARCHAR(100),
 exam_category VARCHAR(100),
 position_description TEXT,
 recruitment_count INTEGER NOT NULL,
 target_group TEXT,
 education_requirement TEXT,
 degree_requirement TEXT,
 gender_requirement TEXT,
 household_requirement TEXT,
 political_status_requirement TEXT,
 grassroots_experience_requirement TEXT,
 professional_exam_required BOOLEAN,
 professional_test_required BOOLEAN,
 differential_inspection BOOLEAN,
 differential_inspection_detail TEXT,
 psychological_test_required BOOLEAN,
 special_medical_exam_required BOOLEAN,
 work_location TEXT,
 remarks TEXT,
 information_website TEXT,
 consultation_phones_json TEXT NOT NULL DEFAULT '[]',
 source_document_id INTEGER NOT NULL REFERENCES source_documents(id),
 source_row_number INTEGER NOT NULL,
 raw_payload_json TEXT NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(exam_batch_id, natural_key)
);

CREATE TABLE civil_service_position_major_requirements (
 id INTEGER PRIMARY KEY,
 position_id INTEGER NOT NULL REFERENCES civil_service_positions_v2(id) ON DELETE CASCADE,
 education_level VARCHAR(32) NOT NULL CHECK(education_level IN ('associate','bachelor','postgraduate','all')),
 requirement_raw TEXT NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(position_id, education_level)
);

CREATE TABLE source_document_origins (
 id INTEGER PRIMARY KEY,
 source_document_id INTEGER NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
 origin_type VARCHAR(32) NOT NULL CHECK(origin_type IN ('official_page','official_attachment','mirror_download','local_conversion')),
 url TEXT NOT NULL,
 publisher VARCHAR(200),
 verification_status VARCHAR(32) NOT NULL CHECK(verification_status IN ('pending','verified','needs_review','rejected')),
 verified_at DATETIME,
 note TEXT,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(source_document_id, origin_type, url)
);

CREATE INDEX ix_civil_batches_scope ON civil_service_exam_batches(exam_type, exam_year, province_code, batch_code);
CREATE INDEX ix_civil_v2_region ON civil_service_positions_v2(exam_batch_id, city_name, work_location);
CREATE INDEX ix_civil_v2_education ON civil_service_positions_v2(exam_batch_id, education_requirement);
CREATE INDEX ix_civil_v2_position_code ON civil_service_positions_v2(position_code);
CREATE INDEX ix_civil_v2_source ON civil_service_positions_v2(source_document_id);
CREATE INDEX ix_civil_major_search ON civil_service_position_major_requirements(education_level, requirement_raw);
CREATE INDEX ix_document_origins_document ON source_document_origins(source_document_id);

INSERT INTO data_sources(
 code,name,publisher,base_url,source_type,acquisition_method,update_frequency,terms_note
) VALUES (
 'shandong-civil-service',
 '山东省各级机关考试录用公务员职位表',
 '中共山东省委组织部',
 'https://gwy.sdrsks.org.cn/',
 'official_spreadsheet',
 'official page with verified attachment or reviewable mirror',
 'annual',
 '省级机关及各市按文件分别归档；镜像传输文件在人工核验前保持 needs_review'
);
