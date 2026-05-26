# KaamPaao

On-demand local-services PWA. Contains phone-OTP auth (customer + provider + admin), a provider-onboarding flow with KYC document uploads, and an admin approval queue.

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Generate a secret key and paste into .env as SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

python init_db.py            # creates instance/kaampaao.db
flask --app app run --debug  # http://127.0.0.1:5000
```

## Project layout

```
app.py                       Flask app, routes, forms, auth helpers
otp.py                       OTP issue/verify + pluggable delivery
uploads.py                   File save/delete/path helpers (provider docs)
init_db.py                   DB initializer (--reset for schema changes)
schema.sql                   users, otp_codes, provider_{profiles,documents,review_log}
templates/                   Jinja templates
  _brand_panel.html          Shared brand panel (auth pages)
  _site_footer.html          Site footer with "Register as a professional" link
  base.html                  Shell: meta, manifest, footer
  login.html / signup.html   Customer login & signup
  provider/signup.html       Provider account creation
  provider/profile.html      Personal/professional fields
  provider/documents.html    KYC document uploads
  provider/_summary.html     Read-only summary partial
  dashboards/                customer | provider (status-branched) | admin
  admin/                     providers_list | provider_detail
static/css/styles.css        Single stylesheet
static/js/auth.js            Phone OTP + signup phone-verify
instance/kaampaao.db         SQLite file (gitignored)
instance/uploads/            Provider document files (gitignored)
```

## Authentication model

- All roles use the same auth pages. `users.role` ∈ `{admin, customer, provider}`. After login, the server redirects to `/dashboard/<role>`.
- **Login is phone + OTP only** (`POST /login_otp`). Indian numbers only (`+91`, 10 digits starting 6-9). There is no password.
- **Sign-up** (creates `customer` accounts) collects name, email, and verified phone — no password. The phone is verified inline via OTP *before* the form can be submitted; the verified phone is held in `session` for 15 minutes and matched against the submitted phone on the server. **Phone is the unique account identifier** (rejected pre-OTP if already registered). Email is captured for contact/notifications but is not unique — multiple accounts may share an email.
- CSRF protected via Flask-WTF for all forms and AJAX OTP calls (`X-CSRFToken` header).
- OTPs: 6 digits, 5-min expiry, max 5 attempts, one request per phone+purpose per 30 sec.

### OTP delivery

Set `OTP_PROVIDER` in `.env`:
- `dev` (default) — print code to server console and echo it back in the JSON API so the page can show a dev banner under the phone input. **Never use in production.**
- `log` — print code to server console only; do not return it.
- Real providers (Twilio, MSG91, etc.) — add a `send()` branch in `otp.py`.

### Seeding an admin

Admins log in the same way as everyone else (phone + OTP). Set both env vars before running `init_db.py`:

```
SEED_ADMIN_NAME=Site Admin
SEED_ADMIN_EMAIL=admin@kaampaao.local
SEED_ADMIN_PHONE=+919999999999
```

### Schema changes during development

The schema has evolved (added `users.status`, plus `provider_profiles`, `provider_documents`, `provider_review_log`). If your `instance/kaampaao.db` predates these, reset it:

```bash
python init_db.py --reset
```

## Provider onboarding

Anyone can apply to be a service provider via the "Register as a professional" link in the site footer (`/provider/signup`).

1. **Account** — name + email + phone OTP. Creates `role='provider'`, `status='incomplete'`.
2. **Profile** — `/provider/profile` collects personal/address/identity (Aadhaar 12 digits, PAN regex), bank for payouts (account number, IFSC), service categories (≥1 of cleaning/plumbing/electrical/painting/repairs), sub-skills, years of experience, service-area pincodes, short bio.
3. **Documents** — `/provider/documents` collects profile photo, Aadhaar image, PAN image, address proof, cancelled cheque. **Trade certificate** is additionally required if the provider selected electrical or plumbing. JPG/PNG/PDF only, 5 MB max per file (server-enforced via `MAX_CONTENT_LENGTH`).
4. **Submit** — flips status to `pending`. Editing is locked while pending.
5. **Admin review** — at `/admin/providers`: list filterable by status, click into a detail page showing all fields + each uploaded document (previewable inline), then **Approve** / **Reject** / **Request more info**. Reject and Request-more-info require a note that the provider sees on their dashboard.
6. **Resubmit** — after reject or needs_info, the provider can edit and resubmit. The review log records every action.

Document files live in `instance/uploads/providers/<user_id>/`. Serving is gated by `/uploads/providers/<doc_id>` (owner or admin only).

## Production deployment

```bash
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export FLASK_ENV=production
gunicorn -w 3 -b 0.0.0.0:8000 app:app
```

Notes:
- `SESSION_COOKIE_SECURE` is enabled automatically when `FLASK_ENV=production`. Serve behind HTTPS.
- Put gunicorn behind nginx / Caddy for TLS, gzip, and static-file serving.
- Back up `instance/kaampaao.db` regularly.

## Out of scope (planned for later)

- OAuth / social login
- Real SMS provider (Twilio / MSG91 / AWS SNS) — `otp.py` is structured for a one-file swap
- Email verification + password reset email
- Real dashboards (booking flow, categories, provider matching, ratings)
- Service worker / offline caching (manifest hook is already in place)
- Rate limiting (`Flask-Limiter`)
- Logging / Sentry
