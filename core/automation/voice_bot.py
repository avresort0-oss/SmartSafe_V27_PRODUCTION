"""
SmartSafe V27 - Voice Bot Integration
Provides voice message processing with Twilio and Google Speech-to-Text.
"""

import os
import base64
from typing import Optional, Dict, Any
from twilio.twiml.voice_response import VoiceResponse
from google.cloud import speech
import logging

logger = logging.getLogger(__name__)


class VoiceBotService:
    """Voice bot service using Twilio and Google Speech."""

    def __init__(
        self,
        twilio_account_sid: Optional[str] = None,
        twilio_auth_token: Optional[str] = None,
        google_credentials_path: Optional[str] = None,
    ):
        self.twilio_account_sid = twilio_account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_auth_token = twilio_auth_token or os.getenv("TWILIO_AUTH_TOKEN")

        if google_credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = google_credentials_path
        self.speech_client = speech.SpeechClient()

    def speech_to_text(self, audio_data: bytes, language_code: str = "en-US") -> str:
        """Convert speech audio to text using Google Speech-to-Text."""
        try:
            audio = speech.RecognitionAudio(content=audio_data)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language_code,
            )

            response = self.speech_client.recognize(config=config, audio=audio)

            if response.results:
                return response.results[0].alternatives[0].transcript
            return ""
        except Exception as e:
            logger.error(f"Speech-to-text failed: {e}")
            return ""

    def generate_twiml_response(self, message: str) -> str:
        """Generate TwiML for voice response."""
        response = VoiceResponse()
        response.say(message, voice="alice")
        return str(response)

    def process_voice_message(self, audio_url: str, language: str = "en-US") -> str:
        """Process voice message from URL and return transcribed text."""
        # This would download audio from URL and process
        # For now, return placeholder
        logger.info(f"Processing voice message from {audio_url} in {language}")
        return "Voice message transcribed"


# Global instance
_voice_service: Optional[VoiceBotService] = None


def get_voice_service() -> Optional[VoiceBotService]:
    """Get global voice bot service instance."""
    return _voice_service


def init_voice_service(
    twilio_sid: Optional[str] = None,
    twilio_token: Optional[str] = None,
    google_creds: Optional[str] = None,
):
    """Initialize global voice bot service."""
    global _voice_service
    try:
        _voice_service = VoiceBotService(twilio_sid, twilio_token, google_creds)
        logger.info("Voice bot service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize voice service: {e}")
        _voice_service = None
