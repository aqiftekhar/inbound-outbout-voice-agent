"""
Web dashboard backend - replaces manage.py's CLI as the primary way to view
patients/appointments, add new ones, trigger calls, and review the activity
log. Everything reads/writes through db.py (SQLite) - no JSON files
anywhere in this stack anymore.

Run: uvicorn web_app:app --host 0.0.0.0 --port 8080
"""

import asyncio
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db


def _integrity_error_to_message(e: sqlite3.IntegrityError) -> str:
    """
    Translates a raw SQLite constraint violation into a clear, human-
    readable message - without this, FastAPI's default response for an
    unhandled exception is plain text ("Internal Server Error"), which
    breaks the frontend's response.json() call entirely (it isn't JSON at
    all), and gives the person filling out the form no idea what to fix.
    """
    msg = str(e)
    if "UNIQUE constraint failed: patients.mobile" in msg:
        return "That mobile number is already registered to another patient."
    if "UNIQUE" in msg or "PRIMARY KEY" in msg:
        return "A record with that ID already exists."
    if "FOREIGN KEY constraint failed" in msg:
        return ("One of the selected IDs (doctor, clinic, or patient) doesn't exist. "
                "Please double-check the dropdown selections.")
    if "CHECK constraint failed" in msg:
        return "One of the submitted values isn't valid (e.g. gender must be 'm' or 'f')."
    if "NOT NULL constraint failed" in msg:
        field = msg.split("NOT NULL constraint failed:")[-1].strip()
        return f"Required field is missing: {field}"
    return f"Could not save the record: {msg}"
from trigger_call import trigger_outbound_call

db.init_db()

app = FastAPI(title="ai Medical - Voice Ops Dashboard")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
@app.get("/api/doctors")
async def api_doctors():
    return db.list_doctors()


@app.get("/api/clinics")
async def api_clinics():
    return db.list_clinics()


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------
class PatientIn(BaseModel):
    patient_id: str
    name: str
    name_ar: str
    gender: str
    mobile: str
    dob: date
    city: str
    last_visit: date
    followup_interval_months: int
    followup_specialty: str
    followup_doctor_id: str


@app.get("/api/patients")
async def api_list_patients():
    return db.list_patients()


@app.post("/api/patients")
async def api_add_patient(patient: PatientIn):
    if db.find_patient(patient_id=patient.patient_id):
        raise HTTPException(400, f"Patient {patient.patient_id} already exists")
    try:
        return db.add_patient(**patient.model_dump())
    except sqlite3.IntegrityError as e:
        raise HTTPException(400, _integrity_error_to_message(e))


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------
class AppointmentIn(BaseModel):
    appointment_id: str
    patient_id: str
    date: date
    time: str
    doctor_id: str
    clinic_id: str
    reason: Optional[str] = None


@app.get("/api/appointments")
async def api_list_appointments(patient_id: Optional[str] = None):
    return db.list_appointments(patient_id=patient_id)


@app.post("/api/appointments")
async def api_add_appointment(apt: AppointmentIn):
    # Catches a real mistake that happened in practice: appointment_id and
    # patient_id fields entered swapped in the form. Both values silently
    # "worked" - patient_id matched an existing patient, appointment_id
    # was accepted as any string - so the row saved successfully with the
    # wrong patient attached to it, and the appointment became permanently
    # invisible to that patient's actual lookups. This check makes that
    # specific mistake impossible to save instead of failing silently.
    if not apt.appointment_id.upper().startswith("APT-"):
        raise HTTPException(
            400,
            f"'{apt.appointment_id}' doesn't look like an appointment ID (expected to start "
            f"with 'APT-'). Did you swap the Appointment ID and Patient ID fields?",
        )
    if not apt.patient_id.upper().startswith("PAT-"):
        raise HTTPException(
            400,
            f"'{apt.patient_id}' doesn't look like a patient ID (expected to start with "
            f"'PAT-'). Did you swap the Appointment ID and Patient ID fields?",
        )
    if not db.find_patient(patient_id=apt.patient_id):
        raise HTTPException(400, f"Unknown patient_id: {apt.patient_id}")
    try:
        return db.add_appointment(
            appointment_id=apt.appointment_id, patient_id=apt.patient_id,
            date_=apt.date, time=apt.time, doctor_id=apt.doctor_id,
            clinic_id=apt.clinic_id, reason=apt.reason,
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(400, _integrity_error_to_message(e))


# ---------------------------------------------------------------------------
# Call triggering
# ---------------------------------------------------------------------------
class CallNowIn(BaseModel):
    patient_id: str
    journey: str  # "A" or "B"
    phone: Optional[str] = None


@app.post("/api/call-now")
async def api_call_now(req: CallNowIn):
    patient = db.find_patient(patient_id=req.patient_id)
    if not patient:
        raise HTTPException(404, f"Unknown patient_id: {req.patient_id}")
    if req.journey not in ("A", "B"):
        raise HTTPException(400, "journey must be 'A' or 'B'")

    phone = req.phone or patient["mobile"]
    try:
        await trigger_outbound_call(req.journey, req.patient_id, phone)
    except SystemExit as e:
        raise HTTPException(500, str(e))
    return {"status": "triggered", "patient_id": req.patient_id, "journey": req.journey, "phone": phone}


# ---------------------------------------------------------------------------
# Activity log (dispositions + transcripts)
# ---------------------------------------------------------------------------
@app.get("/api/dispositions")
async def api_dispositions(limit: int = 50):
    return db.list_dispositions(limit=limit)


@app.get("/api/dispositions/{call_id}/transcript")
async def api_transcript(call_id: str):
    return db.get_transcript(call_id)