"""
SmartSafe V27 - Machine Learning Risk Assessment Engine
Advanced predictive risk analysis and adaptive rate limiting
"""

from __future__ import annotations

import json
import logging
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict, deque
import threading

try:
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier, IsolationForest
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, accuracy_score
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

from core.config import SETTINGS

logger = logging.getLogger(__name__)


@dataclass
class MLFeature:
    """ML feature data structure"""
    timestamp: float
    hourly_count: int
    daily_count: int
    avg_delay: float
    risk_score: int
    success_rate: float
    pattern_score: float
    diversity_score: float
    time_of_day: int
    day_of_week: int
    account_age_days: int
    consecutive_failures: int
    recipient_unique_ratio: float
    message_length: float
    media_ratio: float
    outcome: int  # 1 = success, 0 = failure/ban


@dataclass
class MLPrediction:
    """ML prediction result"""
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: float  # 0.0 to 1.0
    predicted_success_rate: float
    recommended_delay_multiplier: float
    anomaly_score: float
    features_used: List[str]
    model_version: str


class MLRiskEngine:
    """
    Machine Learning Risk Assessment Engine
    
    Features:
    - Predictive risk analysis using historical data
    - Adaptive rate limiting based on ML predictions
    - Anomaly detection for unusual patterns
    - Real-time risk scoring with ML models
    """
    
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or Path("logs/ml_models")
        self.model_path.mkdir(parents=True, exist_ok=True)
        
        # ML components
        self.risk_classifier: Optional[RandomForestClassifier] = None
        self.anomaly_detector: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        
        # Feature storage
        self.features_history: deque = deque(maxlen=10000)
        self.recent_predictions: deque = deque(maxlen=1000)
        
        # Model metadata
        self.model_version = "1.0.0"
        self.last_training_time: Optional[datetime] = None
        self.training_samples = 0
        self.model_accuracy = 0.0
        
        # Threading for async training
        self.training_lock = threading.Lock()
        self.is_training = False
        
        # Initialize or load models
        self._initialize_models()
        
        logger.info(f"ML Risk Engine initialized (ML available: {ML_AVAILABLE})")
    
    def _initialize_models(self):
        """Initialize or load ML models"""
        if not ML_AVAILABLE:
            logger.warning("ML libraries not available, using rule-based fallback")
            return
        
        try:
            # Try to load existing models
            classifier_path = self.model_path / "risk_classifier.pkl"
            anomaly_path = self.model_path / "anomaly_detector.pkl"
            scaler_path = self.model_path / "scaler.pkl"
            
            if classifier_path.exists():
                with open(classifier_path, 'rb') as f:
                    self.risk_classifier = pickle.load(f)
                logger.info("Loaded existing risk classifier model")
            
            if anomaly_path.exists():
                with open(anomaly_path, 'rb') as f:
                    self.anomaly_detector = pickle.load(f)
                logger.info("Loaded existing anomaly detector model")
            
            if scaler_path.exists():
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                logger.info("Loaded existing scaler")
            
            # Load metadata
            metadata_path = self.model_path / "metadata.json"
            if metadata_path.exists():
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    self.model_version = metadata.get("version", "1.0.0")
                    self.last_training_time = datetime.fromisoformat(metadata.get("last_training", datetime.now().isoformat()))
                    self.training_samples = metadata.get("training_samples", 0)
                    self.model_accuracy = metadata.get("accuracy", 0.0)
            
        except Exception as e:
            logger.error(f"Failed to load ML models: {e}")
            self._create_default_models()
    
    def _create_default_models(self):
        """Create default ML models"""
        if not ML_AVAILABLE:
            return
        
        try:
            # Risk classifier for predicting success/failure
            self.risk_classifier = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
            
            # Anomaly detector for unusual patterns
            self.anomaly_detector = IsolationForest(
                contamination=0.1,
                random_state=42,
                n_jobs=-1
            )
            
            # Feature scaler
            self.scaler = StandardScaler()
            
            logger.info("Created default ML models")
        except Exception as e:
            logger.error(f"Failed to create ML models: {e}")
    
    def extract_features(self, risk_data: Dict[str, Any]) -> MLFeature:
        """Extract ML features from risk data"""
        try:
            return MLFeature(
                timestamp=time.time(), # Capture timestamp
                hourly_count=int(risk_data.get("hourly_count", 0)), # Retrieve and convert hourly count
                daily_count=int(risk_data.get("daily_count", 0)), # Retrieve and convert daily count

                avg_delay=float(risk_data.get("avg_delay", 0)), # Retrieve and convert average delay
                risk_score=int(risk_data.get("risk_score", 0)), # Retrieve and convert risk score

                success_rate=float(risk_data.get("success_rate", 0)), # Retrieve and convert success rate
                pattern_score=float(risk_data.get("pattern_score", 0)), # Retrieve and convert pattern score

                diversity_score=float(risk_data.get("diversity_score", 0)), # Retrieve and convert diversity score
                time_of_day=datetime.now().hour, # Extract time of day
                day_of_week=datetime.now().weekday(),# Extract day of week

                account_age_days=int(risk_data.get("account_age_days", 0)), # Retrieve and convert account age
                consecutive_failures=int(risk_data.get("consecutive_failures", 0)), # Retrieve and convert consecutive failures

                recipient_unique_ratio=float(risk_data.get("recipient_unique_ratio", 0)), # Retrieve and convert recipient unique ratio
                message_length=float(risk_data.get("message_length", 0)),# Retrieve and convert message length
                media_ratio=float(risk_data.get("media_ratio", 0)), # Retrieve and convert media ratio
                outcome=int(risk_data.get("outcome", 1))  # Default to success # Retrieve and convert outcome, default to 1

            )
        except (ValueError, TypeError) as e:
            logger.error(f"Data conversion error: {e}")
        except Exception as e: # Fallback for unexpected errors
            logger.error(f"Unexpected error during feature extraction: {e}")
            # Return default features
            return MLFeature(
                timestamp=time.time(), # Providing some default values
                hourly_count=0, daily_count=0, avg_delay=0, risk_score=0,
                success_rate=0, pattern_score=0, diversity_score=0,
                time_of_day=datetime.now().hour, day_of_week=datetime.now().weekday(),
                account_age_days=0, consecutive_failures=0,
                recipient_unique_ratio=0, message_length=0, media_ratio=0,
                outcome=1
            )
    
    def predict_risk(self, risk_data: Dict[str, Any]) -> MLPrediction:
        """
        Predict risk using ML models
        
        Args:
            risk_data: Dictionary containing current risk metrics
            
        Returns:
            MLPrediction with risk assessment and recommendations
        """
        if not ML_AVAILABLE or not self.risk_classifier:
            prediction = self._rule_based_prediction(risk_data)
            self.recent_predictions.append(prediction)
            return prediction
        
        try:
            # Extract features
            features = self.extract_features(risk_data)
            self.features_history.append(features)
            
            # Prepare feature vector
            feature_vector = self._prepare_feature_vector(features)
            
            # Scale features
            if self.scaler:
                feature_vector = self.scaler.transform([feature_vector])
            
            # Predict risk level
            risk_prediction = self.risk_classifier.predict_proba(feature_vector)[0]
            risk_class = self.risk_classifier.predict(feature_vector)[0]
            
            # Detect anomalies
            anomaly_score = 0
            if self.anomaly_detector:
                anomaly_score = self.anomaly_detector.decision_function(feature_vector)[0]
            
            # Create prediction result
            risk_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
            risk_level = risk_levels[min(risk_class, 3)]
            confidence = float(risk_prediction.max())
            
            # Calculate recommendations
            predicted_success_rate = float(risk_prediction[1] if len(risk_prediction) > 1 else confidence)
            recommended_delay = self._calculate_delay_multiplier(risk_level, confidence)
            
            prediction = MLPrediction(
                risk_level=risk_level,
                confidence=confidence,
                predicted_success_rate=predicted_success_rate,
                recommended_delay_multiplier=recommended_delay,
                anomaly_score=float(anomaly_score),
                features_used=self._get_feature_names(),
                model_version=self.model_version
            )
            
            self.recent_predictions.append(prediction)
            return prediction
            
        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            return self._rule_based_prediction(risk_data)
    
    def _prepare_feature_vector(self, features: MLFeature) -> List[float]:
        """Prepare feature vector for ML models"""
        return [
            features.hourly_count,
            features.daily_count,
            features.avg_delay,
            features.risk_score,
            features.success_rate,
            features.pattern_score,
            features.diversity_score,
            features.time_of_day,
            features.day_of_week,
            features.account_age_days,
            features.consecutive_failures,
            features.recipient_unique_ratio,
            features.message_length,
            features.media_ratio
        ]
    
    def _get_feature_names(self) -> List[str]:
        """Get feature names for explainability"""
        return [
            "hourly_count", "daily_count", "avg_delay", "risk_score",
            "success_rate", "pattern_score", "diversity_score",
            "time_of_day", "day_of_week", "account_age_days",
            "consecutive_failures", "recipient_unique_ratio",
            "message_length", "media_ratio"
        ]
    
    def _calculate_delay_multiplier(self, risk_level: str, confidence: float) -> float:
        """Calculate recommended delay multiplier based on risk"""
        base_multipliers = {
            "LOW": 1.0,
            "MEDIUM": 1.5,
            "HIGH": 2.5,
            "CRITICAL": 4.0
        }
        
        base = base_multipliers.get(risk_level, 1.5)
        
        # Adjust based on confidence
        if confidence < 0.7:
            base *= 1.3  # Be more conservative with low confidence
        
        return round(base, 2)

    def _ml_level_to_score(self, ml_level: str) -> int:
        """Convert ML risk labels to numeric risk score."""
        level_scores = {
            "LOW": 20,
            "MEDIUM": 45,
            "HIGH": 70,
            "CRITICAL": 90,
        }
        return level_scores.get(str(ml_level or "").upper(), 50)
    
    def _rule_based_prediction(self, risk_data: Dict[str, Any]) -> MLPrediction:
        """Fallback rule-based prediction when ML is not available"""
        risk_score = int(risk_data.get("risk_score", 0))
        
        if risk_score < 30:
            risk_level = "LOW"
            confidence = 0.8
            predicted_success = 0.95
        elif risk_score < 60:
            risk_level = "MEDIUM"
            confidence = 0.7
            predicted_success = 0.8
        elif risk_score < 80:
            risk_level = "HIGH"
            confidence = 0.6
            predicted_success = 0.6
        else:
            risk_level = "CRITICAL"
            confidence = 0.9
            predicted_success = 0.3
        
        return MLPrediction(
            risk_level=risk_level,
            confidence=confidence,
            predicted_success_rate=predicted_success,
            recommended_delay_multiplier=self._calculate_delay_multiplier(risk_level, confidence),
            anomaly_score=0.0,
            features_used=["rule_based"],
            model_version="rule_based_v1.0"
        )
    
    def record_outcome(self, prediction: MLPrediction, actual_outcome: bool, risk_data: Dict[str, Any]):
        """Record actual outcome for model training"""
        try:
            # Update feature with actual outcome
            features = self.extract_features(risk_data)
            features.outcome = 1 if actual_outcome else 0
            self.features_history.append(features)
            
            # Trigger training if we have enough samples
            if ML_AVAILABLE and len(self.features_history) >= 100 and not self.is_training:
                self._schedule_training()
                
        except Exception as e:
            logger.error(f"Failed to record outcome: {e}")
    
    def _schedule_training(self):
        """Schedule model training in background"""
        def train_worker():
            with self.training_lock:
                if self.is_training:
                    return
                
                self.is_training = True
                try:
                    self._train_models()
                except Exception as e:
                    logger.error(f"Model training failed: {e}")
                finally:
                    self.is_training = False
        
        threading.Thread(target=train_worker, daemon=True).start()
    
    def _train_models(self):
        """Train ML models with collected data"""
        if not ML_AVAILABLE or len(self.features_history) < 50:
            return
        
        try:
            logger.info("Starting ML model training...")
            
            # Prepare training data
            features_list = list(self.features_history)
            X = []
            y = []
            
            for features in features_list:
                X.append(self._prepare_feature_vector(features))
                # Map outcomes to risk classes
                if features.outcome == 1:
                    risk_class = 0 if features.risk_score < 30 else (1 if features.risk_score < 60 else 2)
                else:
                    risk_class = 3  # Failure/ban
                y.append(risk_class)
            
            X = np.array(X)
            y = np.array(y)
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Scale features
            if self.scaler:
                X_train_scaled = self.scaler.fit_transform(X_train)
                X_test_scaled = self.scaler.transform(X_test)
            else:
                X_train_scaled = X_train
                X_test_scaled = X_test
            
            # Train risk classifier
            self.risk_classifier.fit(X_train_scaled, y_train)
            
            # Train anomaly detector
            self.anomaly_detector.fit(X_train_scaled)
            
            # Evaluate model
            y_pred = self.risk_classifier.predict(X_test_scaled)
            self.model_accuracy = accuracy_score(y_test, y_pred)
            
            # Save models
            self._save_models()
            
            # Update metadata
            self.last_training_time = datetime.now()
            self.training_samples = len(features_list)
            
            logger.info(f"ML model training completed. Accuracy: {self.model_accuracy:.3f}")
            
        except Exception as e:
            logger.error(f"Model training failed: {e}")
    
    def _save_models(self):
        """Save trained models to disk"""
        try:
            # Save models
            with open(self.model_path / "risk_classifier.pkl", 'wb') as f:
                pickle.dump(self.risk_classifier, f)
            
            with open(self.model_path / "anomaly_detector.pkl", 'wb') as f:
                pickle.dump(self.anomaly_detector, f)
            
            with open(self.model_path / "scaler.pkl", 'wb') as f:
                pickle.dump(self.scaler, f)
            
            # Save metadata
            metadata = {
                "version": self.model_version,
                "last_training": self.last_training_time.isoformat() if self.last_training_time else None,
                "training_samples": self.training_samples,
                "accuracy": self.model_accuracy
            }
            
            with open(self.model_path / "metadata.json", 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info("ML models saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save models: {e}")
    
    def get_model_stats(self) -> Dict[str, Any]:
        """Get model statistics"""
        return {
            "ml_available": ML_AVAILABLE,
            "model_version": self.model_version,
            "last_training": self.last_training_time.isoformat() if self.last_training_time else None,
            "training_samples": self.training_samples,
            "accuracy": self.model_accuracy,
            "features_collected": len(self.features_history),
            "predictions_made": len(self.recent_predictions),
            "is_training": self.is_training
        }
    
    def force_training(self):
        """Force model training with current data"""
        if not ML_AVAILABLE:
            return False
        
        if len(self.features_history) < 50:
            logger.warning("Insufficient data for training (need at least 50 samples)")
            return False
        
        self._schedule_training()
        return True
