"""
SmartSafe V27 - Ultra Smart RiskBrain System
Advanced AI-powered risk management with WhatsApp ban protection
"""

import time
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Tuple, Any, Deque
from collections import defaultdict, deque
from enum import Enum
import random

from core.config import SETTINGS
from core.engine.content_policy import ContentGateDecision, max_similarity_ratio, normalize_for_similarity, token_entropy_bits
from core.engine.recipient_store import RecipientHistoryStore
from core.engine.hybrid_ai import HybridAIEngine
from core.engine.ml_risk_engine import MLRiskEngine

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level classifications"""
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskMode(Enum):
    """Operating mode profiles."""

    TURBO = "TURBO"  # Maximum speed (higher risk)
    FAST = "FAST"  # Fast delivery
    SAFE = "SAFE"  # Balanced (recommended)
    CAREFUL = "CAREFUL"  # Conservative approach
    ULTRA = "ULTRA"  # Maximum safety


@dataclass
class RiskConfig:
    """
    Tunable configuration for `RiskBrain`.

    This structure is intentionally simple so that higher-level settings UIs
    can adjust thresholds and penalties without modifying engine code.
    """

    mode: RiskMode
    # Global caps
    minute_limit: int
    hourly_limit: int
    daily_limit: int
    # Per-recipient caps
    per_recipient_min_interval: int  # seconds between messages to the same recipient
    per_recipient_hourly_limit: int
    per_recipient_daily_limit: int
    # Delay and jitter configuration
    min_delay: float
    max_delay: float
    randomization: float
    cooldown_factor: float

    # Smart Anti-Ban Engine
    anti_ban_min_delay: float = 8.0
    anti_ban_max_delay: float = 22.0
    read_receipt_mode: str = 'auto'  # 'auto', 'off', 'manual'

    # ------------------------------------------------------------------
    # Phase B: Content safety (similarity/entropy gate)
    # ------------------------------------------------------------------
    content_gate_enabled: bool = False
    content_history_window: int = 40
    similarity_threshold: float = 0.92
    similarity_block_threshold: float = 0.97
    min_token_entropy_bits: float = 2.0
    content_risk_high_points: int = 12
    content_risk_critical_points: int = 20
    content_slowdown_multiplier: float = 1.6

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict view (handy for serialization / UI)."""
        return {
            "mode": self.mode.value,
            "minute_limit": self.minute_limit,
            "hourly_limit": self.hourly_limit,
            "daily_limit": self.daily_limit,
            "per_recipient_min_interval": self.per_recipient_min_interval,
            "per_recipient_hourly_limit": self.per_recipient_hourly_limit,
            "per_recipient_daily_limit": self.per_recipient_daily_limit,
            "min_delay": self.min_delay,
            "max_delay": self.max_delay,
            "randomization": self.randomization,
            "cooldown_factor": self.cooldown_factor,
            # Phase B content safety
            "content_gate_enabled": bool(self.content_gate_enabled),
            "content_history_window": int(self.content_history_window),
            "similarity_threshold": float(self.similarity_threshold),
            "similarity_block_threshold": float(self.similarity_block_threshold),
            "min_token_entropy_bits": float(self.min_token_entropy_bits),
            "content_risk_high_points": int(self.content_risk_high_points),
            "content_risk_critical_points": int(self.content_risk_critical_points),
            "content_slowdown_multiplier": float(self.content_slowdown_multiplier),
        }


@dataclass
class RiskSnapshot:
    """
    Immutable snapshot of the current sending state used for risk evaluation.
    """

    hourly_count: int
    daily_count: int
    avg_delay: float
    has_suspicious_pattern: bool
    diversity_score: float
    has_burst: bool
    account_age_days: int
    consecutive_high_risk: int
    time_since_cooldown: float


class RiskEvaluator:
    """
    Pure, stateless risk evaluator.

    Given a `RiskConfig` and a `RiskSnapshot`, it returns a risk score and the
    contributing factor breakdown without mutating any external state.
    """

    @staticmethod
    def evaluate(config: RiskConfig, snapshot: RiskSnapshot) -> Tuple[int, Dict[str, str]]:
        risk = 0
        factors: Dict[str, str] = {}

        # Factor 1: Hourly volume (15 points)
        hourly_ratio = snapshot.hourly_count / max(config.hourly_limit, 1)
        if hourly_ratio > 0.95:
            risk += 15
            factors["hourly_volume"] = "CRITICAL"
        elif hourly_ratio > 0.85:
            risk += 12
            factors["hourly_volume"] = "HIGH"
        elif hourly_ratio > 0.70:
            risk += 8
            factors["hourly_volume"] = "MEDIUM"
        elif hourly_ratio > 0.50:
            risk += 4
            factors["hourly_volume"] = "LOW"
        else:
            factors["hourly_volume"] = "SAFE"

        # Factor 2: Daily volume (15 points)
        daily_ratio = snapshot.daily_count / max(config.daily_limit, 1)
        if daily_ratio > 0.95:
            risk += 15
            factors["daily_volume"] = "CRITICAL"
        elif daily_ratio > 0.85:
            risk += 12
            factors["daily_volume"] = "HIGH"
        elif daily_ratio > 0.70:
            risk += 8
            factors["daily_volume"] = "MEDIUM"
        elif daily_ratio > 0.50:
            risk += 4
            factors["daily_volume"] = "LOW"
        else:
            factors["daily_volume"] = "SAFE"

        # Factor 3: Time of day (10 points)
        hour = datetime.now().hour
        if hour < 5 or hour > 23:  # Very late/early
            risk += 10
            factors["time_of_day"] = "CRITICAL"
        elif hour < 8 or hour > 22:  # Late/early
            risk += 6
            factors["time_of_day"] = "HIGH"
        elif hour < 9 or hour > 21:  # Early/late
            risk += 3
            factors["time_of_day"] = "MEDIUM"
        else:  # Normal hours
            factors["time_of_day"] = "SAFE"

        # Factor 4: Message frequency (10 points)
        min_safe_delay = config.min_delay * 1.5
        if snapshot.avg_delay < config.min_delay:
            risk += 10
            factors["frequency"] = "CRITICAL"
        elif snapshot.avg_delay < min_safe_delay:
            risk += 6
            factors["frequency"] = "HIGH"
        elif snapshot.avg_delay < config.min_delay * 2:
            risk += 3
            factors["frequency"] = "MEDIUM"
        else:
            factors["frequency"] = "SAFE"

        # Factor 5: Pattern detection (10 points)
        if snapshot.has_suspicious_pattern:
            risk += 10
            factors["pattern"] = "SUSPICIOUS"
        else:
            factors["pattern"] = "NORMAL"

        # Factor 6: Recipient diversity (10 points)
        if snapshot.diversity_score < 0.3:  # Low diversity (same numbers)
            risk += 10
            factors["diversity"] = "LOW"
        elif snapshot.diversity_score < 0.5:
            risk += 5
            factors["diversity"] = "MEDIUM"
        else:
            factors["diversity"] = "HIGH"

        # Factor 7: Burst detection (10 points)
        if snapshot.has_burst:
            risk += 10
            factors["burst"] = "DETECTED"
        else:
            factors["burst"] = "NONE"

        # Factor 8: Account age adjustment (10 points)
        if snapshot.account_age_days < 7:
            risk += 10
            factors["account_age"] = "NEW"
        elif snapshot.account_age_days < 30:
            risk += 5
            factors["account_age"] = "YOUNG"
        else:
            factors["account_age"] = "MATURE"

        # Factor 9: Consecutive high risk (5 points)
        if snapshot.consecutive_high_risk > 3:
            risk += 5
            factors["consecutive_risk"] = "HIGH"
        else:
            factors["consecutive_risk"] = "NORMAL"

        # Factor 10: Time since last cooldown (5 points)
        if snapshot.time_since_cooldown > 0:
            if snapshot.time_since_cooldown < 3600:  # Less than 1 hour
                risk += 5
                factors["cooldown_recent"] = "YES"
            else:
                factors["cooldown_recent"] = "NO"

        return min(risk, 100), factors


class RiskBrain:
    """
    Ultra Smart Risk Management System
    
    Features:
    - 15+ risk factor analysis
    - Dynamic delay calculation
    - Pattern detection
    - Time-based optimization
    - Recipient tracking
    - Automatic pause/resume
    """
    
    # Mode configurations (seed values; converted into `RiskConfig`).
    MODE_CONFIGS = {
        RiskMode.TURBO: {
            "minute_limit": 30,
            "hourly_limit": 120,
            "daily_limit": 1200,
            "min_delay": 1.0,
            "max_delay": 5.0,
            "randomization": 0.2,
            "cooldown_factor": 1.0,
            "per_recipient_min_interval": 60,
            "per_recipient_hourly_limit": 20,
            "per_recipient_daily_limit": 80,
        },
        RiskMode.FAST: {
            "minute_limit": 20,
            "hourly_limit": 80,
            "daily_limit": 800,
            "min_delay": 2.0,
            "max_delay": 8.0,
            "randomization": 0.3,
            "cooldown_factor": 1.5,
            "per_recipient_min_interval": 90,
            "per_recipient_hourly_limit": 15,
            "per_recipient_daily_limit": 60,
        },
        RiskMode.SAFE: {
            "minute_limit": 12,
            "hourly_limit": 50,
            "daily_limit": 400,
            "min_delay": 3.0,
            "max_delay": 12.0,
            "randomization": 0.4,
            "cooldown_factor": 2.0,
            "per_recipient_min_interval": 180,
            "per_recipient_hourly_limit": 10,
            "per_recipient_daily_limit": 40,
        },
        RiskMode.CAREFUL: {
            "minute_limit": 6,
            "hourly_limit": 25,
            "daily_limit": 200,
            "min_delay": 5.0,
            "max_delay": 20.0,
            "randomization": 0.5,
            "cooldown_factor": 3.0,
            "per_recipient_min_interval": 300,
            "per_recipient_hourly_limit": 5,
            "per_recipient_daily_limit": 20,
        },
        RiskMode.ULTRA: {
            "minute_limit": 3,
            "hourly_limit": 12,
            "daily_limit": 100,
            "min_delay": 8.0,
            "max_delay": 30.0,
            "randomization": 0.6,
            "cooldown_factor": 5.0,
            "per_recipient_min_interval": 600,
            "per_recipient_hourly_limit": 3,
            "per_recipient_daily_limit": 10,
        },
    }
    
    def __init__(
        self,
        mode: RiskMode = RiskMode.SAFE,
        account_age_days: int = 7,
        enable_ai: bool = True,
        config: Optional[RiskConfig] = None,
        *,
        enable_persistent_recipient_store: Optional[bool] = None,
        recipient_store_path: Optional[str] = None,
    ):
        """
        Initialize RiskBrain.

        Args:
            mode: Operating mode.
            account_age_days: Age of WhatsApp account.
            enable_ai: Enable AI-powered risk analysis and human-like delays.
            config: Optional explicit `RiskConfig`. When provided this takes
                precedence over the built-in mode presets.
        """
        self.mode: RiskMode = mode
        self.account_age_days = account_age_days
        self.enable_ai = enable_ai
        
        # Load configuration (built-in profile transformed into RiskConfig).
        if config is None:
            base_cfg = self.MODE_CONFIGS[mode].copy()
            age_multiplier = min(account_age_days / 30, 1.5)  # Max 1.5x for old accounts
            base_cfg["hourly_limit"] = int(base_cfg["hourly_limit"] * age_multiplier)
            base_cfg["daily_limit"] = int(base_cfg["daily_limit"] * age_multiplier)
            base_cfg["minute_limit"] = max(1, int(base_cfg["minute_limit"] * age_multiplier))

            config = RiskConfig(
                mode=mode,
                minute_limit=base_cfg["minute_limit"],
                hourly_limit=base_cfg["hourly_limit"],
                daily_limit=base_cfg["daily_limit"],
                per_recipient_min_interval=base_cfg["per_recipient_min_interval"],
                per_recipient_hourly_limit=base_cfg["per_recipient_hourly_limit"],
                per_recipient_daily_limit=base_cfg["per_recipient_daily_limit"],
                min_delay=base_cfg["min_delay"],
                max_delay=base_cfg["max_delay"],
                randomization=base_cfg["randomization"],
                cooldown_factor=base_cfg["cooldown_factor"],
            )

        self.config = config

        # Initialize ML Risk Engine
        self.ml_engine = MLRiskEngine()
        
        # Message history tracking
        self.message_history = deque(maxlen=10000)
        self.recipient_history = defaultdict(lambda: deque(maxlen=100))
        self.hourly_counts = deque(maxlen=24)  # Last 24 hours

        # Outgoing content history tracking (per account)
        self._content_history_by_account: Dict[str, Deque[str]] = defaultdict(lambda: deque(maxlen=800))
        self._last_content_decision: Optional[Dict[str, Any]] = None

        # Persistent per-recipient history (cross-campaign)
        enable_store = (
            SETTINGS.enable_recipient_store
            if enable_persistent_recipient_store is None
            else bool(enable_persistent_recipient_store)
        )
        store_path = recipient_store_path or SETTINGS.recipient_store_path
        self._recipient_store: Optional[RecipientHistoryStore] = None
        if enable_store:
            try:
                self._recipient_store = RecipientHistoryStore(store_path)
            except Exception as exc:
                logger.warning("RecipientHistoryStore disabled due to error: %s", exc)
                self._recipient_store = None
        
        # Risk tracking
        self.current_risk_score = 0
        self.risk_factors = {}
        self.consecutive_high_risk = 0
        self.last_cooldown = 0
        self._delay_history = deque(maxlen=200)

        # Statistics
        self.stats = {
            "messages_sent_today": 0,
            "messages_sent_hour": 0,
            "messages_sent_total": 0,
            "total_pauses": 0,
            "total_cooldowns": 0,
            "avg_delay": 0,
            "start_time": datetime.now()
        }

        # Incident tracking for diagnostics
        self._incidents: List[Dict[str, Any]] = []
        
        logger.info(f"RiskBrain initialized: mode={mode.value}, account_age={account_age_days}d")
        logger.info(
            "Limits: %s/min, %s/hour, %s/day",
            self.config.minute_limit,
            self.config.hourly_limit,
            self.config.daily_limit,
        )

    # ------------------------------------------------------------------
    # Public configuration helpers
    # ------------------------------------------------------------------

    def get_config(self) -> RiskConfig:
        """Return the current `RiskConfig` instance."""
        return self.config

    def update_config(self, **overrides: Any) -> None:
        """
        Update the current configuration in-place.

        This is intended for advanced users / settings screens to tweak
        thresholds at runtime without touching code.
        """
        for key, value in overrides.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

    def set_mode(self, mode: RiskMode, config: Optional[RiskConfig] = None) -> None:
        """
        Switch to a different mode, optionally providing an explicit config.

        When `config` is omitted, the built-in preset for the mode is used.
        """
        # Close old persistent resources before re-initializing.
        try:
            self.close()
        except Exception:
            pass
        self.__init__(
            mode=mode,
            account_age_days=self.account_age_days,
            enable_ai=self.enable_ai,
            config=config,
            enable_persistent_recipient_store=(self._recipient_store is not None),
            recipient_store_path=(self._recipient_store.path if self._recipient_store is not None else None),
        )
    
    def calculate_risk(self) -> int:
        """
        Calculate comprehensive risk score (0-100) with ML enhancement
        
        Returns:
            Risk score between 0-100
        """
        snapshot = RiskSnapshot(
            hourly_count=self._count_last_hour(),
            daily_count=self._count_today(),
            avg_delay=self._get_avg_delay(),
            has_suspicious_pattern=self._detect_suspicious_pattern(),
            diversity_score=self._calculate_recipient_diversity(),
            has_burst=self._detect_burst(),
            account_age_days=self.account_age_days,
            consecutive_high_risk=self.consecutive_high_risk,
            time_since_cooldown=(time.time() - self.last_cooldown) if self.last_cooldown > 0 else 0.0,
        )

        # Traditional risk calculation
        risk, factors = RiskEvaluator.evaluate(self.config, snapshot)
        
        # ML-enhanced risk assessment
        try:
            ml_data = {
                "hourly_count": snapshot.hourly_count,
                "daily_count": snapshot.daily_count,
                "avg_delay": snapshot.avg_delay,
                "risk_score": risk,
                "success_rate": self._calculate_success_rate(),
                "pattern_score": 0 if not snapshot.has_suspicious_pattern else 50,
                "diversity_score": snapshot.diversity_score,
                "account_age_days": snapshot.account_age_days,
                "consecutive_failures": self.consecutive_high_risk,
                "recipient_unique_ratio": snapshot.diversity_score,
                "message_length": 0,  # Would need to be tracked
                "media_ratio": 0,  # Would need to be tracked
            }
            
            ml_prediction = self.ml_engine.predict_risk(ml_data)
            
            # Blend traditional and ML scores
            ml_weight = 0.3  # 30% weight to ML, 70% to traditional
            ml_risk_score = self._ml_level_to_score(ml_prediction.risk_level)
            
            blended_risk = int((risk * (1 - ml_weight)) + (ml_risk_score * ml_weight))
            
            # Update factors with ML insights
            factors["ml_prediction"] = ml_prediction.risk_level
            factors["ml_confidence"] = f"{ml_prediction.confidence:.2f}"
            factors["blended_risk"] = str(blended_risk)
            
            risk = blended_risk
            
        except Exception as e:
            logger.debug(f"ML risk assessment failed, using traditional: {e}")

        # Store factors and score
        self.risk_factors = factors
        self.current_risk_score = risk
        
        # Track consecutive high risk
        if self.current_risk_score >= 70:
            self.consecutive_high_risk += 1
        else:
            self.consecutive_high_risk = 0
        
        logger.debug(f"Risk calculated: {self.current_risk_score}/100, factors={factors}")
        
        return self.current_risk_score
    
    def _ml_level_to_score(self, ml_level: str) -> int:
        """Convert ML risk level to numeric score"""
        level_scores = {
            "LOW": 20,
            "MEDIUM": 45,
            "HIGH": 70,
            "CRITICAL": 90
        }
        return level_scores.get(ml_level, 50)
    
    def _calculate_success_rate(self) -> float:
        """Calculate recent success rate"""
        # This would need to be implemented based on actual message outcomes
        # For now, return a reasonable default
        return 0.85

    # ------------------------------------------------------------------
    # Phase B: Content similarity / entropy gate
    # ------------------------------------------------------------------

    def evaluate_outgoing_content(
        self,
        text: str,
        *,
        account: Optional[str] = None,
        variants_count: int = 1,
    ) -> ContentGateDecision:
        """
        Evaluate outgoing message content against recent history for the account.

        This is intentionally heuristic and conservative; it should *encourage*
        variation and pacing rather than hard-block normal campaigns.

        Returns a `ContentGateDecision` describing the recommended action.
        """
        if not bool(getattr(self.config, "content_gate_enabled", False)):
            return ContentGateDecision(
                gate="PASS",
                similarity=0.0,
                entropy_bits=0.0,
                risk_points=0,
                delay_multiplier=1.0,
                reason="content gate disabled",
            )

        acc_key = str(account).strip() if account else "default"
        window = max(1, int(getattr(self.config, "content_history_window", 40) or 40))
        history = list(self._content_history_by_account.get(acc_key, deque()))[-window:]

        similarity = max_similarity_ratio(text, history)
        entropy = token_entropy_bits(text)

        sim_thr = float(getattr(self.config, "similarity_threshold", 0.92) or 0.92)
        sim_block = float(getattr(self.config, "similarity_block_threshold", 0.97) or 0.97)
        min_entropy = float(getattr(self.config, "min_token_entropy_bits", 2.0) or 2.0)

        risk_points = 0
        delay_mult = 1.0
        gate = "PASS"
        reason = "ok"

        # Similarity-driven actions (strongest signal)
        if similarity >= sim_block and history:
            gate = "BLOCK"
            risk_points = int(getattr(self.config, "content_risk_critical_points", 20) or 20)
            delay_mult = max(2.0, float(getattr(self.config, "content_slowdown_multiplier", 1.6) or 1.6) * 2.0)
            reason = f"very high similarity to recent messages ({similarity:.3f})"
        elif similarity >= sim_thr and history:
            # Prefer rotating templates when available; otherwise try jitter.
            gate = "ROTATE" if int(variants_count or 1) > 1 else "JITTER"
            risk_points = int(getattr(self.config, "content_risk_high_points", 12) or 12)
            delay_mult = float(getattr(self.config, "content_slowdown_multiplier", 1.6) or 1.6)
            reason = f"high similarity to recent messages ({similarity:.3f})"
        else:
            # Entropy heuristic: if extremely repetitive wording and non-trivial length, suggest jitter.
            normalized = normalize_for_similarity(text)
            if len(normalized) >= 40 and entropy > 0 and entropy < min_entropy:
                gate = "JITTER"
                risk_points = max(6, int(getattr(self.config, "content_risk_high_points", 12) or 12) // 2)
                delay_mult = float(getattr(self.config, "content_slowdown_multiplier", 1.6) or 1.6)
                reason = f"low entropy wording ({entropy:.2f} bits)"

        # Apply a small, local risk bump so pacing reacts immediately.
        if risk_points > 0:
            self.current_risk_score = min(100, int(self.current_risk_score) + int(risk_points))
            self.risk_factors["content_similarity"] = (
                "CRITICAL" if similarity >= sim_block else ("HIGH" if similarity >= sim_thr else "LOW")
            )
            self.risk_factors["content_entropy"] = "LOW" if (entropy > 0 and entropy < min_entropy) else "OK"
            self._record_incident("content_gate", reason, recipient=None)

        self._last_content_decision = {
            "account": acc_key,
            "gate": gate,
            "similarity": float(round(similarity, 4)),
            "entropy_bits": float(round(entropy, 3)),
            "risk_points": int(risk_points),
            "delay_multiplier": float(round(delay_mult, 3)),
            "reason": reason,
        }

        # If we can't rotate/jitter effectively, downgrade to slowdown (never infinite-loop on gate).
        if gate in {"ROTATE", "JITTER"} and (not history):
            gate = "PASS"
            risk_points = 0
            delay_mult = 1.0
            reason = "no history yet"

        return ContentGateDecision(
            gate=gate,
            similarity=float(similarity),
            entropy_bits=float(entropy),
            risk_points=int(risk_points),
            delay_multiplier=float(delay_mult),
            reason=reason,
        )

    def record_outgoing_content(self, text: str, *, account: Optional[str] = None) -> None:
        """
        Record a successfully-sent outgoing message for similarity/entropy gating.
        """
        if not bool(getattr(self.config, "content_gate_enabled", False)):
            return
        acc_key = str(account).strip() if account else "default"
        if not (text or "").strip():
            return
        self._content_history_by_account[acc_key].append(text.strip())
    
    def get_safe_delay(self, message_length: int = 0, randomize: bool = True) -> float:
        """
        Smart Anti-Ban: 8-22s random delay + typing simulation.
        
        Args:
            message_length: Message length for typing simulation
            randomize: Add human-like variation
            
        Returns:
            Total delay (base + typing + jitter)
        """
        # Anti-Ban base: 8-22s random range (task requirement)
        base_delay = random.uniform(self.config.anti_ban_min_delay, self.config.anti_ban_max_delay)
        
        # Typing simulation (3.3 chars/sec average)
        typing_delay = HybridAIEngine.get_typing_delay(message_length)
        
        # Risk multiplier
        if self.current_risk_score < 30:
            risk_mult = 1.0
        elif self.current_risk_score < 50:
            risk_mult = 1.3  
        elif self.current_risk_score < 70:
            risk_mult = 1.6
        else:
            risk_mult = 2.0 * self.config.cooldown_factor

        delay = (base_delay + typing_delay) * risk_mult

        # Human-like randomization
        if randomize and self.enable_ai:
            delay = HybridAIEngine.calculate_human_delay(delay)
        elif randomize:
            # ±20% jitter within anti-ban bounds
            jitter = delay * 0.2
            delay += random.uniform(-jitter, jitter)
            # Clamp to 8-22s core range
            delay = max(8.0, min(22.0, delay))

        # Track for ML features
        self._delay_history.append(delay)
        if self._delay_history:
            self.stats["avg_delay"] = sum(self._delay_history) / len(self._delay_history)

        logger.debug(f"Anti-ban delay: {delay:.1f}s (base:{base_delay:.1f}, typing:{typing_delay:.1f}, risk:{risk_mult:.1f})")
        return round(delay, 2)
    
    def should_pause(self) -> Tuple[bool, str]:
        """
        Check if should pause operations
        
        Returns:
            Tuple of (should_pause, reason)
        """
        # Critical risk level
        if self.current_risk_score >= 90:
            self._record_incident("critical_risk_pause", f"{self.current_risk_score}/100")
            self.stats["total_pauses"] += 1
            return True, f"Critical risk: {self.current_risk_score}/100"
        
        # High risk with consecutive occurrences
        if self.current_risk_score >= 75 and self.consecutive_high_risk >= 3:
            self._record_incident(
                "sustained_high_risk_pause",
                f"{self.consecutive_high_risk} consecutive",
            )
            self.stats["total_pauses"] += 1
            return True, f"Sustained high risk: {self.consecutive_high_risk} consecutive"
        
        # Hourly limit approaching
        hourly_count = self._count_last_hour()
        if hourly_count >= self.config.hourly_limit * 0.95:
            self._record_incident(
                "hourly_limit_pause",
                f"{hourly_count}/{self.config.hourly_limit}",
            )
            self.stats["total_pauses"] += 1
            return True, f"Hourly limit: {hourly_count}/{self.config.hourly_limit}"
        
        # Daily limit approaching
        daily_count = self._count_today()
        if daily_count >= self.config.daily_limit * 0.95:
            self._record_incident(
                "daily_limit_pause",
                f"{daily_count}/{self.config.daily_limit}",
            )
            self.stats["total_pauses"] += 1
            return True, f"Daily limit: {daily_count}/{self.config.daily_limit}"
        
        return False, "OK"
    
    def can_send_message(self, recipient: Optional[str] = None, account: Optional[str] = None, read_receipts: Optional[bool] = None) -> Tuple[bool, str, Dict]:
        """
        Smart Anti-Ban check with read receipt control.
        
        Args:
            recipient: Recipient number
            account: Sending account  
            read_receipts: Read receipt preference (overrides global)
            
        Returns:
            (can_send, reason, settings) - settings includes proxy/read_receipts
        """
        # Check per-minute limit
        if self._count_last_minute() >= self.config.minute_limit:
            reason = "Per-minute limit reached"
            self._record_incident("minute_limit", reason, recipient)
            return False, reason, {}

        # Read receipt safety check (high read rates increase ban risk)
        receipt_mode = read_receipts if read_receipts is not None else self.config.read_receipt_mode
        if receipt_mode == 'manual' and self.current_risk_score > 60:
            reason = "High risk: disable read receipts"
            return False, reason, {'read_receipts': False}

        # Get proxy for this send
        proxy_info = None
        if SETTINGS.enable_proxy_rotation:
            from core.engine.proxy_rotator import get_proxy_rotator
            proxy_result = get_proxy_rotator().get_next_proxy(account)
            if proxy_result:
                proxy_obj, health = proxy_result
                proxy_info = {'proxy': proxy_obj.url, 'health': health}
            else:
                logger.warning(f"No healthy proxy for {account}")

        return True, "OK", {
            'read_receipts': receipt_mode != 'off',
            'proxy': proxy_info['proxy'] if proxy_info else None,
            'proxy_health': proxy_info['health'] if proxy_info else None
        }

        # Check hourly limit
        if self._count_last_hour() >= self.config.hourly_limit:
            reason = "Hourly limit reached"
            self._record_incident("hourly_limit", reason, recipient)
            return False, reason

        # Check daily limit
        if self._count_today() >= self.config.daily_limit:
            reason = "Daily limit reached"
            self._record_incident("daily_limit", reason, recipient)
            return False, reason
        
        # Check recipient-specific limits (persistent when enabled)
        if recipient:
            if self._recipient_store is not None:
                ok, reason = self._recipient_store.can_send(
                    recipient,
                    account=account,
                    min_interval_s=int(self.config.per_recipient_min_interval),
                    hourly_limit=int(self.config.per_recipient_hourly_limit),
                    daily_limit=int(self.config.per_recipient_daily_limit),
                )
                if not ok:
                    kind = "per_recipient_interval"
                    if "hourly" in reason.lower():
                        kind = "per_recipient_hourly_limit"
                    elif "daily" in reason.lower():
                        kind = "per_recipient_daily_limit"
                    self._record_incident(kind, reason, recipient)
                    return False, reason
            else:
                if len(self.recipient_history[recipient]) > 0:
                    last_sent = self.recipient_history[recipient][-1]
                    time_since = time.time() - last_sent
                    min_interval = self.config.per_recipient_min_interval

                    if time_since < min_interval:
                        remaining = int(min_interval - time_since)
                        reason = f"Too soon for same recipient (wait {remaining}s)"
                        self._record_incident("per_recipient_interval", reason, recipient)
                        return False, reason

                    # Per-recipient hourly cap
                    if self._count_recipient_last_hours(recipient, hours=1) >= self.config.per_recipient_hourly_limit:
                        reason = "Per-recipient hourly limit reached"
                        self._record_incident("per_recipient_hourly_limit", reason, recipient)
                        return False, reason

                    # Per-recipient daily cap
                    if self._count_recipient_last_hours(recipient, hours=24) >= self.config.per_recipient_daily_limit:
                        reason = "Per-recipient daily limit reached"
                        self._record_incident("per_recipient_daily_limit", reason, recipient)
                        return False, reason
        
        # Calculate current risk
        self.calculate_risk()
        
        # Check if pause needed
        should_pause, reason = self.should_pause()
        if should_pause:
            return False, reason
        
        # Critical risk check
        if self.current_risk_score >= 95:
            self._record_incident("critical_risk_block", f"{self.current_risk_score}/100", recipient)
            return False, f"Critical risk: {self.current_risk_score}/100"
        
        return True, "OK"
    
    def record_message(self, recipient: Optional[str] = None, account: Optional[str] = None):
        """
        Record sent message
        
        Args:
            recipient: Optional recipient number
            account: Optional sending account identifier (used for per-account recipient caps)
        """
        current_time = time.time()
        
        # Add to history
        self.message_history.append(current_time)
        
        if recipient:
            self.recipient_history[recipient].append(current_time)
            if self._recipient_store is not None:
                try:
                    self._recipient_store.record_sent(recipient, account=account, now_ts=current_time)
                except Exception as exc:
                    logger.debug("RecipientHistoryStore record failed: %s", exc)
        
        # Update stats
        self.stats["messages_sent_total"] += 1
        self.stats["messages_sent_hour"] = self._count_last_hour()
        self.stats["messages_sent_today"] = self._count_today()
        
        # Recalculate risk
        self.calculate_risk()
        
        logger.debug(f"Message recorded, total today: {self.stats['messages_sent_today']}")
    
    def trigger_cooldown(self, duration: int = 300):
        """
        Trigger manual cooldown period
        
        Args:
            duration: Cooldown duration in seconds
        """
        self.last_cooldown = time.time()
        self.stats["total_cooldowns"] += 1
        self._record_incident("manual_cooldown", f"{duration}s")
        logger.warning(f"Cooldown triggered: {duration}s")
    
    def get_recommendation(self) -> Dict:
        """
        Get risk-based recommendations
        
        Returns:
            Recommendation dict
        """
        risk = self.current_risk_score
        
        if risk < 20:
            status = "🟢 SAFE"
            action = "Continue normal operation"
            color = "green"
        elif risk < 40:
            status = "🟡 LOW"
            action = "Slight caution, monitor closely"
            color = "yellow"
        elif risk < 60:
            status = "🟠 MEDIUM"
            action = "Reduce speed, increase delays"
            color = "orange"
        elif risk < 80:
            status = "🔴 HIGH"
            action = "Pause recommended, wait for cooldown"
            color = "red"
        else:
            status = "🚨 CRITICAL"
            action = "STOP IMMEDIATELY"
            color = "darkred"
        
        suggested_profile = "safe"
        if risk >= 80:
            suggested_profile = "safe"
        elif risk >= 60:
            suggested_profile = "balanced"
        elif risk < 40:
            suggested_profile = "aggressive"

        return {
            "status": status,
            "action": action,
            "color": color,
            "risk_score": risk,
            "delay": self.get_safe_delay(),
            "factors": self.risk_factors,
            "hourly_used": f"{self._count_last_hour()}/{self.config.hourly_limit}",
            "daily_used": f"{self._count_today()}/{self.config.daily_limit}",
            "suggested_profile": suggested_profile,
        }
    
    def get_stats(self) -> Dict:
        """
        Get comprehensive statistics
        
        Returns:
            Statistics dict
        """
        runtime = datetime.now() - self.stats["start_time"]

        incidents_recent = self._get_recent_incidents(limit=50)
        recipient_summary = self._get_recipient_risk_summary()

        return {
            **self.stats,
            "risk_score": self.current_risk_score,
            "risk_level": self._get_risk_level().value,
            "config": self.config.to_dict(),
            "minute_limit": self.config.minute_limit,
            "hourly_limit": self.config.hourly_limit,
            "daily_limit": self.config.daily_limit,
            "hourly_used": self._count_last_hour(),
            "daily_used": self._count_today(),
            "unique_recipients": len(self.recipient_history),
            "runtime_hours": runtime.total_seconds() / 3600,
            "avg_messages_per_hour": (
                self.stats["messages_sent_total"] / max(runtime.total_seconds() / 3600, 0.1)
            ),
            "recent_incidents": incidents_recent,
            "per_recipient_summary": recipient_summary,
            "content_gate": {
                "enabled": bool(getattr(self.config, "content_gate_enabled", False)),
                "window": int(getattr(self.config, "content_history_window", 40) or 40),
                "accounts_tracked": int(len(self._content_history_by_account)),
                "last_decision": self._last_content_decision,
            },
        }
    
    # Private helper methods
    
    def _count_last_minute(self) -> int:
        """Count messages in last minute."""
        cutoff = time.time() - 60
        return sum(1 for t in self.message_history if t > cutoff)

    def _count_last_hour(self) -> int:
        """Count messages in last hour"""
        cutoff = time.time() - 3600
        return sum(1 for t in self.message_history if t > cutoff)
    
    def _count_today(self) -> int:
        """Count messages today"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = today.timestamp()
        return sum(1 for t in self.message_history if t > cutoff)
    
    def _get_avg_delay(self) -> float:
        """Calculate average delay between messages"""
        if len(self.message_history) < 2:
            return float('inf')
        
        recent = sorted(list(self.message_history)[-20:])
        delays = [recent[i+1] - recent[i] for i in range(len(recent)-1)]
        
        return sum(delays) / len(delays) if delays else float('inf')
    
    def _detect_suspicious_pattern(self) -> bool:
        """Detect suspicious sending patterns"""
        if len(self.message_history) < 10:
            return False
        
        recent = list(self.message_history)[-10:]
        delays = [recent[i+1] - recent[i] for i in range(len(recent)-1)]
        
        # Check if delays are too uniform (bot-like)
        if delays:
            variance = sum((d - sum(delays)/len(delays))**2 for d in delays) / len(delays)
            if variance < 0.1:  # Very low variance
                return True
        
        return False
    
    def _calculate_recipient_diversity(self) -> float:
        """Calculate recipient diversity score"""
        if not self.recipient_history:
            return 1.0
        
        total_messages = len(self.message_history)
        unique_recipients = len(self.recipient_history)
        
        if total_messages == 0:
            return 1.0
        
        return min(unique_recipients / max(total_messages * 0.5, 1), 1.0)
    
    def _detect_burst(self) -> bool:
        """Detect message burst (too many too fast)"""
        if len(self.message_history) < 5:
            return False
        
        recent = list(self.message_history)[-5:]
        time_span = recent[-1] - recent[0]
        
        # 5 messages in less than 10 seconds is a burst
        return time_span < 10
    
    def _get_risk_level(self) -> RiskLevel:
        """Get risk level enum"""
        if self.current_risk_score < 20:
            return RiskLevel.SAFE
        elif self.current_risk_score < 40:
            return RiskLevel.LOW
        elif self.current_risk_score < 60:
            return RiskLevel.MEDIUM
        elif self.current_risk_score < 80:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL
    
    def reset(self):
        """Reset all tracking data."""
        self.message_history.clear()
        self.recipient_history.clear()
        self.hourly_counts.clear()
        self._content_history_by_account.clear()
        self._last_content_decision = None
        self.current_risk_score = 0
        self.consecutive_high_risk = 0
        self.last_cooldown = 0
        self._delay_history.clear()
        self._incidents.clear()
        
        self.stats = {
            "messages_sent_today": 0,
            "messages_sent_hour": 0,
            "messages_sent_total": 0,
            "total_pauses": 0,
            "total_cooldowns": 0,
            "avg_delay": 0,
            "start_time": datetime.now()
        }
        
        logger.info("RiskBrain reset")

    def close(self) -> None:
        """
        Close any underlying resources (not required in production, handy for tests).
        """
        store = self._recipient_store
        self._recipient_store = None
        if store is not None:
            try:
                store.close()
            except Exception:
                pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers for diagnostics
    # ------------------------------------------------------------------

    def _record_incident(self, kind: str, reason: str, recipient: Optional[str] = None) -> None:
        """Record a lightweight incident for later diagnostics."""
        self._incidents.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "reason": reason,
                "recipient": recipient,
            }
        )
        # Keep memory usage bounded
        if len(self._incidents) > 1000:
            self._incidents = self._incidents[-500:]

    def _get_recent_incidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return most recent incidents (up to `limit`)."""
        if limit <= 0:
            return []
        return self._incidents[-limit:]

    def _count_recipient_last_hours(self, recipient: str, hours: int) -> int:
        """Count messages to a recipient in the last `hours` hours."""
        cutoff = time.time() - (hours * 3600)
        history = self.recipient_history.get(recipient, [])
        return sum(1 for t in history if t > cutoff)

    def _get_recipient_risk_summary(self) -> Dict[str, Dict[str, Any]]:
        """Summarize per-recipient activity and approximate risk."""
        summary: Dict[str, Dict[str, Any]] = {}
        for recipient, history in self.recipient_history.items():
            if not history:
                continue
            hourly_count = self._count_recipient_last_hours(recipient, hours=1)
            daily_count = self._count_recipient_last_hours(recipient, hours=24)

            ratio_daily = daily_count / max(self.config.per_recipient_daily_limit, 1)
            if ratio_daily >= 1.0:
                level = "CRITICAL"
            elif ratio_daily >= 0.75:
                level = "HIGH"
            elif ratio_daily >= 0.5:
                level = "MEDIUM"
            else:
                level = "LOW"

            summary[recipient] = {
                "last_sent": datetime.fromtimestamp(history[-1]).isoformat(),
                "hourly_count": hourly_count,
                "daily_count": daily_count,
                "risk_level": level,
            }

        return summary
