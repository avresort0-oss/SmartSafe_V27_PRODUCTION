"""
SmartSafe V27 - Translation Service
Provides multi-language support with Google Translate.
"""

import os
from typing import Optional
from google.cloud import translate
import logging

logger = logging.getLogger(__name__)


class TranslationService:
    """Translation service using Google Translate."""

    def __init__(self, credentials_path: Optional[str] = None):
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        self.client = translate.Client()

    def translate_text(
        self, text: str, target_language: str, source_language: Optional[str] = None
    ) -> str:
        """Translate text to target language."""
        try:
            result = self.client.translate(
                text, target_language=target_language, source_language=source_language
            )
            return result["translatedText"]
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return text  # Return original text on failure

    def detect_language(self, text: str) -> Optional[str]:
        """Detect the language of the text."""
        try:
            result = self.client.detect_language(text)
            return result["language"]
        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            return None


# Global instance
_translation_service: Optional[TranslationService] = None


def get_translation_service() -> Optional[TranslationService]:
    """Get global translation service instance."""
    return _translation_service


def init_translation_service(credentials_path: Optional[str] = None):
    """Initialize global translation service."""
    global _translation_service
    try:
        _translation_service = TranslationService(credentials_path)
        logger.info("Translation service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize translation service: {e}")
        _translation_service = None
