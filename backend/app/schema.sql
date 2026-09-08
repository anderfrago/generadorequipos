CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('ADMIN','TEACHER')),
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classes (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, academic_year TEXT NOT NULL,
 evaluation_period TEXT NOT NULL DEFAULT 'INICIAL', code TEXT NOT NULL UNIQUE,
 active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS class_teachers (
 class_id TEXT NOT NULL REFERENCES classes(id), user_id TEXT NOT NULL REFERENCES users(id),
 PRIMARY KEY(class_id,user_id)
);
CREATE TABLE IF NOT EXISTS students (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', external_ref TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS enrollments (
 id TEXT PRIMARY KEY, class_id TEXT NOT NULL REFERENCES classes(id),
 student_id TEXT NOT NULL REFERENCES students(id), active INTEGER NOT NULL DEFAULT 1,
 token_hash TEXT UNIQUE, token_version INTEGER NOT NULL DEFAULT 0,
 UNIQUE(class_id,student_id)
);
CREATE TABLE IF NOT EXISTS submissions (
 id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL REFERENCES enrollments(id),
 revision INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','SUBMITTED')),
 confirmed INTEGER NOT NULL DEFAULT 0, answers TEXT NOT NULL DEFAULT '{}',
 conditions TEXT NOT NULL DEFAULT '[]', other_condition TEXT NOT NULL DEFAULT '',
 open_response TEXT NOT NULL DEFAULT '', result TEXT,
 questionnaire_version TEXT NOT NULL,
 created_at TEXT NOT NULL, saved_at TEXT NOT NULL, submitted_at TEXT,
 UNIQUE(enrollment_id,revision)
);
CREATE TABLE IF NOT EXISTS observations (
 enrollment_id TEXT PRIMARY KEY REFERENCES enrollments(id),
 author_id TEXT NOT NULL REFERENCES users(id), data TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relations (
 id TEXT PRIMARY KEY, class_id TEXT NOT NULL REFERENCES classes(id),
 student_a TEXT NOT NULL REFERENCES students(id), student_b TEXT NOT NULL REFERENCES students(id),
 type TEXT NOT NULL CHECK(type IN ('NO_JUNTAR','MEJOR_SEPARADOS','CONVIENE_JUNTOS')),
 comment TEXT NOT NULL DEFAULT '', CHECK(student_a<>student_b), UNIQUE(class_id,student_a,student_b)
);
CREATE TABLE IF NOT EXISTS proposals (
 id TEXT PRIMARY KEY, class_id TEXT NOT NULL REFERENCES classes(id),
 status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','VALIDATED')),
 kind TEXT NOT NULL, data TEXT NOT NULL, source_model TEXT NOT NULL,
 created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS manual_changes (
 id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL REFERENCES proposals(id),
 before_data TEXT NOT NULL, created_at TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, action TEXT NOT NULL,
 entity_id TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_enrollments_class ON enrollments(class_id);
CREATE INDEX IF NOT EXISTS idx_submissions_enrollment ON submissions(enrollment_id,revision DESC);
CREATE INDEX IF NOT EXISTS idx_proposals_class ON proposals(class_id,created_at DESC);
CREATE TABLE IF NOT EXISTS invitation_deliveries (
 id TEXT PRIMARY KEY,
 enrollment_id TEXT NOT NULL REFERENCES enrollments(id),
 fingerprint TEXT NOT NULL,
 recipient TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('SENDING','SENT','FAILED','UNKNOWN')),
 message TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 actor_id TEXT NOT NULL REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_invitation_enrollment ON invitation_deliveries(enrollment_id,created_at DESC);
