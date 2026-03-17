"""
SmartSafe V27 - AI Service
Unified AI service for message analysis using OpenAI/Blackbox AI
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


# Default to using OpenAI or compatible API
DEFAULT_API_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-3.5-turbo"

# LiteLLM configuration (if using external LiteLLM proxy)
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "")  # e.g., "http://localhost:4000"
LITELLM_ENABLED = os.getenv("LITELLM_ENABLED", "false").lower() == "true"
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "grok-fast")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")


@dataclass
class AIAnalysisResult:
    """Result of AI analysis"""
    sentiment: str  # positive, negative, neutral, mixed, excited, frustrated, confused
    sentiment_score: float  # -1.0 to 1.0
    emotion: Optional[str] = None  # joy, anger, sadness, fear, surprise, etc.
    confidence: float = 0.0  # 0.0 to 1.0
    summary: Optional[str] = None  # AI-generated summary
    key_themes: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    suggested_response: Optional[str] = None
    is_important: bool = False
    anomaly_score: float = 0.0  # 0.0 to 1.0
    raw_response: Optional[Dict] = None


@dataclass
class AIInsight:
    """AI-generated insight"""
    insight_type: str  # summary, recommendation, prediction, anomaly, trend
    title: str
    description: str
    confidence: float
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AIService:
    """Main AI service for SmartSafe"""

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None, 
                 model: Optional[str] = None):
        # Get API credentials from environment
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("BLACKBOX_API_KEY") or ""
        self.api_url = api_url or os.getenv("AI_API_URL", DEFAULT_API_URL)
        self.model = model or os.getenv("AI_MODEL", DEFAULT_MODEL)
        
        # Fallback to Blackbox AI if no OpenAI key
        if not self.api_key:
            self.api_key = os.getenv("BLACKBOX_API_KEY", "")
        
        # Use Blackbox AI endpoint if available
        self.use_blackbox = os.getenv("USE_BLACKBOX_API", "false").lower() == "true"
        if self.use_blackbox:
            self.api_url = "https://api.blackbox.ai/v1"
            self.model = "blackbox"
        
        # Rate limiting
        self._lock = threading.Lock()
        self._last_request_time = 0
        self.min_request_interval = 1.0  # seconds between requests
        
        # Cache
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = 300  # 5 minutes
        
        # Enable/disable flag
        self.enabled = bool(self.api_key)
        
        if self.enabled:
            logger.info(f"AIService initialized with model: {self.model}")
        else:
            logger.warning("AIService initialized without API key - using fallback mode")

    def analyze_message(self, message: str, context: Optional[str] = None) -> AIAnalysisResult:
        """
        Analyze a single message using AI
        
        Args:
            message: The message text to analyze
            context: Optional context about the conversation
            
        Returns:
            AIAnalysisResult with sentiment, emotions, themes, etc.
        """
        if not self.enabled:
            return self._fallback_analysis(message)
        
        # Check cache
        cache_key = f"analyze_{hash(message)}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        try:
            prompt = self._build_analysis_prompt(message, context)
            response = self._call_ai(prompt)
            result = self._parse_analysis_response(response)
            
            # Cache result
            self._set_cached(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error in AI analysis: {e}")
            return self._fallback_analysis(message)

    def analyze_responses(self, responses: List[str], campaign_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze multiple responses for insights
        
        Args:
            responses: List of response messages
            campaign_id: Optional campaign context
            
        Returns:
            Dict with aggregated insights
        """
        if not self.enabled or not responses:
            return self._fallback_bulk_analysis(responses)
        
        try:
            prompt = self._build_bulk_analysis_prompt(responses, campaign_id)
            response = self._call_ai(prompt)
            result = self._parse_bulk_analysis_response(response)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in bulk AI analysis: {e}")
            return self._fallback_bulk_analysis(responses)

    def generate_insights(self, data: Dict[str, Any], insight_type: str = "general") -> List[AIInsight]:
        """
        Generate AI insights from data
        
        Args:
            data: Data to analyze
            insight_type: Type of insights to generate
            
        Returns:
            List of AIInsight objects
        """
        if not self.enabled:
            return self._generate_fallback_insights(data, insight_type)
        
        try:
            prompt = self._build_insights_prompt(data, insight_type)
            response = self._call_ai(prompt)
            insights = self._parse_insights_response(response)
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating insights: {e}")
            return self._generate_fallback_insights(data, insight_type)

    def predict_performance(self, historical_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict campaign performance based on historical data
        
        Args:
            historical_data: Historical metrics and data
            
        Returns:
            Prediction results
        """
        if not self.enabled:
            return self._fallback_prediction(historical_data)
        
        try:
            prompt = self._build_prediction_prompt(historical_data)
            response = self._call_ai(prompt)
            prediction = self._parse_prediction_response(response)
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error in prediction: {e}")
            return self._fallback_prediction(historical_data)

    def suggest_response(self, customer_message: str, history: Optional[List[str]] = None) -> str:
        """
        Suggest a response to a customer message
        
        Args:
            customer_message: The customer's message
            history: Optional conversation history
            
        Returns:
            Suggested response text
        """
        if not self.enabled:
            return self._fallback_suggestion(customer_message)
        
        try:
            prompt = self._build_response_suggestion_prompt(customer_message, history)
            response = self._call_ai(prompt)
            suggestion = self._parse_suggestion_response(response)
            
            return suggestion
            
        except Exception as e:
            logger.error(f"Error generating suggestion: {e}")
            return self._fallback_suggestion(customer_message)

    def enhance_prompt(self, prompt: str, context: Optional[str] = None) -> str:
        """
        Enhance a prompt by providing additional context, clarification, or rephrasing.
        
        Args:
            prompt: The original prompt to enhance
            context: Optional context about how the prompt will be used
            
        Returns:
            Enhanced prompt with better clarity and context
        """
        if not self.enabled:
            return self._fallback_enhance_prompt(prompt)
        
        try:
            enhancement_prompt = f"""You are a prompt engineering expert. Enhance the following prompt to make it clearer, 
more specific, and more effective for AI processing.

Original Prompt: {prompt}

{f"Context: {context}" if context else ""}

Provide the enhanced prompt that:
1. Is more specific and clear
2. Includes relevant context
3. Has better structure for AI understanding
4. Maintains the original intent

Enhanced Prompt:"""
            
            response = self._call_ai(enhancement_prompt)
            # Extract just the enhanced prompt from the response
            enhanced = response.strip()
            # If the response contains multiple lines, take the first substantial line
            lines = [l.strip() for l in enhanced.split('\n') if l.strip() and not l.startswith('Enhanced')]
            if lines:
                return lines[0]
            return enhanced if enhanced else prompt
            
        except Exception as e:
            logger.error(f"Error enhancing prompt: {e}")
            return self._fallback_enhance_prompt(prompt)

    def _fallback_enhance_prompt(self, prompt: str) -> str:
        """Fallback prompt enhancement using simple heuristics"""
        # Simple enhancement: add clarity and structure
        enhanced = prompt.strip()
        if not enhanced.endswith(('?', '.', '!')):
            enhanced += '.'
        # Capitalize first letter
        enhanced = enhanced[0].upper() + enhanced[1:]
        return enhanced

    def detect_anomalies(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detect anomalies in message data
        
        Args:
            messages: List of message data
            
        Returns:
            List of detected anomalies
        """
        if not self.enabled:
            return self._fallback_anomaly_detection(messages)
        
        try:
            prompt = self._build_anomaly_prompt(messages)
            response = self._call_ai(prompt)
            anomalies = self._parse_anomaly_response(response)
            
            return anomalies
            
        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
            return self._fallback_anomaly_detection(messages)

    def _build_analysis_prompt(self, message: str, context: Optional[str]) -> str:
        """Build prompt for message analysis"""
        return f"""Analyze this WhatsApp message and provide:
1. Sentiment (positive, negative, neutral, mixed, excited, frustrated, confused, interested, uninterested)
2. Emotion (joy, anger, sadness, fear, surprise, interest, boredom)
3. Confidence score (0-1)
4. Key themes/topics (list)
5. Categories (urgent, inquiry, complaint, compliment, question, feedback, other)
6. Is this important? (yes/no)
7. Brief summary (1-2 sentences)

Message: "{message}"
{f"Context: {context}" if context else ""}

Respond in JSON format:
{{
  "sentiment": "...",
  "sentiment_score": -1.0 to 1.0,
  "emotion": "...",
  "confidence": 0.0 to 1.0,
  "key_themes": [...],
  "categories": [...],
  "is_important": true/false,
  "summary": "..."
}}"""

    def _build_bulk_analysis_prompt(self, responses: List[str], campaign_id: Optional[str]) -> str:
        """Build prompt for bulk response analysis"""
        sample_responses = responses[:20] if len(responses) > 20 else responses
        
        return f"""Analyze these {len(responses)} customer responses and provide:
1. Overall sentiment distribution
2. Key themes and topics
3. Common questions or concerns
4. Notable positive/negative points
5. Suggested improvements
6. Top 5 most important responses

Responses:
{chr(10).join([f"- {r[:200]}" for r in sample_responses])}

{"Campaign: " + campaign_id if campaign_id else ""}

Provide comprehensive analysis in JSON:
{{
  "sentiment_distribution": {{"positive": %, "negative": %, "neutral": %}},
  "key_themes": [...],
  "common_concerns": [...],
  "positive_points": [...],
  "suggestions": [...],
  "important_messages": [...],
  "overall_summary": "..."
}}"""

    def _build_insights_prompt(self, data: Dict[str, Any], insight_type: str) -> str:
        """Build prompt for generating insights"""
        return f"""Generate actionable insights from this data:
Type: {insight_type}

Data: {json.dumps(data, indent=2)[:2000]}

Provide insights in JSON:
{{
  "insights": [
    {{
      "type": "summary|recommendation|prediction|anomaly|trend",
      "title": "...",
      "description": "...",
      "confidence": 0.0 to 1.0,
      "data": {{}}
    }}
  ]
}}"""

    def _build_prediction_prompt(self, historical_data: Dict[str, Any]) -> str:
        """Build prompt for performance prediction"""
        return f"""Based on this historical data, predict:
1. Expected response rate
2. Best time to send messages
3. Potential issues to watch
4. Recommendations

Historical Data: {json.dumps(historical_data, indent=2)[:1500]}

Provide prediction in JSON:
{{
  "predicted_response_rate": "%",
  "best_send_time": "...",
  "risk_factors": [...],
  "recommendations": [...],
  "confidence": 0.0 to 1.0
}}"""

    def _build_response_suggestion_prompt(self, customer_message: str, history: Optional[List[str]]) -> str:
        """Build prompt for response suggestion"""
        history_text = ""
        if history:
            history_text = f"\nConversation history:\n{chr(10).join([f'Customer: {h}' for h in history[-3:]])}"
        
        return f"""Suggest a professional WhatsApp response to this customer message:
Customer: "{customer_message}"{history_text}

Provide 1-3 short, professional response options in JSON:
{{
  "suggestions": ["...", "..."],
  "best_option": "..."
}}"""

    def _build_anomaly_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Build prompt for anomaly detection"""
        return f"""Analyze these messages for anomalies:
{json.dumps(messages[:50], indent=2)[:2000]}

Detect:
1. Unusual response patterns
2. Sudden spikes in negative sentiment
3. Unusual timing patterns
4. Potential issues

Provide anomalies in JSON:
{{
  "anomalies": [
    {{
      "type": "pattern|timing|sentiment|volume",
      "description": "...",
      "severity": "low|medium|high",
      "data": {{}}
    }}
  ]
}}"""

    def _call_ai(self, prompt: str) -> str:
        """Make API call to AI service"""
        with self._lock:
            # Rate limiting
            current_time = datetime.now(timezone.utc).timestamp()
            time_since_last = current_time - self._last_request_time
            if time_since_last < self.min_request_interval:
                import time
                time.sleep(self.min_request_interval - time_since_last)
            
            self._last_request_time = datetime.now(timezone.utc).timestamp()
        
        # Check if LiteLLM is enabled
        if LITELLM_ENABLED and LITELLM_PROXY_URL:
            return self._call_litellm(prompt)
        
        if self.use_blackbox:
            return self._call_blackbox(prompt)
        else:
            return self._call_openai(prompt)

    def _call_litellm(self, prompt: str) -> str:
        """Call LiteLLM proxy API"""
        headers = {
            "Authorization": f"Bearer {LITELLM_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Use the configured model from environment
        model = LITELLM_MODEL or "grok-fast"
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a SmartSafe AI assistant analyzing WhatsApp messages."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        try:
            response = requests.post(
                f"{LITELLM_PROXY_URL}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60  # Longer timeout for LiteLLM
            )
            
            if response.status_code != 200:
                error_msg = f"LiteLLM API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                # Fall back to direct Blackbox call
                logger.info("Falling back to direct Blackbox API call")
                return self._call_blackbox(prompt)
            
            result = response.json()
            
            # Handle different response formats
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            elif "choices" in result and len(result["choices"]) == 0:
                raise Exception("LiteLLM returned empty choices")
            else:
                # Try alternative format
                raise Exception(f"Unexpected LiteLLM response format: {result}")
                
        except Exception as e:
            logger.error(f"LiteLLM call failed: {e}")
            # Fall back to direct API call
            return self._call_blackbox(prompt)

    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a SmartSafe AI assistant analyzing WhatsApp messages."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        response = requests.post(
            f"{self.api_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code} - {response.text}")
        
        result = response.json()
        return result["choices"][0]["message"]["content"]

    def _call_blackbox(self, prompt: str) -> str:
        """Call Blackbox AI API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a SmartSafe AI assistant analyzing WhatsApp messages."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        response = requests.post(
            f"{self.api_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Blackbox API error: {response.status_code}")
        
        result = response.json()
        return result["choices"][0]["message"]["content"]

    def _parse_analysis_response(self, response: str) -> AIAnalysisResult:
        """Parse AI analysis response"""
        try:
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                
                return AIAnalysisResult(
                    sentiment=data.get("sentiment", "neutral"),
                    sentiment_score=float(data.get("sentiment_score", 0.0)),
                    emotion=data.get("emotion"),
                    confidence=float(data.get("confidence", 0.5)),
                    summary=data.get("summary"),
                    key_themes=data.get("key_themes", []),
                    categories=data.get("categories", []),
                    is_important=data.get("is_important", False),
                    raw_response=data
                )
        except Exception as e:
            logger.error(f"Error parsing analysis response: {e}")
        
        return self._fallback_analysis("")

    def _parse_bulk_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse bulk analysis response"""
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except Exception as e:
            logger.error(f"Error parsing bulk analysis: {e}")
        
        return {}

    def _parse_insights_response(self, response: str) -> List[AIInsight]:
        """Parse insights response"""
        insights = []
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                
                for item in data.get("insights", []):
                    insights.append(AIInsight(
                        insight_type=item.get("type", "general"),
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        confidence=float(item.get("confidence", 0.5)),
                        data=item.get("data", {})
                    ))
        except Exception as e:
            logger.error(f"Error parsing insights: {e}")
        
        return insights

    def _parse_prediction_response(self, response: str) -> Dict[str, Any]:
        """Parse prediction response"""
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except Exception as e:
            logger.error(f"Error parsing prediction: {e}")
        
        return {}

    def _parse_suggestion_response(self, response: str) -> str:
        """Parse suggestion response"""
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                return data.get("best_option", data.get("suggestions", [""])[0])
        except Exception as e:
            logger.error(f"Error parsing suggestion: {e}")
        
        return ""

    def _parse_anomaly_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse anomaly detection response"""
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                return data.get("anomalies", [])
        except Exception as e:
            logger.error(f"Error parsing anomalies: {e}")
        
        return []

    def _get_cached(self, key: str) -> Optional[AIAnalysisResult]:
        """Get cached result"""
        if key in self._cache:
            result, timestamp = self._cache[key]
            if (datetime.now(timezone.utc).timestamp() - timestamp) < self._cache_ttl:
                return result
        return None

    def _set_cached(self, key: str, result: AIAnalysisResult):
        """Cache result"""
        self._cache[key] = (result, datetime.now(timezone.utc).timestamp())

    # Fallback methods for when AI is not available
    def _fallback_analysis(self, message: str) -> AIAnalysisResult:
        """Fallback analysis using simple heuristics"""
        import re
        
        message_lower = message.lower()
        
        # Simple sentiment detection
        positive_words = ["yes", "thanks", "great", "good", "love", "perfect", "awesome", "interested", "ok", "sure"]
        negative_words = ["no", "not", "bad", "stop", "hate", "angry", "frustrated", "unhappy", "disappointed"]
        
        pos_count = sum(1 for word in positive_words if word in message_lower)
        neg_count = sum(1 for word in negative_words if word in message_lower)
        
        if pos_count > neg_count:
            sentiment = "positive"
            sentiment_score = min(0.5 + (pos_count * 0.1), 1.0)
        elif neg_count > pos_count:
            sentiment = "negative"
            sentiment_score = max(-0.5 - (neg_count * 0.1), -1.0)
        else:
            sentiment = "neutral"
            sentiment_score = 0.0
        
        # Check for questions
        is_question = "?" in message_lower or any(w in message_lower for w in ["what", "how", "when", "where", "why", "can"])
        
        return AIAnalysisResult(
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            emotion="interested" if is_question else None,
            confidence=0.3,
            summary="Fallback analysis - AI not configured",
            is_important=is_question
        )

    def _fallback_bulk_analysis(self, responses: List[str]) -> Dict[str, Any]:
        """Fallback bulk analysis"""
        if not responses:
            return {"summary": "No responses to analyze"}
        
        positive = sum(1 for r in responses if any(w in r.lower() for w in ["yes", "thanks", "great", "good"]))
        negative = sum(1 for r in responses if any(w in r.lower() for w in ["no", "bad", "stop", "hate"]))
        
        total = len(responses)
        
        return {
            "sentiment_distribution": {
                "positive": f"{(positive/total*100):.1f}%",
                "negative": f"{(negative/total*100):.1f}%",
                "neutral": f"{((total-positive-negative)/total*100):.1f}%"
            },
            "key_themes": ["Fallback - configure AI for themes"],
            "overall_summary": f"Analyzed {total} responses. Configure AI API for detailed insights."
        }

    def _generate_fallback_insights(self, data: Dict[str, Any], insight_type: str) -> List[AIInsight]:
        """Generate fallback insights"""
        return [
            AIInsight(
                insight_type="recommendation",
                title="AI Not Configured",
                description="Configure OpenAI or Blackbox API key for AI insights",
                confidence=1.0
            )
        ]

    def _fallback_prediction(self, historical_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback prediction"""
        return {
            "predicted_response_rate": "Unknown - configure AI",
            "best_send_time": "09:00 - 11:00 or 14:00 - 16:00",
            "recommendations": ["Configure AI API for predictions"],
            "confidence": 0.0
        }

    def _fallback_suggestion(self, customer_message: str) -> str:
        """Fallback suggestion"""
        if "?" in customer_message:
            return "Thank you for your message. Let me check and get back to you."
        return "Thank you for reaching out. How can I help you today?"

    def _fallback_anomaly_detection(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fallback anomaly detection"""
        return []

    def clear_cache(self):
        """Clear analysis cache"""
        self._cache.clear()
        logger.info("AI service cache cleared")


# Global instance
_ai_service: Optional[AIService] = None
_service_lock = threading.Lock()


def get_ai_service() -> AIService:
    """Get global AI service instance"""
    global _ai_service
    
    with _service_lock:
        if _ai_service is None:
            _ai_service = AIService()
        return _ai_service

