"""
Outbound call trigger simulator.

Both Journey A (appointment reminder) and Journey B (due-for-followup) are
OUTBOUND calls per the spec - the clinic calls the patient, not the other
way around. This is fundamentally different from the earlier Almosafer
project's inbound-only SIP dispatch, so a separate trigger mechanism is
needed: create a room, dial the patient via the outbound SIP trunk, and
dispatch the agent into that room with metadata telling it which patient
and which journey this call is for.

*** SDK VERIFICATION NEEDED ***
This script was written without live access to check the exact field names
of CreateSIPParticipantRequest / CreateAgentDispatchRequest against your
installed livekit-api version. The method names follow the same family as
the SIP trunk/dispatch-rule calls already working elsewhere in this project
(create_sip_inbound_trunk, create_sip_outbound_trunk, transfer_sip_participant),
so the general shape should be right, but before relying on this for a real
demo, run:

    python3 -c "from livekit import api; import inspect; print(inspect.signature(api.CreateSIPParticipantRequest.__init__))"
    python3 -c "from livekit import api; import inspect; print(inspect.signature(api.CreateAgentDispatchRequest.__init__))"

and adjust field names below if they differ.

Usage:
    python3 trigger_call.py --journey A --patient PAT-10021
    python3 trigger_call.py --journey B --patient PAT-10021
"""

import argparse
import asyncio
import json
import logging
import time

from livekit import api

from config import Settings

logger = logging.getLogger("trigger-call")


async def trigger_outbound_call(journey: str, patient_id: str, phone_number: str):
    settings = Settings.load()

    if not settings.outbound_trunk_id:
        raise SystemExit(
            "OUTBOUND_TRUNK_ID is not set in your .env - you need an outbound SIP "
            "trunk configured (see setup_outbound_trunk.py in the sibling project "
            "for the pattern) before you can dial out to a patient's number."
        )

    room_name = f"ai-call-{journey}-{patient_id}-{int(time.time())}"
    call_id = f"CALL-{room_name}"
    metadata = json.dumps({
        "journey": journey,
        "patient_id": patient_id,
        "call_id": call_id,
    })

    lkapi = api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        # 1. Explicitly dispatch the agent into the (not-yet-existing) room,
        #    carrying journey/patient metadata so entrypoint() knows which
        #    call this is - this is the outbound equivalent of the inbound
        #    dispatch rule used in the sibling project's setup_sip.py.
        logger.info(f"Dispatching agent '{settings.agent_name}' to room {room_name}")
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=settings.agent_name,
                room=room_name,
                metadata=metadata,
            )
        )

        # 2. Dial the patient's number into that same room via the outbound
        #    SIP trunk - this is the actual "ringing the patient" step.
        logger.info(f"Dialing {phone_number} via outbound trunk {settings.outbound_trunk_id}")
        await lkapi.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=settings.outbound_trunk_id,
                sip_call_to=phone_number,
                room_name=room_name,
                participant_identity=f"patient-{patient_id}",
                participant_name=patient_id,
            )
        )
        logger.info(f"Outbound call triggered: call_id={call_id} room={room_name}")
        print(f"Triggered. call_id={call_id} room={room_name}")
    finally:
        await lkapi.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journey", choices=["A", "B"], required=True)
    parser.add_argument("--patient", required=True, help="Patient ID, e.g. PAT-10021")
    parser.add_argument(
        "--phone", default=None,
        help="Override phone number to dial (defaults to the patient's record mobile number)",
    )
    args = parser.parse_args()

    if args.phone:
        phone = args.phone
    else:
        import synthetic_data as data
        patient = data.PATIENTS.get(args.patient)
        if not patient:
            raise SystemExit(f"Unknown patient_id: {args.patient}")
        phone = patient["mobile"]

    asyncio.run(trigger_outbound_call(args.journey, args.patient, phone))