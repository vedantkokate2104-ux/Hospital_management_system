"""Hospital business rules and read models on MongoDB.

In the PostgreSQL version these were stored procedures, triggers and
views. Here each rule is a Python function: it checks the rule, raises
HMSError with a readable message if it is broken, and makes the change
with atomic conditional updates (find_one_and_update with a filter) so
two requests can't both take the same room or the last tablets.
"""
import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta

from pymongo import ReturnDocument

from db import HMSError, audit, clean, get_db, next_id, rows, to_datetime

GENDERS = ("Male", "Female", "Other")
BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
APPT_STATUSES = ("Scheduled", "Completed", "Cancelled")
PHONE_RE = re.compile(r"^\+?[0-9]{10,13}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
OPD_OPEN, OPD_CLOSE = time(8, 0), time(20, 0)
FLAGGED = ("High", "Critical", "Borderline")


def today():
    return datetime.combine(date.today(), time())


def age(dob):
    t = date.today()
    return t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))


def full_name(person, prefix=""):
    return f"{prefix}{person['first_name']} {person['last_name']}"


def require(doc, message):
    if doc is None:
        raise HMSError(message)
    return doc


# =====================================================================
# Patients
# =====================================================================
def _validate_patient(p):
    for field, label in [("first_name", "First name"), ("last_name", "Last name"),
                         ("dob", "Date of birth"), ("gender", "Gender"), ("phone", "Phone")]:
        if not p.get(field):
            raise HMSError(f"{label} is required.")
    if p["gender"] not in GENDERS:
        raise HMSError("Gender must be Male, Female or Other.")
    if p.get("blood_group") and p["blood_group"] not in BLOOD_GROUPS:
        raise HMSError("Unknown blood group.")
    if not PHONE_RE.match(p["phone"]):
        raise HMSError("Phone number must have 10 to 13 digits.")
    if p.get("email") and not EMAIL_RE.match(p["email"]):
        raise HMSError("Email address is not valid.")
    if p.get("pincode") and not re.fullmatch(r"[0-9]{6}", p["pincode"]):
        raise HMSError("Pincode must have 6 digits.")
    try:
        dob = to_datetime(p["dob"])
    except ValueError:
        raise HMSError("Date of birth is not a valid date.")
    if dob.date() > date.today():
        raise HMSError("Date of birth cannot be in the future.")


def _patient_doc(p):
    """Form fields -> document. The address is an embedded document and
    allergies an array (they were a composite type and TEXT[] in SQL)."""
    return {
        "first_name": p["first_name"],
        "last_name": p["last_name"],
        "dob": to_datetime(p["dob"]),
        "gender": p["gender"],
        "blood_group": p.get("blood_group"),
        "phone": p["phone"],
        "email": p.get("email"),
        "address": {k: p.get(k) for k in ("street", "city", "state", "pincode")},
        "allergies": list(p.get("allergies") or []),
    }


def patient_view(doc):
    """Flatten the stored document into what the templates show."""
    p = clean(doc)
    address = p.pop("address", None) or {}
    p.update({k: address.get(k) for k in ("street", "city", "state", "pincode")})
    p["age"] = age(p["dob"])
    return p


def get_patient(patient_id):
    doc = get_db().patients.find_one({"patient_id": patient_id})
    return patient_view(doc) if doc else None


def search_patients(q=""):
    filt = {}
    if q:
        pattern = {"$regex": re.escape(q), "$options": "i"}
        filt = {"$or": [{"first_name": pattern}, {"last_name": pattern},
                        {"phone": {"$regex": re.escape(q)}}, {"allergies": q}]}
    cursor = get_db().patients.find(filt).sort([("last_name", 1), ("first_name", 1)])
    return [patient_view(d) for d in cursor]


def create_patient(p, registered_on=None):
    _validate_patient(p)
    doc = _patient_doc(p) | {"patient_id": next_id("patients"),
                             "registered_on": registered_on or datetime.now()}
    get_db().patients.insert_one(doc)
    audit("patients", "INSERT", doc["patient_id"], new=doc)
    return doc["patient_id"]


def update_patient(patient_id, p):
    _validate_patient(p)
    db = get_db()
    old = require(db.patients.find_one({"patient_id": patient_id}), "Patient does not exist.")
    new = db.patients.find_one_and_update({"patient_id": patient_id}, {"$set": _patient_doc(p)},
                                          return_document=ReturnDocument.AFTER)
    audit("patients", "UPDATE", patient_id, old, new)


def delete_patient(patient_id):
    """Delete a patient with everything that belongs to them
    (ON DELETE CASCADE in SQL). A room they still occupy is freed."""
    db = get_db()
    old = require(db.patients.find_one({"patient_id": patient_id}), "Patient does not exist.")
    active = db.admissions.find_one({"patient_id": patient_id, "status": "Admitted"})
    if active:
        db.rooms.update_one({"room_id": active["room_id"]}, {"$set": {"status": "Available"}})
    for coll in ("appointments", "admissions", "bills", "medical_records"):
        db[coll].delete_many({"patient_id": patient_id})
    db.patients.delete_one({"patient_id": patient_id})
    audit("patients", "DELETE", patient_id, old=old)


def add_lab_report(patient_id, test, flag, results, doctor_id=None):
    if not test:
        raise HMSError("Test name is required.")
    require(get_db().patients.find_one({"patient_id": patient_id}), "Patient does not exist.")
    add_medical_record(patient_id, "Lab Report",
                       {"test": test, "results": results, "flag": flag or "Normal"},
                       doctor_id=doctor_id)


def add_medical_record(patient_id, record_type, details, doctor_id=None,
                       recorded_at=None, summary_xml=None):
    """Medical records keep free-form `details` (shape differs per test)
    and an optional XML discharge summary stored as text."""
    get_db().medical_records.insert_one({
        "record_id": next_id("medical_records"),
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "record_type": record_type,
        "recorded_at": recorded_at or datetime.now(),
        "details": details,
        "summary_xml": summary_xml,
    })


def patient_records(patient_id):
    out = []
    for r in rows(get_db().medical_records.find({"patient_id": patient_id}).sort("recorded_at", -1)):
        r["details_pretty"] = json.dumps(r["details"], indent=2, default=str)
        out.append(r)
    return out


# =====================================================================
# Staff (one collection; `role` says which subclass a document is)
# =====================================================================
def _departments():
    return {d["dept_id"]: d for d in get_db().departments.find()}


def doctor_directory():
    depts = _departments()
    out = []
    for d in get_db().staff.find({"role": "Doctor"}):
        dep = depts[d["dept_id"]]
        out.append({"doctor_id": d["staff_id"], "doctor_name": full_name(d, "Dr. "),
                    "specialization": d["specialization"], "department": dep["name"],
                    "floor_no": dep["floor_no"], "consultation_fee": d["consultation_fee"],
                    "phone": d["phone"], "email": d["email"]})
    return out


def nurses():
    depts = _departments()
    out = rows(get_db().staff.find({"role": "Nurse"}).sort("last_name", 1))
    for n in out:
        n["department"] = depts[n["dept_id"]]["name"]
    return out


def all_staff():
    depts = _departments()
    out = []
    for s in rows(get_db().staff.find().sort("staff_id", 1)):
        out.append(s | {"full_name": full_name(s), "department": depts[s["dept_id"]]["name"]})
    return out


def _doctor(doctor_id):
    return get_db().staff.find_one({"staff_id": doctor_id, "role": "Doctor"})


# =====================================================================
# Appointments
# =====================================================================
def appointments_view(match, sort=-1, limit=None):
    """Appointments joined with patient and doctor ($lookup)."""
    pipeline = [{"$match": match}, {"$sort": {"appointment_time": sort}}]
    if limit:
        pipeline.append({"$limit": limit})
    pipeline += [
        {"$lookup": {"from": "patients", "localField": "patient_id",
                     "foreignField": "patient_id", "as": "patient"}},
        {"$lookup": {"from": "staff", "localField": "doctor_id",
                     "foreignField": "staff_id", "as": "doctor"}},
        {"$unwind": "$patient"},
        {"$unwind": "$doctor"},
        {"$addFields": {
            "patient_name": {"$concat": ["$patient.first_name", " ", "$patient.last_name"]},
            "doctor_name": {"$concat": ["Dr. ", "$doctor.first_name", " ", "$doctor.last_name"]},
            "specialization": "$doctor.specialization",
            "consultation_fee": "$doctor.consultation_fee",
            "allergies": "$patient.allergies",
        }},
        {"$project": {"_id": 0, "patient": 0, "doctor": 0}},
    ]
    return rows(get_db().appointments.aggregate(pipeline))


def get_appointment(appointment_id):
    found = appointments_view({"appointment_id": appointment_id})
    return found[0] if found else None


def book_appointment(patient_id, doctor_id, when, reason):
    db = get_db()
    if not db.patients.find_one({"patient_id": patient_id}) or not _doctor(doctor_id):
        raise HMSError("Unknown patient or doctor")
    if when is None:
        raise HMSError("Date and time are required.")
    if not OPD_OPEN <= when.time() <= OPD_CLOSE:
        raise HMSError("Appointments are only allowed between 08:00 and 20:00")
    appointment_id = next_id("appointments")
    # the unique index uq_doctor_slot refuses a second patient in the same slot
    db.appointments.insert_one({
        "appointment_id": appointment_id, "patient_id": patient_id, "doctor_id": doctor_id,
        "appointment_time": when, "reason": reason, "status": "Scheduled", "prescriptions": [],
    })
    return appointment_id


def prescribe(appointment_id, medicine_id, dosage, quantity, duration_days):
    """Add a medicine to an appointment and reduce pharmacy stock.
    The stock is only decremented if enough is left (atomic check)."""
    db = get_db()
    if not dosage:
        raise HMSError("Dosage is required.")
    if not quantity or quantity < 1:
        raise HMSError("Quantity must be at least 1.")
    if not duration_days or duration_days < 1:
        raise HMSError("Duration must be at least 1 day.")
    appt = require(db.appointments.find_one({"appointment_id": appointment_id}),
                   f"Appointment {appointment_id} does not exist")
    if appt["status"] == "Cancelled":
        raise HMSError("Cannot prescribe on a cancelled appointment")

    med = db.medicines.find_one_and_update(
        {"medicine_id": medicine_id, "stock_qty": {"$gte": quantity}},
        {"$inc": {"stock_qty": -quantity}})
    if med is None:
        m = require(db.medicines.find_one({"medicine_id": medicine_id}), "Unknown medicine")
        raise HMSError(f"Insufficient stock for {m['name']}: {m['stock_qty']} available, "
                       f"{quantity} requested")

    db.appointments.update_one({"appointment_id": appointment_id}, {"$push": {"prescriptions": {
        "prescription_id": next_id("prescriptions"), "medicine_id": medicine_id,
        "name": med["name"], "unit_price": med["unit_price"],
        "dosage": dosage, "quantity": quantity, "duration_days": duration_days,
    }}})


def set_appointment_status(appointment_id, new_status):
    """Complete or cancel an appointment. Completing it creates its bill:
    consultation fee + prescribed medicines."""
    db = get_db()
    if new_status not in APPT_STATUSES:
        raise HMSError("Unknown appointment status.")
    appt = require(db.appointments.find_one({"appointment_id": appointment_id}),
                   f"Appointment {appointment_id} does not exist")
    if appt["status"] == new_status:
        return
    if appt["status"] != "Scheduled":
        raise HMSError(f"Appointment {appointment_id} is already {appt['status']} and cannot be changed")

    appt = db.appointments.find_one_and_update(
        {"appointment_id": appointment_id, "status": "Scheduled"},
        {"$set": {"status": new_status}}, return_document=ReturnDocument.AFTER)
    if appt is None:
        raise HMSError(f"Appointment {appointment_id} was changed by someone else, try again")

    if new_status == "Completed":
        fee = _doctor(appt["doctor_id"])["consultation_fee"]
        meds = sum(p["quantity"] * p["unit_price"] for p in appt.get("prescriptions", []))
        create_bill(appt["patient_id"], fee + meds, appt["appointment_time"].date(),
                    appointment_id=appointment_id)


# =====================================================================
# Admissions
# =====================================================================
def admission_charge(adm, room=None, doctor=None, until=None):
    """Room charge for every day stayed (minimum 1) + doctor's fee."""
    db = get_db()
    room = room or db.rooms.find_one({"room_id": adm["room_id"]})
    doctor = doctor or _doctor(adm["doctor_id"])
    end = to_datetime(adm.get("discharge_date") or until or date.today())
    days = max((end - to_datetime(adm["admit_date"])).days, 1)
    return days * room["daily_charge"] + doctor["consultation_fee"]


def admit_patient(patient_id, room_id, doctor_id, diagnosis, admit_date=None):
    db = get_db()
    admit = to_datetime(admit_date) or today()
    if not db.patients.find_one({"patient_id": patient_id}) or not _doctor(doctor_id):
        raise HMSError("Unknown patient or doctor")
    if db.admissions.find_one({"patient_id": patient_id, "status": "Admitted"}):
        raise HMSError(f"Patient {patient_id} is already admitted")
    room = require(db.rooms.find_one({"room_id": room_id}), f"Room {room_id} does not exist")
    if room["status"] != "Available":
        raise HMSError(f"Room {room['room_number']} is not available (status: {room['status']})")
    # temporal rule: the new stay [admit, open) must not overlap an earlier stay
    if db.admissions.find_one({"room_id": room_id, "$or": [{"discharge_date": None},
                                                           {"discharge_date": {"$gt": admit}}]}):
        raise HMSError(f"Room {room['room_number']} is already booked for that period")

    # claim the room: only succeeds while it is still Available
    if db.rooms.find_one_and_update({"room_id": room_id, "status": "Available"},
                                    {"$set": {"status": "Occupied"}}) is None:
        raise HMSError(f"Room {room['room_number']} was just taken, choose another")

    doc = {"admission_id": next_id("admissions"), "patient_id": patient_id, "room_id": room_id,
           "doctor_id": doctor_id, "admit_date": admit, "discharge_date": None,
           "diagnosis": diagnosis, "status": "Admitted"}
    try:
        db.admissions.insert_one(doc)   # uq_one_active_admission backs up the check above
    except Exception:
        db.rooms.update_one({"room_id": room_id}, {"$set": {"status": "Available"}})
        raise
    audit("admissions", "INSERT", doc["admission_id"], new=doc)
    return doc["admission_id"]


def discharge_patient(admission_id, discharge_date=None):
    """Close the admission, free the room and generate the bill."""
    db = get_db()
    adm = require(db.admissions.find_one({"admission_id": admission_id}),
                  f"Admission {admission_id} does not exist")
    if adm["discharge_date"] is not None:
        raise HMSError(f"Admission {admission_id} was already discharged on "
                       f"{adm['discharge_date'].date()}")
    discharge = to_datetime(discharge_date) or today()
    if discharge < adm["admit_date"]:
        raise HMSError(f"Discharge date cannot be before admit date ({adm['admit_date'].date()})")

    new = db.admissions.find_one_and_update(
        {"admission_id": admission_id, "status": "Admitted"},
        {"$set": {"discharge_date": discharge, "status": "Discharged"}},
        return_document=ReturnDocument.AFTER)
    if new is None:
        raise HMSError(f"Admission {admission_id} was already discharged")
    db.rooms.update_one({"room_id": adm["room_id"]}, {"$set": {"status": "Available"}})
    audit("admissions", "UPDATE", admission_id, adm, new)
    create_bill(adm["patient_id"], admission_charge(new), discharge.date(), admission_id=admission_id)


def admissions_view(match, sort):
    """Admissions joined with patient, room and doctor."""
    pipeline = [
        {"$match": match},
        {"$sort": sort},
        {"$lookup": {"from": "patients", "localField": "patient_id",
                     "foreignField": "patient_id", "as": "patient"}},
        {"$lookup": {"from": "rooms", "localField": "room_id", "foreignField": "room_id", "as": "room"}},
        {"$lookup": {"from": "staff", "localField": "doctor_id", "foreignField": "staff_id", "as": "doctor"}},
        {"$lookup": {"from": "bills", "localField": "admission_id",
                     "foreignField": "admission_id", "as": "bill"}},
        {"$unwind": "$patient"}, {"$unwind": "$room"}, {"$unwind": "$doctor"},
    ]
    out = []
    for a in get_db().admissions.aggregate(pipeline):
        row = clean(a)
        row.update({
            "patient_name": full_name(a["patient"]),
            "room_number": a["room"]["room_number"],
            "room_type": a["room"]["room_type"],
            "doctor_name": full_name(a["doctor"], "Dr. "),
            "amount": a["bill"][0]["amount"] if a["bill"] else None,
        })
        if row["discharge_date"] is None:
            row["days_admitted"] = (date.today() - row["admit_date"]).days
            row["charge_so_far"] = admission_charge(a, a["room"], a["doctor"])
        else:
            row["days"] = (row["discharge_date"] - row["admit_date"]).days
        for key in ("patient", "room", "doctor", "bill"):
            row.pop(key)
        out.append(row)
    return out


def current_admissions():
    return admissions_view({"status": "Admitted"}, {"admit_date": 1})


# =====================================================================
# Billing
# =====================================================================
def create_bill(patient_id, amount, bill_date, appointment_id=None, admission_id=None):
    doc = {"bill_id": next_id("bills"), "patient_id": patient_id,
           "appointment_id": appointment_id, "admission_id": admission_id,
           "amount": round(float(amount), 2), "bill_date": to_datetime(bill_date),
           "payment_status": "Unpaid", "paid_on": None}
    get_db().bills.insert_one(doc)
    audit("bills", "INSERT", doc["bill_id"], new=doc)
    return doc["bill_id"]


def pay_bill(bill_id, paid_on=None):
    """Mark a bill paid and stamp the payment date."""
    db = get_db()
    old = require(db.bills.find_one({"bill_id": bill_id}), f"Bill {bill_id} does not exist")
    if old["payment_status"] == "Paid":
        return
    new = db.bills.find_one_and_update(
        {"bill_id": bill_id, "payment_status": "Unpaid"},
        {"$set": {"payment_status": "Paid", "paid_on": to_datetime(paid_on) or today()}},
        return_document=ReturnDocument.AFTER)
    if new:
        audit("bills", "UPDATE", bill_id, old, new)


def bills_view(status=""):
    match = {"payment_status": status} if status else {}
    pipeline = [
        {"$match": match},
        {"$sort": {"bill_date": -1, "bill_id": -1}},
        {"$lookup": {"from": "patients", "localField": "patient_id",
                     "foreignField": "patient_id", "as": "patient"}},
        {"$unwind": "$patient"},
        {"$addFields": {
            "patient_name": {"$concat": ["$patient.first_name", " ", "$patient.last_name"]},
            "source": {"$cond": [{"$ne": ["$appointment_id", None]}, "OPD", "IPD"]},
        }},
        {"$project": {"_id": 0, "patient": 0}},
    ]
    return rows(get_db().bills.aggregate(pipeline))


def billing_summary():
    """Totals per patient (was the view v_patient_billing_summary)."""
    paid = {"$eq": ["$payment_status", "Paid"]}
    pipeline = [
        {"$group": {"_id": "$patient_id",
                    "bills": {"$sum": 1},
                    "total_billed": {"$sum": "$amount"},
                    "total_paid": {"$sum": {"$cond": [paid, "$amount", 0]}},
                    "outstanding": {"$sum": {"$cond": [paid, 0, "$amount"]}}}},
        {"$lookup": {"from": "patients", "localField": "_id", "foreignField": "patient_id", "as": "patient"}},
        {"$unwind": "$patient"},
        {"$project": {"_id": 0, "patient_id": "$_id", "bills": 1, "total_billed": 1,
                      "total_paid": 1, "outstanding": 1,
                      "patient_name": {"$concat": ["$patient.first_name", " ", "$patient.last_name"]}}},
        {"$sort": {"outstanding": -1}},
    ]
    return list(get_db().bills.aggregate(pipeline))


# =====================================================================
# Pharmacy
# =====================================================================
LOW_STOCK = {"$expr": {"$lt": ["$stock_qty", "$reorder_level"]}}


def medicines():
    out = rows(get_db().medicines.find().sort("name", 1))
    for m in out:
        m["low"] = m["stock_qty"] < m["reorder_level"]
    return out


def low_stock():
    return rows(get_db().medicines.find(LOW_STOCK).sort("stock_qty", 1))


def restock_low_medicines(quantity):
    """Walk a cursor over every medicine below its reorder level and add
    `quantity` units to each. Returns how many were restocked."""
    if not quantity or quantity <= 0:
        raise HMSError("Restock quantity must be positive")
    db = get_db()
    restocked = 0
    for m in db.medicines.find(LOW_STOCK):
        db.medicines.update_one({"_id": m["_id"]}, {"$inc": {"stock_qty": quantity}})
        restocked += 1
    return restocked


# =====================================================================
# Reports
# =====================================================================
def dashboard_stats():
    db = get_db()
    start = today()
    unpaid = list(db.bills.aggregate([{"$match": {"payment_status": "Unpaid"}},
                                      {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]))
    return {
        "patients": db.patients.count_documents({}),
        "doctors": db.staff.count_documents({"role": "Doctor"}),
        "nurses": db.staff.count_documents({"role": "Nurse"}),
        "admitted": db.admissions.count_documents({"status": "Admitted"}),
        "free_rooms": db.rooms.count_documents({"status": "Available"}),
        "today": db.appointments.count_documents({
            "status": "Scheduled",
            "appointment_time": {"$gte": start, "$lt": start + timedelta(days=1)}}),
        "unpaid": unpaid[0]["total"] if unpaid else 0,
    }


def refresh_monthly_revenue():
    """Recompute monthly revenue and store it in its own collection with
    $out: an on-demand materialized view."""
    is_opd = {"$ne": ["$appointment_id", None]}
    get_db().bills.aggregate([
        {"$group": {"_id": {"y": {"$year": "$bill_date"}, "m": {"$month": "$bill_date"}},
                    "opd_revenue": {"$sum": {"$cond": [is_opd, "$amount", 0]}},
                    "ipd_revenue": {"$sum": {"$cond": [is_opd, 0, "$amount"]}},
                    "total_revenue": {"$sum": "$amount"},
                    "collected": {"$sum": {"$cond": [{"$eq": ["$payment_status", "Paid"]}, "$amount", 0]}}}},
        {"$project": {"_id": 0, "month": {"$dateFromParts": {"year": "$_id.y", "month": "$_id.m"}},
                      "opd_revenue": 1, "ipd_revenue": 1, "total_revenue": 1, "collected": 1}},
        {"$out": "mv_monthly_revenue"},
    ])


def monthly_revenue():
    return rows(get_db().mv_monthly_revenue.find().sort("month", 1))


def doctor_workload(date_from, date_to):
    """Appointments and revenue per doctor between two dates, built by
    walking a cursor over the doctors."""
    db = get_db()
    start, end = to_datetime(date_from), to_datetime(date_to) + timedelta(days=1)
    out = []
    for d in db.staff.find({"role": "Doctor"}).sort("last_name", 1):
        appts = list(db.appointments.find({"doctor_id": d["staff_id"],
                                           "appointment_time": {"$gte": start, "$lt": end}},
                                          {"appointment_id": 1, "status": 1}))
        ids = [a["appointment_id"] for a in appts]
        revenue = sum(b["amount"] for b in db.bills.find({"appointment_id": {"$in": ids}}))
        out.append({"doctor_id": d["staff_id"], "doctor_name": full_name(d, "Dr. "),
                    "specialization": d["specialization"], "total": len(appts),
                    "completed": sum(a["status"] == "Completed" for a in appts),
                    "cancelled": sum(a["status"] == "Cancelled" for a in appts),
                    "revenue": revenue})
    return out


def flagged_lab_results():
    names = {p["patient_id"]: full_name(p) for p in get_db().patients.find()}
    out = []
    for r in get_db().medical_records.find({"details.flag": {"$in": list(FLAGGED)}}).sort("recorded_at", -1):
        out.append({"record_id": r["record_id"], "recorded_at": r["recorded_at"],
                    "patient_id": r["patient_id"], "patient_name": names.get(r["patient_id"], "?"),
                    "test": r["details"].get("test"), "flag": r["details"]["flag"]})
    return out


def audit_log(limit=25):
    return rows(get_db().audit_log.find({}, {"old_data": 0, "new_data": 0})
                .sort("log_id", -1).limit(limit))


# =====================================================================
# Export a full patient record as JSON or XML
# =====================================================================
def patient_json(patient_id):
    db = get_db()
    p = db.patients.find_one({"patient_id": patient_id})
    if p is None:
        return None
    doc = {
        "patient_id": p["patient_id"],
        "name": full_name(p),
        "dob": p["dob"].date().isoformat(),
        "gender": p["gender"],
        "blood_group": p.get("blood_group"),
        "address": p.get("address"),
        "allergies": p.get("allergies", []),
        "appointments": [
            {"id": a["appointment_id"], "time": a["appointment_time"].isoformat(),
             "doctor_id": a["doctor_id"], "status": a["status"], "reason": a.get("reason")}
            for a in db.appointments.find({"patient_id": patient_id}).sort("appointment_time", 1)],
        "medical_records": [
            {"type": m["record_type"], "recorded_at": m["recorded_at"].isoformat(), "details": m["details"]}
            for m in db.medical_records.find({"patient_id": patient_id}).sort("recorded_at", 1)],
    }
    return json.dumps(doc, indent=2, default=str)


def patient_xml(patient_id):
    db = get_db()
    p = db.patients.find_one({"patient_id": patient_id})
    if p is None:
        return None
    root = ET.Element("patient", id=str(patient_id))
    for field in ("first_name", "last_name", "dob", "gender", "blood_group", "phone"):
        value = p.get(field)
        if value is not None:
            ET.SubElement(root, field).text = value.date().isoformat() if field == "dob" else str(value)

    doctors = {d["staff_id"]: full_name(d, "Dr. ") for d in db.staff.find({"role": "Doctor"})}
    appts = ET.SubElement(root, "appointments")
    for a in db.appointments.find({"patient_id": patient_id}).sort("appointment_time", 1):
        el = ET.SubElement(appts, "appointment", id=str(a["appointment_id"]), status=a["status"])
        ET.SubElement(el, "time").text = a["appointment_time"].isoformat()
        ET.SubElement(el, "doctor").text = doctors.get(a["doctor_id"], "")
        if a.get("reason"):
            ET.SubElement(el, "reason").text = a["reason"]

    adms = ET.SubElement(root, "admissions")
    for a in db.admissions.find({"patient_id": patient_id}).sort("admit_date", 1):
        el = ET.SubElement(adms, "admission", id=str(a["admission_id"]))
        ET.SubElement(el, "admit_date").text = a["admit_date"].date().isoformat()
        if a.get("discharge_date"):
            ET.SubElement(el, "discharge_date").text = a["discharge_date"].date().isoformat()
        if a.get("diagnosis"):
            ET.SubElement(el, "diagnosis").text = a["diagnosis"]

    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
