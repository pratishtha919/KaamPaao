CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    email      TEXT    NOT NULL,
    phone      TEXT    NOT NULL UNIQUE,
    role       TEXT    NOT NULL DEFAULT 'customer'
                       CHECK (role IN ('admin', 'customer', 'provider')),
    status     TEXT    NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active','incomplete','pending','approved','rejected','needs_info')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_users_role_status ON users(role, status);

CREATE TABLE IF NOT EXISTS otp_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone       TEXT    NOT NULL,
    purpose     TEXT    NOT NULL CHECK (purpose IN ('login', 'signup_verify')),
    code_hash   TEXT    NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    consumed_at TIMESTAMP,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_otp_phone_purpose ON otp_codes(phone, purpose);

CREATE TABLE IF NOT EXISTS provider_profiles (
    user_id               INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    dob                   DATE,
    gender                TEXT CHECK (gender IN ('male','female','other','prefer_not_to_say')),
    job_role              TEXT,
    address_street        TEXT,
    address_city          TEXT,
    address_state         TEXT,
    address_pincode       TEXT,
    aadhaar_number        TEXT,
    pan_number            TEXT,
    bank_holder           TEXT,
    bank_account          TEXT,
    bank_ifsc             TEXT,
    categories_json       TEXT NOT NULL DEFAULT '[]',
    sub_skills            TEXT,
    years_experience      INTEGER,
    service_pincodes_json TEXT NOT NULL DEFAULT '[]',
    bio                   TEXT,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS provider_documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind          TEXT    NOT NULL CHECK (kind IN (
                      'profile_photo','aadhaar_image','pan_image',
                      'address_proof','cancelled_cheque','trade_certificate'
                  )),
    file_path     TEXT    NOT NULL,
    mime_type     TEXT    NOT NULL,
    original_name TEXT    NOT NULL,
    size_bytes    INTEGER NOT NULL,
    uploaded_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_provider_docs_user ON provider_documents(user_id);

CREATE TABLE IF NOT EXISTS provider_review_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    actor_id   INTEGER REFERENCES users(id),
    action     TEXT    NOT NULL CHECK (action IN
                   ('submitted','approved','rejected','needs_info','resubmitted')),
    note       TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_review_log_user ON provider_review_log(user_id, id DESC);
