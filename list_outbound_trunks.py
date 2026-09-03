"""
Lists outbound SIP trunks already configured on your LiveKit server, so you
can check whether one usable for patient dialing already exists before
creating a new one with setup_outbound_dialing_trunk.py.

Read-only - safe to run anytime.
"""

import asyncio

from livekit import api

from config import Settings


async def main():
    settings = Settings.load()
    lkapi = api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        outbound = await lkapi.sip.list_sip_outbound_trunk(api.ListSIPOutboundTrunkRequest())
    finally:
        await lkapi.aclose()

    print("\n--- Outbound Trunks on this LiveKit server ---")
    if not outbound.items:
        print("  (none found - you need to create one, see setup_outbound_dialing_trunk.py)")
    for t in outbound.items:
        print(
            f"  sip_trunk_id={t.sip_trunk_id}\n"
            f"    name={t.name}\n"
            f"    address={t.address}\n"
            f"    numbers={list(t.numbers)}  "
            f"({'unrestricted - can dial any number' if not t.numbers else 'RESTRICTED to these numbers only'})\n"
        )


if __name__ == "__main__":
    asyncio.run(main())