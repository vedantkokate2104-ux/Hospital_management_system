"""Database helpers: one shared MongoDB client, id counters, audit log
and readable error messages."""
import getpass
import os
from datetime import date, datetime, time

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError, ServerSelectionTimeoutError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_client = None


def get_db():
    """The hospital database. MongoClient keeps its own connection pool,
    so one client is shared by every request."""
    global _client
    if _client is None:
        _client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"),
                              serverSelectionTimeoutMS=5000, tz_aware=False)
    return _client[os.getenv("MONGO_DB", "hospital_db")]


class HMSError(Exception):
    """A business rule was broken; the message is shown to the user."""


def next_id(name):
    """Auto-increment integer id (what SERIAL did in SQL), kept in the
    counters collection and incremented atomically."""
    doc = get_db().counters.find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    return doc["seq"]


# ---------------------------------------------------------------------
# Dates: BSON only has datetimes, so calendar dates are stored as
# midnight and turned back into date objects when read.
# ---------------------------------------------------------------------
DATE_FIELDS = {"dob", "hire_date", "admit_date", "discharge_date", "bill_date", "paid_on", "month"}


def to_datetime(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time())
    return datetime.fromisoformat(value)


def clean(doc):
    """Drop Mongo's _id and convert stored dates back to date objects."""
    if doc is None:
        return None
    doc = {k: v for k, v in doc.items() if k != "_id"}
    for key in DATE_FIELDS & doc.keys():
        if isinstance(doc[key], datetime):
            doc[key] = doc[key].date()
    return doc


def rows(cursor):
    return [clean(d) for d in cursor]


# ---------------------------------------------------------------------
# Audit log (the PostgreSQL version filled it from triggers)
# ---------------------------------------------------------------------
def audit(collection, operation, row_id, old=None, new=None):
    strip = lambda d: None if d is None else {k: v for k, v in d.items() if k != "_id"}
    get_db().audit_log.insert_one({
        "log_id": next_id("audit_log"),
        "table_name": collection,
        "operation": operation,
        "row_id": str(row_id),
        "changed_by": getpass.getuser(),
        "changed_at": datetime.now(),
        "old_data": strip(old),
        "new_data": strip(new),
    })


# Friendlier text for unique-index violations, keyed by index name
INDEX_MESSAGES = {
    "uq_doctor_slot": "The doctor already has an appointment at that time.",
    "uq_one_active_admission": "This patient is already admitted.",
    "uq_room_number": "A room with that number already exists.",
    "uq_medicine_name": "A medicine with that name already exists.",
}


def error_message(exc):
    """Readable text for a business-rule or MongoDB error."""
    if isinstance(exc, HMSError):
        return str(exc)
    if isinstance(exc, DuplicateKeyError):
        for name, text in INDEX_MESSAGES.items():
            if name in str(exc):
                return text
        return "That record already exists."
    if isinstance(exc, ServerSelectionTimeoutError):
        return "Could not connect to MongoDB. Is the server running?"
    if isinstance(exc, PyMongoError) and getattr(exc, "code", None) == 121:
        return "The data failed the collection's schema validation."
    return str(exc).splitlines()[0]
