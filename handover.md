# KaamPaao — agent-to-agent handover

This file is everything an incoming agent needs to pick up work on the KaamPaao project without asking the user. Read top-to-bottom once; thereafter use it as a reference.

---

## 1. Product

**KaamPaao** is an on-demand local-services PWA built for the Indian market. The product premise (described by the user verbatim early in the session):

> "KaamPaao is an on demand service provider PWA where users can browse categories, select specific service and schedule a slot with instant and future bookings. System will assign bookings to available local service provider. User will provide rating when the service provider's job is done."

Roughly the Urban Company / TaskRabbit space. Service categories on the brand pitch are: **Cleaning, Plumbing, Electrical, Painting, Repairs**.

### Three user roles
- `customer` — books services (booking flow not yet built).
- `provider` — a verified professional who fulfils bookings.
- `admin` — reviews provider applications.

### What is shipped today
- Phone-OTP authentication for everyone.
- Customer signup (account creation only — there's no customer-side booking UI yet).
- Full provider onboarding: account → profile → KYC docs → submit → admin review → approve/reject/needs_info → edit & resubmit.
- Admin approval queue with per-application detail view and decision form.
- Provider dashboard branches on status (incomplete checklist, pending banner, approved banner, rejected/needs_info banners with reviewer notes).
- Site footer with "Register as a professional" CTA.
- Full-bleed responsive layout with sticky footer.
- Running as a user-level systemd service (`kaampaao.service`) via gunicorn.

### What is explicitly **not** built
- Service catalogue, booking creation, provider matching/dispatch, customer-facing provider listings.
- Customer dashboard beyond "Welcome".
- Provider dashboard beyond status branches (no jobs list, no calendar, no ratings).
- Real SMS provider (OTPs are dev-mode — printed to server console and echoed in the JSON API so the page shows them in an orange banner).
- Real Aadhaar / PAN / bank verification (we collect and store only).
- Service worker / installable PWA (manifest hooks exist; no SW).
- Email or SMS notifications on status change.
- Booking / payment / payout pipelines.
- Search, ratings, reviews.
- A real CI, tests-in-repo, deployment automation, GitHub remote.

---

## 2. The user — how to work with them

The user is the product owner / single decision-maker on this project. They iterate very quickly and are highly prescriptive about UI. Working notes:

- **Don't propose unsolicited features.** They want to direct the UI shape themselves. Implement exactly what they asked for; only deviate when an option is technically infeasible.
- **Ask clarifying questions for ambiguous asks**, but consolidate into one round (use AskUserQuestion with 1-4 multi-choice questions). They've explicitly said they want clarifications when the approach is ambiguous.
- **Be terse.** No emoji unless asked. Short status updates beat paragraphs. No trailing summaries of what you just did — they can read the diff.
- **They change their mind often.** Past decisions are not load-bearing; treat each session as fresh and confirm via memory/files what's currently true. Examples within this session: added phone OTP, then removed password entirely; introduced Phone/Email tabs, then removed Email login; tried prominent Sign Up button below Login, then removed it in favor of a footer link.
- **They explicitly enjoy starting/stopping the server themselves.** Don't auto-start.
- They've been entering and exiting Plan mode repeatedly. When you re-enter Plan mode, evaluate whether the existing plan file matches their current request; if not, overwrite. They will sometimes reject your `ExitPlanMode` to clarify their answers — re-ask with reformulated options.
- They tried to hand off a plan to "Ultraplan" (cloud planner) which requires a GitHub repo. The project is **not** a git repo today, so Ultraplan is unavailable until they `git init` and install the Claude GitHub app. They know this.
- Localisation context: Indian market. Phone is `+91` only, KYC fields are Aadhaar + PAN, bank fields use IFSC, address has pincode. Don't internationalise without being asked.

---

## 3. File layout

Project root: `/home/user1/ai_code/KaamPaao/`

```
KaamPaao/
├── app.py                       Flask app, all routes, forms, helpers
├── otp.py                       OTP issue/verify, pluggable delivery
├── uploads.py                   File save/delete/path-resolve helpers
├── init_db.py                   DB initialiser (supports --reset)
├── schema.sql                   All DDL
├── requirements.txt             Pinned deps
├── .env                         SECRET_KEY + config (gitignored)
├── .env.example                 Template
├── .gitignore                   instance/, venv/, .env, *.db, ...
├── README.md                    Human-facing README (kept reasonably current)
├── kaampaao.service             Systemd unit (committed; copy to ~/.config/systemd/user/)
├── handover.md                  THIS FILE
├── venv/                        Python virtualenv (gitignored)
├── instance/
│   ├── kaampaao.db              SQLite DB (gitignored)
│   └── uploads/providers/<user_id>/<kind>_<uuid>.<ext>
├── templates/
│   ├── base.html                Shell: meta, manifest, footer, flash region, skip link
│   ├── _brand_panel.html        Brand panel partial (auth pages)
│   ├── _site_footer.html        Site footer partial (everywhere)
│   ├── login.html               Phone-OTP login (single form, footer link to signup)
│   ├── signup.html              Customer signup (name + email + phone+OTP)
│   ├── provider/
│   │   ├── signup.html          Provider account creation
│   │   ├── profile.html         Profile form (4 sections, see §7)
│   │   ├── documents.html       File uploads (6 kinds, 2 required)
│   │   └── _summary.html        Read-only profile summary partial
│   ├── dashboards/
│   │   ├── customer.html        Welcome page + logout
│   │   ├── provider.html        Status-branched (incomplete | pending | approved | rejected | needs_info)
│   │   └── admin.html           Welcome + "Provider applications" link
│   └── admin/
│       ├── providers_list.html  Filterable application queue
│       └── provider_detail.html Full application view + decision form
└── static/
    ├── css/styles.css           Single stylesheet (custom properties + components)
    ├── js/auth.js               Phone OTP UI + signup phone verify
    ├── img/logo.svg             KaamPaao wordmark
    └── manifest.webmanifest     PWA manifest stub
```

External files relevant to the agent (outside the project):
```
/home/user1/.claude/plans/i-want-you-to-vast-stearns.md
    Current/last plan file. Reused across sessions — read at start of new
    planning sessions; overwrite for new tasks, edit for continuations.

/home/user1/.claude/projects/-home-user1-ai-code-KaamPaao/memory/
    MEMORY.md                    Index of memories.
    project_kaampaao.md          Project memory (kept in sync with major changes).

~/.config/systemd/user/kaampaao.service
    Active systemd unit, symlinked into default.target.wants/.

~/.claude/plugins/cache/claude-plugins-official/
    frontend-design/             Plugin (skill).
    playwright/                  Plugin with MCP server (npx @playwright/mcp).
                                 Tools don't load mid-session — restart Claude
                                 Code to surface browser_* tools.
```

---

## 4. Tech stack

- **Python 3.11.2** on Debian 12 (`thinkpad1`).
- **Flask 3.0.3** + **Flask-WTF 1.2.1** + **email-validator 2.2.0** + **python-dotenv 1.0.1** + **gunicorn 22.0.0**. See `requirements.txt`.
- **SQLite** (file-based at `instance/kaampaao.db`). Accessed via stdlib `sqlite3`, `Row` factory. JSON1 not used at SQL level; multi-value columns store JSON as TEXT and Python `json.loads/dumps` reads/writes.
- **Frontend:** vanilla HTML, Jinja, plain CSS (custom properties, no framework), plain JS (no build step). Inter font from Google Fonts.
- **No Node toolchain.** `node` is not on PATH. The Playwright plugin uses `npx` from a system install if/when it's invoked.
- venv at `/home/user1/ai_code/KaamPaao/venv`. Always activate it before running anything Python:
  ```bash
  source venv/bin/activate
  ```

---

## 5. Database

### Tables — `schema.sql`

```sql
users
  id            INTEGER PK AUTOINCREMENT
  name          TEXT NOT NULL
  email         TEXT NOT NULL                 -- NOT unique by design
  phone         TEXT NOT NULL UNIQUE          -- '+91XXXXXXXXXX' format
  role          TEXT NOT NULL DEFAULT 'customer'
                CHECK (role IN ('admin','customer','provider'))
  status        TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','incomplete','pending',
                                  'approved','rejected','needs_info'))
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

  Indexes: idx_users_phone(phone), idx_users_role_status(role, status)

otp_codes
  id            INTEGER PK AUTOINCREMENT
  phone         TEXT NOT NULL
  purpose       TEXT NOT NULL CHECK (purpose IN ('login','signup_verify'))
  code_hash     TEXT NOT NULL                 -- werkzeug.security pbkdf2 hash
  expires_at    TIMESTAMP NOT NULL
  attempts      INTEGER NOT NULL DEFAULT 0    -- counts every check, capped at 5
  consumed_at   TIMESTAMP                     -- NULL until verified
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

  Index: idx_otp_phone_purpose(phone, purpose)

provider_profiles                              -- 1:1 with users
  user_id               INTEGER PK FK -> users(id) ON DELETE CASCADE
  dob                   DATE
  gender                TEXT CHECK (gender IN ('male','female','other','prefer_not_to_say'))
  job_role              TEXT
  address_street        TEXT
  address_city          TEXT
  address_state         TEXT
  address_pincode       TEXT
  aadhaar_number        TEXT                   -- 12 digits, basic length check
  pan_number            TEXT                   -- regex [A-Z]{5}[0-9]{4}[A-Z]
  bank_holder           TEXT                   -- nullable
  bank_account          TEXT                   -- nullable, 9-18 digits when set
  bank_ifsc             TEXT                   -- nullable, 11-char IFSC when set
  categories_json       TEXT NOT NULL DEFAULT '[]'    -- JSON array of category keys
  sub_skills            TEXT                   -- free-text, ≤200 chars
  years_experience      INTEGER                -- 0-60
  service_pincodes_json TEXT NOT NULL DEFAULT '[]'    -- JSON array of 6-digit pincodes
  bio                   TEXT                   -- ≤500 chars
  updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

provider_documents                             -- 1:many with users
  id            INTEGER PK AUTOINCREMENT
  user_id       INTEGER FK -> users(id) ON DELETE CASCADE
  kind          TEXT NOT NULL CHECK (kind IN (
                  'profile_photo','aadhaar_image','pan_image',
                  'address_proof','cancelled_cheque','trade_certificate'))
  file_path     TEXT NOT NULL                  -- relative to <instance>/
  mime_type     TEXT NOT NULL
  original_name TEXT NOT NULL
  size_bytes    INTEGER NOT NULL
  uploaded_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
  UNIQUE(user_id, kind)                        -- one current file per kind

  Index: idx_provider_docs_user(user_id)

provider_review_log                            -- append-only audit
  id          INTEGER PK AUTOINCREMENT
  user_id     INTEGER FK -> users(id) ON DELETE CASCADE  -- the provider
  actor_id    INTEGER FK -> users(id)         -- NULL when provider self-acts (submit/resubmit)
  action      TEXT NOT NULL CHECK (action IN
                ('submitted','approved','rejected','needs_info','resubmitted'))
  note        TEXT                            -- required for reject/needs_info
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

  Index: idx_review_log_user(user_id, id DESC)
```

### Writing pattern — upserts
- `provider_profiles`: `INSERT INTO ... ON CONFLICT(user_id) DO UPDATE SET ... updated_at=CURRENT_TIMESTAMP`
- `provider_documents`: `INSERT INTO ... ON CONFLICT(user_id, kind) DO UPDATE SET ... uploaded_at=CURRENT_TIMESTAMP`
- `provider_review_log`: always INSERT (append only).
- `users.status`: simple UPDATE via the admin decision route.

### Reset / migration
`init_db.py --reset` drops all five tables (children first to avoid FK noise) and re-applies the schema. There are no real migrations — for any schema change, drop + re-create. The user is fine with this because the DB is dev-only; document the `--reset` need in any plan that changes columns.

### Current DB rows (as of handover)
```
id  name          role      status      phone
1   Admin         admin     active      +919000000001
2   Riya Sharma   provider  incomplete  +919876543220
3   Young Person  provider  incomplete  +919876543299
```

- **Admin** id=1 — the seed admin. Login via phone-OTP using `9000000001` (no +91 on the form).
- **Riya** id=2 — provider with a saved profile (gender=female, job_role=Plumber, all required fields filled including bank details), but `status='incomplete'` because she never actually submitted in the final state. (An earlier verification script claimed she was approved end-to-end; that was a false-positive in the test — the actual approve POST 302'd because status wasn't `pending`. The form logic itself is correct; only the test assertion was wrong.) Her `provider_documents` has no rows.
- **Young Person** id=3 — exists only because of a DOB<18 rejection test; has no profile rows.

If you want a clean slate for browser testing, run `python init_db.py --reset` then INSERT an admin (or set `SEED_ADMIN_*` env vars before reset). The unit file pulls envs from `.env` — currently it has SECRET_KEY, FLASK_ENV=development, DATABASE_PATH=kaampaao.db.

---

## 6. Authentication model

**Phone-OTP only.** No passwords anywhere. No email-based login. (Email is collected at signup as a contact identifier and is intentionally **not unique** — at user's explicit request, multiple accounts may share an email.)

### Phone normalisation — `otp.py:normalize_phone`
- Accepts arbitrary user input.
- Strips non-digits.
- If digits start with `91` and len=12, drops the prefix.
- Requires final length = 10 and first digit ∈ {6-9}.
- Returns canonical `+91XXXXXXXXXX` or `None`.

### OTP delivery — `otp.py`
- 6-digit numeric code, 5-minute expiry, max 5 verification attempts, 30-second throttle per phone+purpose.
- Code is hashed with `werkzeug.security.generate_password_hash` (pbkdf2-sha256) before storage. We never store cleartext.
- Provider abstraction in `send_otp()`. Three options driven by `OTP_PROVIDER` env:
  - `dev` (default) — prints `[OTP dev] phone=... purpose=... code=...` to stdout AND returns the code in the JSON response (`dev_code`). The frontend shows it in an orange dashed banner under the phone input. **Never use in production.**
  - `log` — prints to stdout only.
  - Any other value — currently raises "Unknown provider". Add a branch in `otp.py:send_otp` to wire a real SMS gateway (Twilio, MSG91, AWS SNS). One file, one function — that's the only place to touch for delivery.
- `purge_expired(conn)` exists but isn't called anywhere yet. Safe to call ad-hoc; deletes rows older than 24h.

### Login flow
- `GET /login` → renders single phone form (`templates/login.html`).
- JS in `static/js/auth.js`:
  - Normalises the local 10-digit field to `+91XXXXXXXXXX` in a hidden `data-phone-e164` input.
  - "Send OTP" button POSTs JSON to `/api/otp/request` with `purpose='login'`. CSRF goes in `X-CSRFToken` header (the form's `csrf_token()` is read from the rendered HTML).
  - On success, OTP block appears; on dev mode, the dev banner shows the code.
  - The actual login is a regular form POST to `/login_otp` with `phone`, `code`, `csrf_token`.
- `POST /login_otp` verifies via `otp_mod.verify`, looks up `users` by phone, calls `_login_user(user, remember=False)` → `session['user_id']=user.id`, redirects to `/dashboard/<role>`. Generic `"Invalid phone number or code."` error on any failure (no phone-enumeration leak).
- Footer link: "New here? Create an account" → `/signup`.

### Signup flow (customer)
- `GET/POST /signup` → `templates/signup.html`.
- Form: name (letters+spaces only, see §7.2), email, phone (with inline Verify button).
- Phone verification happens via JS: POST `/api/otp/request` with `purpose='signup_verify'` → user types code → POST `/api/otp/verify` → server calls `_mark_phone_verified(phone)` which writes `session['verified_phone']=phone` and a timestamp.
- The form submit-handler in JS refuses to submit unless `verifiedPhone === pf.sync()` (current input matches the verified one).
- Server-side `SignupForm.validate_phone`:
  1. Normalises.
  2. Rejects if `_get_user_by_phone(normalized)` returns a row (duplicate).
  3. Rejects unless `_phone_is_verified_in_session(normalized)` (matches session + within `VERIFIED_PHONE_TTL = 15 minutes`).
- On success: `INSERT INTO users ... role='customer'`, auto-login, redirect to `/dashboard/customer`.
- **Pre-OTP duplicate check** at `/api/otp/request` (when `purpose='signup_verify'`) returns `409 {error: phone_exists, message: "An account with this phone number already exists."}`. This is so a user who enters an already-registered number sees the error *before* an OTP is generated. JS displays the message inline under the phone field (`[data-phone-error]`), not in the OTP block.

### Signup flow (provider)
- `GET/POST /provider/signup` → `templates/provider/signup.html`. Identical UX to customer signup, different heading & route. Reuses the same `signup_verify` OTP purpose, same JS (template includes `data-form="signup"`).
- Successful provider signup INSERTs `role='provider', status='incomplete'`, auto-login, redirect to `/dashboard/provider`.

### Session & CSRF
- `Flask-WTF CSRFProtect(app)` is on for everything.
- JSON endpoints (`/api/otp/*`) accept the token via `X-CSRFToken` header.
- POST forms include `{{ form.csrf_token }}` or `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- Session cookie: `HTTPONLY=True`, `SAMESITE='Lax'`, `SECURE=True` only when `FLASK_ENV=production`.
- `_login_user` calls `session.clear()` before setting `user_id` — **this invalidates any CSRF token issued before login**. If you ever extract a token from a GET that happens before login, expect a 400 on the next POST. Fetch CSRF fresh after login.
- `SECRET_KEY` from env. App refuses to start in production without it. In dev it falls back to a hardcoded warning string.
- `?next=` redirects honored only when `_is_safe_next` passes (same host).

---

## 7. Forms — `app.py`

All forms live in `app.py` (no `forms.py` split — the user prefers cohesion).

### 7.1 `SignupForm` & `ProviderSignupForm`
Same fields (name, email, phone) and same `validate_phone`. Kept as **separate classes** for independent evolution (per user-confirmed plan decision). `validate_phone` does normalisation + duplicate check + session-verified check.

### 7.2 Name validator (both signup forms)
- Filter: collapses whitespace (`" ".join(v.split())`).
- Validators: `DataRequired()`, `Length(min=2, max=80)`, `Regexp(NAME_REGEX, message=NAME_MESSAGE)`.
- `NAME_REGEX = r"^[A-Za-z][A-Za-z\s]*$"` — must start with a letter; letters and spaces only.
- `NAME_MESSAGE = "Letters and spaces only."`
- This was added at the user's request — they specified "allow only alphabetical chars - a to z and A to Z" for the name field. We allow spaces for multi-word names like "Riya Sharma".

### 7.3 `ProviderProfileForm` — four-section order **must be preserved**
The user dictated this exact order; templates render fieldsets in this sequence. WTForms doesn't enforce order but Python class attribute order is preserved on iteration.

**Section 1 — Private details**
- `dob` — `DateField`, required, `_validate_adult` (rejects under-18).
- `gender` — `SelectField(choices=GENDER_CHOICES)`, required.
  - `GENDER_CHOICES = [('male','Male'), ('female','Female'), ('other','Other'), ('prefer_not_to_say','Prefer not to say')]`.
- `aadhaar_number` — `Regexp(r"^\d{12}$")`. Length-only check; no Verhoeff. Filter strips non-digits.
- `pan_number` — `Regexp(r"^[A-Z]{5}[0-9]{4}[A-Z]$")`. Filter upper-cases.

**Section 2 — Professional info**
- `job_role` — `StringField`, required, `Length(min=2, max=80)`. Examples in placeholder: "Plumber, House cleaner".
- `years_experience` — `IntegerField`, `NumberRange(min=0, max=60)`. Label is "Experience (years)".
- `address_street` — required, ≤200 chars.
- `address_city`, `address_state` — required, ≤80 chars.
- `address_pincode` — `Regexp(r"^\d{6}$")`.
- `categories` — `SelectMultipleField(choices=SERVICE_CATEGORIES)`, ≥1 required.
  - `SERVICE_CATEGORIES = [('cleaning','Cleaning'), ('plumbing','Plumbing'), ('electrical','Electrical'), ('painting','Painting'), ('repairs','Repairs')]`.
- `sub_skills` — optional, free text, ≤200 chars.
- `service_pincodes` — comma-separated text; custom `_validate_service_pincodes` splits & validates each as 6-digit Indian pincode. Saved as JSON list to `service_pincodes_json`.

**Section 3 — Account details (all `Optional()`)**
- `bank_holder` — optional, ≤80.
- `bank_account` — optional, `Regexp(r"^\d{9,18}$")`, filter strips non-digits.
- `bank_ifsc` — optional, `Regexp(r"^[A-Z]{4}0[A-Z0-9]{6}$")`, filter upper-cases.

**Section 4 — Bio**
- `bio` — `TextAreaField`, required, ≤500 chars.

**Completeness check** — `_profile_complete(profile)` walks `PROFILE_REQUIRED_COLUMNS`:
```python
("dob","gender","job_role","years_experience",
 "address_street","address_city","address_state","address_pincode",
 "aadhaar_number","pan_number","bio")
```
plus a check that `_decode_list(categories_json)` is non-empty. **Bank fields are deliberately excluded** — they're post-approval-optional.

### 7.4 `ProviderDocumentsForm`
Six `FileField`s, all with `FileAllowed(['jpg','jpeg','png','pdf'])`, **no `FileRequired`**. Required-set for submission lives on `REQUIRED_DOC_KINDS`:
```python
REQUIRED_DOC_KINDS = ("profile_photo", "aadhaar_image")
```
The other four (`pan_image`, `address_proof`, `cancelled_cheque`, `trade_certificate`) are *uploadable but not required*. There used to be a conditional trade-certificate rule for electrical/plumbing — **removed** at user request. There's no `_trade_cert_required` helper anymore.

### 7.5 `DecisionForm` (admin)
- `action` — `RadioField` over `[('approve','Approve'), ('reject','Reject'), ('needs_info','Request more info')]`. Required.
- `note` — `TextAreaField`, optional at WTForms level. Server-side check in the route requires non-empty `note` when `action ∈ {reject, needs_info}`.

---

## 8. Routes — `app.py`

All registered inside `_register_routes(app)`. Helpers nested inside that function rely on closure scope; order of definition within `_register_routes` doesn't matter because lookups happen at call time.

### Public
| Method | Path | Behavior |
|---|---|---|
| GET | `/` | Logged in → role dashboard; else → `/login`. |
| GET | `/login` | Render login page. Redirects to dashboard if already logged in. |
| POST | `/login_otp` | Phone-OTP login. Honours `?next=` if safe. |
| GET/POST | `/signup` | Customer signup. |
| GET/POST | `/provider/signup` | Provider account creation (status=`incomplete`). |
| POST | `/logout` | `session.clear()`, redirect to `/login`. |

### OTP JSON API
| Method | Path | Behavior |
|---|---|---|
| POST | `/api/otp/request` | Body: `{phone, purpose}`. Returns `{ok, dev_code?, ...}`. Pre-rejects duplicate phone for `signup_verify` purpose with HTTP 409. Throttle: HTTP 429. |
| POST | `/api/otp/verify` | Body: `{phone, purpose, code}`. On success for `signup_verify`, marks phone verified in session for 15 min. |

### Provider (require `role='provider'` via `_require_role('provider')`)
| Method | Path | Behavior |
|---|---|---|
| GET | `/dashboard/provider` | Status-branched UI; computes `profile_complete`, `missing_docs`, `can_submit`, latest review-log note. |
| GET/POST | `/provider/profile` | Edit profile. Blocked by `_editable_or_redirect` when status=`pending`. Approved providers **can** edit (this was relaxed so they can add bank details post-approval). |
| GET/POST | `/provider/documents` | Upload files. Same edit lock as profile. Saved via `uploads.save_document`; old file deleted on replace. |
| POST | `/provider/submit` | Validates completeness; flips `incomplete`/`rejected`/`needs_info` → `pending`; appends `submitted` or `resubmitted` to review log. |
| GET | `/uploads/providers/<int:doc_id>` | Guarded file serving. 403 unless `user.id == doc.user_id` OR `role=='admin'`. Login redirect for anonymous. Uses `send_from_directory(app.instance_path, doc.file_path, max_age=0)`. |

### Admin (require `role='admin'`)
| Method | Path | Behavior |
|---|---|---|
| GET | `/dashboard/admin` | Shows pending count + link to applications list. |
| GET | `/admin/providers` | List filtered by `?status=pending|approved|rejected|needs_info|all` (default `pending`). |
| GET | `/admin/providers/<int:user_id>` | Full detail: profile, docs (preview tiles), review log, decision form. |
| POST | `/admin/providers/<int:user_id>/decision` | Updates `users.status`, appends review log. Only valid when current status is `pending`. Note required for reject/needs_info. |

### Dashboards (per-role)
- `/dashboard/customer`, `/dashboard/provider`, `/dashboard/admin` — each gated by `_require_role(...)` which redirects mismatched roles to their own dashboard with a flash.

### Error handling
- `@app.errorhandler(404)` → redirect to `/` (so stray paths bounce home rather than show a 404 page).
- `@app.errorhandler(413)` → friendly flash "File too large. Max 5 MB per upload." and redirect to `request.referrer` (or `/dashboard/provider`).

### Removed routes (don't re-add unprompted)
- `POST /login` (email + password) — removed when login became phone-OTP only.
- `GET /forgot` — removed alongside passwords.

---

## 9. File uploads — `uploads.py`

Small isolated module. Functions:

- `save_document(instance_path, user_id, kind, file_storage) -> dict`
  - Validates filename has an allowed extension (`jpg|jpeg|png|pdf`).
  - Generates unique filename: `f"{kind}_{uuid4().hex}.{ext}"`.
  - Ensures `<instance>/uploads/providers/<user_id>/` exists.
  - Saves the file. Returns `{file_path, mime_type, original_name, size_bytes}` for DB upsert.
  - Raises `ValueError` on missing/empty file or disallowed extension.
- `delete_document_file(instance_path, relative_path)` — best-effort `unlink(missing_ok=True)`, silently swallows errors. Called before document replacement.
- `absolute_path(instance_path, relative_path)` — resolves and **guards against `..` traversal** by checking `candidate.is_relative_to(upload_root.resolve())`. Raises `ValueError` if escape attempted.

Flask config (in `create_app`):
- `MAX_CONTENT_LENGTH = 6 * 1024 * 1024` (6 MB). Per-file UX limit advertised as 5 MB. Excess triggers 413 → friendly flash.
- `OTP_DEV_REVEAL` (computed) — True when `OTP_PROVIDER=dev`. Used by `/api/otp/request` to include `dev_code` in the JSON.

The `instance/` directory is gitignored, so all uploads stay out of version control.

---

## 10. Templates & frontend

### 10.1 Shell — `base.html`
- `<meta name="viewport" ...>` with `viewport-fit=cover`.
- `<meta name="theme-color" content="#FF6B35">`.
- `<meta name="apple-mobile-web-app-capable" content="yes">`.
- Inter from Google Fonts (preconnect + stylesheet).
- `<link rel="manifest" href="/static/manifest.webmanifest">`.
- Skip-to-content link.
- Flash region (top, fixed, with `role="alert"`).
- `<main id="main">{% block content %}{% endblock %}</main>` followed by `{% include "_site_footer.html" %}` and `{% block scripts %}`.

### 10.2 Site footer — `_site_footer.html`
- Brand line, About / Reviews / Help (placeholder anchors with `href="#"`), social icons (inline SVG, placeholder hrefs).
- **Active CTA**: `<a href="{{ url_for('provider_signup') }}" class="footer-cta">Register as a professional →</a>`.
- The CTA is hidden when `current_user` exists and is already a provider (avoid prompting them to "register again").

### 10.3 Auth pages — `login.html`, `signup.html`, `provider/signup.html`
- Use `_brand_panel.html` (left, 45%) + form-card (right, 55%) split via `.auth-layout` CSS Grid.
- Form-card max-width: 440px. Centered on mobile (single column).
- Customer/provider signup forms have phone field with inline Verify button, OTP block (hidden by default), `[data-phone-verified]` confirmation block (hidden by default), all driven by `static/js/auth.js`.

### 10.4 Provider profile form — `provider/profile.html`
Four `<fieldset class="form-fieldset">` blocks in the order specified in §7.3. Fields rendered with the `.field` / `.field-row` patterns (see §10.7). The breadcrumb at the top links Dashboard ↔ Documents.

### 10.5 Provider documents form — `provider/documents.html`
For each `kind` in `DOC_KINDS`:
- Label, an "Uploaded" badge if present.
- Inline preview: `<img>` for image MIMEs, `<a>` for PDF.
- File input (`accept=".jpg,.jpeg,.png,.pdf"`).
- A `*` mark next to required ones (`profile_photo`, `aadhaar_image`).

Single `<form enctype="multipart/form-data">`; partial uploads supported (each request processes whichever fields have non-empty files).

### 10.6 Provider dashboard — `dashboards/provider.html`
Single template, status-branched:

- `incomplete` → checklist:
  - "Complete your profile" link (passes when `profile_complete` is true and ≥1 category set).
  - One line per `required_kinds` (just `profile_photo` + `aadhaar_image`) — turns green when uploaded.
  - Submit button (disabled until `can_submit`).
- `pending` → blue "Awaiting review" banner + read-only summary (`{% include 'provider/_summary.html' %}`).
- `approved` → green "Approved" banner + summary + placeholder for booking UI.
- `rejected` / `needs_info` → warning banner with latest review-log note, plus "Edit profile" / "Edit documents" buttons and a Resubmit button.

### 10.7 Admin templates — `admin/providers_list.html`, `admin/provider_detail.html`
- List uses the existing `.tab.is-active` styles for filter tabs (`?status=...`).
- Detail page has sections: Personal info (kv-grid), Documents (preview tile grid), Review history (chronological), Decision panel (radios + note textarea). Small inline JS toggles `note` `required` attribute when reject/needs_info is selected. Server validates regardless.

### 10.8 CSS — `static/css/styles.css`
Design tokens (custom properties on `:root`):
```
--brand:       #FF6B35    (warm orange)
--brand-deep:  #E85826    (hover/active)
--ink:         #1F2937    (body text, headings)
--ink-muted:   #6B7280    (labels, helper text)
--surface:     #F9FAFB    (page background)
--card:        #FFFFFF
--border:      #E5E7EB
--focus-ring:  #FFB199    (orange-tinted, 3px outline)
--success:     #10B981
--success-bg:  #ECFDF5
--error:       #EF4444
--error-bg:    #FEF2F2

--radius-input: 8px
--radius-card:  16px
--shadow-card:  0 10px 30px rgba(31, 41, 55, 0.08)
```
Typography: Inter via Google Fonts (weights 400/500/600/700). Inputs 48px tall, 16px font (prevents iOS zoom-on-focus).

Key invariants:
- `[hidden] { display: none !important; }` is a **foundational rule** near the top of the stylesheet. It exists because rules like `.auth-form { display: flex }` and `.otp-block { display: flex }` would otherwise override the user-agent default for `[hidden]`. **Don't remove this.** Two bugs in this session traced back to it.
- Body is a sticky-footer flex column: `body { min-height: 100vh; min-height: 100dvh; display: flex; flex-direction: column; }`, `main#main { flex: 1 0 auto; width: 100%; }`. This makes the footer hug the bottom on short pages and the layout fill the viewport.
- `.dashboard`, `.provider-shell`, `.admin-shell` are full-width (`max-width: none`, `padding: 24px 32px`, 16px on `≤640px`). The user explicitly rejected a centered 960px column.
- Auth pages use a 45/55 CSS Grid (`.auth-layout`) on `≥768px`, single column below. Brand panel collapses to a 96px header strip on mobile.
- Status pills (`.status-pill.status-<state>`) have per-state colour pairs that also work for review-log actions (`submitted`/`resubmitted` reuse `pending`-like blue).
- Themed `<select>`: `appearance: none` + custom chevron via background gradients to match input height.
- File inputs styled via `::file-selector-button` so the button matches the brand.

### 10.9 JS — `static/js/auth.js`
Single IIFE. Handles:
- Phone input plumbing: `wirePhoneField(scope)` normalises the local 10-digit `[name="phone_local"]` into hidden `[data-phone-e164]` on every keystroke (`local.value.replace(/\D+/g, '').slice(0, 10)`).
- Login phone-OTP form (`data-form="login-otp"`): "Send OTP" → AJAX → OTP block appears with dev banner → user submits real form to `/login_otp`.
- Signup phone verification (`data-form="signup"`): inline Verify button → OTP block → green "Phone verified" panel → submit button (`[data-needs-phone-verified]`) enables only when `verifiedPhone === pf.sync()`.
- Submit-spinner enhancement on `[data-submit]` (replaces button label with `<span class="spinner">`).
- Auto-focus first empty required input on load.
- Inline `data-phone-error` slot for "phone already registered" and similar — replaces the old approach of putting errors inside the OTP block.

Conventions:
- The customer signup OTP input has `id="signup-otp"`. The provider signup template **reuses** this id (originally was `provider-otp` until we discovered the JS hardcoded `$('#signup-otp')`). Templates are separate routes/pages so the id collision is harmless.
- `csrfToken(form)` reads the `<input name="csrf_token">` value from the nearest form and sends it as `X-CSRFToken` for AJAX.
- All AJAX uses `fetch` with `credentials: 'same-origin'`.

---

## 11. PWA hooks (no service worker)

Currently the project is **PWA-ready** but not an installable PWA:

- `static/manifest.webmanifest` exists with `display: 'standalone'`, theme/background colors, single SVG icon (`sizes: "any"`).
- `<link rel="manifest">` + `theme-color` + `apple-mobile-web-app-capable` in `base.html`.
- No `serviceWorker.register()` call anywhere.
- No PNG icons (Android wants 192×192 and 512×512 PNGs, ideally maskable).
- Lighthouse PWA install check will fail.

Earlier in the session the user asked "This project is PWA?" — I confirmed it's PWA-ready not installable, then started scoping the addition (installable vs cached-shell vs full-offline-first). The user deferred and exited plan mode before the scope was locked in. The plan slot was overwritten with subsequent tasks. **Don't proactively add a service worker without explicit ask.**

---

## 12. Operations — gunicorn + systemd

### Unit file — `kaampaao.service` (committed)
```ini
[Unit]
Description=KaamPaao web service (Flask + gunicorn)
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/user1/ai_code/KaamPaao
EnvironmentFile=/home/user1/ai_code/KaamPaao/.env
ExecStart=/home/user1/ai_code/KaamPaao/venv/bin/gunicorn \
    --workers 2 \
    --bind 127.0.0.1:5000 \
    --access-logfile - \
    --error-logfile - \
    app:app
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

Installed as a **user-level service** at `~/.config/systemd/user/kaampaao.service`, enabled into `default.target.wants/`. No sudo used.

### Operating commands
```
systemctl --user status kaampaao       # current state
systemctl --user start|stop|restart kaampaao
systemctl --user enable|disable --now kaampaao
journalctl --user -u kaampaao -f       # live logs (includes dev OTPs)
loginctl enable-linger user1           # needs sudo; keeps service alive after logout
```

### Caveats noted to user
- Binds `127.0.0.1` only. For LAN/phone testing, change `--bind` to `0.0.0.0:5000` in the unit file and `systemctl --user restart kaampaao`.
- `FLASK_ENV=development` so cookies aren't `Secure`-flagged (we're on HTTP localhost). Flipping to `production` requires HTTPS in front (nginx/Caddy).
- For an actual production deploy: copy unit to `/etc/systemd/system/`, change `WantedBy=multi-user.target`, add explicit `User=`/`Group=`, set up nginx + LetsEncrypt, set `FLASK_ENV=production`.

### Dev alternative
If you want the auto-reload behaviour, stop the service and use the Flask dev server:
```
systemctl --user stop kaampaao
source venv/bin/activate
flask --app app run --debug
```

### `.env` contents (real values redacted)
```
SECRET_KEY=<set via openssl-rand-hex-32>
FLASK_ENV=development
DATABASE_PATH=kaampaao.db
# (no OTP_PROVIDER -> defaults to 'dev')
```

`.env.example` documents `SEED_ADMIN_NAME/EMAIL/PHONE`. The user has never seeded an admin via that — the current admin row was INSERTed by a verification script during the form-rework testing.

---

## 13. Verification recipes

The user expects we verify changes before claiming they work. Use the Flask test client; it's much faster than spinning up a real browser. All examples assume a freshly reset DB. Always wipe the OTP table between sequential admin logins to bypass the 30-second throttle.

### Reset to a known state
```python
import os, sqlite3, subprocess
if os.path.exists('instance/kaampaao.db'): os.remove('instance/kaampaao.db')
subprocess.check_call(['python', 'init_db.py'])
conn = sqlite3.connect('instance/kaampaao.db')
conn.execute("INSERT INTO users (id, name, email, phone, role, status) "
             "VALUES (1, 'Admin', 'a@x', '+919000000001', 'admin', 'active')")
conn.commit(); conn.close()
```

### CSRF helper
```python
import re
def csrf(html):
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    return m.group(1).decode() if m else None
```

### Important pitfalls
- **CSRF resets on login.** `_login_user` calls `session.clear()`; any token issued before login is invalid. Always fetch CSRF from a GET *after* login.
- **Throttle is per-phone+purpose.** Wipe `otp_codes` between admin re-logins or call `time.sleep(31)`. Wipe helper:
  ```python
  def wipe_otp():
      c = sqlite3.connect('instance/kaampaao.db'); c.execute("DELETE FROM otp_codes"); c.commit(); c.close()
  ```
- **WTForms multi-value fields** (`categories`): pass as a Python list in the `data=` dict — `{'categories': ['cleaning', 'plumbing']}`. Werkzeug expands this to repeated form values.
- **WTForms test-client `data=` cannot be a list of tuples** — must be a dict (or pass a `MultiDict`).
- **AUTOINCREMENT IDs survive reset only if `sqlite_sequence` is wiped.** Easier: don't rely on IDs being deterministic across runs. Look them up by phone:
  ```python
  conn = sqlite3.connect('instance/kaampaao.db'); conn.row_factory = sqlite3.Row
  pid = conn.execute("SELECT id FROM users WHERE phone = ?", ('+91...',)).fetchone()['id']
  ```
- **`admin_decision` route guards on `status='pending'`.** If you try to approve a provider who's still `incomplete`, the route 302s to the detail page with a flash error — not to the list. (This caused a false-positive in a past verification.)
- **Approved providers can edit profile.** This was a deliberate relaxation (so they can add bank details after approval). Don't add a lock back without checking with the user.

### Browser-driven verification
The Playwright MCP plugin is installed but its tools aren't loaded in the current session — Claude Code needs a restart. After restart, `browser_navigate`, `browser_click`, `browser_take_screenshot`, etc. will be available.

---

## 14. Memory & plan files (outside the project)

- **Plan file:** `/home/user1/.claude/plans/i-want-you-to-vast-stearns.md`
  - Shared across planning sessions; the harness loads it when entering plan mode.
  - Current contents reflect the most recent task (provider profile-form restructure). Overwrite for new tasks, edit for genuine continuations.
- **Project memory:** `/home/user1/.claude/projects/-home-user1-ai-code-KaamPaao/memory/`
  - `MEMORY.md` — index (auto-loaded into context every turn).
  - `project_kaampaao.md` — comprehensive snapshot of the project. Keep it in sync with major changes, especially auth-model changes and schema changes.

---

## 15. Iteration history (chronological summary of decisions made)

Reading these is useful when you suspect the user's current preference contradicts something I wrote. They've reversed earlier decisions many times.

1. Initial scope: login + signup page only. Flask + SQLite + vanilla HTML/CSS/JS.
2. Built email+password customer signup with split layout, brand panel, tab pattern (Log In | Sign Up).
3. Added phone-OTP **as a second login method** plus inline phone verification on signup.
4. **Removed email login entirely.** Login became phone-OTP only.
5. UI: replaced Log In/Sign Up tabs with Phone/Email method tabs, then removed the Email tab entirely. Login is now a single phone form.
6. Removed Sign Up button below Login in favor of a footer "Create an account" link (less prominent, less cluttered).
7. **Removed password fields from signup.** Schema lost the `password_hash` column. No passwords anywhere in the system.
8. **Removed email duplicate detection.** Email is no longer unique. Schema lost `UNIQUE COLLATE NOCASE` on email and the email index. Only phone duplicates are caught — pre-OTP, with the exact message `"An account with this phone number already exists."`.
9. CSS bug discovery: `display:flex` on `.auth-form`/`.otp-block`/`.phone-verified` was overriding the `hidden` attribute. Fixed with a foundational `[hidden] { display: none !important }` rule near the top of styles.css.
10. Added the **provider onboarding + admin approval** feature (largest chunk). New tables: `provider_profiles`, `provider_documents`, `provider_review_log`. New module: `uploads.py`. New templates under `provider/` and `admin/`. New routes (see §8). Required docs were initially 5 + conditional trade cert.
11. Layout: made the app full-bleed (removed `max-width: 960px` from dashboards/shells); body became a flex-column sticky-footer layout.
12. **Restructured the provider profile form** into a strict 4-section order (Private / Professional / Account / Bio) with new fields `gender` and `job_role`. Made bank fields **all optional** ("can be filled after approval"). Required docs shrunk to 2 (`profile_photo`, `aadhaar_image`). Trade-cert conditional logic removed. Approved providers can now edit their profile (this was the lock relaxation).
13. **Name validator** — added `Regexp(r"^[A-Za-z][A-Za-z\s]*$")` to both signup forms after the user said "allow only alphabetical chars - a to z and A to Z".
14. Set up gunicorn under user-level systemd as `kaampaao.service`. Replaced ad-hoc `flask run` with the service.

Things the user briefly considered and **deferred or rejected**:
- Full PWA enablement (service worker, PNG icons, install prompt) — deferred. Plan slot was opened then user exited before locking scope.
- Ultraplan handoff (cloud planner) — blocked because the project isn't a git repo.
- Removing Aadhaar/PAN/Categories from the profile entirely — user chose "keep all three under appropriate sections".
- Multi-step wizard for provider onboarding — user chose the two-page flow instead.

---

## 16. Plugins & MCP environment

`~/.claude/plugins/installed_plugins.json` lists:
- `frontend-design@claude-plugins-official` — surfaces as a skill (`frontend-design:frontend-design`), available now.
- `playwright@claude-plugins-official` — provides a `playwright` MCP server (`npx @playwright/mcp@latest`). **Tools don't load mid-session.** A Claude Code restart is required; after restart, `browser_navigate`, `browser_click`, `browser_take_screenshot`, etc. become available. This was noted to the user just before handover.

Other MCP servers attached at session start (per current ToolSearch):
- `claude.ai Gmail` (OAuth required, not authenticated).
- `claude.ai Google Calendar` (OAuth required, not authenticated).
- `claude.ai Google Drive` (OAuth required, not authenticated).

Available skills (per `/reload-plugins`):
- `frontend-design`, `update-config`, `keybindings-help`, `simplify`, `fewer-permission-prompts`, `loop`, `schedule`, `claude-api`, `init`, `review`, `security-review`.

---

## 17. Known issues / open items

- **Admin table** (`admin/providers_list.html`) is a 6-column HTML table. On very narrow phones it horizontal-scrolls. User accepted this for now but flagged it as a rough edge.
- **No tests in repo.** All verification has been ad-hoc Flask test client scripts run from the CLI. There's no pytest setup.
- **No git repo.** `git init` has not been run. This blocks Ultraplan and any GitHub-based tooling.
- **Approved provider's profile edits don't trigger re-review.** If they change Aadhaar/PAN/etc. post-approval, admin doesn't see the change unless they re-open the detail page. The user is aware; out of scope for now.
- **OTP for login on unregistered phones returns ok=True** (intentional, to avoid phone enumeration). The actual login attempt then fails with the generic error.
- **No background-cleanup of OTP rows.** `otp.purge_expired()` exists but isn't called by anything. Rows accumulate forever.
- **No password recovery flow.** Not needed because there are no passwords, but if you add one, the OTP infra is reusable.

---

## 18. Conventions to keep

- **No emoji in code, comments, or UI** unless the user explicitly asks. (System prompt level rule.)
- **Don't create documentation files** unless the user asks. (Same.) This handover file was explicitly requested.
- **Edit existing files in preference to creating new ones.**
- **Don't add tests, CI configs, or pre-commit hooks** unsolicited.
- **Comments are minimal.** Only explain WHY when non-obvious. No comments that describe WHAT the code does or reference the current PR / "added for X flow".
- **No backwards-compatibility shims.** If the user removes a field, drop the column, drop the validator, drop the template element. Don't leave dead code "in case".
- **The user wants edge-to-edge full-bleed layouts.** Don't reintroduce `max-width` on shells/dashboards.
- **The user wants minimal cross-page links.** Footer text links only — no big secondary CTAs unless asked.
- **Phone is the unique identifier.** Don't add UNIQUE to email. Don't add password. Don't propose OAuth.
- **Indian-only.** Don't internationalise phone, address, or bank fields.
- **Use Flask-WTF.** Don't reinvent CSRF or form parsing.
- **Use sqlite3 stdlib.** No ORM, no SQLAlchemy.
- **Inter font + the existing palette.** Don't introduce a new colour without asking.

---

## 19. Quick reference

- **Admin login:** phone `9000000001` (no +91), OTP in dev banner / server console.
- **Server:** `http://127.0.0.1:5000` via `systemctl --user status kaampaao`.
- **Live logs:** `journalctl --user -u kaampaao -f`.
- **DB:** `sqlite3 instance/kaampaao.db`.
- **Reset DB:** `python init_db.py --reset` (then re-seed admin if needed).
- **Dev OTPs are in the JSON response** (`dev_code` key) and on stdout — both. Banner on the page shows them automatically.

If anything in this file conflicts with the live code, **the live code wins** — update this file when you change the code. Always re-read `app.py`, `schema.sql`, and `static/css/styles.css` at the start of a new session to confirm current state before acting on assumptions.
