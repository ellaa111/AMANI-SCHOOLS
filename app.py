import os
import re
import logging
from datetime import timedelta
from functools import wraps
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from supabase import create_client

app = Flask(__name__)

# ---- A02: strong secret key and safe cookies ----
secret = os.environ.get("SECRET_KEY", "")
if len(secret) < 32:
    raise RuntimeError("SECRET_KEY missing or too short (32+ characters needed)")
app.secret_key = secret
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("APP_ENV") == "production",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    WTF_CSRF_TIME_LIMIT=None,
)

# ---- CSRF protection ----
csrf = CSRFProtect(app)

# ---- A04: rate limiting ----
limiter = Limiter(get_remote_address, app=app,
                  default_limits=["120 per minute"], storage_uri="memory://")

# ---- A09: security log ----
sec_log = logging.getLogger("security")
sec_log.setLevel(logging.INFO)
_h = RotatingFileHandler("security.log", maxBytes=1_000_000, backupCount=3)
_h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
sec_log.addHandler(_h)

def _c(v):
    return str(v).replace("\n", " ").replace("\r", " ")[:120]

def audit(event, **details):
    extra = " ".join(f"{k}={_c(v)}" for k, v in details.items())
    sec_log.info("%s ip=%s user=%s %s", event, request.remote_addr,
                 _c(session.get("email", "-")), extra)

# ---- A01: server-side key, database locked to the public ----
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_ANON_KEY = os.environ["SUPABASE_KEY"]               # only used to check logins
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]    # server only, never shared
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def login_required(roles=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if "user" not in session or "role" not in session:
                return redirect(url_for("login"))
            if roles and session["role"] not in roles:
                audit("ACCESS_DENIED", path=request.path, role=session["role"])
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco


# ---------- Auth ----------
# ---------- Auth ----------
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute; 30 per hour", methods=["POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()[:254]
        password = request.form.get("password") or ""
        try:
            auth_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)   # <-- THIS LINE (fresh client per login)
            res = auth_client.auth.sign_in_with_password({"email": email, "password": password})
            user = res.user
            prof = (supabase.table("profiles").select("role, full_name, student_id")
                    .eq("id", user.id).single().execute())
            session.clear()
            session.permanent = True
            session["user"] = user.id
            session["email"] = user.email
            session["role"] = prof.data["role"]
            session["name"] = prof.data["full_name"]
            session["student_id"] = prof.data.get("student_id")
            audit("LOGIN_OK", role=prof.data["role"])
            return redirect(url_for("dashboard"))
        except Exception as e:
            audit("LOGIN_FAILED", attempted=email, reason=type(e).__name__)
            flash("Invalid email or password.", "error")
    return render_template("login.html")
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Dashboard ----------
@app.route("/")
@login_required()
def dashboard():
    stats = {}
    for tbl, key in [("students", "students"), ("teachers", "teachers"), ("classes", "classes")]:
        stats[key] = supabase.table(tbl).select("id", count="exact").limit(0).execute().count or 0
    announcements = supabase.table("announcements").select("*").order("created_at", desc=True).limit(5).execute().data
    return render_template("dashboard.html", stats=stats, announcements=announcements)


# ---------- Students ----------
@app.route("/students")
@login_required(roles=["admin", "teacher"])
def students():
    q = re.sub(r"[^\w\s\-/.@]", "", request.args.get("q", ""))[:50].strip()
    query = supabase.table("students").select("*")
    if q:
        query = query.or_(f"full_name.ilike.%{q}%,admission_no.ilike.%{q}%")
    rows = query.execute().data
    return render_template("students.html", students=rows, q=q)

@app.route("/students/add", methods=["GET", "POST"])
@login_required(roles=["admin"])
def add_student():
    if request.method == "POST":
        f = request.form
        if (not f.get("full_name", "").strip() or len(f["full_name"]) > 100
                or not re.fullmatch(r"[A-Za-z0-9/\-]{1,30}", f.get("admission_no", ""))
                or f.get("gender") not in ("Male", "Female")
                or (f.get("class_id") and not f["class_id"].isdigit())
                or not re.fullmatch(r"(\+?[0-9 \-]{7,15})?", f.get("parent_phone", ""))):
            flash("Please check the student details.", "error")
            return redirect(url_for("add_student"))
        try:
            supabase.table("students").insert({
                "full_name": f["full_name"].strip(),
                "admission_no": f["admission_no"],
                "gender": f["gender"],
                "date_of_birth": f.get("date_of_birth") or None,
                "class_id": f.get("class_id") or None,
                "parent_phone": f.get("parent_phone", ""),
            }).execute()
        except Exception:
            flash("Could not save the student (is the admission number already used?).", "error")
            return redirect(url_for("add_student"))
        audit("STUDENT_ADDED", admission_no=f["admission_no"])
        flash("Student added.", "success")
        return redirect(url_for("students"))
    classes = supabase.table("classes").select("*").execute().data
    return render_template("student_form.html", classes=classes, student=None)


@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@login_required(roles=["admin"])
def edit_student(sid):
    if request.method == "POST":
        f = request.form
        if (not f.get("full_name", "").strip() or len(f["full_name"]) > 100
                or not re.fullmatch(r"[A-Za-z0-9/\-]{1,30}", f.get("admission_no", ""))
                or f.get("gender") not in ("Male", "Female")
                or (f.get("class_id") and not f["class_id"].isdigit())
                or not re.fullmatch(r"(\+?[0-9 \-]{7,15})?", f.get("parent_phone", ""))):
            flash("Please check the student details.", "error")
            return redirect(url_for("edit_student", sid=sid))
        try:
            supabase.table("students").update({
                "full_name": f["full_name"].strip(),
                "admission_no": f["admission_no"],
                "gender": f["gender"],
                "class_id": f.get("class_id") or None,
                "parent_phone": f.get("parent_phone", ""),
            }).eq("id", sid).execute()
        except Exception:
            flash("Could not update the student.", "error")
            return redirect(url_for("edit_student", sid=sid))
        audit("STUDENT_EDITED", id=sid)
        flash("Student updated.", "success")
        return redirect(url_for("students"))
    student = supabase.table("students").select("*").eq("id", sid).single().execute().data
    classes = supabase.table("classes").select("*").execute().data
    return render_template("student_form.html", classes=classes, student=student)



@app.route("/students/<sid>/delete", methods=["POST"])
@login_required(roles=["admin"])
def delete_student(sid):
    supabase.table("students").delete().eq("id", sid).execute()
    flash("Student deleted.", "success")
    return redirect(url_for("students"))


# ---------- Attendance ----------
@app.route("/attendance", methods=["GET", "POST"])
@login_required(roles=["admin", "teacher"])
def attendance():
    classes = supabase.table("classes").select("*").execute().data
    if request.method == "POST":
        f = request.form
        supabase.table("attendance").upsert({
            "student_id": f["student_id"],
            "date": f["date"],
            "status": f["status"],
            "recorded_by": session["user"],
        }, on_conflict="student_id,date").execute()
        flash("Attendance saved.", "success")
    class_id = request.args.get("class_id", "")
    date = request.args.get("date", "")
    records, students = [], []
    if class_id and date:
        students = supabase.table("students").select("*").eq("class_id", class_id).execute().data
        records = supabase.table("attendance").select("*").eq("date", date).execute().data
    rec_map = {r["student_id"]: r["status"] for r in records}
    return render_template("attendance.html", classes=classes, students=students,
                           class_id=class_id, date=date, rec_map=rec_map)


# ---------- Results ----------
@app.route("/results", methods=["GET", "POST"])
@login_required(roles=["admin", "teacher"])
def results():
    classes = supabase.table("classes").select("*").execute().data
    if request.method == "POST":
        f = request.form
        try:
            marks = float(f["marks"])
            if not (0 <= marks <= 100) or not f["student_id"].isdigit():
                raise ValueError
        except (ValueError, KeyError):
            flash("Enter a valid student and marks between 0 and 100.", "error")
        else:
            supabase.table("results").insert({
                "student_id": f["student_id"],
                "subject": f["subject"][:50],
                "exam_name": f["exam_name"][:50],
                "marks": marks,
                "grade": f.get("grade", "")[:3],
            }).execute()
            audit("RESULT_SAVED", student=f["student_id"])
            flash("Result saved.", "success")
    class_id = request.args.get("class_id", "")
    if not class_id.isdigit():
        class_id = ""
    rows, students = [], []
    if class_id:
        students = supabase.table("students").select("*").eq("class_id", class_id).execute().data
        ids = [s["id"] for s in students]
        if ids:
            rows = supabase.table("results").select("*").in_("student_id", ids).execute().data
    return render_template("results.html", classes=classes, class_id=class_id,
                           students=students, results=rows)


# ---------- Fees ----------
@app.route("/fees")
@login_required()
def fees():
    rows = []
    if session["role"] in ("admin", "teacher"):
        rows = supabase.table("fees").select("*, students(full_name, admission_no)").execute().data
    elif session["role"] == "student":
        # student role: assume profile linked to student record
        rows = supabase.table("fees").select("*").eq("student_id", session.get("student_id", "")).execute().data
    return render_template("fees.html", fees=rows)


# ---------- Announcements ----------
@app.route("/announcements", methods=["GET", "POST"])
@login_required()
def announcements():
    if request.method == "POST":
        if session["role"] != "admin":
            audit("ACCESS_DENIED", path=request.path, role=session["role"])
            abort(403)
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if not title or len(title) > 150 or not body or len(body) > 2000:
            flash("Title (max 150 characters) and message (max 2000) are required.", "error")
        else:
            supabase.table("announcements").insert({
                "title": title,
                "body": body,
                "posted_by": session["user"],
            }).execute()
            audit("ANNOUNCEMENT_POSTED")
            flash("Announcement posted.", "success")
    rows = (supabase.table("announcements").select("*")
            .order("created_at", desc=True).execute().data)
    return render_template("announcements.html", rows=rows)


@app.after_request
def set_security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'")
    if "user" in session:
        resp.headers["Cache-Control"] = "no-store"
    return resp


def render_error(code, title, message):
    return render_template("error.html", code=code, title=title, message=message), code


@app.errorhandler(403)
def e403(e):
    return render_error(403, "Access denied", "You do not have permission to view this page.")


@app.errorhandler(404)
def e404(e):
    return render_error(404, "Page not found", "That page does not exist.")


@app.errorhandler(429)
def e429(e):
    audit("RATE_LIMITED", path=request.path)
    return render_error(429, "Too many attempts", "Please wait a minute and try again.")


@app.errorhandler(CSRFError)
def ecsrf(e):
    audit("CSRF_REJECTED", path=request.path)
    return render_error(400, "Request rejected", "Your form expired. Refresh and try again.")


@app.errorhandler(500)
def e500(e):
    sec_log.error("SERVER_ERROR path=%s", _c(request.path), exc_info=True)
    return render_error(500, "Something went wrong", "The error has been logged.")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1")