from __future__ import annotations

import csv
import io
import json
import os
import sqlite3

from datetime import datetime
from functools import wraps
from typing import Any

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Render uses /tmp for temporary writable storage.
# For local operation, the database will be stored beside app.py.
if os.environ.get("RENDER"):
    DB_PATH = os.environ.get(
        "DATABASE_PATH",
        os.path.join("/tmp", "hr_mis.db"),
    )
else:
    DB_PATH = os.environ.get(
        "DATABASE_PATH",
        os.path.join(BASE_DIR, "hr_mis.db"),
    )


app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "meiden-hr-mis-secret-key-change-in-production",
)


# ============================================================
# HR MIS SECTIONS
# ============================================================

SECTIONS = {
    "workforce": {
        "title": "Workforce Summary",
        "fields": [
            ("total_employees", "Total Employees", "number"),
            ("permanent_employees", "Permanent Employees", "number"),
            ("contract_employees", "Contract Employees", "number"),
            ("male_employees", "Male Employees", "number"),
            ("female_employees", "Female Employees", "number"),
            ("new_joinings", "New Joinings", "number"),
            ("separations", "Separations", "number"),
            ("net_headcount_change", "Net Headcount Change", "number"),
            ("employee_turnover", "Employee Turnover %", "number"),
        ],
    },

    "attendance": {
        "title": "Attendance Dashboard",
        "fields": [
            ("present_percent", "Present %", "number"),
            ("absent_percent", "Absent %", "number"),
            ("leave_percent", "Leave %", "number"),
            ("late_comers", "Late Comers", "number"),
            (
                "regularization_requests",
                "Regularization Requests",
                "number",
            ),
            (
                "shift_wise_attendance",
                "Shift-wise Attendance",
                "number",
            ),
            (
                "biometric_exceptions",
                "Biometric Exceptions",
                "number",
            ),
            ("man_days_available", "Man-days Available", "number"),
            ("man_days_utilized", "Man-days Utilized", "number"),
        ],
    },

    "leave": {
        "title": "Leave Management",
        "table": True,
        "rows": [
            "Casual Leave (CL)",
            "Sick Leave (SL)",
            "Earned Leave (EL)",
            "Maternity Leave",
            "Paternity Leave",
            "Comp-Off",
        ],
        "columns": [
            "Opening Balance",
            "Availed",
            "Balance",
        ],
    },

    "overtime": {
        "title": "Overtime (OT) Analysis",
        "table": True,
        "rows": [
            "Production",
            "Quality",
            "Testing",
            "FES",
            "Admin",
        ],
        "columns": [
            "Employees",
            "OT Hours",
            "OT Cost",
        ],
    },

    "recruitment": {
        "title": "Recruitment Status",
        "fields": [
            ("open_positions", "Open Positions", "number"),
            ("positions_closed", "Positions Closed", "number"),
            (
                "interviews_conducted",
                "Interviews Conducted",
                "number",
            ),
            ("offers_released", "Offers Released", "number"),
            ("joinings", "Joinings", "number"),
            (
                "offer_acceptance_rate",
                "Offer Acceptance Rate %",
                "number",
            ),
            (
                "average_hiring_time",
                "Average Hiring Time (days)",
                "number",
            ),
        ],
    },

    "compliance": {
        "title": "Statutory Compliance Dashboard",
        "table": True,
        "rows": [
            "PF Payment",
            "ESI Payment",
            "PT Payment",
            "Labour Welfare Fund",
            "Factory Returns",
            "Contract Labour Compliance",
        ],
        "columns": [
            "Due Date",
            "Status",
        ],
        "status_table": True,
    },

    "training": {
        "title": "Training & Development",
        "fields": [
            (
                "training_programs",
                "Training Programs Conducted",
                "number",
            ),
            (
                "employees_trained",
                "Employees Trained",
                "number",
            ),
            ("training_hours", "Training Hours", "number"),
            ("safety_trainings", "Safety Trainings", "number"),
            (
                "skill_matrix_updated",
                "Skill Matrix Updated (%)",
                "number",
            ),
            (
                "effectiveness_score",
                "Training Effectiveness Score",
                "number",
            ),
        ],
    },

    "canteen": {
        "title": "Canteen Management",
        "fields": [
            ("meals_served", "Meals Served", "number"),
            ("breakfast_count", "Breakfast Count", "number"),
            ("lunch_count", "Lunch Count", "number"),
            ("dinner_count", "Dinner Count", "number"),
            ("subsidy_cost", "Canteen Subsidy Cost", "number"),
            (
                "feedback_score",
                "Employee Feedback Score",
                "number",
            ),
            ("hygiene_score", "Hygiene Audit Score", "number"),
        ],
    },

    "security": {
        "title": "Security Management",
        "fields": [
            ("visitor_count", "Visitor Count", "number"),
            ("vehicle_entries", "Vehicle Entries", "number"),
            ("material_inward", "Material Inward", "number"),
            ("material_outward", "Material Outward", "number"),
            (
                "security_incidents",
                "Security Incidents",
                "number",
            ),
            (
                "lost_found_cases",
                "Lost & Found Cases",
                "number",
            ),
        ],
    },

    "welfare": {
        "title": "Employee Welfare & Grievances",
        "fields": [
            (
                "grievances_received",
                "Grievances Received",
                "number",
            ),
            (
                "grievances_closed",
                "Grievances Closed",
                "number",
            ),
            ("pending_cases", "Pending Cases", "number"),
            (
                "suggestion_entries",
                "Suggestion Scheme Entries",
                "number",
            ),
            (
                "engagement_activities",
                "Employee Engagement Activities",
                "number",
            ),
            (
                "welfare_programs",
                "Welfare Programs Conducted",
                "number",
            ),
        ],
    },
}


# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monthly_mis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                data TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def load_month(month: str) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT data
            FROM monthly_mis
            WHERE month = ?
            """,
            (month,),
        ).fetchone()

    if not row:
        return {}

    try:
        return json.loads(row["data"])
    except (json.JSONDecodeError, TypeError):
        return {}


def save_month(month: str, data: dict[str, Any]) -> None:
    updated_at = datetime.now().isoformat(timespec="seconds")
    updated_by = session.get("user", "HR Team")

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO monthly_mis (
                month,
                data,
                updated_by,
                updated_at
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(month) DO UPDATE SET
                data = excluded.data,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                month,
                json.dumps(data),
                updated_by,
                updated_at,
            ),
        )
        conn.commit()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


def current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


# ============================================================
# LOGIN AND LOGOUT
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == "admin" and password == "admin123":
            session.clear()
            session["user"] = username
            session["username"] = username
            session["logged_in"] = True

            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
@login_required
def dashboard():
    month = request.args.get("month", current_month())
    data = load_month(month)

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT month
            FROM monthly_mis
            ORDER BY month DESC
            """
        ).fetchall()

    months = [row["month"] for row in rows]

    workforce = data.get("workforce", {})
    attendance = data.get("attendance", {})
    recruitment = data.get("recruitment", {})
    training = data.get("training", {})
    welfare = data.get("welfare", {})
    overtime = data.get("overtime", {})

    total = number(workforce.get("total_employees"))
    permanent = number(workforce.get("permanent_employees"))
    contract = number(workforce.get("contract_employees"))
    male = number(workforce.get("male_employees"))
    female = number(workforce.get("female_employees"))

    ot_labels = list(overtime.keys()) if overtime else []

    ot_hours = []

    for department in ot_labels:
        department_data = overtime.get(department, {})

        if isinstance(department_data, dict):
            ot_hours.append(
                number(department_data.get("OT Hours"))
            )
        else:
            ot_hours.append(0)

    dashboard_data = {
        "total": total,
        "permanent": permanent,
        "contract": contract,
        "male": male,
        "female": female,
        "new_joinings": number(
            workforce.get("new_joinings")
        ),
        "separations": number(
            workforce.get("separations")
        ),
        "present": number(
            attendance.get("present_percent")
        ),
        "absent": number(
            attendance.get("absent_percent")
        ),
        "leave": number(
            attendance.get("leave_percent")
        ),
        "open_positions": number(
            recruitment.get("open_positions")
        ),
        "joinings": number(
            recruitment.get("joinings")
        ),
        "trained": number(
            training.get("employees_trained")
        ),
        "pending_grievances": number(
            welfare.get("pending_cases")
        ),
        "ot_labels": ot_labels,
        "ot_hours": ot_hours,
    }

    return render_template(
        "dashboard.html",
        month=month,
        months=months,
        d=dashboard_data,
        sections=SECTIONS,
    )


# ============================================================
# MONTHLY ENTRY
# ============================================================

@app.route("/monthly-entry", methods=["GET", "POST"])
@login_required
def monthly_entry():
    month = (
        request.args.get("month")
        or request.form.get("month")
        or current_month()
    )

    if request.method == "POST":
        return redirect(
            url_for(
                "entry",
                section_key="workforce",
                month=month,
            )
        )

    return render_template(
        "monthly_entry.html",
        month=month,
        sections=SECTIONS,
    )


# ============================================================
# SECTION ENTRY
# ============================================================

@app.route(
    "/entry/<section_key>",
    methods=["GET", "POST"],
)
@login_required
def entry(section_key: str):
    if section_key not in SECTIONS:
        return "Section not found", 404

    month = (
        request.args.get("month")
        or request.form.get("month")
        or current_month()
    )

    all_data = load_month(month)
    section = SECTIONS[section_key]

    if request.method == "POST":
        section_data: dict[str, Any] = {}

        if section.get("table"):
            for row in section["rows"]:
                section_data[row] = {}

                for column in section["columns"]:
                    field_name = f"{row}__{column}"

                    section_data[row][column] = (
                        request.form.get(field_name, "").strip()
                    )

        else:
            for key, _label, _field_type in section["fields"]:
                section_data[key] = (
                    request.form.get(key, "").strip()
                )

        all_data[section_key] = section_data
        save_month(month, all_data)

        flash(
            f"{section['title']} saved successfully "
            f"for {month}.",
            "success",
        )

        return redirect(
            url_for(
                "entry",
                section_key=section_key,
                month=month,
            )
        )

    return render_template(
        "entry.html",
        section_key=section_key,
        section=section,
        month=month,
        values=all_data.get(section_key, {}),
        sections=SECTIONS,
    )


# ============================================================
# RECORDS
# ============================================================

@app.route("/records")
@login_required
def records():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                month,
                updated_by,
                updated_at
            FROM monthly_mis
            ORDER BY month DESC
            """
        ).fetchall()

    return render_template(
        "records.html",
        rows=rows,
        sections=SECTIONS,
    )


# ============================================================
# CSV EXPORT
# ============================================================

@app.route("/export/<month>.csv")
@login_required
def export_csv(month: str):
    data = load_month(month)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["HR & Admin MIS Report"])
    writer.writerow(["Month", month])
    writer.writerow([])

    for section_key, section_data in data.items():
        section_title = SECTIONS.get(
            section_key,
            {},
        ).get(
            "title",
            section_key,
        )

        writer.writerow([section_title])

        if isinstance(section_data, dict):
            for key, value in section_data.items():

                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        writer.writerow(
                            [
                                key,
                                sub_key,
                                sub_value,
                            ]
                        )

                else:
                    writer.writerow(
                        [
                            key,
                            value,
                        ]
                    )

        writer.writerow([])

    filename = f"HR_MIS_{month}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            )
        },
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():
    return {
        "status": "healthy",
        "application": "Meiden HR MIS",
    }, 200


# ============================================================
# GLOBAL TEMPLATE VALUES
# ============================================================

@app.context_processor
def inject_globals():
    return {
        "current_month": current_month(),
        "logged_in_user": session.get("user"),
    }


# ============================================================
# INITIALIZE DATABASE
# ============================================================

init_db()


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
