"""Create the hospital_db MongoDB database: collections with $jsonSchema
validators, indexes, and sample data. Safe to re-run: it drops and
recreates the database.

    python init_db.py
"""
import sys

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import PyMongoError

import sample_data
from db import get_db

NULLABLE_STR = {"bsonType": ["string", "null"]}
INT = {"bsonType": ["int", "long"]}

# $jsonSchema validators: the MongoDB equivalent of CHECK constraints,
# domains and ENUM types. Writes that break them are rejected.
VALIDATORS = {
    "patients": {
        "required": ["patient_id", "first_name", "last_name", "dob", "gender", "phone", "allergies"],
        "properties": {
            "patient_id": INT,
            "dob": {"bsonType": "date"},
            "gender": {"enum": ["Male", "Female", "Other"]},
            "blood_group": {"enum": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", None]},
            "phone": {"bsonType": "string", "pattern": r"^\+?[0-9]{10,13}$"},
            "email": {"bsonType": ["string", "null"], "pattern": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"},
            "address": {"bsonType": ["object", "null"],
                        "properties": {"street": NULLABLE_STR, "city": NULLABLE_STR,
                                       "state": NULLABLE_STR, "pincode": NULLABLE_STR}},
            "allergies": {"bsonType": "array", "items": {"bsonType": "string"}},
        },
    },
    "staff": {
        "required": ["staff_id", "role", "first_name", "last_name", "phone", "email", "salary", "dept_id"],
        "properties": {
            "role": {"enum": ["Doctor", "Nurse"]},
            "salary": {"bsonType": "number", "minimum": 0, "exclusiveMinimum": True},
            "consultation_fee": {"bsonType": "number", "minimum": 0},
            "shift": {"enum": ["Morning", "Evening", "Night"]},
        },
    },
    "rooms": {
        "required": ["room_id", "room_number", "room_type", "daily_charge", "status"],
        "properties": {
            "room_type": {"enum": ["General", "Semi-Private", "Private", "ICU"]},
            "status": {"enum": ["Available", "Occupied", "Maintenance"]},
            "daily_charge": {"bsonType": "number", "minimum": 0, "exclusiveMinimum": True},
        },
    },
    "appointments": {
        "required": ["appointment_id", "patient_id", "doctor_id", "appointment_time", "status"],
        "properties": {
            "appointment_time": {"bsonType": "date"},
            "status": {"enum": ["Scheduled", "Completed", "Cancelled"]},
            "prescriptions": {"bsonType": "array", "items": {
                "bsonType": "object",
                "required": ["medicine_id", "dosage", "quantity", "duration_days"],
                "properties": {"quantity": {"bsonType": ["int", "long"], "minimum": 1},
                               "duration_days": {"bsonType": ["int", "long"], "minimum": 1}}}},
        },
    },
    "admissions": {
        "required": ["admission_id", "patient_id", "room_id", "doctor_id", "admit_date", "status"],
        "properties": {
            "admit_date": {"bsonType": "date"},
            "discharge_date": {"bsonType": ["date", "null"]},
            "status": {"enum": ["Admitted", "Discharged"]},
        },
    },
    "medicines": {
        "required": ["medicine_id", "name", "unit_price", "stock_qty", "reorder_level"],
        "properties": {
            "unit_price": {"bsonType": "number", "minimum": 0},
            "stock_qty": {"bsonType": ["int", "long"], "minimum": 0},
        },
    },
    "bills": {
        "required": ["bill_id", "patient_id", "amount", "bill_date", "payment_status"],
        "properties": {
            "amount": {"bsonType": "number", "minimum": 0},
            "payment_status": {"enum": ["Unpaid", "Paid"]},
            "paid_on": {"bsonType": ["date", "null"]},
        },
    },
    "medical_records": {
        "required": ["record_id", "patient_id", "record_type", "recorded_at", "details"],
        "properties": {"details": {"bsonType": "object"}, "summary_xml": NULLABLE_STR},
    },
}


def unique(field, **kw):
    return IndexModel([(field, ASCENDING)], unique=True, **kw)


INDEXES = {
    "departments": [unique("dept_id"), unique("name")],
    "staff": [unique("staff_id"), unique("email"),
              IndexModel([("license_no", ASCENDING)], unique=True, name="uq_license_no",
                         partialFilterExpression={"role": "Doctor"}),
              IndexModel([("role", ASCENDING)])],
    "patients": [unique("patient_id"),
                 IndexModel([("last_name", ASCENDING), ("first_name", ASCENDING)], name="idx_patient_name"),
                 IndexModel([("allergies", ASCENDING)], name="idx_patient_allergies")],  # multikey
    "rooms": [unique("room_id"), unique("room_number", name="uq_room_number")],
    "appointments": [unique("appointment_id"),
                     IndexModel([("doctor_id", ASCENDING), ("appointment_time", ASCENDING)],
                                unique=True, name="uq_doctor_slot"),
                     IndexModel([("appointment_time", ASCENDING)]),
                     IndexModel([("patient_id", ASCENDING)])],
    # a patient can have at most one open admission
    "admissions": [unique("admission_id"),
                   IndexModel([("patient_id", ASCENDING)], unique=True, name="uq_one_active_admission",
                              partialFilterExpression={"status": "Admitted"}),
                   IndexModel([("room_id", ASCENDING), ("admit_date", ASCENDING)])],
    "medicines": [unique("medicine_id"), unique("name", name="uq_medicine_name")],
    # one bill per appointment / admission (only where the field is a number)
    "bills": [unique("bill_id"),
              IndexModel([("appointment_id", ASCENDING)], unique=True, name="uq_bill_appointment",
                         partialFilterExpression={"appointment_id": {"$type": "number"}}),
              IndexModel([("admission_id", ASCENDING)], unique=True, name="uq_bill_admission",
                         partialFilterExpression={"admission_id": {"$type": "number"}}),
              IndexModel([("patient_id", ASCENDING)], name="idx_bills_unpaid",
                         partialFilterExpression={"payment_status": "Unpaid"})],
    "medical_records": [unique("record_id"), IndexModel([("patient_id", ASCENDING)]),
                        IndexModel([("details.flag", ASCENDING)], name="idx_records_flag")],
    "audit_log": [unique("log_id"), IndexModel([("changed_at", DESCENDING)])],
}


def create_schema(db):
    for name, schema in VALIDATORS.items():
        db.create_collection(name, validator={"$jsonSchema": {"bsonType": "object", **schema}})
    for name, indexes in INDEXES.items():
        db[name].create_indexes(indexes)


def main():
    db = get_db()
    try:
        db.client.admin.command("ping")
    except PyMongoError as exc:
        sys.exit(f"Could not connect to MongoDB: {exc}\n"
                 "Start the MongoDB server and check MONGO_URI in your .env file.")

    # drop collections one by one: a plain readWrite user (the usual
    # Atlas role) may drop collections but not the whole database
    for name in db.list_collection_names():
        db.drop_collection(name)
    print(f"Creating collections and indexes in {db.name} ...")
    create_schema(db)
    print("Loading sample data ...")
    sample_data.load()
    print("Database ready. Start the app with:  python app.py")


if __name__ == "__main__":
    main()
