# ai Medical Center Voice Bot - Implementation

Implements the *ai.ai KSA Voice Bot Demo - Technical Journey Specification v1.0*.

**Read this before treating the build as "done."** Section 4 below lists genuine
gaps and SDK-version uncertainties that need verification before a live demo,
consistent with the spec's own Section 19 ("Notes for Productionization Later").

## 1. File structure

```
ai_medical/
├── agent.py                          Main voice agent: entrypoint, aiMedicalAgent (all function_tools)
├── journey_state.py                  Explicit A0-A10 / B0-B9 state machine + guards (spec 8.2, 9.2)
├── mock_api.py                       The 7 simulated API contracts (spec Section 7), exact field names
├── synthetic_data.py                 Patients/appointments/slots/doctors/clinics (spec Section 6)
├── date_utils.py                     Arabic/English/ISO date parsing for DOB + preferred-date
├── call_logger.py                    Section 16 disposition JSON + real transcript + demo console
├── config.py                         Settings (.env-driven)
├── trigger_call.py                   Outbound call trigger simulator
├── list_outbound_trunks.py           Lists existing outbound SIP trunks (read-only, run before creating one)
├── setup_outbound_dialing_trunk.py   Creates the outbound SIP trunk trigger_call.py needs
├── .env.example
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
└── tests/
    └── test_journeys.py              Logic-layer tests: TC01-TC12 + E04/E06/E07 + guards + date parsing (28 checks, all passing)
```

**Separate, standalone infrastructure (not part of this repo):** a self-hosted
LiveKit server + SIP bridge stack (`livekit-server` + `livekit-sip` + Redis)
is required for this project to connect to at all - `trigger_call.py` and
`agent.py` both depend on `LIVEKIT_URL` pointing at a running instance of
this. If you don't already have one, see the separate `livekit-stack`
delivery (docker-compose + `livekit.yaml` + `sip-config.yaml`) provided
alongside this project.

## 2. Requirements traceability

### Section 13 - Technical Implementation Checklist

| Requirement | Status | Where |
|---|---|---|
| Synthetic patient database | Done | `synthetic_data.py` PATIENTS |
| Synthetic appointment database | Done | `synthetic_data.py` APPOINTMENTS |
| Slot availability API, deterministic | Done | `mock_api.get_available_slots` |
| Patient lookup by mobile number | Done | `mock_api.find_patient(mobile=...)` |
| Lightweight identity verification by DOB | Done | `verify_identity` tool + `date_utils.parse_spoken_date` |
| Intent detection: confirm/reschedule/cancel/booking/human | Done, via tool-calling | LLM selects which `function_tool` to call; each tool *is* the intent |
| Entity extraction for dates/times (AR/EN) | Done (deterministic parsing), LLM computes ISO dates from relative phrases | `date_utils.py` + system prompt gives LLM "today's date" to reason from |
| Appointment retrieval | Done | `get_appointment_details` tool |
| Reschedule write-back | Done | `commit_reschedule` -> `mock_api.reschedule_appointment` |
| Cancellation write-back | Done | `commit_cancel` -> `mock_api.cancel_appointment` |
| New booking write-back | Done | `commit_new_booking` -> `mock_api.create_new_appointment` |
| Outbound call trigger simulator | Done, **field names verified against real SDK** (`CreateSIPParticipantRequest`, `CreateAgentDispatchRequest` both confirmed by introspecting the actual installed `livekit-api` package) | `trigger_call.py` |
| Arabic TTS voice suitable for KSA | Depends on your ElevenLabs voice_id choice | `config.py` - pick a Saudi-accented voice ID |
| Barge-in / interruption handling | Done, **using the current non-deprecated API** (`TurnHandlingOptions.interruption`, verified to construct with zero deprecation warnings against the real SDK) with explicit `min_duration`/`min_words` tuning knobs | `agent.py` AgentSession construction, `INTERRUPTION_MIN_DURATION`/`INTERRUPTION_MIN_WORDS` in `.env` |
| Call transcript logging | **Done, using verified real SDK events** (`user_input_transcribed` for caller speech, `conversation_item_added` for assistant turns) - writes a real per-call JSON transcript, not just placeholder metadata | `call_logger.py` `record_turn()` / `_write_transcript()`, files under `transcripts/` |
| Final disposition/outcome logging | Done | `CallLog.write_disposition()` -> `call_dispositions.jsonl` |
| Demo console/dashboard | Done as **console output**, not a web UI | `call_logger.py` `console_*` methods - see Section 4 |
| 10+ automated test conversations | Done as **logic-layer tests**, not full audio conversations | `tests/test_journeys.py` (28 checks, all passing) - see Section 4 |

### Section 15 - QA Test Pack

| ID | Test | Status |
|---|---|---|
| TC01 | Confirm immediately | Automated - `tests/test_journeys.py` |
| TC02 | Reschedule selected slot | Automated |
| TC03 | Cancel confirmed | Automated |
| TC04 | Reschedule unavailable -> alternatives | Automated |
| TC05 | Identity fail twice -> no exposure | Automated |
| TC06 | Human request -> immediate transfer | Automated (state-level) |
| TC07 | Due booking accepted | Automated |
| TC08 | Due later -> callback recorded | Automated |
| TC09 | Ambiguous time -> confirm pattern | Automated (data-availability check only - the actual dialogue behavior is an LLM/prompt responsibility, see Section 4) |
| TC10 | Barge-in | **Not unit-testable** - requires a real call; covered architecturally, not by this test suite |
| TC11 | API failure -> no false confirm | Automated |
| TC12 | English switch | Automated |

Run: `cd ai_medical && PYTHONPATH=. python3 tests/test_journeys.py`

### Section 12 - Edge Cases

| ID | Case | Status |
|---|---|---|
| E01 | Wrong person | `mark_wrong_person` tool - no detail exposure, ends call |
| E02 | Verification fail | `verify_identity` - retry once, then exhausted -> transfer/end |
| E03 | No slots on preferred date | `get_available_slots` falls back to next available instead of empty |
| E04 | Customer changes mind | `decline_pending_action` reverts state, clears selection, **no API called** |
| E05 | Cancellation uncertainty | Enforced via `propose_cancel` -> `commit_cancel` two-step + system prompt Rule 3 |
| E06 | Already cancelled | `cancel_appointment` returns `ALREADY_CANCELLED`, handled distinctly from a fresh cancel |
| E07 | Concurrent slot taken | `reschedule_appointment`/`create_new_appointment` check `available` at commit time, not just offer time |
| E08 | Human request | `request_human_transfer` - immediate, works from any state |
| E09 | Silence | `silence_watchdog` in `agent.py` - reprompts twice then ends. **Now event-driven** (`user_input_transcribed`), not polling - verified against real SDK |
| E10 | Language switch | `switch_language` tool - **STT stays Arabic-configured, see Section 4 for the real limitation here** |
| E11 | Off-topic medical question | System prompt Rule 8 (no dedicated tool - this is a "don't do X," not an action) |
| E12 | Multiple family members | System prompt Rule 13b - never exposes another patient's data, routes to human/separate call |

### Section 17 - Demo Success Criteria

| Criterion | Status |
|---|---|
| Journey A completes confirm/reschedule/cancel | Done |
| Journey B completes new booking | Done |
| Natural language, not IVR menus | Done - no DTMF anywhere in this bot, pure tool-calling from conversation |
| Arabic-first, English fallback | Arabic-first done; English fallback **best-effort, see Section 4** |
| Confirms consequential actions before writing | Done - every commit_* tool requires a prior select/propose step with explicit confirmation instructed in the system prompt |
| Real-time API lookups/updates with dummy data | Done - `mock_api.py`, with simulated latency and actual state mutation |
| Distinguishes completed vs. failed actions | Done - every commit tool checks `result["status"]` explicitly, never assumes success |
| Transcript + disposition saved every call | Disposition: done. Full verbatim transcript: **partial, see Section 4** |
| Human transfer with context, not repeat-everything | Partial - `request_human_transfer` does a real SIP transfer if configured, but doesn't yet pass a structured context payload to a receiving human agent screen (no such system exists in this demo scope) - see Section 4 |

## 3. Known spec discrepancy (flagged, not silently resolved)

Section 7.6 (`get_followup` API) and the Journey B dialogue script (9.3) both
specify **Dr. Sara Al-Harbi / Dermatology / DOC-101** for patient PAT-10021's
due follow-up. Section 6.5's slot table lists the same slot times under
**Dr. Khalid Al-Qahtani / General Medicine** instead. This implementation
follows the API contract + dialogue script (DOC-101). **Confirm with whoever
wrote the spec** which is actually correct before treating Journey B as final.

## 4. Real limitations - verify before calling this "production grade"

These aren't things I skipped carelessly - they're things I don't have the
ability to verify without either live SDK access or an actual test call, and
I'm not going to claim false confidence on them. Several items previously
listed here have since been **verified and fixed** against the real
installed SDK (see the changelog at the bottom) - what remains below is
genuinely still open.

- **Bilingual STT (E10 / Arabic-English switch)**: `switch_language` flips
  the *conversation's* language (LLM responds in English, TTS should follow
  if you configure `ELEVENLABS_VOICE_ID_EN`), but **Deepgram STT stays
  configured for `language="ar"` for the whole call** - it isn't hot-swapped.
  This means English speech recognition quality after a language switch is
  unverified and likely degraded, exactly the same open question identified
  in the sibling Almosafer project. Test this specifically with a real
  English-speaking call before claiming full bilingual support.

- **Demo console is console output, not a web dashboard.** Section 14 calls
  it a "recommended demo console" - implemented as structured `print()`
  output rather than a separate web UI, since that's a meaningfully larger
  separate deliverable. Straightforward to build as an HTML/React artifact
  tailing `call_dispositions.jsonl` + `transcripts/` if you want it - say
  the word.

- **Human transfer context payload**: `request_human_transfer` performs a
  real SIP transfer (if `FREEPBX_HOST`/`SIP_TRANSFER_EXTENSION` are
  configured) or ends the call in demo mode, and logs `human_transfer=true`
  in the disposition - but there's no receiving system in this demo scope to
  actually *display* a structured case summary to a human agent (no
  CRM/case-management integration exists to hand off to, matching spec
  Section 19's own "integrate actual HIS/EMR/CRM systems" being explicitly
  deferred to later productionization).

- **Outbound SIP trunk `numbers` field semantics, partially learned the
  hard way**: LiveKit's `create_outbound_trunk` API **requires** at least
  one number in `numbers` - confirmed by actually hitting
  `"no trunk numbers specified"` against a live server, not assumed. What's
  still unverified: whether that number is used only as an identifying
  caller-ID/registration value, or whether it also restricts which
  *destination* numbers the trunk can dial. Test an actual end-to-end
  outbound call (`trigger_call.py`) with a real receiving phone before
  trusting this trunk config for anything beyond the specific number tested.

- **End-to-end outbound call has not yet been confirmed working.** Every
  individual piece (trunk creation, agent dispatch, SIP participant
  creation, the full journey state machine, the mock APIs) has been
  verified in isolation, but no one has yet reported a real phone
  successfully ringing, being answered, and completing a full Journey A or
  B conversation through this system end-to-end. That's the actual
  remaining validation step before calling this demo-ready.

## 4a. Verified and fixed since the last version (changelog)

The following were previously flagged here as unverified/uncertain. Since
this project now has live SDK access for verification, they've been
checked directly against the real installed `livekit-agents==1.6.10` /
`livekit-api==1.2.0` and fixed where needed:

- **`trigger_call.py` field names** (`CreateSIPParticipantRequest`,
  `CreateAgentDispatchRequest`) - confirmed correct by introspecting the
  real protobuf/dataclass field names. No changes needed.
- **Silence-reprompt watchdog** - was polling `session.history.items`
  length as an approximation. Replaced with a direct subscription to the
  real `user_input_transcribed` event (confirmed to exist via
  `AgentSession`'s actual emitted event list), which is both more accurate
  and lower-latency than polling.
- **Verbatim transcript logging** - was previously just a placeholder
  string (`transcript_reference = f"TRANS-{call_id}"` with nothing behind
  it). Now genuinely implemented: `user_input_transcribed` (caller speech)
  and `conversation_item_added` (assistant speech) are both subscribed to
  in `agent.py`, feeding `CallLog.record_turn()`, which writes a real JSON
  transcript to `transcripts/{transcript_reference}.json` for every call.
- **`turn_detection`, `min_endpointing_delay`, `max_endpointing_delay`,
  `preemptive_generation` as flat `AgentSession` kwargs** - all four are
  deprecated as of the installed SDK version (confirmed via a live
  `DeprecationWarning`), in favor of a single bundled
  `turn_handling=TurnHandlingOptions(...)` parameter. Migrated `agent.py`
  to the new API - confirmed to construct with **zero** deprecation
  warnings. This also newly exposes explicit interruption sensitivity
  tuning (`interruption.min_duration`, `interruption.min_words`) that
  wasn't available/documented before - now configurable via
  `INTERRUPTION_MIN_DURATION` / `INTERRUPTION_MIN_WORDS` in `.env`.
- **Outbound trunk creation deprecation** - `create_sip_outbound_trunk` /
  `list_sip_outbound_trunk` are deprecated in favor of
  `create_outbound_trunk` / `list_outbound_trunk`. Both scripts updated.
- **Outbound trunk `numbers` requirement** - originally assumed `numbers=[]`
  meant "unrestricted." Confirmed wrong by hitting a live `400
  invalid_argument: no trunk numbers specified` error. Fixed to require a
  real provider-facing DID (`OUTBOUND_TRUNK_NUMBER`), not an internal
  extension.

## 5. Running the demo

### Prerequisite: a running LiveKit server + SIP bridge

Both `agent.py` and `trigger_call.py` need `LIVEKIT_URL` to point at an
actually-running LiveKit deployment with SIP support. If you don't already
have this, stand it up first (separate `livekit-stack` delivery, or your own
LiveKit Cloud project). Then, one-time setup for outbound dialing:

```bash
python3 list_outbound_trunks.py          # check what already exists first
python3 setup_outbound_dialing_trunk.py  # creates one if needed - copy the
                                          # printed sip_trunk_id into
                                          # OUTBOUND_TRUNK_ID in .env
```

### Local (no Docker)

```bash
cd ai_medical
python3 -m venv venv
. venv/bin/activate          # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env          # then fill in real LIVEKIT/DEEPGRAM/GROQ/ELEVENLABS keys
                               # + OUTBOUND_TRUNK_ID from the step above

# Prefetch model assets (Silero VAD) - doesn't need your real keys yet:
python3 -m livekit.agents download-files

# Logic-layer tests (no voice stack/keys needed at all):
PYTHONPATH=. python3 tests/test_journeys.py

# Start the worker (needs real keys in .env from this point on):
python3 agent.py start        # or `dev` for hot-reload during development

# In a separate terminal, trigger an outbound call:
python3 trigger_call.py --journey A --patient PAT-10021
python3 trigger_call.py --journey B --patient PAT-10021
```

After a call ends, check `call_dispositions.jsonl` for the outcome record
and `transcripts/TRANS-CALL-<room>.json` for the real verbatim transcript.

### Docker

All commands below were verified against the pinned `requirements.txt` versions
in a clean venv (`livekit-agents==1.6.10`, `livekit==1.1.14` - matching your
LiveKit deployment's `rtc-version` exactly), and `agent.py`'s boot sequence
was smoke-tested end-to-end (plugin registration, VAD prewarm, worker
registration attempt) before being written into the Dockerfile.

```bash
# From the project root (one level above docker/):
cp .env.example .env           # fill in real keys

cd docker
docker compose build
docker compose up -d
docker compose logs -f agent
```

Trigger an outbound call against the running container:

```bash
docker compose --profile manual run --rm trigger --journey A --patient PAT-10021
docker compose --profile manual run --rm trigger --journey B --patient PAT-10021
```

Disposition records persist across restarts at `docker/data/call_dispositions.jsonl`
on the host (mounted into the container at `/app/data/`).

Stop everything:

```bash
docker compose down
```

### A note on `download-files`

The Dockerfile uses `python -m livekit.agents download-files` rather than
`python agent.py download-files`. I tested both: the latter is flagged
deprecated as of SDK version 1.5.10 by the SDK itself, *and* it fails outright
unless dummy LiveKit/Deepgram/Groq/ElevenLabs env vars are supplied first
(because `agent.py` imports `config.py`, which requires those vars at import
time, even though downloading a VAD model has nothing to do with LiveKit
connectivity). The module-level invocation needs neither - confirmed by
actually running it.