"""
Call disposition + transcript logging - now backed by SQLite (db.py),
replacing the earlier call_dispositions.jsonl + transcripts/*.json files.
This is what the web dashboard's Activity Log queries directly.

Transcript turns are written immediately as they happen (record_turn),
not buffered until the end - so a crashed call still leaves a partial
transcript behind, and the web dashboard can show an in-progress call's
transcript live.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import db

logger = logging.getLogger("ai-call-log")


class CallLog:
    """One instance per call. Writes transcript turns to SQLite immediately
    as they happen, and the final disposition record when the call ends."""

    def __init__(self, call_id: str, journey: str, patient_id: Optional[str]):
        self.call_id = call_id
        self.journey = journey
        self.patient_id = patient_id
        self.appointment_id: Optional[str] = None
        self.intent: Optional[str] = None
        self.language = "ar-SA"
        self.verification = "PENDING"
        self.outcome: Optional[str] = None
        self.old_date: Optional[str] = None
        self.old_time: Optional[str] = None
        self.new_date: Optional[str] = None
        self.new_time: Optional[str] = None
        self.slot_id: Optional[str] = None
        self.api_actions: list[str] = []
        self.human_transfer = False
        self.transcript_reference = f"TRANS-{call_id}"
        self.current_state: Optional[str] = None

    def record_turn(self, role: str, text: str):
        """Writes a real verbatim turn immediately to SQLite, sourced from
        AgentSession's `user_input_transcribed` (role='user') and
        `conversation_item_added` (role='assistant') events - see agent.py."""
        if not text:
            return
        ts = datetime.now(timezone.utc).astimezone().isoformat()
        db.insert_transcript_turn(self.call_id, role, text, ts)
        self.console_transcript_line(role, text)

    # ---- demo console (kept - useful for live tailing during development) ----
    def console_state(self, state_name: str):
        self.current_state = state_name
        print(f"[CALL] {self.call_id} | state -> {state_name}")

    def console_api_call(self, api_name: str, request: dict, response: dict):
        import json
        self.api_actions.append(api_name)
        print(f"[CALL] {self.call_id} | API {api_name}")
        print(f"    request : {json.dumps(request, default=str, ensure_ascii=False)}")
        print(f"    response: {json.dumps(response, default=str, ensure_ascii=False)}")

    def console_transcript_line(self, speaker: str, text: str):
        print(f"[CALL] {self.call_id} | {speaker}: {text}")

    def console_summary(self):
        print(
            f"[CALL] {self.call_id} | SUMMARY "
            f"patient={self.patient_id} intent={self.intent} state={self.current_state} "
            f"outcome={self.outcome} human_transfer={self.human_transfer} "
            f"api_calls={self.api_actions}"
        )

    # ---- disposition record ----
    def to_disposition(self) -> dict:
        return {
            "call_id": self.call_id,
            "patient_id": self.patient_id,
            "appointment_id": self.appointment_id,
            "journey": "APPOINTMENT_REMINDER" if self.journey == "A" else "FOLLOWUP_DUE",
            "intent": self.intent,
            "language": self.language,
            "verification": self.verification,
            "outcome": self.outcome,
            "old_date": self.old_date,
            "old_time": self.old_time,
            "new_date": self.new_date,
            "new_time": self.new_time,
            "slot_id": self.slot_id,
            "api_actions": self.api_actions,
            "human_transfer": self.human_transfer,
            "transcript_reference": self.transcript_reference,
            "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        }

    def write_disposition(self):
        record = self.to_disposition()
        try:
            db.insert_disposition(record)
            logger.info(f"Disposition written for {self.call_id}: outcome={self.outcome}")
        except Exception as e:
            logger.error(f"Failed to write disposition for {self.call_id}: {e}")
        self.console_summary()
        return record