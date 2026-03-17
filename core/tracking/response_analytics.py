"""
SmartSafe V27 - Response Analytics Engine
Analyzes response patterns, calculates metrics, and provides insights
"""

from __future__ import annotations

import logging
import statistics
import threading
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from .message_tracking_service import get_tracking_service
from .redis_cache import get_redis_cache

logger = logging.getLogger(__name__)


@dataclass
class ResponseMetrics:
    """Response metrics data structure"""

    total_responses: int
    response_rate: float
    avg_response_time_minutes: float
    response_distribution: Dict[
        str, int
    ]  # positive, negative, neutral, question, opt_out
    sentiment_distribution: Dict[str, int]  # positive, negative, neutral
    peak_response_hours: List[int]
    most_common_responses: List[Tuple[str, int]]
    response_trend: List[Tuple[str, float]]  # date -> response_rate


@dataclass
class CampaignInsights:
    """Campaign performance insights"""

    best_performing_content: Optional[str]
    worst_performing_content: Optional[str]
    optimal_send_time: Optional[str]
    response_quality_score: float
    engagement_level: str  # high, medium, low
    recommendations: List[str]


class ResponseAnalytics:
    """Analytics engine for WhatsApp message responses"""

    def __init__(self):
        self.tracking_service = get_tracking_service()
        self.redis_cache = get_redis_cache()

        # Fallback in-memory cache
        self._cache = {}
        self._cache_timestamp = None
        self._cache_ttl_minutes = 5

        logger.info("ResponseAnalytics initialized")

    def get_response_metrics(
        self, campaign_id: Optional[str] = None, days: int = 30
    ) -> ResponseMetrics:
        """Get comprehensive response metrics"""
        cache_key = f"metrics_{campaign_id}_{days}"

        # Check Redis cache first
        if self.redis_cache:
            cached = self.redis_cache.get(cache_key)
            if cached:
                logger.debug(f"Retrieved metrics from Redis cache: {cache_key}")
                return ResponseMetrics(**cached)

        # Check in-memory cache as fallback
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        try:
            # Get messages from tracking service
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                # Get all messages from last N days
                messages = self._get_recent_messages(days)

            if not messages:
                return ResponseMetrics(
                    total_responses=0,
                    response_rate=0.0,
                    avg_response_time_minutes=0.0,
                    response_distribution={},
                    sentiment_distribution={},
                    peak_response_hours=[],
                    most_common_responses=[],
                    response_trend=[],
                )

            # Calculate metrics
            total_messages = len(messages)
            responded_messages = [msg for msg in messages if msg.response_received]
            total_responses = len(responded_messages)

            # Response rate
            response_rate = (
                (total_responses / total_messages * 100) if total_messages > 0 else 0.0
            )

            # Average response time
            response_times = []
            for msg in responded_messages:
                if msg.response_timestamp and msg.sent_timestamp:
                    time_diff = msg.response_timestamp - msg.sent_timestamp
                    response_times.append(
                        time_diff.total_seconds() / 60
                    )  # Convert to minutes

            avg_response_time = (
                statistics.mean(response_times) if response_times else 0.0
            )

            # Response distribution
            response_distribution = self._calculate_response_distribution(
                responded_messages
            )

            # Sentiment distribution
            sentiment_distribution = self._calculate_sentiment_distribution(
                responded_messages
            )

            # Peak response hours
            peak_response_hours = self._calculate_peak_response_hours(
                responded_messages
            )

            # Most common responses
            most_common_responses = self._get_most_common_responses(responded_messages)

            # Response trend over time
            response_trend = self._calculate_response_trend(messages, days)

            metrics = ResponseMetrics(
                total_responses=total_responses,
                response_rate=response_rate,
                avg_response_time_minutes=avg_response_time,
                response_distribution=response_distribution,
                sentiment_distribution=sentiment_distribution,
                peak_response_hours=peak_response_hours,
                most_common_responses=most_common_responses,
                response_trend=response_trend,
            )

            # Prevent cache leak by limiting size
            if len(self._cache) > 100:
                self._cache.clear()

            # Cache results
            self._cache[cache_key] = metrics
            self._cache_timestamp = datetime.now(timezone.utc)

            # Cache in Redis (TTL 300 seconds = 5 minutes)
            if self.redis_cache:
                self.redis_cache.set(cache_key, metrics.__dict__, ttl=300)

            return metrics

        except Exception as e:
            logger.error(f"Error calculating response metrics: {e}")
            raise

    def get_campaign_insights(self, campaign_id: str) -> CampaignInsights:
        """Get detailed insights for a specific campaign"""
        try:
            messages = self.tracking_service.get_messages_by_campaign(campaign_id)

            if not messages:
                return CampaignInsights(
                    best_performing_content=None,
                    worst_performing_content=None,
                    optimal_send_time=None,
                    response_quality_score=0.0,
                    engagement_level="low",
                    recommendations=["No data available for analysis"],
                )

            # Analyze content performance
            content_performance = self._analyze_content_performance(messages)
            best_content = (
                max(content_performance.items(), key=lambda x: x[1])[0]
                if content_performance
                else None
            )
            worst_content = (
                min(content_performance.items(), key=lambda x: x[1])[0]
                if content_performance
                else None
            )

            # Analyze optimal send time
            optimal_time = self._find_optimal_send_time(messages)

            # Calculate response quality score
            quality_score = self._calculate_response_quality_score(messages)

            # Determine engagement level
            engagement_level = self._determine_engagement_level(messages)

            # Generate recommendations
            recommendations = self._generate_recommendations(messages, campaign_id)

            return CampaignInsights(
                best_performing_content=best_content,
                worst_performing_content=worst_content,
                optimal_send_time=optimal_time,
                response_quality_score=quality_score,
                engagement_level=engagement_level,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Error generating campaign insights: {e}")
            raise

    def get_response_heatmap(
        self, campaign_id: Optional[str] = None, days: int = 7
    ) -> Dict[str, int]:
        """Generate response heatmap by hour and day"""
        try:
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                messages = self._get_recent_messages(days)

            responded_messages = [msg for msg in messages if msg.response_received]

            heatmap = defaultdict(int)

            for msg in responded_messages:
                if msg.response_timestamp:
                    hour = msg.response_timestamp.hour
                    day_name = msg.response_timestamp.strftime("%A")
                    key = f"{day_name}_{hour:02d}:00"
                    heatmap[key] += 1

            return dict(heatmap)

        except Exception as e:
            logger.error(f"Error generating response heatmap: {e}")
            return {}

    def get_response_funnel(self, campaign_id: str) -> Dict[str, int]:
        """Generate response funnel analysis"""
        try:
            messages = self.tracking_service.get_messages_by_campaign(campaign_id)

            if not messages:
                return {}

            funnel = {
                "sent": len(messages),
                "delivered": len(
                    [
                        msg
                        for msg in messages
                        if msg.delivery_status in ["delivered", "read"]
                    ]
                ),
                "read": len([msg for msg in messages if msg.delivery_status == "read"]),
                "responded": len([msg for msg in messages if msg.response_received]),
            }

            # Calculate conversion rates
            funnel["delivery_rate"] = (
                (funnel["delivered"] / funnel["sent"] * 100)
                if funnel["sent"] > 0
                else 0
            )
            funnel["read_rate"] = (
                (funnel["read"] / funnel["delivered"] * 100)
                if funnel["delivered"] > 0
                else 0
            )
            funnel["response_rate"] = (
                (funnel["responded"] / funnel["read"] * 100)
                if funnel["read"] > 0
                else 0
            )

            return funnel

        except Exception as e:
            logger.error(f"Error generating response funnel: {e}")
            return {}

    def get_response_patterns(
        self, campaign_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze response patterns and trends"""
        try:
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                messages = self._get_recent_messages(30)

            responded_messages = [msg for msg in messages if msg.response_received]

            if not responded_messages:
                return {}

            # Response length analysis
            response_lengths = [
                len(msg.response_content or "") for msg in responded_messages
            ]
            avg_response_length = (
                statistics.mean(response_lengths) if response_lengths else 0
            )

            # Response time patterns
            response_times = []
            for msg in responded_messages:
                if msg.response_timestamp and msg.sent_timestamp:
                    time_diff = msg.response_timestamp - msg.sent_timestamp
                    response_times.append(time_diff.total_seconds() / 60)

            # Response time buckets
            time_buckets = {
                "immediate": len([t for t in response_times if t < 5]),
                "quick": len([t for t in response_times if 5 <= t < 30]),
                "normal": len([t for t in response_times if 30 <= t < 120]),
                "slow": len([t for t in response_times if t >= 120]),
            }

            # Word frequency analysis
            all_responses = " ".join(
                [msg.response_content or "" for msg in responded_messages]
            ).lower()
            word_freq = Counter(all_responses.split())
            most_common_words = word_freq.most_common(20)

            return {
                "avg_response_length": avg_response_length,
                "response_time_buckets": time_buckets,
                "most_common_words": most_common_words,
                "total_responses_analyzed": len(responded_messages),
            }

        except Exception as e:
            logger.error(f"Error analyzing response patterns: {e}")
            return {}

    def _get_recent_messages(self, days: int) -> List:
        """Get recent messages for analysis"""
        return self.tracking_service.get_recent_messages(days)

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache is valid"""
        if not self._cache_timestamp:
            return False

        age_minutes = (
            datetime.now(timezone.utc) - self._cache_timestamp
        ).total_seconds() / 60
        return age_minutes < self._cache_ttl_minutes and cache_key in self._cache

    def _calculate_response_distribution(
        self, responded_messages: List
    ) -> Dict[str, int]:
        """Calculate distribution of response types"""
        distribution = defaultdict(int)

        for msg in responded_messages:
            response_type = getattr(msg, "response_type", "unknown")
            distribution[response_type] += 1

        return dict(distribution)

    def _calculate_sentiment_distribution(
        self, responded_messages: List
    ) -> Dict[str, int]:
        """Calculate distribution of sentiment scores"""
        distribution = {"positive": 0, "negative": 0, "neutral": 0}

        for msg in responded_messages:
            sentiment = getattr(msg, "sentiment_score", None)
            if sentiment is None:
                distribution["neutral"] += 1
            elif sentiment > 0.1:
                distribution["positive"] += 1
            elif sentiment < -0.1:
                distribution["negative"] += 1
            else:
                distribution["neutral"] += 1

        return distribution

    def _calculate_peak_response_hours(self, responded_messages: List) -> List[int]:
        """Find peak hours when responses are received"""
        hour_counts = defaultdict(int)

        for msg in responded_messages:
            if msg.response_timestamp:
                hour = msg.response_timestamp.hour
                hour_counts[hour] += 1

        if not hour_counts:
            return []

        # Return top 3 peak hours
        sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
        return [hour for hour, count in sorted_hours[:3]]

    def _get_most_common_responses(
        self, responded_messages: List, limit: int = 10
    ) -> List[Tuple[str, int]]:
        """Get most common response texts"""
        response_counts = Counter()

        for msg in responded_messages:
            content = (msg.response_content or "").strip()
            if content:
                response_counts[content] += 1

        return response_counts.most_common(limit)

    def _calculate_response_trend(
        self, messages: List, days: int
    ) -> List[Tuple[str, float]]:
        """Calculate response rate trend over time"""
        # Group messages by date
        daily_stats = defaultdict(lambda: {"sent": 0, "responded": 0})

        for msg in messages:
            date_str = msg.sent_timestamp.strftime("%Y-%m-%d")
            daily_stats[date_str]["sent"] += 1
            if msg.response_received:
                daily_stats[date_str]["responded"] += 1

        # Calculate daily response rates
        trend = []
        for date_str in sorted(daily_stats.keys()):
            stats = daily_stats[date_str]
            response_rate = (
                (stats["responded"] / stats["sent"] * 100) if stats["sent"] > 0 else 0
            )
            trend.append((date_str, response_rate))

        return trend

    def _analyze_content_performance(self, messages: List) -> Dict[str, float]:
        """Analyze performance of different message contents"""
        content_stats = defaultdict(lambda: {"sent": 0, "responded": 0})

        for msg in messages:
            content = msg.message_content[
                :100
            ]  # Use first 100 chars as content identifier
            content_stats[content]["sent"] += 1
            if msg.response_received:
                content_stats[content]["responded"] += 1

        # Calculate response rates for each content
        content_performance = {}
        for content, stats in content_stats.items():
            response_rate = (
                (stats["responded"] / stats["sent"] * 100) if stats["sent"] > 0 else 0
            )
            content_performance[content] = response_rate

        return content_performance

    def _find_optimal_send_time(self, messages: List) -> Optional[str]:
        """Find optimal time to send messages for better response rates"""
        hour_stats = defaultdict(lambda: {"sent": 0, "responded": 0})

        for msg in messages:
            hour = msg.sent_timestamp.hour
            hour_stats[hour]["sent"] += 1
            if msg.response_received:
                hour_stats[hour]["responded"] += 1

        # Calculate response rates by hour
        hour_rates = {}
        for hour, stats in hour_stats.items():
            response_rate = (
                (stats["responded"] / stats["sent"] * 100) if stats["sent"] > 0 else 0
            )
            hour_rates[hour] = response_rate

        if not hour_rates:
            return None

        # Find hour with highest response rate
        best_hour = max(hour_rates.items(), key=lambda x: x[1])[0]
        return f"{best_hour:02d}:00 - {best_hour + 1:02d}:00"

    def _calculate_response_quality_score(self, messages: List) -> float:
        """Calculate overall response quality score (0-100)"""
        responded_messages = [msg for msg in messages if msg.response_received]

        if not responded_messages:
            return 0.0

        # Factors for quality score
        response_rate = len(responded_messages) / len(messages) * 100

        # Average sentiment (positive responses increase score)
        sentiments = [
            msg.sentiment_score
            for msg in responded_messages
            if msg.sentiment_score is not None
        ]
        avg_sentiment = statistics.mean(sentiments) if sentiments else 0

        # Response speed (faster responses indicate engagement)
        response_times = []
        for msg in responded_messages:
            if msg.response_timestamp and msg.sent_timestamp:
                time_diff = msg.response_timestamp - msg.sent_timestamp
                response_times.append(time_diff.total_seconds() / 60)

        avg_response_time = (
            statistics.mean(response_times) if response_times else 60
        )  # Default 1 hour
        time_score = max(0, 100 - avg_response_time)  # Faster = higher score

        # Combine factors
        quality_score = (
            (response_rate * 0.4)
            + ((avg_sentiment + 1) * 50 * 0.3)
            + (time_score * 0.3)
        )

        return min(max(quality_score, 0), 100)  # Clamp between 0-100

    def _determine_engagement_level(self, messages: List) -> str:
        """Determine engagement level based on metrics"""
        if not messages:
            return "low"

        response_rate = (
            len([msg for msg in messages if msg.response_received])
            / len(messages)
            * 100
        )

        if response_rate >= 50:
            return "high"
        elif response_rate >= 20:
            return "medium"
        else:
            return "low"

    def _generate_recommendations(self, messages: List, campaign_id: str) -> List[str]:
        """Generate actionable recommendations based on analysis"""
        recommendations = []

        if not messages:
            return ["No data available for recommendations"]

        response_rate = (
            len([msg for msg in messages if msg.response_received])
            / len(messages)
            * 100
        )

        # Response rate recommendations
        if response_rate < 10:
            recommendations.append(
                "Consider reviewing message content - very low response rate"
            )
        elif response_rate < 25:
            recommendations.append(
                "Try personalizing messages better to improve response rate"
            )
        elif response_rate > 50:
            recommendations.append(
                "Excellent response rate! Consider scaling this campaign"
            )

        # Timing recommendations
        hour_stats = defaultdict(lambda: {"sent": 0, "responded": 0})
        for msg in messages:
            hour = msg.sent_timestamp.hour
            hour_stats[hour]["sent"] += 1
            if msg.response_received:
                hour_stats[hour]["responded"] += 1

        if hour_stats:
            hour_rates = {
                hour: (stats["responded"] / stats["sent"] * 100)
                if stats["sent"] > 0
                else 0
                for hour, stats in hour_stats.items()
            }

            best_hour = max(hour_rates.items(), key=lambda x: x[1])[0]
            worst_hour = min(hour_rates.items(), key=lambda x: x[1])[0]

            if hour_rates[best_hour] - hour_rates[worst_hour] > 20:
                recommendations.append(
                    f"Consider sending more messages around {best_hour:02d}:00 for better response rates"
                )

        # Content recommendations
        responded_messages = [msg for msg in messages if msg.response_received]
        if responded_messages:
            positive_responses = len(
                [
                    msg
                    for msg in responded_messages
                    if msg.sentiment_score and msg.sentiment_score > 0.1
                ]
            )

            if positive_responses / len(responded_messages) < 0.3:
                recommendations.append(
                    "Many responses seem neutral or negative - consider adjusting message tone"
                )

        return recommendations

    def clear_cache(self):
        """Clear analytics cache"""
        self._cache.clear()
        self._cache_timestamp = None
        if self.redis_cache:
            self.redis_cache.clear_all()
        logger.info("Analytics cache cleared")


# Global instance
_response_analytics: Optional[ResponseAnalytics] = None
_analytics_lock = threading.Lock()


def get_response_analytics() -> ResponseAnalytics:
    """Get global response analytics instance"""
    global _response_analytics

    with _analytics_lock:
        if _response_analytics is None:
            _response_analytics = ResponseAnalytics()
        return _response_analytics
