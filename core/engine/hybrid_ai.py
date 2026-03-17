"""
SmartSafe V27 - Hybrid AI Engine
Human-like delay calculation
"""

import random

class HybridAIEngine:
    """AI-powered delay calculator for human-like behavior"""
    
    @staticmethod
    def calculate_human_delay(base_delay: float = 5) -> float:
        """
        Calculate human-like delay with randomness
        
        Args:
            base_delay: Base delay in seconds
        
        Returns:
            Delay with human-like variation
        """
        # Add ±30% variation
        variation = random.uniform(0.7, 1.3)
        delay = base_delay * variation
        
        # 10% chance of longer pause (simulate reading, thinking)
        if random.random() < 0.1:
            delay += random.uniform(5, 15)
        
        return delay
    
    @staticmethod
    def get_typing_delay(message_length: int) -> float:
        """
        Calculate typing time based on message length
        Average: 40 words/min = 3.3 chars/sec
        
        Args:
            message_length: Length of message in characters
        
        Returns:
            Estimated typing time in seconds
        """
        typing_time = message_length / 3.3
        return max(2, min(typing_time, 30))  # Min 2s, max 30s
    
    @staticmethod
    def add_random_pause() -> float:
        """Random pause to simulate human behavior"""
        if random.random() < 0.15:  # 15% chance
            return random.uniform(10, 30)  # 10-30s pause
        return 0
