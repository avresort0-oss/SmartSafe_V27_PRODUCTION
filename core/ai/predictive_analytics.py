"""
SmartSafe V27 - Predictive Analytics
AI-powered prediction and forecasting for campaign performance
"""

from __future__ import annotations

import logging
import statistics
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.tracking.message_tracking_service import get_tracking_service
from core.tracking.response_analytics import get_response_analytics
from .ai_service import AIService, get_ai_service

logger = logging.getLogger(__name__)


@dataclass
class PerformancePrediction:
    """Campaign performance prediction"""
    predicted_response_rate: float  # percentage
    predicted_delivery_rate: float
    predicted_read_rate: float
    confidence: float  # 0.0 to 1.0
    best_send_time: str  # e.g., "09:00 - 11:00"
    best_send_day: str  # e.g., "Tuesday"
    risk_factors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TimeSlotAnalysis:
    """Analysis of a specific time slot"""
    hour: int
    day_of_week: int  # 0=Monday, 6=Sunday
    messages_sent: int
    responses: int
    response_rate: float
    avg_response_time_minutes: float


@dataclass
class TrendAnalysis:
    """Trend analysis result"""
    trend_type: str  # improving, declining, stable
    change_percentage: float
    data_points: List[Tuple[str, float]]
    prediction: str


class PredictiveAnalytics:
    """AI-powered predictive analytics for campaigns"""

    def __init__(self):
        self.tracking_service = get_tracking_service()
        self.response_analytics = get_response_analytics()
        self.ai_service = get_ai_service()
        
        # Prediction cache
        self._prediction_cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = 600  # 10 minutes
        
        logger.info("PredictiveAnalytics initialized")

    def predict_performance(self, campaign_id: Optional[str] = None) -> PerformancePrediction:
        """
        Predict campaign performance
        
        Args:
            campaign_id: Optional campaign to predict for
            
        Returns:
            PerformancePrediction with forecasts
        """
        # Check cache
        cache_key = f"prediction_{campaign_id or 'all'}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        try:
            # Get historical data
            historical_data = self._get_historical_data(campaign_id)
            
            if self.ai_service.enabled:
                # Use AI for prediction
                ai_result = self.ai_service.predict_performance(historical_data)
                
                prediction = PerformancePrediction(
                    predicted_response_rate=float(ai_result.get("predicted_response_rate", "0").replace("%", "")),
                    predicted_delivery_rate=90.0,  # Default
                    predicted_read_rate=75.0,  # Default
                    confidence=ai_result.get("confidence", 0.5),
                    best_send_time=ai_result.get("best_send_time", "09:00 - 11:00"),
                    best_send_day=ai_result.get("best_send_day", "Tuesday"),
                    risk_factors=ai_result.get("risk_factors", []),
                    recommendations=ai_result.get("recommendations", [])
                )
            else:
                # Use statistical prediction
                prediction = self._statistical_prediction(historical_data)
            
            # Cache result
            self._set_cached(cache_key, prediction)
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error predicting performance: {e}")
            return self._default_prediction()

    def find_optimal_send_time(self, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Find optimal time to send messages
        
        Args:
            campaign_id: Optional campaign filter
            
        Returns:
            Dict with optimal time recommendations
        """
        try:
            # Get time slot analysis
            time_analysis = self._analyze_time_slots(campaign_id)
            
            if not time_analysis:
                return {
                    "best_hour": 10,
                    "best_day": "Tuesday",
                    "best_time_range": "09:00 - 11:00",
                    "expected_response_rate": 0.0,
                    "alternative_times": []
                }
            
            # Find best hour
            best_hour = max(time_analysis, key=lambda x: x.response_rate)
            
            # Find best day
            day_stats = self._analyze_day_performance(time_analysis)
            best_day = max(day_stats.items(), key=lambda x: x[1])[0]
            
            # Get alternatives
            alternatives = sorted(
                time_analysis, 
                key=lambda x: x.response_rate, 
                reverse=True
            )[:3]
            
            return {
                "best_hour": best_hour.hour,
                "best_day": best_day,
                "best_time_range": f"{best_hour.hour:02d}:00 - {best_hour.hour+1:02d}:00",
                "expected_response_rate": best_hour.response_rate,
                "alternative_times": [
                    {
                        "hour": a.hour,
                        "day": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][a.day_of_week],
                        "response_rate": a.response_rate
                    }
                    for a in alternatives if a.hour != best_hour.hour
                ],
                "all_hours": [
                    {
                        "hour": t.hour,
                        "day": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][t.day_of_week],
                        "response_rate": t.response_rate,
                        "messages_sent": t.messages_sent
                    }
                    for t in time_analysis
                ]
            }
            
        except Exception as e:
            logger.error(f"Error finding optimal time: {e}")
            return {
                "best_hour": 10,
                "best_day": "Tuesday",
                "best_time_range": "09:00 - 11:00",
                "expected_response_rate": 0.0,
                "alternative_times": []
            }

    def analyze_trends(self, campaign_id: Optional[str] = None, 
                     days: int = 30) -> Dict[str, TrendAnalysis]:
        """
        Analyze performance trends
        
        Args:
            campaign_id: Optional campaign filter
            days: Number of days to analyze
            
        Returns:
            Dict with trend analyses
        """
        try:
            # Get messages
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                messages = self.tracking_service.get_recent_messages(days)
            
            if not messages:
                return {}
            
            # Calculate daily metrics
            daily_metrics = self._calculate_daily_metrics(messages)
            
            # Analyze each metric
            trends = {}
            
            # Response rate trend
            response_rates = [m["response_rate"] for m in daily_metrics.values()]
            trends["response_rate"] = self._analyze_single_trend(
                response_rates, 
                daily_metrics.keys(),
                "Response Rate"
            )
            
            # Sentiment trend
            sentiments = [m["avg_sentiment"] for m in daily_metrics.values() if m["avg_sentiment"] is not None]
            if sentiments:
                trends["sentiment"] = self._analyze_single_trend(
                    sentiments,
                    daily_metrics.keys(),
                    "Sentiment"
                )
            
            # Volume trend
            volumes = [m["total"] for m in daily_metrics.values()]
            trends["volume"] = self._analyze_single_trend(
                volumes,
                daily_metrics.keys(),
                "Message Volume"
            )
            
            return trends
            
        except Exception as e:
            logger.error(f"Error analyzing trends: {e}")
            return {}

    def detect_anomalies(self, campaign_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Detect anomalies in campaign data
        
        Args:
            campaign_id: Optional campaign filter
            
        Returns:
            List of detected anomalies
        """
        try:
            # Get recent messages
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                messages = self.tracking_service.get_recent_messages(days=30)
            
            if not messages:
                return []
            
            # Convert to format for AI analysis
            message_data = [
                {
                    "timestamp": msg.sent_timestamp.isoformat() if msg.sent_timestamp else None,
                    "status": msg.delivery_status,
                    "response": msg.response_received,
                    "response_time": (
                        (msg.response_timestamp - msg.sent_timestamp).total_seconds() / 60
                        if msg.response_timestamp and msg.sent_timestamp else None
                    )
                }
                for msg in messages
            ]
            
            if self.ai_service.enabled:
                # Use AI for anomaly detection
                anomalies = self.ai_service.detect_anomalies(message_data)
                return anomalies
            else:
                # Use statistical anomaly detection
                return self._statistical_anomaly_detection(message_data)
                
        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
            return []

    def forecast_response_volume(self, campaign_id: Optional[str] = None,
                                days_ahead: int = 7) -> List[Dict[str, Any]]:
        """
        Forecast response volume for upcoming days
        
        Args:
            campaign_id: Optional campaign filter
            days_ahead: Number of days to forecast
            
        Returns:
            List of daily forecasts
        """
        try:
            # Get historical data
            historical = self._get_historical_data(campaign_id)
            
            # Simple moving average forecast
            recent_days = 7
            daily_responses = historical.get("daily_responses", {})
            
            if not daily_responses:
                return [{"date": (datetime.now(timezone.utc) + timedelta(days=i)).strftime("%Y-%m-%d"),
                         "predicted_responses": 0, "confidence": 0.0} for i in range(days_ahead)]
            
            # Get last N days average
            sorted_days = sorted(daily_responses.keys(), reverse=True)[:recent_days]
            recent_values = [daily_responses[d] for d in sorted_days if d in daily_responses]
            
            if not recent_values:
                avg_responses = 0
            else:
                avg_responses = sum(recent_values) / len(recent_values)
            
            # Apply trend adjustment
            trend = self._calculate_trend_factor(recent_values)
            
            # Generate forecasts
            forecasts = []
            for i in range(days_ahead):
                date = (datetime.now(timezone.utc) + timedelta(days=i)).strftime("%Y-%m-%d")
                
                # Apply trend with some randomness
                predicted = avg_responses * (1 + trend * i * 0.1)
                predicted = max(0, predicted)  # Ensure non-negative
                
                # Confidence decreases with time
                confidence = max(0.3, 0.8 - (i * 0.08))
                
                forecasts.append({
                    "date": date,
                    "predicted_responses": int(predicted),
                    "confidence": round(confidence, 2),
                    "day_name": ["Monday", "Tuesday", "Wednesday", "Thursday", 
                                "Friday", "Saturday", "Sunday"][(datetime.now().weekday() + i) % 7]
                })
            
            return forecasts
            
        except Exception as e:
            logger.error(f"Error forecasting volume: {e}")
            return []

    def get_risk_assessment(self, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Assess risk factors for a campaign
        
        Args:
            campaign_id: Optional campaign filter
            
        Returns:
            Risk assessment results
        """
        try:
            # Get campaign analytics
            if campaign_id:
                analytics = self.tracking_service.get_campaign_analytics(campaign_id)
            else:
                analytics = self._get_overall_analytics()
            
            risk_factors = []
            risk_score = 0.0
            
            # Check response rate
            response_rate = analytics.get("response_rate", 0)
            if response_rate < 5:
                risk_factors.append("Very low response rate (<5%)")
                risk_score += 0.4
            elif response_rate < 10:
                risk_factors.append("Low response rate (<10%)")
                risk_score += 0.2
            
            # Check delivery rate
            delivery_rate = analytics.get("delivery_rate", 0)
            if delivery_rate < 70:
                risk_factors.append("Low delivery rate (<70%)")
                risk_score += 0.3
            
            # Check failure rate
            failure_analysis = analytics.get("failure_analysis", {})
            if failure_analysis:
                total_failures = sum(failure_analysis.values())
                if total_failures > 10:
                    risk_factors.append(f"High failure count ({total_failures})")
                    risk_score += 0.2
            
            # Check response time
            avg_response = analytics.get("avg_response_time_minutes", 0)
            if avg_response > 120:  # 2 hours
                risk_factors.append("Slow average response time")
                risk_score += 0.1
            
            return {
                "risk_score": min(risk_score, 1.0),
                "risk_level": "high" if risk_score > 0.6 else "medium" if risk_score > 0.3 else "low",
                "risk_factors": risk_factors,
                "recommendations": self._generate_risk_recommendations(risk_factors)
            }
            
        except Exception as e:
            logger.error(f"Error assessing risk: {e}")
            return {"risk_score": 0.0, "risk_level": "unknown", "risk_factors": [], "recommendations": []}

    def _get_historical_data(self, campaign_id: Optional[str]) -> Dict[str, Any]:
        """Get historical data for analysis"""
        try:
            # Get recent messages
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                messages = self.tracking_service.get_recent_messages(days=30)
            
            if not messages:
                return {}
            
            # Calculate daily stats
            daily_responses = defaultdict(int)
            daily_sent = defaultdict(int)
            
            for msg in messages:
                date_key = msg.sent_timestamp.strftime("%Y-%m-%d")
                daily_sent[date_key] += 1
                
                if msg.response_received:
                    daily_responses[date_key] += 1
            
            # Calculate rates
            total_sent = len(messages)
            total_responded = sum(daily_responses.values())
            
            return {
                "total_sent": total_sent,
                "total_responded": total_responded,
                "overall_response_rate": (total_responded / total_sent * 100) if total_sent > 0 else 0,
                "daily_responses": dict(daily_responses),
                "daily_sent": dict(daily_sent),
                "message_count": len(messages)
            }
            
        except Exception as e:
            logger.error(f"Error getting historical data: {e}")
            return {}

    def _analyze_time_slots(self, campaign_id: Optional[str]) -> List[TimeSlotAnalysis]:
        """Analyze performance by time slots"""
        try:
            if campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                messages = self.tracking_service.get_recent_messages(days=30)
            
            if not messages:
                return []
            
            # Group by hour and day
            slot_data = defaultdict(lambda: {"sent": 0, "responded": 0, "response_times": []})
            
            for msg in messages:
                hour = msg.sent_timestamp.hour
                day = msg.sent_timestamp.weekday()
                key = (hour, day)
                
                slot_data[key]["sent"] += 1
                
                if msg.response_received and msg.response_timestamp:
                    slot_data[key]["responded"] += 1
                    
                    time_diff = msg.response_timestamp - msg.sent_timestamp
                    slot_data[key]["response_times"].append(time_diff.total_seconds() / 60)
            
            # Calculate rates
            analysis = []
            for (hour, day), data in slot_data.items():
                if data["sent"] > 0:
                    response_rate = data["responded"] / data["sent"] * 100
                    avg_time = (
                        sum(data["response_times"]) / len(data["response_times"]) 
                        if data["response_times"] else 0
                    )
                    
                    analysis.append(TimeSlotAnalysis(
                        hour=hour,
                        day_of_week=day,
                        messages_sent=data["sent"],
                        responses=data["responded"],
                        response_rate=response_rate,
                        avg_response_time_minutes=avg_time
                    ))
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing time slots: {e}")
            return []

    def _analyze_day_performance(self, time_analysis: List[TimeSlotAnalysis]) -> Dict[str, float]:
        """Analyze performance by day of week"""
        day_totals = defaultdict(lambda: {"sent": 0, "responded": 0})
        
        for slot in time_analysis:
            day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][slot.day_of_week]
            day_totals[day_name]["sent"] += slot.messages_sent
            day_totals[day_name]["responded"] += slot.responses
        
        return {
            day: (stats["responded"] / stats["sent"] * 100) if stats["sent"] > 0 else 0
            for day, stats in day_totals.items()
        }

    def _calculate_daily_metrics(self, messages: List) -> Dict[str, Dict[str, Any]]:
        """Calculate daily metrics"""
        daily = defaultdict(lambda: {"total": 0, "responded": 0, "sentiments": []})
        
        for msg in messages:
            date_key = msg.sent_timestamp.strftime("%Y-%m-%d")
            daily[date_key]["total"] += 1
            
            if msg.response_received:
                daily[date_key]["responded"] += 1
                if msg.sentiment_score is not None:
                    daily[date_key]["sentiments"].append(msg.sentiment_score)
        
        result = {}
        for date, data in daily.items():
            response_rate = (data["responded"] / data["total"] * 100) if data["total"] > 0 else 0
            avg_sentiment = (
                sum(data["sentiments"]) / len(data["sentiments"]) 
                if data["sentiments"] else None
            )
            
            result[date] = {
                "total": data["total"],
                "responded": data["responded"],
                "response_rate": response_rate,
                "avg_sentiment": avg_sentiment
            }
        
        return result

    def _analyze_single_trend(self, values: List[float], dates: List[str], 
                             metric_name: str) -> TrendAnalysis:
        """Analyze a single metric trend"""
        if len(values) < 2:
            return TrendAnalysis(
                trend_type="stable",
                change_percentage=0.0,
                data_points=list(zip(dates, values)) if dates else [],
                prediction=f"Insufficient data for {metric_name} trend"
            )
        
        # Calculate linear regression
        n = len(values)
        x = list(range(n))
        y = values
        
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator
        
        # Determine trend type
        avg_value = sum(y) / n
        if avg_value == 0:
            trend_type = "stable"
            change_pct = 0
        elif slope > avg_value * 0.05:
            trend_type = "improving"
            change_pct = (slope * n / avg_value) * 100
        elif slope < -avg_value * 0.05:
            trend_type = "declining"
            change_pct = (slope * n / avg_value) * 100
        else:
            trend_type = "stable"
            change_pct = 0
        
        return TrendAnalysis(
            trend_type=trend_type,
            change_percentage=round(change_pct, 2),
            data_points=list(zip(dates, values)),
            prediction=f"{metric_name} is {trend_type}"
        )

    def _statistical_prediction(self, historical_data: Dict) -> PerformancePrediction:
        """Generate statistical prediction"""
        # Simple statistical approach
        response_rate = historical_data.get("overall_response_rate", 10)
        
        # Find best time from historical
        daily_sent = historical_data.get("daily_sent", {})
        
        return PerformancePrediction(
            predicted_response_rate=response_rate,
            predicted_delivery_rate=90.0,
            predicted_read_rate=70.0,
            confidence=0.5,
            best_send_time="09:00 - 11:00",
            best_send_day="Tuesday",
            risk_factors=["Limited historical data"],
            recommendations=["Continue collecting data for better predictions"]
        )

    def _default_prediction(self) -> PerformancePrediction:
        """Return default prediction"""
        return PerformancePrediction(
            predicted_response_rate=10.0,
            predicted_delivery_rate=90.0,
            predicted_read_rate=70.0,
            confidence=0.0,
            best_send_time="09:00 - 11:00",
            best_send_day="Tuesday",
            risk_factors=["No data available"],
            recommendations=["Send messages to generate data"]
        )

    def _calculate_trend_factor(self, values: List[float]) -> float:
        """Calculate trend factor from values"""
        if len(values) < 2:
            return 0.0
        
        # Simple linear trend
        recent = values[:len(values)//2] if len(values) > 2 else values
        older = values[len(values)//2:] if len(values) > 2 else values
        
        if not recent or not older:
            return 0.0
        
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        
        if older_avg == 0:
            return 0.0
        
        return (recent_avg - older_avg) / older_avg

    def _statistical_anomaly_detection(self, messages: List[Dict]) -> List[Dict[str, Any]]:
        """Statistical anomaly detection"""
        anomalies = []
        
        # Check response rates
        responded = [m for m in messages if m.get("response")]
        
        if len(responded) > 10:
            response_times = [m.get("response_time", 0) for m in responded if m.get("response_time")]
            
            if response_times:
                mean_time = statistics.mean(response_times)
                std_time = statistics.stdev(response_times) if len(response_times) > 1 else 0
                
                # Find outliers
                for m in responded:
                    rt = m.get("response_time", 0)
                    if rt > mean_time + 3 * std_time:
                        anomalies.append({
                            "type": "timing",
                            "description": f"Unusually slow response: {rt:.0f} minutes",
                            "severity": "high",
                            "timestamp": m.get("timestamp")
                        })
        
        return anomalies

    def _get_overall_analytics(self) -> Dict[str, Any]:
        """Get overall analytics"""
        messages = self.tracking_service.get_recent_messages(days=30)
        
        if not messages:
            return {}
        
        total = len(messages)
        responded = sum(1 for m in messages if m.response_received)
        
        return {
            "response_rate": (responded / total * 100) if total > 0 else 0,
            "delivery_rate": 90.0,
            "failure_analysis": {}
        }

    def _generate_risk_recommendations(self, risk_factors: List[str]) -> List[str]:
        """Generate recommendations based on risk factors"""
        recommendations = []
        
        for factor in risk_factors:
            if "response rate" in factor.lower():
                recommendations.append("Consider improving message content and targeting")
            if "delivery" in factor.lower():
                recommendations.append("Verify phone numbers and check WhatsApp API status")
            if "failure" in factor.lower():
                recommendations.append("Review error messages and fix underlying issues")
        
        if not recommendations:
            recommendations.append("Continue monitoring campaign performance")
        
        return recommendations

    def _get_cached(self, key: str) -> Optional[PerformancePrediction]:
        """Get cached prediction"""
        with self._cache_lock:
            if key in self._prediction_cache:
                result, timestamp = self._prediction_cache[key]
                age = (datetime.now(timezone.utc).timestamp() - timestamp)
                if age < self._cache_ttl:
                    return result
        return None

    def _set_cached(self, key: str, prediction: PerformancePrediction):
        """Cache prediction"""
        with self._cache_lock:
            self._prediction_cache[key] = (prediction, datetime.now(timezone.utc).timestamp())

    def clear_cache(self):
        """Clear prediction cache"""
        with self._cache_lock:
            self._prediction_cache.clear()
        logger.info("PredictiveAnalytics cache cleared")


# Global instance
_predictive_analytics: Optional[PredictiveAnalytics] = None
_analytics_lock = threading.Lock()


def get_predictive_analytics() -> PredictiveAnalytics:
    """Get global predictive analytics instance"""
    global _predictive_analytics
    
    with _analytics_lock:
        if _predictive_analytics is None:
            _predictive_analytics = PredictiveAnalytics()
        return _predictive_analytics

