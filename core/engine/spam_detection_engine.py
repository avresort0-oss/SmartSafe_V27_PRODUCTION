
import re
import logging

logger = logging.getLogger(__name__)

class SpamDetectionEngine(object):
    def __init__(self):
        super().__init__()
        self.name = "spam_detection"
        self.spam_patterns = [
            r'buy now',
            r'click here',
            r'free money',
            r'urgent'
        ]

    def process_message(self, message):
        """Process message for spam detection"""
        content = message.get('content', '').lower()
        spam_score = 0

        for pattern in self.spam_patterns:
            if re.search(pattern, content):
                spam_score += 1

        is_spam = spam_score >= 2

        return {
            'engine': self.name,
            'is_spam': is_spam,
            'spam_score': spam_score,
            'confidence': min(spam_score / len(self.spam_patterns), 1.0),
            'action': 'block' if is_spam else 'proceed'
        }

    def get_default_config(self):
        return {
            'enabled': True,
            'priority': 2,
            'spam_threshold': 2,
            'custom_patterns': []
        }
