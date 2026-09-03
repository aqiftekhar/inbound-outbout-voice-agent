"""
API layer implementing the 7 API contracts from Section 7 of the spec -
same function signatures and response shapes as before, so agent.py needs
NO changes. The difference: these now read/write through db.py (SQLite)
instead of mutating an in-memory dict, so data actually persists across
restarts and can be viewed/edited via manage.py.

Kept as async functions (wrapping sync sqlite3 calls in asyncio.to_thread)
so this still slots into the same function_tool call pattern in agent.py,
and so a real DB call doesn't block the event loop during a live call.
"""

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

import db
from config import get_demo_today

logger = logging.getLogger("ai-mock-api")

_LATENCY_SECONDS = 0.15


async def _simulate_latency():
    await asyncio.sleep(_LATENCY_SECONDS)


def _doctor_and_clinic(doctor_id: str) -> dict:
    result = db.doctor_and_clinic(doctor_id)
    return result or {}


# ---------------------------------------------------------------------------
# 7.1 Find Patient
# ---------------------------------------------------------------------------
async def find_patient(mobile: Optional[str] = None, patient_id: Optional[str] = None) -> Optional[dict]:
    await _simulate_latency()
    p = await asyncio.to_thread(db.find_patient, mobile, patient_id)
    if not p:
        return None
    return {
        "patient_id": p["patient_id"], "name": p["name"], "name_ar": p["name_ar"],
        "gender": p["gender"], "mobile": p["mobile"], "dob": p["dob"], "city": p["city"],
    }


# ---------------------------------------------------------------------------
# 7.2 Get Upcoming Appointment
# ---------------------------------------------------------------------------
async def get_upcoming_appointment(patient_id: str) -> Optional[dict]:
    await _simulate_latency()
    row = await asyncio.to_thread(db.get_upcoming_appointment, patient_id)
    if not row:
        return None
    return {
        "appointment_id": row["appointment_id"], "date": row["date"], "time": row["time"],
        "status": row["status"], "doctor_id": row["doctor_id"], "doctor_name": row["doctor_name"],
        "specialty": row["specialty"], "clinic_name": row["clinic_name"], "city": row["city"],
    }


def get_appointment_raw(appointment_id: str) -> Optional[dict]:
    return db.get_appointment(appointment_id)


# ---------------------------------------------------------------------------
# 7.3 Get Available Slots
# ---------------------------------------------------------------------------
async def get_available_slots(
    doctor_id: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    preferred_date: Optional[date] = None,
    limit: int = 3,
) -> list[dict]:
    await _simulate_latency()
    from_date = from_date or get_demo_today()
    to_date = to_date or (from_date + timedelta(days=14))
    return await asyncio.to_thread(
        db.get_available_slots, doctor_id, from_date, to_date, preferred_date, limit
    )


# ---------------------------------------------------------------------------
# 7.4 Reschedule Appointment
# ---------------------------------------------------------------------------
async def reschedule_appointment(appointment_id: str, new_slot_id: str) -> dict:
    await _simulate_latency()
    result = await asyncio.to_thread(db.reschedule_appointment, appointment_id, new_slot_id)
    if result["status"] == "CONFIRMED":
        logger.info(f"reschedule_appointment: {appointment_id} -> {result['date']} {result['time']}")
    return result


# ---------------------------------------------------------------------------
# 7.5 Cancel Appointment
# ---------------------------------------------------------------------------
async def cancel_appointment(appointment_id: str, reason: Optional[str] = None) -> dict:
    await _simulate_latency()
    result = await asyncio.to_thread(db.cancel_appointment, appointment_id, reason)
    logger.info(f"cancel_appointment: {appointment_id} -> {result['status']}")
    return result


# ---------------------------------------------------------------------------
# 7.6 Get Follow-up Due Status
# ---------------------------------------------------------------------------
async def get_followup_status(patient_id: str) -> Optional[dict]:
    await _simulate_latency()
    p = await asyncio.to_thread(db.get_patient_followup_fields, patient_id)
    if not p or not p["last_visit"]:
        return None
    last_visit = p["last_visit"]
    months = p["followup_interval_months"]
    due_date = date(
        last_visit.year + (last_visit.month + months - 1) // 12,
        (last_visit.month + months - 1) % 12 + 1,
        last_visit.day,
    )
    return {
        "last_visit": last_visit,
        "followup_interval_months": months,
        "due_date": due_date,
        "is_due": due_date <= get_demo_today(),
        "specialty": p["followup_specialty"],
        "doctor_id": p["followup_doctor_id"],
    }


# ---------------------------------------------------------------------------
# 7.7 Create New Appointment
# ---------------------------------------------------------------------------
async def create_new_appointment(patient_id: str, slot_id: str, reason: str = "Routine follow-up") -> dict:
    await _simulate_latency()
    new_id = await asyncio.to_thread(db.next_new_appointment_id)
    result = await asyncio.to_thread(db.create_new_appointment, new_id, patient_id, slot_id, reason)
    if result["status"] == "CONFIRMED":
        logger.info(f"create_new_appointment: {new_id} for {patient_id} at {result['date']} {result['time']}")
    return result


def simulate_slot_taken(slot_id: str):
    """For QA test E07: mark a slot unavailable after it was offered."""
    db.simulate_slot_taken(slot_id)