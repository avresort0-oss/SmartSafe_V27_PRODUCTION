"""
SmartSafe V27 - Response Analyzer
AI-powered response analysis for tracked messages
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from core.tracking.message_tracking_service import get_tracking_service, TrackedMessage
from .ai_service import AIService, get_ai_service

logger = logging.getLogger(__name__)


@dataclass
class ResponseInsight:
    """AI-generated insight for a response"""
    message_id: str
    sentiment: str
    sentiment_score: float
    emotion: Optional[str]
    key_themes: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    is_important: bool = False
    summary: Optional[str] = None
    suggested_response: Optional[str] = None
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BulkResponseReport:
    """Comprehensive report for bulk responses"""
    total_analyzed: int
    sentiment_breakdown: Dict[str, int]
    emotion_breakdown: Dict[str, int]
    theme_frequency: Dict[str, int]
    category_breakdown: Dict[str, int]
    important_messages: List[str]
    overall_summary: str
    key_themes: List[str]
    common_concerns: List[str]
    positive_highlights: List[str]
    recommendations: List[str]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ResponseAnalyzer:
    """AI-powered response analyzer for tracked messages"""

    def __init__(self):
        self.tracking_service = get_tracking_service()
        self.ai_service = get_ai_service()
        
        # Analysis cache
        self._cache: Dict[str, ResponseInsight] = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = 300  # 5 minutes
        
        # Background analysis settings
        self._analysis_queue: List[str] = []
        self._analysis_lock = threading.Lock()
        
        logger.info("ResponseAnalyzer initialized")

    def analyze_response(self, message_id: str, force: bool = False) -> Optional[ResponseInsight]:
        """
        Analyze a single response using AI
        
        Args:
            message_id: The message ID to analyze
            force: Force re-analysis even if cached
            
        Returns:
            ResponseInsight with AI analysis
        """
        # Check cache
        if not force and message_id in self._cache:
            cached = self._cache[message_id]
            age = (datetime.now(timezone.utc) - cached.analyzed_at).total_seconds()
            if age < self._cache_ttl:
                return cached
        
        # Get message from tracking service
        message = self.tracking_service.get_message(message_id)
        
        if not message or not message.response_received:
            logger.warning(f"Message {message_id} not found or has no response")
            return None
        
        try:
            # Use AI to analyze the response
            result = self.ai_service.analyze_message(
                message.response_content or "",
                context=f"Original message: {message.message_content[:200]}"
            )
            
            insight = ResponseInsight(
                message_id=message_id,
                sentiment=result.sentiment,
                sentiment_score=result.sentiment_score,
                emotion=result.emotion,
                key_themes=result.key_themes,
                categories=result.categories,
                is_important=result.is_important,
                summary=result.summary,
                suggested_response=result.suggested_response
            )
            
            # Cache result
            with self._cache_lock:
                self._cache[message_id] = insight
            
            # Update message with AI analysis in database
            self._update_message_ai_analysis(message, insight)
            
            return insight
            
        except Exception as e:
            logger.error(f"Error analyzing response {message_id}: {e}")
            return None

    def analyze_responses_bulk(self, campaign_id: Optional[str] = None, 
                               days: int = 30) -> BulkResponseReport:
        """
        Analyze all responses for a campaign or time period
        
        Args:
            campaign_id: Optional campaign ID to filter
            days: Number of days to look back
            
        Returns:
            Comprehensive BulkResponseReport
        """
        try:
            # Get messages
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                messages = self.tracking_service.get_recent_messages(days)
            
            # Filter to only messages with responses
            responded_messages = [msg for msg in messages if msg.response_received]
            
            if not responded_messages:
                return BulkResponseReport(
                    total_analyzed=0,
                    sentiment_breakdown={},
                    emotion_breakdown={},
                    theme_frequency={},
                    category_breakdown={},
                    important_messages=[],
                    overall_summary="No responses to analyze",
                    key_themes=[],
                    common_concerns=[],
                    positive_highlights=[],
                    recommendations=[]
                )
            
            # Extract response texts
            response_texts = [msg.response_content or "" for msg in responded_messages]
            
            # Use AI for bulk analysis
            if self.ai_service.enabled:
                ai_result = self.ai_service.analyze_responses(response_texts, campaign_id)
            else:
                ai_result = {}
            
            # Build breakdown from cached/individual analysis
            sentiment_breakdown = defaultdict(int)
            emotion_breakdown = defaultdict(int)
            theme_frequency = defaultdict(int)
            category_breakdown = defaultdict(int)
            important_messages = []
            
            # Process each response
            for msg in responded_messages:
                insight = self.analyze_response(msg.message_id)
                
                if insight:
                    sentiment_breakdown[insight.sentiment] += 1
                    
                    if insight.emotion:
                        emotion_breakdown[insight.emotion] += 1
                    
                    for theme in insight.key_themes:
                        theme_frequency[theme] += 1
                    
                    for category in insight.categories:
                        category_breakdown[category] += 1
                    
                    if insight.is_important:
                        important_messages.append(msg.message_id)
            
            # Build report
            report = BulkResponseReport(
                total_analyzed=len(responded_messages),
                sentiment_breakdown=dict(sentiment_breakdown),
                emotion_breakdown=dict(emotion_breakdown),
                theme_frequency=dict(theme_frequency),
                category_breakdown=dict(category_breakdown),
                important_messages=important_messages,
                overall_summary=ai_result.get("overall_summary", "Analysis complete"),
                key_themes=ai_result.get("key_themes", list(theme_frequency.keys())[:5]),
                common_concerns=ai_result.get("common_concerns", []),
                positive_highlights=ai_result.get("positive_points", []),
                recommendations=ai_result.get("suggestions", [])
            )
            
            return report
            
        except Exception as e:
            logger.error(f"Error in bulk analysis: {e}")
            return BulkResponseReport(
                total_analyzed=0,
                sentiment_breakdown={},
                emotion_breakdown={},
                theme_frequency={},
                category_breakdown={},
                important_messages=[],
                overall_summary=f"Error: {str(e)}",
                key_themes=[],
                common_concerns=[],
                positive_highlights=[],
                recommendations=[]
            )

    def get_response_suggestion(self, message_id: str) -> Optional[str]:
        """
        Get AI-suggested response for a message
        
        Args:
            message_id: The message ID to get suggestion for
            
        Returns:
            Suggested response text
        """
        try:
            message = self.tracking_service.get_message(message_id)
            
            if not message or not message.response_received:
                return None
            
            # Get conversation history (last few messages)
            recent_messages = self.tracking_service.get_recent_messages(days=7)
            contact_messages = [m for m in recent_messages 
                              if m.contact_phone == message.contact_phone][:5]
            history = [m.message_content for m in contact_messages]
            
            # Get AI suggestion
            suggestion = self.ai_service.suggest_response(
                message.response_content or "",
                history
            )
            
            return suggestion
            
        except Exception as e:
            logger.error(f"Error getting response suggestion: {e}")
            return None

    def detect_urgent_responses(self, campaign_id: Optional[str] = None) -> List[TrackedMessage]:
        """
        Detect urgent responses that need immediate attention
        
        Args:
            campaign_id: Optional campaign filter
            
        Returns:
            List of urgent messages
        """
        try:
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                messages = self.tracking_service.get_recent_messages(days=7)
            
            urgent_messages = []
            
            for msg in messages:
                if not msg.response_received:
                    continue
                
                # Check if analyzed as important or urgent
                insight = self.analyze_response(msg.message_id)
                
                if insight and insight.is_important:
                    # Check for urgent categories
                    if "urgent" in insight.categories or "complaint" in insight.categories:
                        urgent_messages.append(msg)
                    # Check for negative sentiment with high importance
                    elif insight.sentiment in ["negative", "frustrated"] and insight.confidence > 0.7:
                        urgent_messages.append(msg)
            
            return urgent_messages
            
        except Exception as e:
            logger.error(f"Error detecting urgent responses: {e}")
            return []

    def _update_message_ai_analysis(self, message: TrackedMessage, insight: ResponseInsight):
        """Update message with AI analysis results"""
        try:
            # Store AI analysis results in the event data
            # This could be extended to store in database
            logger.debug(f"Updated message {message.message_id} with AI analysis")
            
        except Exception as e:
            logger.error(f"Error updating message AI analysis: {e}")

    def get_important_responses(self, campaign_id: Optional[str] = None, 
                               days: int = 30) -> List[ResponseInsight]:
        """
        Get all important responses
        
        Args:
            campaign_id: Optional campaign filter
            days: Days to look back
            
        Returns:
            List of important response insights
        """
        try:
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                messages = self.tracking_service.get_recent_messages(days)
            
            important = []
            
            for msg in messages:
                if msg.response_received:
                    insight = self.analyze_response(msg.message_id)
                    if insight and insight.is_important:
                        important.append(insight)
            
            return important
            
        except Exception as e:
            logger.error(f"Error getting important responses: {e}")
            return []

    def get_sentiment_trend(self, campaign_id: Optional[str] = None, 
                          days: int = 30) -> Dict[str, List[float]]:
        """
        Get sentiment trend over time
        
        Args:
            campaign_id: Optional campaign filter
            days: Days to analyze
            
        Returns:
            Dict with daily sentiment scores
        """
        try:
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                messages = self.tracking_service.get_recent_messages(days)
            
            # Group by date
            daily_sentiments: Dict[str, List[float]] = defaultdict(list)
            
            for msg in messages:
                if msg.response_received and msg.response_timestamp:
                    date_key = msg.response_timestamp.strftime("%Y-%m-%d")
                    
                    insight = self.analyze_response(msg.message_id)
                    if insight:
                        daily_sentiments[date_key].append(insight.sentiment_score)
            
            # Calculate average per day
            trend = {}
            for date, scores in daily_sentiments.items():
                if scores:
                    trend[date] = sum(scores) / len(scores)
            
            return dict(sorted(trend.items()))
            
        except Exception as e:
            logger.error(f"Error getting sentiment trend: {e}")
            return {}

    def clear_cache(self):
        """Clear analysis cache"""
        with self._cache_lock:
            self._cache.clear()
        logger.info("ResponseAnalyzer cache cleared")


# Global instance
_response_analyzer: Optional[ResponseAnalyzer] = None
_analyzer_lock = threading.Lock()


def get_response_analyzer() -> ResponseAnalyzer:
    """Get global response analyzer instance"""
    global _response_analyzer
    
    with _analyzer_lock:
        if _response_analyzer is None:
            _response_analyzer = ResponseAnalyzer()
        return _response_analyzer

