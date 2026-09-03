"""
SQLite persistence layer for patients/appointments/slots/doctors/clinics.

Replaces the in-memory Python dicts in synthetic_data.py, which reset to
their original 5 fake patients on every process restart and had no way to
view or modify data except hand-editing source code. This module is the
single source of truth mock_api.py reads/writes through; synthetic_data.py
now only supplies the one-time seed data (and TODAY, used elsewhere).

Why SQLite and not a vector DB: a vector DB solves semantic similarity
search over unstructured text (the right tool for the Almosafer FAQ bot's
RAG lookup). Patient/appointment data needs exact-match queries, date-range
filters, and reliable row updates (reschedule/cancel) - a vector DB doesn't
natively support any of that. SQLite is a real relational database with
zero server setup, a single file, and no new dependency (sqlite3 is stdlib).
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent / "ai_medical.db")))


def _adapt_date(d: date) -> str:
    return d.isoformat()


def _convert_date(s: bytes) -> date:
    return date.fromisoformat(s.decode())


sqlite3.register_adapter(date, _adapt_date)
sqlite3.register_converter("DATE", _convert_date)


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS clinics (
    clinic_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doctors (
    doctor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    clinic_id TEXT NOT NULL REFERENCES clinics(clinic_id)
);

CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_ar TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('m', 'f')),
    mobile TEXT NOT NULL UNIQUE,
    dob DATE NOT NULL,
    city TEXT NOT NULL,
    last_visit DATE,
    followup_interval_months INTEGER,
    followup_specialty TEXT,
    followup_doctor_id TEXT REFERENCES doctors(doctor_id)
);

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(patient_id),
    date DATE NOT NULL,
    time TEXT NOT NULL,
    doctor_id TEXT NOT NULL REFERENCES doctors(doctor_id),
    clinic_id TEXT NOT NULL REFERENCES clinics(clinic_id),
    status TEXT NOT NULL DEFAULT 'Confirmed',
    reason TEXT,
    cancel_reason TEXT
);

CREATE TABLE IF NOT EXISTS slots (
    slot_id TEXT PRIMARY KEY,
    date DATE NOT NULL,
    time TEXT NOT NULL,
    doctor_id TEXT NOT NULL REFERENCES doctors(doctor_id),
    clinic_id TEXT NOT NULL REFERENCES clinics(clinic_id),
    available INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS dispositions (
    call_id TEXT PRIMARY KEY,
    patient_id TEXT,
    appointment_id TEXT,
    journey TEXT,
    intent TEXT,
    language TEXT,
    verification TEXT,
    outcome TEXT,
    old_date TEXT,
    old_time TEXT,
    new_date TEXT,
    new_time TEXT,
    slot_id TEXT,
    api_actions TEXT,       -- JSON-encoded list
    human_transfer INTEGER,
    transcript_reference TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS transcript_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transcript_call ON transcript_turns(call_id);
"""


def init_db():
    """Creates tables if they don't exist, and seeds from synthetic_data.py
    ONLY if the patients table is currently empty (so re-running this never
    wipes real data you've added via manage.py)."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        if count == 0:
            _seed(conn)


def _seed(conn):
    import synthetic_data as sd

    for cid, c in sd.CLINICS.items():
        conn.execute(
            "INSERT INTO clinics (clinic_id, name, city) VALUES (?, ?, ?)",
            (cid, c["name"], c["city"]),
        )
    for did, d in sd.DOCTORS.items():
        conn.execute(
            "INSERT INTO doctors (doctor_id, name, specialty, clinic_id) VALUES (?, ?, ?, ?)",
            (did, d["name"], d["specialty"], d["clinic_id"]),
        )
    for pid, p in sd.PATIENTS.items():
        conn.execute(
            """INSERT INTO patients
               (patient_id, name, name_ar, gender, mobile, dob, city, last_visit,
                followup_interval_months, followup_specialty, followup_doctor_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pid, p["name"], p["name_ar"], p["gender"], p["mobile"], p["dob"], p["city"],
             p["last_visit"], p["followup_interval_months"], p["followup_specialty"],
             p["followup_doctor_id"]),
        )
    for aid, a in sd.APPOINTMENTS.items():
        conn.execute(
            """INSERT INTO appointments
               (appointment_id, patient_id, date, time, doctor_id, clinic_id, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (aid, a["patient_id"], a["date"], a["time"], a["doctor_id"], a["clinic_id"], a["status"]),
        )
    for sid, s in sd.ALL_SLOTS.items():
        conn.execute(
            """INSERT INTO slots (slot_id, date, time, doctor_id, clinic_id, available)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sid, s["date"], s["time"], s["doctor_id"], s["clinic_id"], int(s["available"])),
        )


def reset_demo_data():
    """Drops and re-seeds everything from synthetic_data.py. Used by the
    test suite to get a clean, known state before each run - NOT something
    to run against real accumulated data."""
    with _connect() as conn:
        conn.executescript(
            "DROP TABLE IF EXISTS appointments; DROP TABLE IF EXISTS slots; "
            "DROP TABLE IF EXISTS patients; DROP TABLE IF EXISTS doctors; "
            "DROP TABLE IF EXISTS clinics; DROP TABLE IF EXISTS dispositions; "
            "DROP TABLE IF EXISTS transcript_turns;"
        )
        conn.executescript(SCHEMA)
        _seed(conn)


# ---------------------------------------------------------------------------
# Dispositions + transcripts - replaces call_dispositions.jsonl and
# transcripts/*.json with real queryable SQLite tables (was previously the
# last remaining JSON-file-based storage in the project).
# ---------------------------------------------------------------------------

def insert_disposition(record: dict):
    import json as _json
    with _connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO dispositions
               (call_id, patient_id, appointment_id, journey, intent, language,
                verification, outcome, old_date, old_time, new_date, new_time,
                slot_id, api_actions, human_transfer, transcript_reference, created_at)
               VALUES (:call_id, :patient_id, :appointment_id, :journey, :intent, :language,
                       :verification, :outcome, :old_date, :old_time, :new_date, :new_time,
                       :slot_id, :api_actions, :human_transfer, :transcript_reference, :created_at)""",
            {**record, "api_actions": _json.dumps(record.get("api_actions") or []),
             "human_transfer": int(bool(record.get("human_transfer")))},
        )


def list_dispositions(limit: int = 100) -> list[dict]:
    import json as _json
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM dispositions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["api_actions"] = _json.loads(d["api_actions"] or "[]")
            d["human_transfer"] = bool(d["human_transfer"])
            results.append(d)
        return results


def insert_transcript_turn(call_id: str, role: str, text: str, ts: str):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO transcript_turns (call_id, role, text, ts) VALUES (?, ?, ?, ?)",
            (call_id, role, text, ts),
        )


def get_transcript(call_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, text, ts FROM transcript_turns WHERE call_id = ? ORDER BY id", (call_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Read/write helpers - used by mock_api.py (async wrappers) and manage.py (direct)
# ---------------------------------------------------------------------------

def doctor_and_clinic(doctor_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            """SELECT d.doctor_id, d.name AS doctor_name, d.specialty, c.name AS clinic_name, c.city
               FROM doctors d JOIN clinics c ON d.clinic_id = c.clinic_id
               WHERE d.doctor_id = ?""",
            (doctor_id,),
        ).fetchone()
        return dict(row) if row else None


def find_patient(mobile: Optional[str] = None, patient_id: Optional[str] = None) -> Optional[dict]:
    with _connect() as conn:
        if patient_id:
            row = conn.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
        elif mobile:
            normalized = mobile.replace(" ", "").replace("-", "")
            row = conn.execute(
                "SELECT * FROM patients WHERE REPLACE(REPLACE(mobile,' ',''),'-','') = ?",
                (normalized,),
            ).fetchone()
        else:
            return None
        return dict(row) if row else None


def list_patients() -> list[dict]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM patients ORDER BY patient_id").fetchall()]


def list_doctors() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT d.*, c.name AS clinic_name FROM doctors d JOIN clinics c ON d.clinic_id = c.clinic_id "
            "ORDER BY d.doctor_id"
        ).fetchall()
        return [dict(r) for r in rows]


def list_clinics() -> list[dict]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM clinics ORDER BY clinic_id").fetchall()]


def add_patient(**fields) -> dict:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO patients
               (patient_id, name, name_ar, gender, mobile, dob, city, last_visit,
                followup_interval_months, followup_specialty, followup_doctor_id)
               VALUES (:patient_id, :name, :name_ar, :gender, :mobile, :dob, :city, :last_visit,
                       :followup_interval_months, :followup_specialty, :followup_doctor_id)""",
            fields,
        )
    return fields


def get_upcoming_appointment(patient_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            """SELECT a.*, d.name AS doctor_name, d.specialty, c.name AS clinic_name, c.city
               FROM appointments a
               JOIN doctors d ON a.doctor_id = d.doctor_id
               JOIN clinics c ON a.clinic_id = c.clinic_id
               WHERE a.patient_id = ? AND (a.status IS NULL OR a.status != 'Cancelled')
               ORDER BY a.date ASC LIMIT 1""",
            (patient_id,),
        ).fetchone()
        return dict(row) if row else None



def list_appointments(patient_id: Optional[str] = None) -> list[dict]:
    with _connect() as conn:
        if patient_id:
            rows = conn.execute(
                """SELECT a.*, d.name AS doctor_name, c.name AS clinic_name
                   FROM appointments a JOIN doctors d ON a.doctor_id = d.doctor_id
                   JOIN clinics c ON a.clinic_id = c.clinic_id
                   WHERE a.patient_id = ? ORDER BY a.date""",
                (patient_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT a.*, d.name AS doctor_name, c.name AS clinic_name
                   FROM appointments a JOIN doctors d ON a.doctor_id = d.doctor_id
                   JOIN clinics c ON a.clinic_id = c.clinic_id
                   ORDER BY a.date"""
            ).fetchall()
        return [dict(r) for r in rows]


def add_appointment(appointment_id: str, patient_id: str, date_: date, time: str,
                     doctor_id: str, clinic_id: str, status: str = "Confirmed",
                     reason: Optional[str] = None) -> dict:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO appointments (appointment_id, patient_id, date, time, doctor_id,
               clinic_id, status, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (appointment_id, patient_id, date_, time, doctor_id, clinic_id, status, reason),
        )
    return {"appointment_id": appointment_id, "date": date_, "time": time, "status": status}


def get_available_slots(doctor_id: str, from_date: date, to_date: date,
                         preferred_date: Optional[date] = None, limit: int = 3) -> list[dict]:
    with _connect() as conn:
        if preferred_date:
            rows = conn.execute(
                """SELECT slot_id, date, time FROM slots
                   WHERE doctor_id = ? AND available = 1 AND date = ?
                   ORDER BY date, time""",
                (doctor_id, preferred_date),
            ).fetchall()
            if rows:
                return [dict(r) for r in rows][:limit]
        rows = conn.execute(
            """SELECT slot_id, date, time FROM slots
               WHERE doctor_id = ? AND available = 1 AND date BETWEEN ? AND ?
               ORDER BY date, time LIMIT ?""",
            (doctor_id, from_date, to_date, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_slot(slot_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM slots WHERE slot_id = ?", (slot_id,)).fetchone()
        return dict(row) if row else None


def get_appointment(appointment_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM appointments WHERE appointment_id = ?", (appointment_id,)).fetchone()
        return dict(row) if row else None


def reschedule_appointment(appointment_id: str, new_slot_id: str) -> dict:
    with _connect() as conn:
        apt = conn.execute("SELECT * FROM appointments WHERE appointment_id = ?", (appointment_id,)).fetchone()
        slot = conn.execute("SELECT * FROM slots WHERE slot_id = ?", (new_slot_id,)).fetchone()
        if not apt:
            return {"status": "FAILED", "error": "APPOINTMENT_NOT_FOUND"}
        if not slot:
            return {"status": "FAILED", "error": "SLOT_NOT_FOUND"}
        if not slot["available"]:
            return {"status": "FAILED", "error": "SLOT_NO_LONGER_AVAILABLE"}
        if apt["status"] == "Cancelled":
            return {"status": "FAILED", "error": "APPOINTMENT_ALREADY_CANCELLED"}

        old_date, old_time = apt["date"], apt["time"]
        conn.execute(
            "UPDATE appointments SET date = ?, time = ?, doctor_id = ?, status = 'Confirmed' WHERE appointment_id = ?",
            (slot["date"], slot["time"], slot["doctor_id"], appointment_id),
        )
        conn.execute("UPDATE slots SET available = 0 WHERE slot_id = ?", (new_slot_id,))
        return {
            "status": "CONFIRMED", "appointment_id": appointment_id,
            "old_date": old_date, "old_time": old_time,
            "date": slot["date"], "time": slot["time"],
        }


def cancel_appointment(appointment_id: str, reason: Optional[str] = None) -> dict:
    with _connect() as conn:
        apt = conn.execute("SELECT * FROM appointments WHERE appointment_id = ?", (appointment_id,)).fetchone()
        if not apt:
            return {"status": "FAILED", "error": "APPOINTMENT_NOT_FOUND"}
        if apt["status"] == "Cancelled":
            return {"status": "ALREADY_CANCELLED", "appointment_id": appointment_id}
        conn.execute(
            "UPDATE appointments SET status = 'Cancelled', cancel_reason = ? WHERE appointment_id = ?",
            (reason, appointment_id),
        )
        return {"status": "CANCELLED", "appointment_id": appointment_id}


def get_patient_followup_fields(patient_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT last_visit, followup_interval_months, followup_specialty, followup_doctor_id "
            "FROM patients WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        return dict(row) if row else None


def create_new_appointment(appointment_id: str, patient_id: str, slot_id: str,
                            reason: str = "Routine follow-up") -> dict:
    with _connect() as conn:
        slot = conn.execute("SELECT * FROM slots WHERE slot_id = ?", (slot_id,)).fetchone()
        if not slot:
            return {"status": "FAILED", "error": "SLOT_NOT_FOUND"}
        if not slot["available"]:
            return {"status": "FAILED", "error": "SLOT_NO_LONGER_AVAILABLE"}
        conn.execute(
            """INSERT INTO appointments (appointment_id, patient_id, date, time, doctor_id,
               clinic_id, status, reason) VALUES (?, ?, ?, ?, ?, ?, 'Confirmed', ?)""",
            (appointment_id, patient_id, slot["date"], slot["time"], slot["doctor_id"],
             slot["clinic_id"], reason),
        )
        conn.execute("UPDATE slots SET available = 0 WHERE slot_id = ?", (slot_id,))
        return {"status": "CONFIRMED", "appointment_id": appointment_id, "date": slot["date"], "time": slot["time"]}


def simulate_slot_taken(slot_id: str):
    with _connect() as conn:
        conn.execute("UPDATE slots SET available = 0 WHERE slot_id = ?", (slot_id,))


def next_new_appointment_id() -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT appointment_id FROM appointments WHERE appointment_id LIKE 'APT-2200%' "
            "ORDER BY appointment_id DESC LIMIT 1"
        ).fetchone()
        if row:
            last_num = int(row["appointment_id"].split("-")[1])
            return f"APT-{max(last_num + 1, 220099)}"
        return "APT-220099"