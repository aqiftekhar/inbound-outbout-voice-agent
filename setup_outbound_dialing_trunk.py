"""
Creates a general-purpose outbound SIP trunk for dialing arbitrary patient
mobile numbers (used by trigger_call.py). This is deliberately separate
from the old Almosafer/ai-AI project's outbound trunk, which was scoped
to a single fixed operator extension for call transfers only.

*** VERIFIED BEHAVIOR (not assumed) ***
An earlier version of this script tried `numbers=[]` assuming empty meant
"unrestricted dialing." That was wrong - LiveKit's create_outbound_trunk
API rejects it outright with "no trunk numbers specified" (confirmed by
actually hitting that error against a live server). At least one number is
required. This now defaults to reusing SIP_TRANSFER_EXTENSION, since the
transfer trunk (transfer_sip_participant) and this dialing trunk
(create_sip_participant) are different LiveKit mechanisms and sharing a
number between them shouldn't cause a conflict - but this hasn't been
verified against a real end-to-end outbound call yet. Set
OUTBOUND_TRUNK_NUMBER in .env explicitly if you have a dedicated extension
for outbound dialing instead.

Run once. Prints the sip_trunk_id to put in your .env's OUTBOUND_TRUNK_ID.
"""

import asyncio
import logging

from livekit import api

from config import Settings

logger = logging.getLogger("setup-outbound-dialing-trunk")


async def main():
    settings = Settings.load()

    if not settings.freepbx_host:
        raise SystemExit("FREEPBX_HOST must be set in .env before creating an outbound trunk.")
    if not settings.outbound_trunk_number:
        raise SystemExit(
            "No number available for this trunk. Set OUTBOUND_TRUNK_NUMBER or "
            "SIP_TRANSFER_EXTENSION in .env - LiveKit requires at least one."
        )

    lkapi = api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        trunk = api.SIPOutboundTrunkInfo(
            name="ai-Medical-Patient-Dialing-Trunk",
            address=f"{settings.freepbx_host}:5060",
            transport=api.SIPTransport.SIP_TRANSPORT_UDP,
            numbers=[settings.outbound_trunk_number],
        )
        resp = await lkapi.sip.create_outbound_trunk(
            api.CreateSIPOutboundTrunkRequest(trunk=trunk)
        )
    except Exception as e:
        logger.error(f"Failed to create outbound trunk: {e}")
        logger.error("If this says a conflicting trunk exists, check list_outbound_trunks.py first.")
        raise
    finally:
        await lkapi.aclose()

    print(f"\nOutbound dialing trunk created.")
    print(f"Add this to your .env:\n\nOUTBOUND_TRUNK_ID={resp.sip_trunk_id}\n")


if __name__ == "__main__":
    asyncio.run(main())