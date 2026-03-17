"""
SmartSafe V27 - Single Engine
For sending individual messages
"""

from typing import Dict
from core.api.whatsapp_baileys import BaileysAPI
from core.config import SETTINGS

class SingleEngine:
    """Single message sending engine"""
    
    def __init__(self, api_host: str = SETTINGS.api_host):
        self.api = BaileysAPI(api_host)
    
    def send_single_message(self, number: str, message: str) -> Dict:
        """
        Send a single message
        
        Args:
            number: Phone number (e.g., "966500000000")
            message: Message text
        
        Returns:
            Result dict with ok status
        """
        return self.api.send_message(number, message)

    def send_message(self, number: str, message: str) -> Dict:
        """
        Backward-compatible alias used by older UI tabs.

        Args:
            number: Phone number (e.g., "966500000000")
            message: Message text

        Returns:
            Result dict with ok status
        """
        return self.send_single_message(number, message)
    
    def check_number(self, number: str) -> Dict:
        """
        Check if number exists on WhatsApp
        
        Args:
            number: Phone number to check
        
        Returns:
            Result dict with exists status
        """
        return self.api.check_profile(number)
    
    def send_with_media(self, number: str, message: str, media_url: str) -> Dict:
        """
        Send message with media attachment
        
        Args:
            number: Phone number
            message: Message text (caption)
            media_url: URL to media file
        
        Returns:
            Result dict
        """
        return self.api.send_message(number, message, media_url=media_url)
