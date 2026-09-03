"""
Centralized configuration for the ai Medical Center appointment voice bot.
"""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

logger = logging.getLogger("ai-medical-config")


class ConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise ConfigError(f"Missing required environment variable: {name}")
    return val


def _optional(name: str, default: str) -> str:
    return os.getenv(name, default)


def get_demo_today():
    """
    Lightweight standalone accessor for the demo reference date - reads
    DEMO_TODAY directly without requiring the full Settings() (which needs
    LiveKit/Deepgram/Groq/ElevenLabs keys just to construct). mock_api.py
    uses this instead of Settings.load(), so the logic-layer test suite
    (tests/test_journeys.py) can keep running with zero API keys - that's
    the whole point of it being a "logic-layer" suite.
    """
    from datetime import date as _date
    return _date.fromisoformat(os.getenv("DEMO_TODAY", "2026-08-17"))


class Settings:
    def __init__(self):
        # --- LiveKit ---
        self.livekit_url: str = _require("LIVEKIT_URL")
        self.livekit_api_key: str = _require("LIVEKIT_API_KEY")
        self.livekit_api_secret: str = _require("LIVEKIT_API_SECRET")

        # --- STT / LLM / TTS providers (same stack as the earlier project) ---
        self.deepgram_api_key: str = _require("DEEPGRAM_API_KEY")
        self.groq_api_key: str = _require("GROQ_API_KEY")
        self.llm_model: str = _optional("LLM_MODEL", "openai/gpt-oss-120b")
        self.llm_base_url: str = _optional("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        self.stt_model: str = _optional("STT_MODEL", "nova-3")
        self.stt_language: str = _optional("STT_LANGUAGE", "ar")

        self.elevenlabs_api_key: str = _require("ELEVENLABS_API_KEY")
        self.elevenlabs_voice_id: str = _require("ELEVENLABS_VOICE_ID")
        self.tts_model: str = _optional("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")
        # Optional second voice for English fallback - if unset, same voice used
        self.elevenlabs_voice_id_en: str = _optional("ELEVENLABS_VOICE_ID_EN", "")

        # --- Outbound SIP trunk (for the outbound call trigger simulator) ---
        self.freepbx_host: str = _optional("FREEPBX_HOST", "")
        self.sip_transfer_extension: str = _optional("SIP_TRANSFER_EXTENSION", "80")
        self.outbound_trunk_id: str = _optional("OUTBOUND_TRUNK_ID", "")
        # The number/extension this outbound trunk registers/presents as on
        # your FreePBX side. LiveKit's create_outbound_trunk API rejects an
        # empty `numbers` list outright ("no trunk numbers specified") -
        # confirmed by actually hitting that error, not assumed. Defaults to
        # reusing SIP_TRANSFER_EXTENSION if not set separately, since the
        # transfer trunk (transfer_sip_participant) and this dialing trunk
        # (create_sip_participant) are different mechanisms and shouldn't
        # conflict by sharing a number.
        self.outbound_trunk_number: str = _optional("OUTBOUND_TRUNK_NUMBER", self.sip_transfer_extension)

        # --- Agent identity ---
        self.agent_name: str = _optional("AGENT_NAME", "ai-medical")

        # --- Guardrails / limits ---
        self.max_call_duration_seconds: int = int(_optional("MAX_CALL_DURATION_SECONDS", "600"))
        self.dtmf_debounce_seconds: float = float(_optional("DTMF_DEBOUNCE_SECONDS", "0.3"))

        # --- Journey-specific business rules (Section 12 edge cases) ---
        self.max_verify_attempts: int = int(_optional("MAX_VERIFY_ATTEMPTS", "2"))  # E02: "retry once"
        self.silence_reprompt_seconds: float = float(_optional("SILENCE_REPROMPT_SECONDS", "8"))
        self.max_silence_reprompts: int = int(_optional("MAX_SILENCE_REPROMPTS", "2"))  # E09: "reprompt twice"

        # --- VAD tuning (carried over from prior tuning conversation) ---
        self.vad_min_speech_duration: float = float(_optional("VAD_MIN_SPEECH_DURATION", "0.1"))
        self.vad_min_silence_duration: float = float(_optional("VAD_MIN_SILENCE_DURATION", "0.8"))
        self.vad_prefix_padding_duration: float = float(_optional("VAD_PREFIX_PADDING_DURATION", "0.5"))
        self.vad_activation_threshold: float = float(_optional("VAD_ACTIVATION_THRESHOLD", "0.5"))

        # --- Endpointing tuning ---
        self.min_endpointing_delay: float = float(_optional("MIN_ENDPOINTING_DELAY", "0.6"))
        self.max_endpointing_delay: float = float(_optional("MAX_ENDPOINTING_DELAY", "6.0"))

        # --- Interruption/barge-in tuning (TurnHandlingOptions.interruption -
        # verified real fields against the installed SDK, not guessed) ---
        self.interruption_min_duration: float = float(_optional("INTERRUPTION_MIN_DURATION", "0.2"))
        self.interruption_min_words: int = int(_optional("INTERRUPTION_MIN_WORDS", "0"))

        # --- Demo reference date ---
        # This is a deployment/demo parameter, not patient data - it does NOT
        # belong in synthetic_data.py's seed dataset. All seeded appointments/
        # slots are dated around this point specifically so the demo stays
        # reproducible regardless of when you actually run it; using the real
        # wall-clock date would make everything look "in the past" if run
        # much later. mock_api.py reads this via the lightweight
        # get_demo_today() below (not through Settings), agent.py reads it
        # via settings.demo_today here.
        self.demo_today = get_demo_today()

    @property
    def operator_sip_uri(self) -> str:
        return f"sip:{self.sip_transfer_extension}@{self.freepbx_host}" if self.freepbx_host else ""

    @classmethod
    def load(cls) -> "Settings":
        try:
            settings = cls()
        except ConfigError as e:
            logger.error(str(e))
            logger.error("Check your .env file - see .env.example for required variables.")
            sys.exit(1)
        return settings


if __name__ == "__main__":
    s = Settings.load()
    logger.info("Configuration OK.")