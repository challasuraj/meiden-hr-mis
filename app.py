from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

app.secret_key = "meiden-hr-mis-secret-key"

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
            ("regularization_requests", "Regularization Requests", "number"),
            ("shift_wise_attendance", "Shift-wise Attendance", "number"),
            ("biometric_exceptions", "Biometric Exceptions", "number"),
            ("man_days_available", "Man-days Available", "number"),
            ("man_days_utilized", "Man-days Utilized", "number"),
        ],
    },
    "leave": {
        "title": "Leave Management",
        "table": True,
        "rows": ["Casual Leave (CL)", "Sick Leave (SL)", "Earned Leave (EL)", "Maternity Leave", "Paternity Leave", "Comp-Off"],
        "columns": ["Opening Balance", "Availed", "Balance"],
    },
    "overtime": {
        "title": "Overtime (OT) Analysis",
        "table": True,
        "rows": ["Production", "Quality", "Testing", "FES", "Admin"],
        "columns": ["Employees", "OT Hours", "OT Cost"],
    },
    "recruitment": {
        "title": "Recruitment Status",
        "fields": [
            ("open_positions", "Open Positions", "number"),
            ("positions_closed", "Positions Closed", "number"),
            ("interviews_conducted", "Interviews Conducted", "number"),
            ("offers_released", "Offers Released", "number"),
            ("joinings", "Joinings", "number"),
            ("offer_acceptance_rate", "Offer Acceptance Rate %", "number"),
            ("average_hiring_time", "Average Hiring Time (days)", "number"),
        ],
    },
    "compliance": {
        "title": "Statutory Compliance Dashboard",
        "table": True,
        "rows": ["PF Payment", "ESI Payment", "PT Payment", "Labour Welfare Fund", "Factory Returns", "Contract Labour Compliance"],
        "columns": ["Due Date", "Status"],
        "status_table": True,
    },
    "training": {
        "title": "Training & Development",
        "fields": [
            ("training_programs", "Training Programs Conducted", "number"),
            ("employees_trained", "Employees Trained", "number"),
            ("training_hours", "Training Hours", "number"),
            ("safety_trainings", "Safety Trainings", "number"),
            ("skill_matrix_updated", "Skill Matrix Updated (%)", "number"),
            ("effectiveness_score", "Training Effectiveness Score", "number"),
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
            ("feedback_score", "Employee Feedback Score", "number"),
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
            ("security_incidents", "Security Incidents", "number"),
            ("lost_found_cases", "Lost & Found Cases", "number"),
        ],
    },
    "welfare": {
        "title": "Employee Welfare & Grievances",
        "fields": [
            ("grievances_received", "Grievances Received", "number"),
            ("grievances_closed", "Grievances Closed", "number"),
            ("pending_cases", "Pending Cases", "number"),
            ("suggestion_entries", "Suggestion Scheme Entries", "number"),
            ("engagement_activities", "Employee Engagement Activities", "number"),
            ("welfare_programs", "Welfare Programs Conducted", "number"),
        ],
    },
}


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
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


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def load_month(month: str) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT data FROM monthly_mis WHERE month = ?", (month,)).fetchone()
    if not row:
        return {}
    return json.loads(row["data"])


def save_month(month: str, data: dict[str, Any]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO monthly_mis (month, data, updated_by, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(month) DO UPDATE SET
                data = excluded.data,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (month, json.dumps(data), session.get("user", "HR Team"), now),
        )


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == "admin" and password == "admin123":
            session["logged_in"] = True
            return redirect(url_for("dashboard"))

        flash("Invalid username or password", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    month = request.args.get("month", current_month())
    data = load_month(month)
    with get_db() as conn:
        months = [r["month"] for r in conn.execute("SELECT month FROM monthly_mis ORDER BY month DESC").fetchall()]

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
    ot_hours = [number(overtime[r].get("OT Hours")) for r in ot_labels]

    dashboard_data = {
        "total": total,
        "permanent": permanent,
        "contract": contract,
        "male": male,
        "female": female,
        "new_joinings": number(workforce.get("new_joinings")),
        "separations": number(workforce.get("separations")),
        "present": number(attendance.get("present_percent")),
        "absent": number(attendance.get("absent_percent")),
        "leave": number(attendance.get("leave_percent")),
        "open_positions": number(recruitment.get("open_positions")),
        "joinings": number(recruitment.get("joinings")),
        "trained": number(training.get("employees_trained")),
        "pending_grievances": number(welfare.get("pending_cases")),
        "ot_labels": ot_labels,
        "ot_hours": ot_hours,
    }

    return render_template("dashboard.html", month=month, months=months, d=dashboard_data, sections=SECTIONS)


@app.route("/entry/<section_key>", methods=["GET", "POST"])
@login_required
def entry(section_key: str):
    if section_key not in SECTIONS:
        return "Section not found", 404
    month = request.args.get("month") or request.form.get("month") or current_month()
    all_data = load_month(month)
    section = SECTIONS[section_key]

    if request.method == "POST":
        section_data: dict[str, Any] = {}
        if section.get("table"):
            for row in section["rows"]:
                section_data[row] = {}
                for col in section["columns"]:
                    field_name = f"{row}__{col}"
                    section_data[row][col] = request.form.get(field_name, "").strip()
        else:
            for key, _label, _type in section["fields"]:
                section_data[key] = request.form.get(key, "").strip()
        all_data[section_key] = section_data
        save_month(month, all_data)
        flash(f"{section['title']} saved successfully for {month}.", "success")
        return redirect(url_for("entry", section_key=section_key, month=month))

    return render_template(
        "entry.html",
        section_key=section_key,
        section=section,
        month=month,
        values=all_data.get(section_key, {}),
        sections=SECTIONS,
    )


@app.route("/monthly-entry", methods=["GET", "POST"])
@login_required
def monthly_entry():
    month = request.args.get("month") or request.form.get("month") or current_month()
    if request.method == "POST":
        return redirect(url_for("entry", section_key="workforce", month=month))
    return render_template("monthly_entry.html", month=month, sections=SECTIONS)


@app.route("/records")
@login_required
def records():
    with get_db() as conn:
        rows = conn.execute("SELECT month, updated_by, updated_at FROM monthly_mis ORDER BY month DESC").fetchall()
    return render_template("records.html", rows=rows, sections=SECTIONS)


@app.route("/export/<month>.csv")
@login_required
def export_csv(month: str):
    data = load_month(month)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Month", month])
    writer.writerow([])
    for section_key, section_data in data.items():
        writer.writerow([SECTIONS.get(section_key, {}).get("title", section_key)])
        if isinstance(section_data, dict):
            for key, value in section_data.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        writer.writerow([key, sub_key, sub_value])
                else:
                    writer.writerow([key, value])
        writer.writerow([])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=HR_MIS_{month}.csv"},
    )


@app.context_processor
def inject_globals():
    return {"current_month": current_month()}


# Create the database table when the application is imported by Gunicorn/Render.
# The previous version only initialized the database when app.py was run directly,
# which caused an Internal Server Error on Render.
init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
