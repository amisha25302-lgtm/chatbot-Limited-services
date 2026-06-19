-- ============================================================
-- SEWA SETU CHHATTISGARH — MySQL Database Schema
-- Database: sewasetu1
-- Compatible with MySQL 8.0+
-- Run: mysql -u root -p < sewasetu1_mysql.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS sewasetu1;
USE sewasetu1;

-- ============================================================
-- TABLE 1: districts
-- ============================================================
CREATE TABLE districts (
    district_id     INT             AUTO_INCREMENT PRIMARY KEY,
    district_name   VARCHAR(60)     NOT NULL,
    district_name_hi VARCHAR(60),
    division        VARCHAR(60),
    hq_city         VARCHAR(60),
    area_sq_km      DECIMAL(10,2),
    population      BIGINT,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE 2: blocks
-- ============================================================
CREATE TABLE blocks (
    block_id        INT             AUTO_INCREMENT PRIMARY KEY,
    district_id     INT             NOT NULL,
    block_name      VARCHAR(80)     NOT NULL,
    block_hq        VARCHAR(80),
    gram_panchayats SMALLINT,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (district_id) REFERENCES districts(district_id)
);

-- ============================================================
-- TABLE 3: users
-- role_type drives chatbot access control
-- ============================================================
CREATE TABLE users (
    user_id         INT             AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(60)     NOT NULL UNIQUE,
    password        VARCHAR(60)     NOT NULL,
    role_type       ENUM('guest','citizen','govt_officer','admin','edm') NOT NULL,
    email           VARCHAR(120)    UNIQUE,
    mobile          VARCHAR(15)     NOT NULL,
    full_name       VARCHAR(100)    NOT NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    last_login      DATETIME,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    preferred_lang  ENUM('hi','en') NOT NULL DEFAULT 'hi',
    district_id     INT,
    block_id        INT,
    FOREIGN KEY (district_id) REFERENCES districts(district_id),
    FOREIGN KEY (block_id)    REFERENCES blocks(block_id)
);

-- ============================================================
-- TABLE 4: departments
-- ============================================================
CREATE TABLE departments (
    dept_id             INT             AUTO_INCREMENT PRIMARY KEY,
    dept_name           VARCHAR(120)    NOT NULL,
    dept_name_hi        VARCHAR(120),
    dept_head_user_id   INT,
    district_id         INT,
    nodal_email         VARCHAR(120),
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dept_head_user_id) REFERENCES users(user_id),
    FOREIGN KEY (district_id)       REFERENCES districts(district_id)
);

-- ============================================================
-- TABLE 5: citizens
-- One row per user with role_type = citizen
-- ============================================================
CREATE TABLE citizens (
    citizen_id      INT             AUTO_INCREMENT PRIMARY KEY,
    user_id         INT             NOT NULL UNIQUE,
    full_name       VARCHAR(100)    NOT NULL,
    dob             DATE            NOT NULL,
    gender          ENUM('male','female','other') NOT NULL,
    aadhaar_number  VARCHAR(12),
    samgra_id       VARCHAR(9),
    category        ENUM('general','obc','sc','st'),
    annual_income   DECIMAL(12,2),
    district_id     INT,
    block_id        INT,
    village_ward    VARCHAR(80),
    address_line    TEXT,
    pincode         VARCHAR(6),
    bpl_status      TINYINT(1)      NOT NULL DEFAULT 0,
    kyc_verified    TINYINT(1)      NOT NULL DEFAULT 0,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)     REFERENCES users(user_id),
    FOREIGN KEY (district_id) REFERENCES districts(district_id),
    FOREIGN KEY (block_id)    REFERENCES blocks(block_id)
);

-- ============================================================
-- TABLE 6: officers
-- One row per user with role_type = govt_officer
-- ============================================================
CREATE TABLE officers (
    officer_id          INT             AUTO_INCREMENT PRIMARY KEY,
    user_id             INT             NOT NULL UNIQUE,
    dept_id             INT             NOT NULL,
    designation         VARCHAR(80)     NOT NULL,
    district_id         INT             NOT NULL,
    block_id            INT,
    employee_code       VARCHAR(20)     NOT NULL UNIQUE,
    total_processed     INT             NOT NULL DEFAULT 0,
    avg_resolution_days DECIMAL(6,2),
    sla_breach_count    INT             NOT NULL DEFAULT 0,
    joining_date        DATE,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)     REFERENCES users(user_id),
    FOREIGN KEY (dept_id)     REFERENCES departments(dept_id),
    FOREIGN KEY (district_id) REFERENCES districts(district_id),
    FOREIGN KEY (block_id)    REFERENCES blocks(block_id)
);

-- ============================================================
-- TABLE 7: services
-- All certificates and services available on the portal
-- ============================================================
CREATE TABLE services (
    service_id              INT             AUTO_INCREMENT PRIMARY KEY,
    service_name            VARCHAR(150)    NOT NULL,
    service_name_hi         VARCHAR(150),
    department_id           INT             NOT NULL,
    category                ENUM('certificate','license','welfare','grievance') NOT NULL,
    fee_amount              DECIMAL(8,2)    NOT NULL DEFAULT 0.00,
    sla_days                SMALLINT        NOT NULL,
    required_docs           JSON,
    eligibility_criteria    TEXT,
    is_online               TINYINT(1)      NOT NULL DEFAULT 1,
    is_active               TINYINT(1)      NOT NULL DEFAULT 1,
    output_format           ENUM('pdf','physical','digital_signed'),
    validity_days           INT,
    created_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(dept_id)
);

-- ============================================================
-- TABLE 8: applications
-- Core transaction — one row per service request
-- ============================================================
CREATE TABLE applications (
    application_id      VARCHAR(20)     PRIMARY KEY,
    citizen_id          INT             NOT NULL,
    service_id          INT             NOT NULL,
    department_id       INT             NOT NULL,
    district_id         INT             NOT NULL,
    block_id            INT,
    assigned_officer    INT,
    status              ENUM('submitted','under_review','pending_docs','approved','rejected','issued')
                                        NOT NULL DEFAULT 'submitted',
    submitted_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_updated_at     DATETIME        ON UPDATE CURRENT_TIMESTAMP,
    approved_at         DATETIME,
    rejection_reason    TEXT,
    fee_paid            TINYINT(1)      NOT NULL DEFAULT 0,
    payment_ref         VARCHAR(50),
    documents_json      JSON,
    sla_breach          TINYINT(1)      NOT NULL DEFAULT 0,
    priority_flag       TINYINT(1)      NOT NULL DEFAULT 0,
    certificate_url     TEXT,
    remarks             TEXT,
    FOREIGN KEY (citizen_id)       REFERENCES citizens(citizen_id),
    FOREIGN KEY (service_id)       REFERENCES services(service_id),
    FOREIGN KEY (department_id)    REFERENCES departments(dept_id),
    FOREIGN KEY (district_id)      REFERENCES districts(district_id),
    FOREIGN KEY (block_id)         REFERENCES blocks(block_id),
    FOREIGN KEY (assigned_officer) REFERENCES users(user_id)
);

-- ============================================================
-- TABLE 9: application_timeline
-- Append-only status history for every application
-- ============================================================
CREATE TABLE application_timeline (
    log_id          BIGINT          AUTO_INCREMENT PRIMARY KEY,
    application_id  VARCHAR(20)     NOT NULL,
    from_status     ENUM('submitted','under_review','pending_docs','approved','rejected','issued'),
    to_status       ENUM('submitted','under_review','pending_docs','approved','rejected','issued') NOT NULL,
    changed_by      INT,
    changed_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    remarks         TEXT,
    ip_address      VARCHAR(45),
    channel         ENUM('portal','mobile_app','chatbot','bulk_upload'),
    FOREIGN KEY (application_id) REFERENCES applications(application_id),
    FOREIGN KEY (changed_by)     REFERENCES users(user_id)
);

-- ============================================================
-- TABLE 10: admin_config
-- Portal settings and feature flags
-- ============================================================
CREATE TABLE admin_config (
    config_id       INT             AUTO_INCREMENT PRIMARY KEY,
    config_key      VARCHAR(100)    NOT NULL UNIQUE,
    config_value    TEXT            NOT NULL,
    scope           ENUM('global','district','department') NOT NULL DEFAULT 'global',
    scope_id        INT,
    updated_by      INT,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    description     TEXT,
    FOREIGN KEY (updated_by) REFERENCES users(user_id)
);

-- ============================================================
-- TABLE 11: permissions
-- Role x resource access control matrix
-- ============================================================
CREATE TABLE permissions (
    perm_id     INT             AUTO_INCREMENT PRIMARY KEY,
    role_type   ENUM('guest','citizen','govt_officer','admin','edm') NOT NULL,
    resource    VARCHAR(100)    NOT NULL,
    can_read    TINYINT(1)      NOT NULL DEFAULT 0,
    can_write   TINYINT(1)      NOT NULL DEFAULT 0,
    can_export  TINYINT(1)      NOT NULL DEFAULT 0,
    can_delete  TINYINT(1)      NOT NULL DEFAULT 0,
    UNIQUE KEY uq_role_resource (role_type, resource)
);

-- ============================================================
-- TABLE 12: edm_reports
-- Monthly KPI snapshots per district for eDM officials
-- ============================================================
CREATE TABLE edm_reports (
    edm_report_id       INT             AUTO_INCREMENT PRIMARY KEY,
    district_id         INT             NOT NULL,
    block_id            INT,
    report_period       DATE            NOT NULL,
    total_applications  INT             DEFAULT 0,
    approved_count      INT             DEFAULT 0,
    rejected_count      INT             DEFAULT 0,
    pending_count       INT             DEFAULT 0,
    avg_processing_days DECIMAL(6,2),
    sla_breaches        INT             DEFAULT 0,
    grievances_filed    INT             DEFAULT 0,
    grievances_resolved INT             DEFAULT 0,
    csc_active_count    INT             DEFAULT 0,
    internet_uptime_pct DECIMAL(5,2),
    operator_count      INT             DEFAULT 0,
    generated_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (district_id) REFERENCES districts(district_id),
    FOREIGN KEY (block_id)    REFERENCES blocks(block_id),
    UNIQUE KEY uq_edm_period (district_id, block_id, report_period)
);

-- ============================================================
-- TABLE 13: escalations
-- Applications flagged for senior review
-- ============================================================
CREATE TABLE escalations (
    escalation_id   INT             AUTO_INCREMENT PRIMARY KEY,
    application_id  VARCHAR(20)     NOT NULL,
    escalated_by    INT             NOT NULL,
    escalated_to    INT             NOT NULL,
    reason          TEXT,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at     DATETIME,
    FOREIGN KEY (application_id) REFERENCES applications(application_id),
    FOREIGN KEY (escalated_by)   REFERENCES users(user_id),
    FOREIGN KEY (escalated_to)   REFERENCES users(user_id)
);

-- ============================================================
-- TABLE 14: chat_sessions
-- One row per chatbot conversation
-- ============================================================
CREATE TABLE chat_sessions (
    session_id      VARCHAR(36)     PRIMARY KEY,
    user_id         INT,
    role_type       ENUM('guest','citizen','govt_officer','admin','edm') NOT NULL DEFAULT 'guest',
    started_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at        DATETIME,
    message_count   SMALLINT        NOT NULL DEFAULT 0,
    language        ENUM('hi','en') NOT NULL DEFAULT 'hi',
    device_type     ENUM('mobile','desktop','kiosk'),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- ============================================================
-- TABLE 15: chat_messages
-- Every message sent and received in the chatbot
-- ============================================================
CREATE TABLE chat_messages (
    msg_id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
    session_id          VARCHAR(36)     NOT NULL,
    sender              ENUM('user','bot') NOT NULL,
    message_text        TEXT            NOT NULL,
    intent              VARCHAR(80),
    entities_json       JSON,
    response_time_ms    INT,
    was_helpful         TINYINT(1),
    sent_at             DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_app_citizen     ON applications(citizen_id);
CREATE INDEX idx_app_status      ON applications(status);
CREATE INDEX idx_app_dept        ON applications(department_id);
CREATE INDEX idx_app_district    ON applications(district_id);
CREATE INDEX idx_app_officer     ON applications(assigned_officer);
CREATE INDEX idx_app_submitted   ON applications(submitted_at);
CREATE INDEX idx_app_sla         ON applications(sla_breach);
CREATE INDEX idx_timeline_app    ON application_timeline(application_id);
CREATE INDEX idx_timeline_date   ON application_timeline(changed_at);
CREATE INDEX idx_officer_dept    ON officers(dept_id, district_id);
CREATE INDEX idx_edm_period      ON edm_reports(district_id, report_period);
CREATE INDEX idx_msg_session     ON chat_messages(session_id);
CREATE INDEX idx_msg_intent      ON chat_messages(intent);

-- ============================================================
-- SEED: PERMISSIONS MATRIX
-- ============================================================
INSERT INTO permissions (role_type, resource, can_read, can_write, can_export, can_delete) VALUES
('guest',        'services',         1, 0, 0, 0),
('guest',        'applications',     0, 0, 0, 0),
('guest',        'officer_metrics',  0, 0, 0, 0),
('guest',        'reports',          0, 0, 0, 0),
('guest',        'district_reports', 0, 0, 0, 0),
('guest',        'user_mgmt',        0, 0, 0, 0),
('guest',        'edm_operations',   0, 0, 0, 0),
('citizen',      'services',         1, 0, 0, 0),
('citizen',      'applications',     1, 1, 1, 0),
('citizen',      'officer_metrics',  0, 0, 0, 0),
('citizen',      'reports',          0, 0, 0, 0),
('citizen',      'district_reports', 0, 0, 0, 0),
('citizen',      'user_mgmt',        0, 0, 0, 0),
('citizen',      'edm_operations',   0, 0, 0, 0),
('govt_officer', 'services',         1, 0, 0, 0),
('govt_officer', 'applications',     1, 1, 1, 0),
('govt_officer', 'officer_metrics',  1, 0, 1, 0),
('govt_officer', 'reports',          1, 0, 1, 0),
('govt_officer', 'district_reports', 0, 0, 0, 0),
('govt_officer', 'user_mgmt',        0, 0, 0, 0),
('govt_officer', 'edm_operations',   0, 0, 0, 0),
('admin',        'services',         1, 1, 1, 0),
('admin',        'applications',     1, 1, 1, 0),
('admin',        'officer_metrics',  1, 0, 1, 0),
('admin',        'reports',          1, 0, 1, 0),
('admin',        'district_reports', 1, 0, 1, 0),
('admin',        'user_mgmt',        1, 1, 1, 0),
('admin',        'edm_operations',   0, 0, 0, 0),
('edm',          'services',         1, 1, 1, 1),
('edm',          'applications',     1, 1, 1, 1),
('edm',          'officer_metrics',  1, 1, 1, 1),
('edm',          'reports',          1, 1, 1, 1),
('edm',          'district_reports', 1, 1, 1, 1),
('edm',          'user_mgmt',        1, 1, 1, 1),
('edm',          'edm_operations',   1, 1, 1, 1);

-- ============================================================
-- SEED: DEFAULT ADMIN CONFIG
-- ============================================================
INSERT INTO admin_config (config_key, config_value, scope, description) VALUES
('max_applications_per_day',    '500',               'global', 'Max new applications per day portal-wide'),
('sla_breach_alert_days',       '2',                 'global', 'Warn officers N days before SLA deadline'),
('chatbot_session_timeout_min', '30',                'global', 'Idle chatbot session timeout in minutes'),
('report_cache_ttl_sec',        '300',               'global', 'Report cache time-to-live in seconds'),
('otp_expiry_sec',              '180',               'global', 'OTP validity window in seconds'),
('default_language',            'hi',                'global', 'Default chatbot response language'),
('minio_bucket_reports',        'sewa-reports',      'global', 'Storage bucket for generated reports'),
('minio_bucket_certs',          'sewa-certificates', 'global', 'Storage bucket for issued certificates');

-- ============================================================
-- END OF SCHEMA
-- ============================================================
