"""Hospital Management System - Flask web app on MongoDB.

The business rules (OPD hours, stock checks, billing, room booking)
live in services.py. The routes call them and flash their messages.
"""
import os
from datetime import date, datetime, timedelta

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, url_for)
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

import services as hms
from db import HMSError, clean, error_message, get_db, rows

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")


def form_or_none(name):
    value = request.form.get(name, "").strip()
    return value or None


def form_int(name):
    value = form_or_none(name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def try_db(action, success_msg):
    """Run a write; flash the success message or the error."""
    try:
        result = action()
        flash(success_msg, "success")
        return True, result
    except (HMSError, PyMongoError, ValueError) as exc:
        flash(error_message(exc), "danger")
        return False, None


@app.errorhandler(ServerSelectionTimeoutError)
def mongo_down(_exc):
    return ("<h1>Database unavailable</h1><p>Could not connect to MongoDB. Start the MongoDB "
            "server and check MONGO_URI in your .env file.</p>"), 503


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------
@app.route("/")
def dashboard():
    upcoming = hms.appointments_view({"status": "Scheduled", "appointment_time": {"$gte": hms.today()}},
                                     sort=1, limit=8)
    return render_template("dashboard.html", stats=hms.dashboard_stats(), upcoming=upcoming,
                           admitted=hms.current_admissions(), low_stock=hms.low_stock())


# ---------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------
@app.route("/patients")
def patients():
    q = request.args.get("q", "").strip()
    return render_template("patients.html", patients=hms.search_patients(q), q=q)


def patient_params():
    allergies = [a.strip() for a in request.form.get("allergies", "").split(",") if a.strip()]
    fields = ("first_name", "last_name", "dob", "gender", "blood_group", "phone", "email",
              "street", "city", "state", "pincode")
    return {f: form_or_none(f) for f in fields} | {"allergies": allergies}


@app.route("/patients/new", methods=["GET", "POST"])
def patient_new():
    if request.method == "POST":
        params = patient_params()
        ok, patient_id = try_db(lambda: hms.create_patient(params), "Patient registered.")
        if ok:
            return redirect(url_for("patient_detail", patient_id=patient_id))
        return render_template("patient_form.html", patient=params, title="Register patient")
    return render_template("patient_form.html", patient={}, title="Register patient")


@app.route("/patients/<int:patient_id>")
def patient_detail(patient_id):
    patient = hms.get_patient(patient_id)
    if patient is None:
        abort(404)
    db = get_db()
    return render_template(
        "patient_detail.html", patient=patient,
        appointments=hms.appointments_view({"patient_id": patient_id}),
        admissions=hms.admissions_view({"patient_id": patient_id}, {"admit_date": -1}),
        bills=rows(db.bills.find({"patient_id": patient_id}).sort("bill_date", -1)),
        records=hms.patient_records(patient_id))


@app.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
def patient_edit(patient_id):
    if request.method == "POST":
        params = patient_params() | {"patient_id": patient_id}
        ok, _ = try_db(lambda: hms.update_patient(patient_id, params), "Patient updated.")
        if ok:
            return redirect(url_for("patient_detail", patient_id=patient_id))
        return render_template("patient_form.html", patient=params, title="Edit patient")
    patient = hms.get_patient(patient_id)
    if patient is None:
        abort(404)
    return render_template("patient_form.html", patient=patient, title="Edit patient")


@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
def patient_delete(patient_id):
    ok, _ = try_db(lambda: hms.delete_patient(patient_id), "Patient deleted.")
    return redirect(url_for("patients") if ok else url_for("patient_detail", patient_id=patient_id))


@app.route("/patients/<int:patient_id>/export.xml")
def patient_xml(patient_id):
    doc = hms.patient_xml(patient_id)
    if doc is None:
        abort(404)
    return Response(doc, mimetype="application/xml")


@app.route("/patients/<int:patient_id>/export.json")
def patient_json(patient_id):
    doc = hms.patient_json(patient_id)
    if doc is None:
        abort(404)
    return Response(doc, mimetype="application/json")


@app.route("/patients/<int:patient_id>/records/new", methods=["POST"])
def record_new(patient_id):
    results = {}
    for line in request.form.get("results", "").splitlines():
        if "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            try:
                results[key] = float(value) if "." in value else int(value)
            except ValueError:
                results[key] = value
    try_db(lambda: hms.add_lab_report(patient_id, form_or_none("test"), form_or_none("flag"), results),
           "Lab report saved.")
    return redirect(url_for("patient_detail", patient_id=patient_id) + "#records")


# ---------------------------------------------------------------------
# Staff (one collection, role = Doctor / Nurse)
# ---------------------------------------------------------------------
@app.route("/staff")
def staff():
    doctors = sorted(hms.doctor_directory(), key=lambda d: (d["department"], d["doctor_name"]))
    return render_template("staff.html", doctors=doctors, nurses=hms.nurses(), everyone=hms.all_staff())


# ---------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------
@app.route("/appointments")
def appointments():
    status = request.args.get("status", "")
    rows_ = hms.appointments_view({"status": status} if status else {})
    return render_template("appointments.html", appointments=rows_, status=status)


def patient_choices(filt=None):
    return rows(get_db().patients.find(filt or {}, {"patient_id": 1, "first_name": 1, "last_name": 1})
                .sort("first_name", 1))


@app.route("/appointments/new", methods=["GET", "POST"])
def appointment_new():
    if request.method == "POST":
        when = form_or_none("appointment_time")
        ok, _ = try_db(lambda: hms.book_appointment(
            form_int("patient_id"), form_int("doctor_id"),
            datetime.fromisoformat(when) if when else None, form_or_none("reason")),
            "Appointment booked.")
        if ok:
            return redirect(url_for("appointments"))
    return render_template("appointment_form.html",
                           patients=patient_choices(),
                           doctors=sorted(hms.doctor_directory(), key=lambda d: d["doctor_name"]),
                           selected_patient=request.args.get("patient_id", type=int))


@app.route("/appointments/<int:appointment_id>/status", methods=["POST"])
def appointment_status(appointment_id):
    new_status = request.form["status"]
    msg = "Appointment completed and bill generated." if new_status == "Completed" else f"Appointment {new_status.lower()}."
    try_db(lambda: hms.set_appointment_status(appointment_id, new_status), msg)
    return redirect(request.referrer or url_for("appointments"))


@app.route("/appointments/<int:appointment_id>", methods=["GET", "POST"])
def appointment_detail(appointment_id):
    if request.method == "POST":
        try_db(lambda: hms.prescribe(appointment_id, form_int("medicine_id"), form_or_none("dosage"),
                                     form_int("quantity"), form_int("duration_days")),
               "Medicine prescribed, stock updated.")
        return redirect(url_for("appointment_detail", appointment_id=appointment_id))

    appt = hms.get_appointment(appointment_id)
    if appt is None:
        abort(404)
    prescriptions = [p | {"cost": p["quantity"] * p["unit_price"]} for p in appt.get("prescriptions", [])]
    bill = clean(get_db().bills.find_one({"appointment_id": appointment_id}))
    return render_template("appointment_detail.html", appt=appt, prescriptions=prescriptions,
                           bill=bill, medicines=hms.medicines())


# ---------------------------------------------------------------------
# Admissions
# ---------------------------------------------------------------------
@app.route("/admissions")
def admissions():
    history = hms.admissions_view({"status": "Discharged"}, {"discharge_date": -1})
    rooms = rows(get_db().rooms.find().sort("room_number", 1))
    return render_template("admissions.html", current=hms.current_admissions(), history=history, rooms=rooms)


@app.route("/admissions/new", methods=["GET", "POST"])
def admission_new():
    if request.method == "POST":
        ok, _ = try_db(lambda: hms.admit_patient(
            form_int("patient_id"), form_int("room_id"), form_int("doctor_id"),
            form_or_none("diagnosis"), form_or_none("admit_date") or date.today().isoformat()),
            "Patient admitted.")
        if ok:
            return redirect(url_for("admissions"))
    db = get_db()
    admitted = db.admissions.distinct("patient_id", {"status": "Admitted"})
    return render_template("admission_form.html",
                           patients=patient_choices({"patient_id": {"$nin": admitted}}),
                           rooms=rows(db.rooms.find({"status": "Available"}).sort("room_number", 1)),
                           doctors=sorted(hms.doctor_directory(), key=lambda d: d["doctor_name"]),
                           today=date.today().isoformat())


@app.route("/admissions/<int:admission_id>/discharge", methods=["POST"])
def admission_discharge(admission_id):
    discharge_date = form_or_none("discharge_date") or date.today().isoformat()
    try_db(lambda: hms.discharge_patient(admission_id, discharge_date),
           "Patient discharged and bill generated.")
    return redirect(url_for("admissions"))


# ---------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------
@app.route("/billing")
def billing():
    status = request.args.get("status", "")
    return render_template("billing.html", bills=hms.bills_view(status),
                           summary=hms.billing_summary(), status=status)


@app.route("/billing/<int:bill_id>/pay", methods=["POST"])
def bill_pay(bill_id):
    try_db(lambda: hms.pay_bill(bill_id), "Payment recorded.")
    return redirect(request.referrer or url_for("billing"))


# ---------------------------------------------------------------------
# Pharmacy
# ---------------------------------------------------------------------
@app.route("/pharmacy")
def pharmacy():
    return render_template("pharmacy.html", medicines=hms.medicines())


@app.route("/pharmacy/restock", methods=["POST"])
def pharmacy_restock():
    qty = request.form.get("quantity", type=int) or 0
    ok, count = try_db(lambda: hms.restock_low_medicines(qty), "Restock finished.")
    if ok:
        flash(f"{count} medicine(s) were below reorder level and got +{qty} units.", "info")
    return redirect(url_for("pharmacy"))


# ---------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------
@app.route("/reports")
def reports():
    workload = hms.doctor_workload(date.today() - timedelta(days=90), date.today() + timedelta(days=30))
    workload.sort(key=lambda w: w["revenue"], reverse=True)
    return render_template("reports.html", revenue=hms.monthly_revenue(), workload=workload,
                           flagged=hms.flagged_lab_results(), audit=hms.audit_log())


@app.route("/reports/refresh", methods=["POST"])
def reports_refresh():
    try_db(hms.refresh_monthly_revenue, "Monthly revenue refreshed.")
    return redirect(url_for("reports"))


@app.template_filter("money")
def money(value):
    return f"₹{value:,.2f}" if value is not None else "-"


if __name__ == "__main__":
    app.run(debug=True)
