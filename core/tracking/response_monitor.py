"""
SmartSafe V27 - Response Monitor
Monitors incoming WhatsApp messages and correlates them with sent messages
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from queue import Queue, Empty

from core.api.whatsapp_baileys import BaileysAPI
from .message_tracking_service import get_tracking_service, MessageEvent

logger = logging.getLogger(__name__)


class ResponseMonitor:
    """Monitors incoming WhatsApp messages and correlates with sent messages"""
    
    def __init__(self, api: Optional[BaileysAPI] = None):
        self.api = api or BaileysAPI()
        self.tracking_service = get_tracking_service()
        
        # Response detection patterns
        self.response_patterns = {
            "positive": [
                r"\b(yes|yeah|yep|sure|okay|ok|good|great|excellent|perfect|love|like|agree|accept)\b",
                r"\b(interested|want|need|please|thank|thanks|awesome|amazing)\b",
                r"👍|😊|😄|👌|✅|💯"
            ],
            "negative": [
                r"\b(no|not|don't|won't|can't|sorry|busy|later|never|stop|end)\b",
                r"\b(unsubscribe|remove|delete|block|spam|annoying)\b",
                r"👎|😞|😒|❌|🚫"
            ],
            "question": [
                r"\?",
                r"\b(how|what|when|where|why|which|who|can|could|would|should)\b",
                r"\b(tell me|explain|clarify|details|information)\b"
            ],
            "opt_out": [
                r"\b(stop|end|unsubscribe|remove|delete|block|spam)\b",
                r"\b(don't|do not|never|no more)\s+(contact|message|text|call)\b"
            ]
        }
        
        # Monitoring state
        self._monitoring = False
        self._stop_event = threading.Event()
        self._monitor_thread = None
        self._last_check_time = datetime.now(timezone.utc)
        
        # Response correlation settings
        self.correlation_window_hours = 24  # Look for responses within 24 hours
        self.min_similarity_threshold = 0.3  # Minimum content similarity for correlation
        
        logger.info("ResponseMonitor initialized")
    
    def start_monitoring(self):
        """Start monitoring incoming messages"""
        if self._monitoring:
            logger.warning("Response monitoring already started")
            return
        
        self._monitoring = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        logger.info("Started response monitoring")
    
    def stop_monitoring(self):
        """Stop monitoring incoming messages"""
        if not self._monitoring:
            return
        
        self._monitoring = False
        self._stop_event.set()
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        logger.info("Stopped response monitoring")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while not self._stop_event.is_set():
            try:
                self._check_incoming_messages()
                time.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(10)  # Wait longer on error
    
    def _check_incoming_messages(self):
        """Check for new incoming messages"""
        try:
            # Get recent messages from WhatsApp API
            # This would need to be implemented in the Node.js server
            # For now, we'll simulate with a placeholder
            recent_messages = self._get_recent_incoming_messages()
            
            for message in recent_messages:
                self._process_incoming_message(message)
                
        except Exception as e:
            logger.error(f"Error checking incoming messages: {e}")
    
    def _get_recent_incoming_messages(self) -> List[Dict]:
        """Get recent incoming messages from WhatsApp API"""
        try:
            # Get messages from the last check
            since_timestamp = int(self._last_check_time.timestamp() * 1000)
            response = self.api.get_incoming_messages(since=since_timestamp)
            
            if response.get("ok"):
                messages = response.get("messages", [])
                self._last_check_time = datetime.now(timezone.utc)
                return messages
            else:
                logger.error(f"Failed to get incoming messages: {response.get('error')}")
                return []
                
        except Exception as e:
            logger.error(f"Failed to get incoming messages: {e}")
            return []
    
    def _process_incoming_message(self, message: Dict):
        """Process an incoming message and correlate with sent messages"""
        try:
            sender_phone = message.get("sender", "")
            content = message.get("content", "")
            message_type = message.get("type", "text")
            timestamp = datetime.fromisoformat(message.get("timestamp", datetime.now().isoformat()))
            
            if not sender_phone or not content:
                return
            
            # Find potential original messages to correlate with
            original_message = self._find_original_message(sender_phone, content, timestamp)
            
            if original_message:
                # Analyze response content
                sentiment = self._analyze_sentiment(content)
                response_type = self._categorize_response(content)
                
                # Record the response
                self.tracking_service.record_response(
                    original_message_id=original_message,
                    response_content=content,
                    response_type=message_type,
                    sentiment=sentiment
                )
                
                # Create response event for real-time updates
                event = MessageEvent(
                    message_id=original_message,
                    event_type="response_received",
                    timestamp=timestamp,
                    data={
                        "sender": sender_phone,
                        "content": content,
                        "type": message_type,
                        "sentiment": sentiment,
                        "response_category": response_type
                    }
                )
                
                logger.info(f"Correlated response from {sender_phone} to message {original_message}")
                
            else:
                # Handle unsolicited incoming message
                self._handle_unsolicited_message(message)
                
        except Exception as e:
            logger.error(f"Error processing incoming message: {e}")
    
    def _find_original_message(self, sender_phone: str, content: str, timestamp: datetime) -> Optional[str]:
        """Find the original message that this is a response to"""
        try:
            # Look for recent sent messages to this sender
            cutoff_time = timestamp - timedelta(hours=self.correlation_window_hours)
            
            # This would query the tracking service database
            # For now, return None - needs database query implementation
            recent_messages = self._get_recent_sent_messages(sender_phone, cutoff_time)
            
            if not recent_messages:
                return None
            
            # Find best match based on timing and content similarity
            best_match = None
            best_score = 0
            
            for msg in recent_messages:
                # Calculate time-based score (more recent = higher score)
                time_diff = timestamp - msg["sent_timestamp"]
                time_score = max(0, 1 - (time_diff.total_seconds() / (24 * 3600)))  # Decay over 24 hours
                
                # Calculate content similarity score
                content_score = self._calculate_content_similarity(content, msg["message_content"])
                
                # Combined score
                total_score = (time_score * 0.7) + (content_score * 0.3)
                
                if total_score > best_score and total_score >= self.min_similarity_threshold:
                    best_score = total_score
                    best_match = msg["message_id"]
            
            return best_match
            
        except Exception as e:
            logger.error(f"Error finding original message: {e}")
            return None
    
    def _get_recent_sent_messages(self, phone: str, since: datetime) -> List[Dict]:
        """Get recent sent messages to a specific phone number"""
        try:
            # Query the tracking service database for recent messages to this phone
            from datetime import timedelta
            cutoff = since - timedelta(hours=self.correlation_window_hours)
            
            # Get recent messages from the last 7 days that haven't received a response yet
            recent_msgs = self.tracking_service.get_recent_messages(days=7)
            
            # Filter by phone number and timeframe
            results = []
            for msg in recent_msgs:
                if msg.contact_phone == phone and msg.sent_timestamp >= cutoff:
                    if not msg.response_received:  # Only messages without response
                        results.append({
                            "message_id": msg.message_id,
                            "sent_timestamp": msg.sent_timestamp,
                            "message_content": msg.message_content
                        })
            
            # Sort by timestamp descending (most recent first)
            results.sort(key=lambda x: x["sent_timestamp"], reverse=True)
            
            return results[:10]  # Return up to 10 recent messages
            
        except Exception as e:
            logger.error(f"Failed to get recent sent messages: {e}")
            return []
    
    def _calculate_content_similarity(self, response: str, original: str) -> float:
        """Calculate similarity between response and original message"""
        try:
            # Simple word-based similarity calculation
            response_words = set(re.findall(r'\b\w+\b', response.lower()))
            original_words = set(re.findall(r'\b\w+\b', original.lower()))
            
            if not response_words or not original_words:
                return 0.0
            
            # Calculate Jaccard similarity
            intersection = response_words & original_words
            union = response_words | original_words
            
            similarity = len(intersection) / len(union) if union else 0.0
            
            # Boost similarity for common response patterns
            if any(word in response_words for word in ["ok", "yes", "no", "thanks", "interested"]):
                similarity += 0.2
            
            return min(similarity, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating content similarity: {e}")
            return 0.0
    
    def _analyze_sentiment(self, content: str) -> Optional[float]:
        """Analyze sentiment of response content"""
        try:
            content_lower = content.lower()
            
            # Simple sentiment analysis based on keywords
            positive_score = 0
            negative_score = 0
            
            # Check positive patterns
            for pattern in self.response_patterns["positive"]:
                if re.search(pattern, content_lower):
                    positive_score += 1
            
            # Check negative patterns
            for pattern in self.response_patterns["negative"]:
                if re.search(pattern, content_lower):
                    negative_score += 1
            
            # Check question patterns (neutral)
            for pattern in self.response_patterns["question"]:
                if re.search(pattern, content_lower):
                    return 0.0  # Neutral for questions
            
            # Calculate sentiment score (-1 to 1)
            total_score = positive_score - negative_score
            
            if total_score > 0:
                return min(total_score / len(self.response_patterns["positive"]), 1.0)
            elif total_score < 0:
                return max(total_score / len(self.response_patterns["negative"]), -1.0)
            else:
                return 0.0
                
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return None
    
    def _categorize_response(self, content: str) -> str:
        """Categorize response type"""
        try:
            content_lower = content.lower()
            
            # Check for opt-out first
            for pattern in self.response_patterns["opt_out"]:
                if re.search(pattern, content_lower):
                    return "opt_out"
            
            # Check for question
            for pattern in self.response_patterns["question"]:
                if re.search(pattern, content_lower):
                    return "question"
            
            # Check for positive
            for pattern in self.response_patterns["positive"]:
                if re.search(pattern, content_lower):
                    return "positive"
            
            # Check for negative
            for pattern in self.response_patterns["negative"]:
                if re.search(pattern, content_lower):
                    return "negative"
            
            # Default to neutral
            return "neutral"
            
        except Exception as e:
            logger.error(f"Error categorizing response: {e}")
            return "unknown"
    
    def _handle_unsolicited_message(self, message: Dict):
        """Handle incoming message that doesn't correlate to a sent message"""
        try:
            sender_phone = message.get("sender", "")
            content = message.get("content", "")
            timestamp = message.get("timestamp", datetime.now().isoformat())
            
            # Log unsolicited message for potential follow-up
            logger.info(f"Unsolicited message from {sender_phone}: {content[:50]}...")
            
            # Could trigger auto-reply rules here if configured
            # This would integrate with the AutoReplyTab
            
        except Exception as e:
            logger.error(f"Error handling unsolicited message: {e}")
    
    def get_response_patterns(self) -> Dict[str, List[str]]:
        """Get current response patterns"""
        return self.response_patterns.copy()
    
    def update_response_patterns(self, patterns: Dict[str, List[str]]):
        """Update response patterns for better categorization"""
        try:
            # Validate patterns
            valid_categories = ["positive", "negative", "question", "opt_out"]
            
            for category, pattern_list in patterns.items():
                if category not in valid_categories:
                    raise ValueError(f"Invalid category: {category}")
                
                if not isinstance(pattern_list, list):
                    raise ValueError(f"Pattern list must be a list for category: {category}")
            
            # Update patterns
            self.response_patterns.update(patterns)
            logger.info("Updated response patterns")
            
        except Exception as e:
            logger.error(f"Error updating response patterns: {e}")
            raise
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status"""
        return {
            "monitoring": self._monitoring,
            "last_check_time": self._last_check_time.isoformat(),
            "correlation_window_hours": self.correlation_window_hours,
            "min_similarity_threshold": self.min_similarity_threshold,
            "response_patterns_count": {cat: len(patterns) for cat, patterns in self.response_patterns.items()}
        }
    
    def set_correlation_settings(self, window_hours: Optional[int] = None, 
                                similarity_threshold: Optional[float] = None):
        """Update correlation settings"""
        if window_hours is not None:
            if 1 <= window_hours <= 168:  # 1 hour to 1 week
                self.correlation_window_hours = window_hours
            else:
                raise ValueError("Window hours must be between 1 and 168")
        
        if similarity_threshold is not None:
            if 0.0 <= similarity_threshold <= 1.0:
                self.min_similarity_threshold = similarity_threshold
            else:
                raise ValueError("Similarity threshold must be between 0.0 and 1.0")
        
        logger.info(f"Updated correlation settings: window={self.correlation_window_hours}h, threshold={self.min_similarity_threshold}")


# Global instance
_response_monitor: Optional[ResponseMonitor] = None
_monitor_lock = threading.Lock()


def get_response_monitor() -> ResponseMonitor:
    """Get global response monitor instance"""
    global _response_monitor
    
    with _monitor_lock:
        if _response_monitor is None:
            _response_monitor = ResponseMonitor()
        return _response_monitor
