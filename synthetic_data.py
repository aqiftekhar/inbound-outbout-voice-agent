"""
Synthetic dummy dataset for the ai.ai KSA healthcare voice bot demo.

Sourced directly from Section 6 of the Technical Journey Specification.
This is fictional demo data only - see spec Section 3, "Scope and Demo Assumptions".

KNOWN SPEC DISCREPANCY (flagged, not silently resolved):
Section 7.6 (get_followup API contract) and the Journey B dialogue script (9.3)
both specify Dr. Sara Al-Harbi / Dermatology / DOC-101 for patient PAT-10021's
due follow-up. Section 6.5's slot table instead lists Dr. Khalid Al-Qahtani /
General Medicine for the same slot times. This dataset follows the API
contract + dialogue script (DOC-101 / Dermatology), treating the doctor name
in the 6.5 table as a documentation error. Verify with the spec author.
"""

from datetime import date

# "Today" for this demo - matches the spec's document date (17 Aug 2026) and
# Journey A's "24 hours before an 18-Aug appointment" trigger logic.
TODAY = date(2026, 8, 17)

CLINICS = {
    "CLN-RYD-01": {"name": "ai Medical Center - Olaya", "city": "Riyadh"},
    "CLN-JED-01": {"name": "ai Medical Center - Al Rawdah", "city": "Jeddah"},
    "CLN-DMM-01": {"name": "ai Medical Center - Al Khobar", "city": "Dammam"},
}

DOCTORS = {
    "DOC-101": {"name": "Dr. Sara Al-Harbi", "specialty": "Dermatology", "clinic_id": "CLN-RYD-01"},
    "DOC-102": {"name": "Dr. Khalid Al-Qahtani", "specialty": "General Medicine", "clinic_id": "CLN-RYD-01"},
    "DOC-201": {"name": "Dr. Reem Al-Ghamdi", "specialty": "Dentistry", "clinic_id": "CLN-JED-01"},
    "DOC-301": {"name": "Dr. Faisal Al-Mutairi", "specialty": "Cardiology", "clinic_id": "CLN-DMM-01"},
}

# Mutable in-process "database" - reset on process restart (demo scope only,
# no persistence layer per spec Section 3 "out of scope: production integrations").
PATIENTS = {
    "PAT-10021": {
        "patient_id": "PAT-10021",
        "name": "Ahmed Al-Otaibi",
        "name_ar": "أحمد العتيبي",
        "gender": "m",
        "mobile": "+966505550101",
        "dob": date(1988, 2, 12),
        "city": "Riyadh",
        "last_visit": date(2026, 2, 12),
        "followup_interval_months": 6,
        "followup_specialty": "Dermatology",
        "followup_doctor_id": "DOC-101",
    },
    "PAT-10022": {
        "patient_id": "PAT-10022",
        "name": "Noura Al-Shehri",
        "name_ar": "نورة الشهري",
        "gender": "f",
        "mobile": "+966555550102",
        "dob": date(1992, 9, 28),
        "city": "Riyadh",
        "last_visit": date(2026, 2, 20),
        "followup_interval_months": 6,
        "followup_specialty": "General Medicine",
        "followup_doctor_id": "DOC-102",
    },
    "PAT-10023": {
        "patient_id": "PAT-10023",
        "name": "Fahad Al-Zahrani",
        "name_ar": "فهد الزهراني",
        "gender": "m",
        "mobile": "+966545550103",
        "dob": date(1985, 6, 4),
        "city": "Jeddah",
        "last_visit": date(2026, 3, 10),
        "followup_interval_months": 6,
        "followup_specialty": "Dentistry",
        "followup_doctor_id": "DOC-201",
    },
    "PAT-10024": {
        "patient_id": "PAT-10024",
        "name": "Maha Al-Qahtani",
        "name_ar": "مها القحطاني",
        "gender": "f",
        "mobile": "+966565550104",
        "dob": date(1979, 11, 19),
        "city": "Dammam",
        "last_visit": date(2026, 1, 15),
        "followup_interval_months": 6,
        "followup_specialty": "Cardiology",
        "followup_doctor_id": "DOC-301",
    },
    "PAT-10025": {
        "patient_id": "PAT-10025",
        "name": "Abdullah Al-Mutairi",
        "name_ar": "عبدالله المطيري",
        "gender": "m",
        "mobile": "+966535550105",
        "dob": date(1990, 5, 7),
        "city": "Riyadh",
        "last_visit": date(2026, 2, 25),
        "followup_interval_months": 12,
        "followup_specialty": "General Medicine",
        "followup_doctor_id": "DOC-102",
    },
}

# Journey A - existing upcoming appointments (Section 6.3)
APPOINTMENTS = {
    "APT-220045": {
        "appointment_id": "APT-220045",
        "patient_id": "PAT-10021",
        "date": date(2026, 8, 18),
        "time": "17:30",
        "doctor_id": "DOC-101",
        "clinic_id": "CLN-RYD-01",
        "status": "Confirmed",
    },
    "APT-220046": {
        "appointment_id": "APT-220046",
        "patient_id": "PAT-10022",
        "date": date(2026, 8, 20),
        "time": "10:00",
        "doctor_id": "DOC-102",
        "clinic_id": "CLN-RYD-01",
        "status": "Confirmed",
    },
    "APT-220047": {
        "appointment_id": "APT-220047",
        "patient_id": "PAT-10023",
        "date": date(2026, 8, 21),
        "time": "16:00",
        "doctor_id": "DOC-201",
        "clinic_id": "CLN-JED-01",
        "status": "Confirmed",
    },
    "APT-220048": {
        "appointment_id": "APT-220048",
        "patient_id": "PAT-10024",
        "date": date(2026, 8, 19),
        "time": "18:30",
        "doctor_id": "DOC-301",
        "clinic_id": "CLN-DMM-01",
        "status": "Confirmed",
    },
}

# Slots - Journey A reschedule pool (Section 6.4), all with Dr. Sara Al-Harbi
SLOTS_JOURNEY_A = {
    "SLOT-301": {"slot_id": "SLOT-301", "date": date(2026, 8, 19), "time": "17:00", "doctor_id": "DOC-101", "clinic_id": "CLN-RYD-01", "available": True},
    "SLOT-302": {"slot_id": "SLOT-302", "date": date(2026, 8, 19), "time": "18:00", "doctor_id": "DOC-101", "clinic_id": "CLN-RYD-01", "available": True},
    "SLOT-303": {"slot_id": "SLOT-303", "date": date(2026, 8, 20), "time": "17:30", "doctor_id": "DOC-101", "clinic_id": "CLN-RYD-01", "available": True},
    "SLOT-304": {"slot_id": "SLOT-304", "date": date(2026, 8, 21), "time": "11:00", "doctor_id": "DOC-101", "clinic_id": "CLN-RYD-01", "available": True},
    "SLOT-305": {"slot_id": "SLOT-305", "date": date(2026, 8, 22), "time": "16:30", "doctor_id": "DOC-101", "clinic_id": "CLN-RYD-01", "available": True},
}

# Slots - Journey B new-booking pool (Section 6.5).
# doctor_id set to DOC-101 per the spec discrepancy note above (see module docstring).
SLOTS_JOURNEY_B = {
    "SLOT-401": {"slot_id": "SLOT-401", "date": date(2026, 8, 21), "time": "09:00", "doctor_id": "DOC-101", "clinic_id": "CLN-RYD-01", "available": True},
    "SLOT-402": {"slot_id": "SLOT-402", "date": date(2026, 8, 21), "time": "11:30", "doctor_id": "DOC-101", "clinic_id": "CLN-RYD-01", "available": True},
    "SLOT-403": {"slot_id": "SLOT-403", "date": date(2026, 8, 22), "time": "15:00", "doctor_id": "DOC-101", "clinic_id": "CLN-RYD-01", "available": True},
    "SLOT-404": {"slot_id": "SLOT-404", "date": date(2026, 8, 24), "time": "17:00", "doctor_id": "DOC-101", "clinic_id": "CLN-RYD-01", "available": True},
    "SLOT-405": {"slot_id": "SLOT-405", "date": date(2026, 8, 25), "time": "10:30", "doctor_id": "DOC-101", "clinic_id": "CLN-RYD-01", "available": True},
}

# All slots share one pool for lookup-by-id convenience (reschedule and new
# booking draw from their own subsets, but a slot_id is unique across both).
ALL_SLOTS = {**SLOTS_JOURNEY_A, **SLOTS_JOURNEY_B}

# Counter for newly created appointments; spec fixes the first one at
# APT-220099 (Section 7.7 / Section 9.3 script), subsequent demo bookings
# increment from there to avoid id collisions within one demo session.
_next_new_appointment_seq = [220099]


def next_new_appointment_id() -> str:
    apt_id = f"APT-{_next_new_appointment_seq[0]}"
    _next_new_appointment_seq[0] += 1
    return apt_id