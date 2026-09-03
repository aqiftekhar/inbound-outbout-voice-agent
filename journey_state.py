"""
Explicit per-call state machine, implementing spec Sections 8.2 (Journey A)
and 9.2 (Journey B) state tables as real code-level guards - not just LLM
discipline. Function tools in agent.py call into this module to check
whether an action is currently legal, and to record transitions for the
demo console (Section 14) and disposition log (Section 16).

Rationale: per spec Rule 4 ("repeat details and obtain confirmation before
consequential actions") and the BRD-style principle "the LLM is the
reasoning layer, not the system of record" - the LLM decides *when* to call
a tool, but this module decides whether that call is *allowed* right now,
independent of what the LLM believes the conversation state to be. This is
what prevents e.g. a hallucinated/confused LLM from calling commit_cancel
before propose_cancel, or committing a reschedule to a slot that was never
actually offered.
"""

from dataclasses import dataclass, field
from typing import Optional

from call_logger import CallLog


class GuardError(Exception):
    """Raised when a tool is called out of sequence. The message is safe to
    return directly to the LLM as a tool result - it explains what must
    happen first, in plain terms, without exposing internal state names."""


@dataclass
class CallState:
    call_id: str
    journey: str  # "A" or "B"
    patient_id: Optional[str]
    call_log: CallLog

    state: str = "A0_CALL_START"
    language: str = "ar"

    verified: bool = False
    verify_attempts: int = 0
    wrong_person: bool = False

    patient: Optional[dict] = None
    intent_taken: Optional[str] = None

    appointment_id: Optional[str] = None
    appointment_snapshot: Optional[dict] = None  # last fetched appointment details

    followup_status: Optional[dict] = None  # Journey B only

    offered_slots: list = field(default_factory=list)
    selected_slot: Optional[dict] = None
    pending_cancel_reason: Optional[str] = None

    human_transfer: bool = False
    outcome: Optional[str] = None
    call_should_end: bool = False

    def __post_init__(self):
        if self.journey == "B":
            self.state = "B0_CALL_START"

    # ---- transitions ----
    def set_state(self, new_state: str):
        self.state = new_state
        self.call_log.console_state(new_state)

    # ---- guards ----
    def require_verified(self):
        if not self.verified:
            raise GuardError(
                "لم يتم التحقق من هوية المتصل بعد. يجب طلب تاريخ الميلاد أولاً "
                "واستدعاء verify_identity قبل تنفيذ أي إجراء آخر."
            )

    def require_journey(self, expected: str):
        if self.journey != expected:
            raise GuardError(
                f"هذا الإجراء غير متاح في هذه الرحلة (الرحلة الحالية: {self.journey})."
            )

    def require_appointment_loaded(self):
        if not self.appointment_id:
            raise GuardError(
                "لم يتم تحميل تفاصيل الموعد بعد. استدعِ get_appointment_details أولاً."
            )

    def require_followup_loaded(self):
        if not self.followup_status:
            raise GuardError(
                "لم يتم تحميل حالة موعد المتابعة بعد. استدعِ get_followup_status أولاً."
            )

    def require_offered_slot(self, slot_id: str) -> dict:
        match = next((s for s in self.offered_slots if s["slot_id"] == slot_id), None)
        if not match:
            raise GuardError(
                "هذا الموعد لم يُعرض على المتصل في آخر بحث. أعد البحث عن المواعيد المتاحة "
                "قبل اختيار موعد."
            )
        return match

    def require_slot_selected(self):
        if not self.selected_slot:
            raise GuardError(
                "لم يتم اختيار موعد بعد. اعرض المواعيد المتاحة واطلب من المتصل الاختيار أولاً."
            )

    def require_cancel_proposed(self):
        if self.state not in ("A5_CANCEL",):
            raise GuardError(
                "يجب اقتراح الإلغاء أولاً (propose_cancel) وتأكيد الرغبة في الإلغاء "
                "قبل تنفيذه فعليًا."
            )

    # ---- verification bookkeeping ----
    def record_verify_failure(self, max_attempts: int) -> bool:
        """Returns True if attempts are now exhausted (must transfer/end)."""
        self.verify_attempts += 1
        return self.verify_attempts >= max_attempts

    def mark_verified(self):
        self.verified = True
        self.call_log.verification = "PASSED"

    def mark_verify_failed(self):
        self.call_log.verification = "FAILED"

    # ---- decline / revert (Edge case E04: customer changes mind) ----
    def revert_pending_action(self):
        """Clears any not-yet-committed proposal (selected slot, pending
        cancel) and returns to the reminder/due-notice state, WITHOUT
        touching any backend data. Used when the customer changes their
        mind before a commit tool has been called."""
        self.selected_slot = None
        self.pending_cancel_reason = None
        if self.journey == "A":
            self.set_state("A2_REMINDER")
        else:
            self.set_state("B2_DUE_NOTICE")