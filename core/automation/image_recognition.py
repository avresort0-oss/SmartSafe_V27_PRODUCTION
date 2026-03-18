"""
SmartSafe V27 - Image Recognition Service
Provides image analysis for media responses using Google Vision.
"""

import io
import os
from typing import Dict, List, Optional
from google.cloud import vision
import logging

logger = logging.getLogger(__name__)


class ImageRecognitionService:
    """Image recognition service using Google Vision API."""

    def __init__(self, credentials_path: Optional[str] = None):
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        self.client = vision.ImageAnnotatorClient()

    def analyze_image(self, image_data: bytes) -> Dict[str, List[str]]:
        """Analyze image and return labels, text, etc."""
        try:
            image = vision.Image(content=image_data)

            # Label detection
            labels = self.client.label_detection(image=image).label_annotations
            label_descriptions = [label.description for label in labels]

            # Text detection
            texts = self.client.text_detection(image=image).text_annotations
            text_content = [text.description for text in texts] if texts else []

            # Object detection
            objects = self.client.object_localization(
                image=image
            ).localized_object_annotations
            object_names = [obj.name for obj in objects]

            return {
                "labels": label_descriptions,
                "texts": text_content,
                "objects": object_names,
            }
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return {"labels": [], "texts": [], "objects": []}

    def detect_text(self, image_data: bytes) -> str:
        """Extract text from image."""
        try:
            image = vision.Image(content=image_data)
            response = self.client.text_detection(image=image)
            texts = response.text_annotations
            return texts[0].description if texts else ""
        except Exception as e:
            logger.error(f"Text detection failed: {e}")
            return ""


# Global instance
_image_service: Optional[ImageRecognitionService] = None


def get_image_service() -> Optional[ImageRecognitionService]:
    """Get global image recognition service instance."""
    return _image_service


def init_image_service(credentials_path: Optional[str] = None):
    """Initialize global image recognition service."""
    global _image_service
    try:
        _image_service = ImageRecognitionService(credentials_path)
        logger.info("Image recognition service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize image service: {e}")
        _image_service = None
