PRAGMA foreign_keys = OFF;

CREATE TABLE civil_service_positions_new (
 id INTEGER PRIMARY KEY, exam_year INTEGER NOT NULL, department_code VARCHAR(50) NOT NULL,
 department_name VARCHAR(200) NOT NULL, employing_department VARCHAR(200),
 organization_nature VARCHAR(200), organization_level VARCHAR(100),
 position_code VARCHAR(50) NOT NULL, position_name VARCHAR(200) NOT NULL,
 position_description TEXT, position_category VARCHAR(100), position_distribution VARCHAR(100),
 exam_category VARCHAR(200), recruitment_count INTEGER, major_requirement_raw TEXT,
 education_requirement TEXT, degree_requirement TEXT, political_status_requirement TEXT,
 grassroots_experience_requirement TEXT, target_group TEXT, work_location VARCHAR(200),
 settlement_location VARCHAR(200), interview_ratio VARCHAR(50), professional_ability_test VARCHAR(50),
 remarks TEXT, source_document_id INTEGER NOT NULL REFERENCES source_documents(id), source_url TEXT NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(exam_year, department_code, position_code)
);

INSERT INTO civil_service_positions_new (
 id,exam_year,department_code,department_name,employing_department,organization_nature,
 organization_level,position_code,position_name,position_description,position_category,
 position_distribution,exam_category,recruitment_count,major_requirement_raw,education_requirement,
 degree_requirement,political_status_requirement,grassroots_experience_requirement,target_group,
 work_location,settlement_location,interview_ratio,professional_ability_test,remarks,
 source_document_id,source_url,created_at,updated_at
)
SELECT id,exam_year,department_code,department_name,employing_department,organization_nature,
 organization_level,position_code,position_name,position_description,position_category,
 position_distribution,exam_category,recruitment_count,major_requirement_raw,education_requirement,
 degree_requirement,political_status_requirement,grassroots_experience_requirement,target_group,
 work_location,settlement_location,interview_ratio,professional_ability_test,remarks,
 source_document_id,source_url,created_at,updated_at
FROM civil_service_positions;

DROP TABLE civil_service_positions;
ALTER TABLE civil_service_positions_new RENAME TO civil_service_positions;
CREATE INDEX ix_civil_search ON civil_service_positions(exam_year, work_location, education_requirement);

PRAGMA foreign_keys = ON;
