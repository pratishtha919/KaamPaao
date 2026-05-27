"""KaamPaao — Flask app.

Customer routes:
    GET  /                          -> dashboard if logged in, else /login
    GET  /login                     -> phone+OTP login page
    POST /login_otp                 -> phone+OTP authenticate, redirect by role
    GET  /signup                    -> customer signup page
    POST /signup                    -> create customer (phone must be OTP-verified)
    POST /logout                    -> clear session
    POST /api/otp/request           -> issue an OTP to a phone (JSON)
    POST /api/otp/verify            -> verify an OTP (JSON)

Provider routes:
    GET/POST /provider/signup       -> provider account creation
    GET/POST /provider/profile      -> personal/professional fields
    GET/POST /provider/documents    -> KYC document upload
    POST     /provider/submit       -> submit application for admin review
    GET      /uploads/providers/<id>-> guarded file serving

Admin routes:
    GET  /admin/providers           -> applications list (filterable)
    GET  /admin/providers/<id>      -> application detail + decision form
    POST /admin/providers/<id>/decision -> approve / reject / needs_info

Dashboards:
    GET  /dashboard/<role>          -> role-scoped (provider branches on status)
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    DateField,
    IntegerField,
    RadioField,
    SelectField,
    SelectMultipleField,
    StringField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

import otp as otp_mod
import uploads as uploads_mod

load_dotenv()

VERIFIED_PHONE_TTL = timedelta(minutes=15)

SERVICE_CATEGORIES = [
    ("cleaning", "Cleaning"),
    ("plumbing", "Plumbing"),
    ("electrical", "Electrical"),
    ("painting", "Painting"),
    ("repairs", "Repairs"),
]
CATEGORY_KEYS = {k for k, _ in SERVICE_CATEGORIES}

GENDER_CHOICES = [
    ("male", "Male"),
    ("female", "Female"),
    ("other", "Other"),
    ("prefer_not_to_say", "Prefer not to say"),
]
GENDER_KEYS = {k for k, _ in GENDER_CHOICES}

DOC_KINDS = (
    "profile_photo", "aadhaar_image", "pan_image",
    "address_proof", "cancelled_cheque", "trade_certificate",
)
DOC_LABELS = {
    "profile_photo": "Profile photo",
    "aadhaar_image": "Aadhaar card",
    "pan_image": "PAN card",
    "address_proof": "Address proof",
    "cancelled_cheque": "Cancelled cheque",
    "trade_certificate": "Trade certificate",
}
REQUIRED_DOC_KINDS = (
    "profile_photo", "aadhaar_image",
)

PROFILE_REQUIRED_COLUMNS = (
    "dob", "gender", "job_role",
    "address_street", "address_city", "address_state", "address_pincode",
    "aadhaar_number", "pan_number",
    "years_experience", "bio",
)

NAME_REGEX = r"^[A-Za-z][A-Za-z\s]*$"
NAME_MESSAGE = "Letters and spaces only."


# --- App setup --------------------------------------------------------------

def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    env = os.environ.get("FLASK_ENV", "development")
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        if env == "production":
            raise RuntimeError("SECRET_KEY must be set in production.")
        secret = "dev-only-insecure-change-me"

    app.config.update(
        SECRET_KEY=secret,
        DATABASE=str(
            Path(app.instance_path) / os.environ.get("DATABASE_PATH", "kaampaao.db")
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(env == "production"),
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        WTF_CSRF_TIME_LIMIT=None,
        OTP_DEV_REVEAL=(os.environ.get("OTP_PROVIDER", "dev").lower() == "dev"),
        # 6 MB request cap; per-file UX limit is 5 MB. The extra MB is overhead.
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
    )

    CSRFProtect(app)
    app.teardown_appcontext(_close_db)
    _register_routes(app)
    return app


# --- Database helpers -------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    if "db" not in g:
        from flask import current_app

        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def _close_db(_exc: BaseException | None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _get_user_by_phone(phone: str) -> sqlite3.Row | None:
    return _get_db().execute(
        "SELECT * FROM users WHERE phone = ?", (phone,)
    ).fetchone()


def _get_user_by_id(user_id: int) -> sqlite3.Row | None:
    return _get_db().execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def _get_provider_profile(user_id: int) -> sqlite3.Row | None:
    return _get_db().execute(
        "SELECT * FROM provider_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()


def _get_provider_docs_by_kind(user_id: int) -> dict[str, sqlite3.Row]:
    rows = _get_db().execute(
        "SELECT * FROM provider_documents WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {row["kind"]: row for row in rows}


def _get_review_log(user_id: int) -> list[sqlite3.Row]:
    return _get_db().execute(
        "SELECT l.*, u.name AS actor_name FROM provider_review_log l "
        "LEFT JOIN users u ON u.id = l.actor_id "
        "WHERE l.user_id = ? ORDER BY l.id DESC",
        (user_id,),
    ).fetchall()


def _latest_decision_note(user_id: int) -> str | None:
    row = _get_db().execute(
        "SELECT note FROM provider_review_log "
        "WHERE user_id = ? AND action IN ('rejected','needs_info') "
        "ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    return row["note"] if row else None


def _add_review_log(user_id: int, actor_id: int | None, action: str, note: str | None) -> None:
    db = _get_db()
    db.execute(
        "INSERT INTO provider_review_log (user_id, actor_id, action, note) "
        "VALUES (?, ?, ?, ?)",
        (user_id, actor_id, action, note),
    )
    db.commit()


def _decode_list(json_text: str | None) -> list[str]:
    if not json_text:
        return []
    try:
        value = json.loads(json_text)
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


# --- Provider completeness --------------------------------------------------

def _profile_complete(profile: sqlite3.Row | None) -> bool:
    if not profile:
        return False
    for col in PROFILE_REQUIRED_COLUMNS:
        value = profile[col]
        if value is None or (isinstance(value, str) and not value.strip()):
            return False
    if not _decode_list(profile["categories_json"]):
        return False
    return True


def _missing_docs(user_id: int) -> list[str]:
    have = _get_provider_docs_by_kind(user_id)
    return [k for k in REQUIRED_DOC_KINDS if k not in have]


def _can_submit(user_id: int, profile: sqlite3.Row | None) -> bool:
    return _profile_complete(profile) and not _missing_docs(user_id)


# --- Forms ------------------------------------------------------------------

class SignupForm(FlaskForm):
    name = StringField(
        "Full Name",
        validators=[
            DataRequired(),
            Length(min=2, max=80),
            Regexp(NAME_REGEX, message=NAME_MESSAGE),
        ],
        filters=[lambda v: " ".join(v.split()) if isinstance(v, str) else v],
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=254)],
        filters=[lambda v: v.strip().lower() if isinstance(v, str) else v],
    )
    phone = StringField(
        "Phone",
        validators=[DataRequired()],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )

    def validate_phone(self, field: StringField) -> None:
        normalized = otp_mod.normalize_phone(field.data)
        if not normalized:
            raise ValidationError("Enter a valid 10-digit Indian mobile number.")
        # Store normalized form back so downstream code uses it.
        field.data = normalized
        if _get_user_by_phone(normalized):
            raise ValidationError("An account with this phone number already exists.")
        if not _phone_is_verified_in_session(normalized):
            raise ValidationError("Please verify your phone number first.")


class ProviderSignupForm(FlaskForm):
    name = StringField(
        "Full Name",
        validators=[
            DataRequired(),
            Length(min=2, max=80),
            Regexp(NAME_REGEX, message=NAME_MESSAGE),
        ],
        filters=[lambda v: " ".join(v.split()) if isinstance(v, str) else v],
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=254)],
        filters=[lambda v: v.strip().lower() if isinstance(v, str) else v],
    )
    phone = StringField(
        "Phone",
        validators=[DataRequired()],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )

    def validate_phone(self, field: StringField) -> None:
        normalized = otp_mod.normalize_phone(field.data)
        if not normalized:
            raise ValidationError("Enter a valid 10-digit Indian mobile number.")
        field.data = normalized
        if _get_user_by_phone(normalized):
            raise ValidationError("An account with this phone number already exists.")
        if not _phone_is_verified_in_session(normalized):
            raise ValidationError("Please verify your phone number first.")


def _validate_adult(_form, field) -> None:
    if not field.data:
        return
    today = date.today()
    years = today.year - field.data.year - (
        (today.month, today.day) < (field.data.month, field.data.day)
    )
    if years < 18:
        raise ValidationError("You must be at least 18 years old.")


def _validate_service_pincodes(_form, field) -> None:
    if not field.data:
        return
    tokens = [t.strip() for t in field.data.split(",") if t.strip()]
    if not tokens:
        return
    for tok in tokens:
        if not (tok.isdigit() and len(tok) == 6):
            raise ValidationError(
                f"'{tok}' is not a valid 6-digit Indian pincode."
            )


class ProviderProfileForm(FlaskForm):
    # Private details
    dob = DateField("Date of birth", validators=[DataRequired(), _validate_adult])
    gender = SelectField(
        "Gender",
        choices=GENDER_CHOICES,
        validators=[DataRequired()],
    )
    aadhaar_number = StringField(
        "Aadhaar number",
        validators=[DataRequired(), Regexp(r"^\d{12}$",
                    message="Must be a 12-digit number.")],
        filters=[lambda v: "".join(ch for ch in v if ch.isdigit())
                 if isinstance(v, str) else v],
    )
    pan_number = StringField(
        "PAN number",
        validators=[DataRequired(), Regexp(r"^[A-Z]{5}[0-9]{4}[A-Z]$",
                    message="Format: ABCDE1234F.")],
        filters=[lambda v: v.strip().upper() if isinstance(v, str) else v],
    )

    # Professional info
    job_role = StringField(
        "Job role",
        validators=[DataRequired(), Length(min=2, max=80)],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )
    years_experience = IntegerField(
        "Experience (years)",
        validators=[DataRequired(), NumberRange(min=0, max=60)],
    )
    address_street = StringField(
        "Street address",
        validators=[DataRequired(), Length(max=200)],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )
    address_city = StringField(
        "City",
        validators=[DataRequired(), Length(max=80)],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )
    address_state = StringField(
        "State",
        validators=[DataRequired(), Length(max=80)],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )
    address_pincode = StringField(
        "Pincode",
        validators=[DataRequired(), Regexp(r"^\d{6}$",
                    message="Must be a 6-digit Indian pincode.")],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )
    categories = SelectMultipleField(
        "Service categories",
        choices=SERVICE_CATEGORIES,
        validators=[DataRequired(message="Select at least one category.")],
    )
    sub_skills = StringField(
        "Sub-skills (comma separated)",
        validators=[Optional(), Length(max=200)],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )
    service_pincodes = StringField(
        "Service-area pincodes (comma separated)",
        validators=[DataRequired(), _validate_service_pincodes],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )

    # Account details — optional, fillable post-approval
    bank_holder = StringField(
        "Account holder name",
        validators=[Optional(), Length(max=80)],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )
    bank_account = StringField(
        "Account number",
        validators=[Optional(), Regexp(r"^\d{9,18}$",
                    message="9 to 18 digits.")],
        filters=[lambda v: "".join(ch for ch in v if ch.isdigit())
                 if isinstance(v, str) else v],
    )
    bank_ifsc = StringField(
        "IFSC",
        validators=[Optional(), Regexp(r"^[A-Z]{4}0[A-Z0-9]{6}$",
                    message="11-character IFSC, e.g. SBIN0001234.")],
        filters=[lambda v: v.strip().upper() if isinstance(v, str) else v],
    )

    # Bio
    bio = TextAreaField(
        "Short bio",
        validators=[DataRequired(), Length(max=500)],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )


class ProviderDocumentsForm(FlaskForm):
    profile_photo = FileField(
        "Profile photo",
        validators=[FileAllowed(uploads_mod.ALLOWED_EXTENSIONS,
                                message="JPG, PNG, or PDF only.")],
    )
    aadhaar_image = FileField(
        "Aadhaar card",
        validators=[FileAllowed(uploads_mod.ALLOWED_EXTENSIONS,
                                message="JPG, PNG, or PDF only.")],
    )
    pan_image = FileField(
        "PAN card",
        validators=[FileAllowed(uploads_mod.ALLOWED_EXTENSIONS,
                                message="JPG, PNG, or PDF only.")],
    )
    address_proof = FileField(
        "Address proof",
        validators=[FileAllowed(uploads_mod.ALLOWED_EXTENSIONS,
                                message="JPG, PNG, or PDF only.")],
    )
    cancelled_cheque = FileField(
        "Cancelled cheque",
        validators=[FileAllowed(uploads_mod.ALLOWED_EXTENSIONS,
                                message="JPG, PNG, or PDF only.")],
    )
    trade_certificate = FileField(
        "Trade certificate",
        validators=[FileAllowed(uploads_mod.ALLOWED_EXTENSIONS,
                                message="JPG, PNG, or PDF only.")],
    )


class DecisionForm(FlaskForm):
    action = RadioField(
        "Decision",
        choices=[("approve", "Approve"),
                 ("reject", "Reject"),
                 ("needs_info", "Request more info")],
        validators=[DataRequired()],
    )
    note = TextAreaField(
        "Note to applicant",
        validators=[Optional(), Length(max=2000)],
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
    )


# --- Session-backed phone verification (signup flow) ------------------------

def _mark_phone_verified(phone: str) -> None:
    session["verified_phone"] = phone
    session["verified_phone_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _phone_is_verified_in_session(phone: str) -> bool:
    if session.get("verified_phone") != phone:
        return False
    ts = session.get("verified_phone_at")
    if not ts:
        return False
    when = datetime.fromisoformat(ts)
    return (datetime.now(timezone.utc) - when) <= VERIFIED_PHONE_TTL


def _clear_phone_verification() -> None:
    session.pop("verified_phone", None)
    session.pop("verified_phone_at", None)


# --- Auth helpers -----------------------------------------------------------

def _current_user() -> sqlite3.Row | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    if "user" not in g:
        g.user = _get_user_by_id(user_id)
    return g.user


def _login_user(user: sqlite3.Row, remember: bool) -> None:
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = bool(remember)


def _dashboard_url(role: str) -> str:
    return url_for(f"dashboard_{role}")


def _is_safe_next(target: str | None) -> bool:
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


# --- Routes -----------------------------------------------------------------

def _register_routes(app: Flask) -> None:

    @app.context_processor
    def inject_user() -> dict:
        return {"current_user": _current_user()}

    @app.route("/")
    def index():
        user = _current_user()
        if user:
            return redirect(_dashboard_url(user["role"]))
        return redirect(url_for("login"))

    @app.route("/login")
    def login():
        if _current_user():
            return redirect(_dashboard_url(_current_user()["role"]))
        return render_template("login.html")

    @app.route("/login_otp", methods=["POST"])
    def login_otp():
        if _current_user():
            return redirect(_dashboard_url(_current_user()["role"]))

        phone = otp_mod.normalize_phone(request.form.get("phone"))
        code = (request.form.get("code") or "").strip()
        if not phone:
            flash("Enter a valid 10-digit Indian mobile number.", "error")
            return redirect(url_for("login"))
        ok = otp_mod.verify(_get_db(), phone, "login", code)
        if not ok:
            flash("Invalid phone number or code.", "error")
            return redirect(url_for("login"))
        user = _get_user_by_phone(phone)
        if not user:
            # Don't reveal whether phone is registered.
            flash("Invalid phone number or code.", "error")
            return redirect(url_for("login"))
        _login_user(user, remember=False)
        next_url = request.args.get("next")
        if _is_safe_next(next_url):
            return redirect(next_url)
        return redirect(_dashboard_url(user["role"]))

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if _current_user():
            return redirect(_dashboard_url(_current_user()["role"]))

        form = SignupForm()
        if form.validate_on_submit():
            db = _get_db()
            db.execute(
                "INSERT INTO users (name, email, phone, role) "
                "VALUES (?, ?, ?, 'customer')",
                (
                    form.name.data,
                    form.email.data,
                    form.phone.data,  # already normalized by validate_phone
                ),
            )
            db.commit()
            user = _get_user_by_phone(form.phone.data)
            _clear_phone_verification()
            _login_user(user, remember=False)
            flash("Welcome to KaamPaao!", "success")
            return redirect(_dashboard_url("customer"))

        status = 400 if request.method == "POST" else 200
        return render_template("signup.html", signup_form=form), status

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You've been logged out.", "success")
        return redirect(url_for("login"))

    # --- OTP JSON API -------------------------------------------------------

    @app.route("/api/otp/request", methods=["POST"])
    def api_otp_request():
        data = request.get_json(silent=True) or request.form
        phone = otp_mod.normalize_phone(data.get("phone"))
        purpose = (data.get("purpose") or "").strip()
        if not phone:
            return jsonify(ok=False, error="invalid_phone",
                           message="Enter a valid 10-digit Indian mobile number."), 400
        if purpose not in otp_mod.PURPOSES:
            return jsonify(ok=False, error="invalid_purpose"), 400

        # Don't waste an OTP if the phone is already registered for signup.
        if purpose == "signup_verify" and _get_user_by_phone(phone):
            return jsonify(ok=False, error="phone_exists",
                           message="An account with this phone number already exists."), 409

        ok, result = otp_mod.issue(_get_db(), phone, purpose)
        if not ok:
            if result == "too_soon":
                return jsonify(ok=False, error="too_soon",
                               message="Please wait a few seconds before requesting another code."), 429
            return jsonify(ok=False, error="send_failed",
                           message="Could not send code. Try again."), 502

        payload = {"ok": True, "phone": phone, "purpose": purpose,
                   "ttl_seconds": int(otp_mod.OTP_TTL.total_seconds())}
        if app.config["OTP_DEV_REVEAL"] and result.dev_code:
            payload["dev_code"] = result.dev_code
        return jsonify(payload)

    @app.route("/api/otp/verify", methods=["POST"])
    def api_otp_verify():
        data = request.get_json(silent=True) or request.form
        phone = otp_mod.normalize_phone(data.get("phone"))
        purpose = (data.get("purpose") or "").strip()
        code = (data.get("code") or "").strip()
        if not phone or purpose not in otp_mod.PURPOSES:
            return jsonify(ok=False, error="invalid_request"), 400

        ok = otp_mod.verify(_get_db(), phone, purpose, code)
        if not ok:
            return jsonify(ok=False, error="invalid_code",
                           message="The code is incorrect or expired."), 400

        if purpose == "signup_verify":
            _mark_phone_verified(phone)
        return jsonify(ok=True, phone=phone, purpose=purpose)

    # --- Provider onboarding -----------------------------------------------

    @app.route("/provider/signup", methods=["GET", "POST"])
    def provider_signup():
        if _current_user():
            return redirect(_dashboard_url(_current_user()["role"]))

        form = ProviderSignupForm()
        if form.validate_on_submit():
            db = _get_db()
            db.execute(
                "INSERT INTO users (name, email, phone, role, status) "
                "VALUES (?, ?, ?, 'provider', 'incomplete')",
                (form.name.data, form.email.data, form.phone.data),
            )
            db.commit()
            user = _get_user_by_phone(form.phone.data)
            _clear_phone_verification()
            _login_user(user, remember=False)
            flash("Account created. Complete your profile to get verified.", "success")
            return redirect(url_for("dashboard_provider"))

        status = 400 if request.method == "POST" else 200
        return render_template("provider/signup.html", signup_form=form), status

    def _provider_or_redirect():
        guard = _require_role("provider")
        if guard is not None:
            return None, guard
        return _current_user(), None

    def _editable_or_redirect(user):
        if user["status"] == "pending":
            flash("Your application is locked while under review.", "error")
            return redirect(url_for("dashboard_provider"))
        return None

    @app.route("/provider/profile", methods=["GET", "POST"])
    def provider_profile():
        user, redirect_resp = _provider_or_redirect()
        if redirect_resp is not None:
            return redirect_resp
        gate = _editable_or_redirect(user)
        if gate is not None:
            return gate

        existing = _get_provider_profile(user["id"])
        form = ProviderProfileForm()
        if request.method == "GET" and existing:
            form.dob.data = (date.fromisoformat(existing["dob"])
                             if existing["dob"] else None)
            form.gender.data = existing["gender"]
            form.job_role.data = existing["job_role"]
            form.address_street.data = existing["address_street"]
            form.address_city.data = existing["address_city"]
            form.address_state.data = existing["address_state"]
            form.address_pincode.data = existing["address_pincode"]
            form.aadhaar_number.data = existing["aadhaar_number"]
            form.pan_number.data = existing["pan_number"]
            form.bank_holder.data = existing["bank_holder"]
            form.bank_account.data = existing["bank_account"]
            form.bank_ifsc.data = existing["bank_ifsc"]
            form.categories.data = _decode_list(existing["categories_json"])
            form.sub_skills.data = existing["sub_skills"]
            form.years_experience.data = existing["years_experience"]
            form.service_pincodes.data = ", ".join(
                _decode_list(existing["service_pincodes_json"])
            )
            form.bio.data = existing["bio"]

        if form.validate_on_submit():
            cats = [c for c in form.categories.data if c in CATEGORY_KEYS]
            pincodes = [t.strip() for t in form.service_pincodes.data.split(",")
                        if t.strip()]
            db = _get_db()
            db.execute(
                "INSERT INTO provider_profiles ("
                "  user_id, dob, gender, job_role,"
                "  address_street, address_city, address_state, address_pincode,"
                "  aadhaar_number, pan_number, bank_holder,"
                "  bank_account, bank_ifsc, categories_json, sub_skills,"
                "  years_experience, service_pincodes_json, bio, updated_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)"
                "ON CONFLICT(user_id) DO UPDATE SET"
                "  dob=excluded.dob,"
                "  gender=excluded.gender,"
                "  job_role=excluded.job_role,"
                "  address_street=excluded.address_street,"
                "  address_city=excluded.address_city,"
                "  address_state=excluded.address_state,"
                "  address_pincode=excluded.address_pincode,"
                "  aadhaar_number=excluded.aadhaar_number,"
                "  pan_number=excluded.pan_number,"
                "  bank_holder=excluded.bank_holder,"
                "  bank_account=excluded.bank_account,"
                "  bank_ifsc=excluded.bank_ifsc,"
                "  categories_json=excluded.categories_json,"
                "  sub_skills=excluded.sub_skills,"
                "  years_experience=excluded.years_experience,"
                "  service_pincodes_json=excluded.service_pincodes_json,"
                "  bio=excluded.bio,"
                "  updated_at=CURRENT_TIMESTAMP",
                (
                    user["id"],
                    form.dob.data.isoformat() if form.dob.data else None,
                    form.gender.data,
                    form.job_role.data,
                    form.address_street.data, form.address_city.data,
                    form.address_state.data, form.address_pincode.data,
                    form.aadhaar_number.data, form.pan_number.data,
                    form.bank_holder.data or None,
                    form.bank_account.data or None,
                    form.bank_ifsc.data or None,
                    json.dumps(cats),
                    form.sub_skills.data or None,
                    form.years_experience.data,
                    json.dumps(pincodes), form.bio.data,
                ),
            )
            db.commit()
            flash("Profile saved.", "success")
            return redirect(url_for("provider_profile"))

        status = 400 if request.method == "POST" else 200
        return render_template("provider/profile.html",
                               profile_form=form, user=user), status

    @app.route("/provider/documents", methods=["GET", "POST"])
    def provider_documents():
        user, redirect_resp = _provider_or_redirect()
        if redirect_resp is not None:
            return redirect_resp
        gate = _editable_or_redirect(user)
        if gate is not None:
            return gate

        profile = _get_provider_profile(user["id"])
        form = ProviderDocumentsForm()
        if form.validate_on_submit():
            db = _get_db()
            saved_any = False
            for kind in DOC_KINDS:
                fs = form[kind].data
                if not fs or not fs.filename:
                    continue
                try:
                    meta = uploads_mod.save_document(
                        app.instance_path, user["id"], kind, fs
                    )
                except ValueError as e:
                    flash(f"{DOC_LABELS[kind]}: {e}", "error")
                    continue
                # Delete the old file if any, then upsert the row.
                existing = db.execute(
                    "SELECT file_path FROM provider_documents "
                    "WHERE user_id = ? AND kind = ?",
                    (user["id"], kind),
                ).fetchone()
                if existing:
                    uploads_mod.delete_document_file(
                        app.instance_path, existing["file_path"]
                    )
                db.execute(
                    "INSERT INTO provider_documents ("
                    "  user_id, kind, file_path, mime_type,"
                    "  original_name, size_bytes, uploaded_at"
                    ") VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP) "
                    "ON CONFLICT(user_id, kind) DO UPDATE SET"
                    "  file_path=excluded.file_path,"
                    "  mime_type=excluded.mime_type,"
                    "  original_name=excluded.original_name,"
                    "  size_bytes=excluded.size_bytes,"
                    "  uploaded_at=CURRENT_TIMESTAMP",
                    (user["id"], kind, meta["file_path"], meta["mime_type"],
                     meta["original_name"], meta["size_bytes"]),
                )
                saved_any = True
            db.commit()
            if saved_any:
                flash("Documents updated.", "success")
            return redirect(url_for("provider_documents"))

        docs = _get_provider_docs_by_kind(user["id"])
        status = 400 if request.method == "POST" else 200
        return render_template(
            "provider/documents.html",
            docs_form=form, user=user, docs=docs,
            required_kinds=REQUIRED_DOC_KINDS,
            doc_kinds=DOC_KINDS, doc_labels=DOC_LABELS,
        ), status

    @app.route("/provider/submit", methods=["POST"])
    def provider_submit():
        user, redirect_resp = _provider_or_redirect()
        if redirect_resp is not None:
            return redirect_resp
        if user["status"] not in ("incomplete", "rejected", "needs_info"):
            flash("Application cannot be submitted in its current state.", "error")
            return redirect(url_for("dashboard_provider"))

        profile = _get_provider_profile(user["id"])
        if not _profile_complete(profile):
            flash("Complete your profile before submitting.", "error")
            return redirect(url_for("provider_profile"))
        missing = _missing_docs(user["id"])
        if missing:
            labels = ", ".join(DOC_LABELS[k] for k in missing)
            flash(f"Upload these documents first: {labels}.", "error")
            return redirect(url_for("provider_documents"))

        was_resubmit = user["status"] in ("rejected", "needs_info")
        db = _get_db()
        db.execute(
            "UPDATE users SET status = 'pending' WHERE id = ?", (user["id"],)
        )
        db.commit()
        _add_review_log(
            user["id"],
            actor_id=None,
            action="resubmitted" if was_resubmit else "submitted",
            note=None,
        )
        flash("Application submitted. We'll review it shortly.", "success")
        return redirect(url_for("dashboard_provider"))

    @app.route("/uploads/providers/<int:doc_id>")
    def serve_provider_doc(doc_id: int):
        user = _current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        doc = _get_db().execute(
            "SELECT * FROM provider_documents WHERE id = ?", (doc_id,)
        ).fetchone()
        if not doc:
            abort(404)
        if user["id"] != doc["user_id"] and user["role"] != "admin":
            abort(403)
        return send_from_directory(
            app.instance_path, doc["file_path"],
            mimetype=doc["mime_type"], max_age=0, conditional=True,
        )

    @app.errorhandler(413)
    def too_large(_e):
        flash("File too large. Max 5 MB per upload.", "error")
        return redirect(request.referrer or url_for("dashboard_provider")), 302

    # --- Admin: provider applications --------------------------------------

    @app.route("/admin/providers")
    def admin_providers_list():
        guard = _require_role("admin")
        if guard is not None:
            return guard
        status_filter = request.args.get("status", "pending")
        valid = {"pending", "approved", "rejected", "needs_info", "all"}
        if status_filter not in valid:
            status_filter = "pending"

        if status_filter == "all":
            rows = _get_db().execute(
                "SELECT u.id, u.name, u.phone, u.status, u.created_at,"
                "       p.categories_json,"
                "       (SELECT created_at FROM provider_review_log"
                "          WHERE user_id = u.id AND action IN ('submitted','resubmitted')"
                "          ORDER BY id DESC LIMIT 1) AS submitted_at "
                "FROM users u LEFT JOIN provider_profiles p ON p.user_id = u.id "
                "WHERE u.role = 'provider' "
                "ORDER BY u.id DESC"
            ).fetchall()
        else:
            rows = _get_db().execute(
                "SELECT u.id, u.name, u.phone, u.status, u.created_at,"
                "       p.categories_json,"
                "       (SELECT created_at FROM provider_review_log"
                "          WHERE user_id = u.id AND action IN ('submitted','resubmitted')"
                "          ORDER BY id DESC LIMIT 1) AS submitted_at "
                "FROM users u LEFT JOIN provider_profiles p ON p.user_id = u.id "
                "WHERE u.role = 'provider' AND u.status = ? "
                "ORDER BY u.id DESC",
                (status_filter,),
            ).fetchall()

        items = []
        for r in rows:
            items.append({
                "id": r["id"], "name": r["name"], "phone": r["phone"],
                "status": r["status"],
                "categories": _decode_list(r["categories_json"]),
                "submitted_at": r["submitted_at"],
            })
        return render_template(
            "admin/providers_list.html",
            user=_current_user(), items=items, status_filter=status_filter,
        )

    @app.route("/admin/providers/<int:user_id>")
    def admin_provider_detail(user_id: int):
        guard = _require_role("admin")
        if guard is not None:
            return guard
        provider = _get_user_by_id(user_id)
        if not provider or provider["role"] != "provider":
            abort(404)
        profile = _get_provider_profile(user_id)
        docs = _get_provider_docs_by_kind(user_id)
        log = _get_review_log(user_id)
        return render_template(
            "admin/provider_detail.html",
            user=_current_user(), provider=provider, profile=profile,
            docs=docs, doc_kinds=DOC_KINDS, doc_labels=DOC_LABELS,
            categories=_decode_list(profile["categories_json"]) if profile else [],
            service_pincodes=(_decode_list(profile["service_pincodes_json"])
                              if profile else []),
            log=log, decision_form=DecisionForm(),
        )

    @app.route("/admin/providers/<int:user_id>/decision", methods=["POST"])
    def admin_provider_decision(user_id: int):
        guard = _require_role("admin")
        if guard is not None:
            return guard
        provider = _get_user_by_id(user_id)
        if not provider or provider["role"] != "provider":
            abort(404)
        if provider["status"] != "pending":
            flash("This application is not in 'pending' state.", "error")
            return redirect(url_for("admin_provider_detail", user_id=user_id))

        form = DecisionForm()
        if not form.validate_on_submit():
            flash("Choose a decision.", "error")
            return redirect(url_for("admin_provider_detail", user_id=user_id))

        action = form.action.data
        note = form.note.data or None
        if action in ("reject", "needs_info") and not note:
            flash("A note is required when rejecting or requesting more info.",
                  "error")
            return redirect(url_for("admin_provider_detail", user_id=user_id))

        action_to_status = {
            "approve": "approved",
            "reject": "rejected",
            "needs_info": "needs_info",
        }
        new_status = action_to_status[action]
        db = _get_db()
        db.execute("UPDATE users SET status = ? WHERE id = ?",
                   (new_status, user_id))
        db.commit()
        log_action = {"approve": "approved", "reject": "rejected",
                      "needs_info": "needs_info"}[action]
        _add_review_log(user_id, actor_id=_current_user()["id"],
                        action=log_action, note=note)
        flash(f"Application {new_status}.", "success")
        return redirect(url_for("admin_providers_list",
                                status=request.args.get("from", "pending")))

    # --- Dashboards ---------------------------------------------------------

    def _require_role(required: str):
        user = _current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        if user["role"] != required:
            flash("You don't have access to that page.", "error")
            return redirect(_dashboard_url(user["role"]))
        return None

    @app.route("/dashboard/customer")
    def dashboard_customer():
        guard = _require_role("customer")
        if guard is not None:
            return guard
        return render_template("dashboards/customer.html", user=_current_user())

    @app.route("/dashboard/provider")
    def dashboard_provider():
        guard = _require_role("provider")
        if guard is not None:
            return guard
        user = _current_user()
        profile = _get_provider_profile(user["id"])
        docs = _get_provider_docs_by_kind(user["id"])
        missing = [k for k in REQUIRED_DOC_KINDS if k not in docs]
        return render_template(
            "dashboards/provider.html",
            user=user, profile=profile, docs=docs,
            doc_labels=DOC_LABELS,
            profile_complete=_profile_complete(profile),
            missing_docs=missing,
            required_kinds=REQUIRED_DOC_KINDS,
            can_submit=_can_submit(user["id"], profile),
            categories=_decode_list(profile["categories_json"]) if profile else [],
            service_pincodes=(_decode_list(profile["service_pincodes_json"])
                              if profile else []),
            note=_latest_decision_note(user["id"]),
        )

    @app.route("/dashboard/admin")
    def dashboard_admin():
        guard = _require_role("admin")
        if guard is not None:
            return guard
        pending_count = _get_db().execute(
            "SELECT COUNT(*) AS c FROM users WHERE role='provider' AND status='pending'"
        ).fetchone()["c"]
        return render_template("dashboards/admin.html",
                               user=_current_user(), pending_count=pending_count)

    @app.errorhandler(404)
    def not_found(_e):
        return redirect(url_for("index"))


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
