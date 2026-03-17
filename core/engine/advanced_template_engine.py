"""
SmartSafe V27 - Advanced Template Engine
Dynamic content blocks, A/B testing, and performance analytics
"""

from __future__ import annotations

import json
import logging
import os
import random
import shutil
import time
import hashlib
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
import threading

from core.config import SETTINGS

logger = logging.getLogger(__name__)


@dataclass
class ContentBlock:
    """Dynamic content block template"""
    id: str
    name: str
    content: str
    variables: List[str] = field(default_factory=list)
    weight: float = 1.0  # For A/B testing
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class TemplateVariant:
    """Template variant for A/B testing"""
    id: str
    template_id: str
    name: str
    content_blocks: List[str]  # Block IDs
    variables: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    is_control: bool = False  # Control group in A/B test
    performance: Dict[str, float] = field(default_factory=dict)


@dataclass
class TemplateMetrics:
    """Template performance metrics"""
    template_id: str
    variant_id: str
    sends: int = 0
    successes: int = 0
    failures: int = 0
    replies: int = 0
    clicks: int = 0  # If trackable links
    conversion_rate: float = 0.0
    avg_response_time: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class ABTestConfig:
    """A/B test configuration"""
    test_id: str
    name: str
    template_id: str
    variants: List[str]  # Variant IDs
    traffic_split: Dict[str, float]  # Variant ID -> traffic percentage
    start_date: datetime
    end_date: Optional[datetime] = None
    min_sample_size: int = 100
    confidence_level: float = 0.95
    status: str = "active"  # active, paused, completed


class AdvancedTemplateEngine:
    """
    Advanced Template System with A/B Testing and Analytics
    
    Features:
    - Dynamic content blocks with variables
    - A/B testing framework for templates
    - Template performance analytics
    - Smart template recommendations
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self._ephemeral_storage = False
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            # Keep test runs hermetic so stale template data does not leak across runs.
            if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("SMARTSAFE_TEST_MODE") == "1":
                self.storage_path = Path(tempfile.mkdtemp(prefix="smartsafe_templates_"))
                self._ephemeral_storage = True
            else:
                self.storage_path = Path("logs/templates")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Storage
        self.content_blocks: Dict[str, ContentBlock] = {}
        self.templates: Dict[str, Any] = {}  # Template definitions
        self.variants: Dict[str, TemplateVariant] = {}
        self.metrics: Dict[str, TemplateMetrics] = {}
        self.ab_tests: Dict[str, ABTestConfig] = {}
        
        # Performance cache
        self._performance_cache: Dict[str, float] = {}
        self._recommendation_cache: Dict[str, List[str]] = {}
        self._cache_timestamp: datetime = datetime.now()
        
        # Threading
        self._lock = threading.RLock()
        self._analytics_thread: Optional[threading.Thread] = None
        self._stop_analytics = threading.Event()
        
        # Load existing data
        self._load_templates()
        self._load_metrics()
        
        # Start analytics processing
        self._start_analytics_processor()
        
        logger.info("Advanced Template Engine initialized")
    
    def create_content_block(self, name: str, content: str, tags: List[str] = None, weight: float = 1.0) -> str:
        """
        Create a new content block
        
        Args:
            name: Block name
            content: Block content with {variable} placeholders
            tags: Optional tags for categorization
            weight: Weight for randomization
            
        Returns:
            Block ID
        """
        with self._lock:
            block_id = self._generate_id("block")
            
            # Extract variables from content
            variables = self._extract_variables(content)
            
            block = ContentBlock(
                id=block_id,
                name=name,
                content=content,
                variables=variables,
                weight=weight,
                tags=tags or []
            )
            
            self.content_blocks[block_id] = block
            self._save_templates()
            
            logger.info(f"Created content block: {name} ({block_id})")
            return block_id
    
    def create_template(self, name: str, description: str, block_ids: List[str]) -> str:
        """
        Create a new template from content blocks
        
        Args:
            name: Template name
            description: Template description
            block_ids: List of content block IDs
            
        Returns:
            Template ID
        """
        with self._lock:
            template_id = self._generate_id("template")
            
            # Validate blocks exist
            for block_id in block_ids:
                if block_id not in self.content_blocks:
                    raise ValueError(f"Content block not found: {block_id}")
            
            template = {
                "id": template_id,
                "name": name,
                "description": description,
                "content_blocks": block_ids,
                "created_at": datetime.now().isoformat(),
                "variants": [],
                "active": True
            }

            # Create a default variant so templates render immediately without A/B setup.
            default_variant_id = self._create_variant(
                template_id=template_id,
                name="Default",
                block_ids=block_ids,
                weight=1.0,
                is_control=True,
            )
            template["variants"] = [default_variant_id]

            self.templates[template_id] = template
            self._save_templates()
            
            logger.info(f"Created template: {name} ({template_id})")
            return template_id
    
    def create_ab_test(self, template_id: str, name: str, variants_config: List[Dict], 
                      duration_days: int = 7) -> str:
        """
        Create an A/B test for a template
        
        Args:
            template_id: Template to test
            name: Test name
            variants_config: List of variant configurations
            duration_days: Test duration in days
            
        Returns:
            Test ID
        """
        with self._lock:
            if template_id not in self.templates:
                raise ValueError(f"Template not found: {template_id}")
            
            test_id = self._generate_id("test")
            
            # Create variants
            variant_ids = []
            traffic_split = {}
            
            for i, config in enumerate(variants_config):
                variant_id = self._create_variant(
                    template_id, 
                    config.get("name", f"Variant {i+1}"),
                    config.get("blocks", self.templates[template_id]["content_blocks"]),
                    config.get("weight", 1.0),
                    is_control=(i == 0)
                )
                variant_ids.append(variant_id)
                traffic_split[variant_id] = config.get("traffic_split", 100.0 / len(variants_config))
            
            # Normalize traffic split
            total = sum(traffic_split.values())
            for variant_id in traffic_split:
                traffic_split[variant_id] = (traffic_split[variant_id] / total) * 100
            
            test_config = ABTestConfig(
                test_id=test_id,
                name=name,
                template_id=template_id,
                variants=variant_ids,
                traffic_split=traffic_split,
                start_date=datetime.now(),
                end_date=datetime.now() + timedelta(days=duration_days),
                min_sample_size=100,
                confidence_level=0.95,
                status="active"
            )
            
            self.ab_tests[test_id] = test_config
            self._save_templates()
            
            logger.info(f"Created A/B test: {name} ({test_id})")
            return test_id
    
    def _create_variant(self, template_id: str, name: str, block_ids: List[str], 
                       weight: float = 1.0, is_control: bool = False) -> str:
        """Create a template variant"""
        variant_id = self._generate_id("variant")
        
        variant = TemplateVariant(
            id=variant_id,
            template_id=template_id,
            name=name,
            content_blocks=block_ids,
            weight=weight,
            is_control=is_control
        )
        
        self.variants[variant_id] = variant
        return variant_id
    
    def render_template(self, template_id: str, variables: Dict[str, Any], 
                       variant_id: Optional[str] = None) -> Tuple[str, str]:
        """
        Render a template with variables
        
        Args:
            template_id: Template ID
            variables: Variable values
            variant_id: Optional specific variant ID
            
        Returns:
            Tuple of (rendered_content, variant_id_used)
        """
        with self._lock:
            if template_id not in self.templates:
                raise ValueError(f"Template not found: {template_id}")
            
            # Determine variant to use
            if variant_id:
                if variant_id not in self.variants:
                    raise ValueError(f"Variant not found: {variant_id}")
            else:
                variant_id = self._select_variant(template_id, variables)
            
            variant = self.variants[variant_id]
            
            # Build content from blocks
            content_parts = []
            for block_id in variant.content_blocks:
                if block_id in self.content_blocks:
                    block = self.content_blocks[block_id]
                    block_content = self._render_block(block, variables)
                    content_parts.append(block_content)
            
            rendered_content = "\n".join(content_parts)
            
            # Track render for analytics
            self._track_render(template_id, variant_id)
            
            return rendered_content, variant_id
    
    def _select_variant(self, template_id: str, variables: Dict[str, Any]) -> str:
        """Select variant based on A/B test or performance"""
        template = self.templates[template_id]
        
        # Check if there's an active A/B test
        active_tests = [test for test in self.ab_tests.values() 
                       if test.template_id == template_id and test.status == "active"]
        
        if active_tests:
            # Use A/B test selection
            test = active_tests[0]  # Use first active test
            
            # Check if test has ended
            if test.end_date and datetime.now() > test.end_date:
                test.status = "completed"
                self._save_templates()
                # Fall back to performance-based selection
                return self._select_by_performance(template_id)
            
            # Select variant based on traffic split
            return self._select_by_traffic_split(test)
        
        # No active test, use performance-based selection
        return self._select_by_performance(template_id)
    
    def _select_by_traffic_split(self, test: ABTestConfig) -> str:
        """Select variant based on traffic split"""
        rand = random.random() * 100
        cumulative = 0.0
        
        for variant_id, split in test.traffic_split.items():
            cumulative += split
            if rand <= cumulative:
                return variant_id
        
        # Fallback to first variant
        return test.variants[0]
    
    def _select_by_performance(self, template_id: str) -> str:
        """Select variant based on historical performance"""
        template = self.templates[template_id]
        template_variant_ids = [vid for vid in template.get("variants", []) if vid in self.variants]
        template_variants = [self.variants[vid] for vid in template_variant_ids]

        # Backward compatibility: older saved templates may not have explicit variants.
        if not template_variants:
            template_variants = [v for v in self.variants.values() if v.template_id == template_id]

        if not template_variants:
            block_ids = list(template.get("content_blocks", []))
            if not block_ids:
                raise ValueError(f"Template has no content blocks: {template_id}")

            fallback_variant_id = self._create_variant(
                template_id=template_id,
                name="Default",
                block_ids=block_ids,
                weight=1.0,
                is_control=True,
            )
            template.setdefault("variants", []).append(fallback_variant_id)
            self._save_templates()
            return fallback_variant_id
        
        # Get performance metrics
        variant_scores = []
        for variant in template_variants:
            metrics = self.metrics.get(f"{template_id}_{variant.id}")
            if metrics and metrics.sends >= 10:  # Minimum sample size
                score = metrics.conversion_rate
            else:
                score = 0.5  # Default score for new variants
            
            variant_scores.append((variant.id, score))
        
        # Weighted random selection based on performance
        if variant_scores:
            total_score = sum(score for _, score in variant_scores)
            if total_score > 0:
                rand = random.random() * total_score
                cumulative = 0.0
                
                for variant_id, score in variant_scores:
                    cumulative += score
                    if rand <= cumulative:
                        return variant_id
        
        # Fallback to random selection
        return random.choice(template_variants).id
    
    def _render_block(self, block: ContentBlock, variables: Dict[str, Any]) -> str:
        """Render a single content block"""
        content = block.content
        
        # Replace variables
        for var in block.variables:
            value = variables.get(var, f"{{{var}}}")
            content = content.replace(f"{{{var}}}", str(value))
        
        return content
    
    def _extract_variables(self, content: str) -> List[str]:
        """Extract variable names from content"""
        import re
        pattern = r'\{([^}]+)\}'
        return re.findall(pattern, content)
    
    def track_outcome(self, template_id: str, variant_id: str, success: bool, 
                     reply_received: bool = False, response_time: Optional[float] = None):
        """
        Track message outcome for analytics
        
        Args:
            template_id: Template ID
            variant_id: Variant ID
            success: Whether message was sent successfully
            reply_received: Whether reply was received
            response_time: Time to response (seconds)
        """
        with self._lock:
            metrics_key = f"{template_id}_{variant_id}"
            
            if metrics_key not in self.metrics:
                self.metrics[metrics_key] = TemplateMetrics(
                    template_id=template_id,
                    variant_id=variant_id
                )
            
            metrics = self.metrics[metrics_key]
            metrics.sends += 1
            
            if success:
                metrics.successes += 1
            else:
                metrics.failures += 1
            
            if reply_received:
                metrics.replies += 1
                if response_time:
                    # Update average response time
                    current_avg = metrics.avg_response_time
                    replies_count = metrics.replies
                    metrics.avg_response_time = ((current_avg * (replies_count - 1)) + response_time) / replies_count
            
            # Update conversion rate
            if metrics.sends > 0:
                metrics.conversion_rate = metrics.replies / metrics.sends
            
            metrics.last_updated = datetime.now()
            
            # Save metrics periodically
            if metrics.sends % 10 == 0:  # Save every 10 sends
                self._save_metrics()
    
    def get_template_analytics(self, template_id: str) -> Dict[str, Any]:
        """Get analytics for a template"""
        with self._lock:
            if template_id not in self.templates:
                return {}
            
            # Get all variants for this template
            template_variants = [v for v in self.variants.values() 
                                if v.template_id == template_id]
            
            analytics = {
                "template_id": template_id,
                "template_name": self.templates[template_id]["name"],
                "total_sends": 0,
                "total_successes": 0,
                "total_failures": 0,
                "total_replies": 0,
                "overall_conversion_rate": 0.0,
                "variants": [],
                "ab_tests": []
            }
            
            # Aggregate variant metrics
            for variant in template_variants:
                metrics_key = f"{template_id}_{variant.id}"
                metrics = self.metrics.get(metrics_key)
                
                variant_data = {
                    "variant_id": variant.id,
                    "variant_name": variant.name,
                    "is_control": variant.is_control,
                    "sends": metrics.sends if metrics else 0,
                    "successes": metrics.successes if metrics else 0,
                    "failures": metrics.failures if metrics else 0,
                    "replies": metrics.replies if metrics else 0,
                    "conversion_rate": metrics.conversion_rate if metrics else 0.0,
                    "avg_response_time": metrics.avg_response_time if metrics else 0.0
                }
                
                analytics["variants"].append(variant_data)
                
                # Aggregate totals
                analytics["total_sends"] += variant_data["sends"]
                analytics["total_successes"] += variant_data["successes"]
                analytics["total_failures"] += variant_data["failures"]
                analytics["total_replies"] += variant_data["replies"]
            
            # Calculate overall conversion rate
            if analytics["total_sends"] > 0:
                analytics["overall_conversion_rate"] = analytics["total_replies"] / analytics["total_sends"]
            
            # Add A/B test information
            for test in self.ab_tests.values():
                if test.template_id == template_id:
                    test_data = {
                        "test_id": test.test_id,
                        "test_name": test.name,
                        "status": test.status,
                        "start_date": test.start_date.isoformat(),
                        "end_date": test.end_date.isoformat() if test.end_date else None,
                        "variants": test.variants,
                        "traffic_split": test.traffic_split
                    }
                    analytics["ab_tests"].append(test_data)
            
            return analytics
    
    def get_recommendations(self, template_id: str) -> List[Dict[str, Any]]:
        """Get template recommendations based on performance"""
        with self._lock:
            if template_id not in self.templates:
                return []
            
            recommendations = []
            analytics = self.get_template_analytics(template_id)
            
            # Analyze variant performance
            if len(analytics["variants"]) > 1:
                best_variant = max(analytics["variants"], key=lambda x: x["conversion_rate"])
                worst_variant = min(analytics["variants"], key=lambda x: x["conversion_rate"])
                
                if best_variant["conversion_rate"] > worst_variant["conversion_rate"] + 0.1:
                    recommendations.append({
                        "type": "variant_optimization",
                        "priority": "high",
                        "title": "Use Best Performing Variant",
                        "description": f"Variant '{best_variant['variant_name']}' has {best_variant['conversion_rate']:.1%} conversion rate vs {worst_variant['conversion_rate']:.1%} for '{worst_variant['variant_name']}'",
                        "action": f"Set variant '{best_variant['variant_id']}' as primary"
                    })
            
            # Check sample size
            if analytics["total_sends"] < 100:
                recommendations.append({
                    "type": "sample_size",
                    "priority": "medium",
                    "title": "Increase Sample Size",
                    "description": f"Only {analytics['total_sends']} sends recorded. Minimum 100 recommended for reliable analytics.",
                    "action": "Send more messages to gather data"
                })
            
            # Check for A/B test opportunities
            active_tests = [t for t in analytics["ab_tests"] if t["status"] == "active"]
            if not active_tests and len(analytics["variants"]) < 3:
                recommendations.append({
                    "type": "ab_testing",
                    "priority": "medium",
                    "title": "Start A/B Test",
                    "description": "Consider creating an A/B test to optimize message content",
                    "action": "Create new A/B test with different content variations"
                })
            
            return recommendations
    
    def _generate_id(self, prefix: str) -> str:
        """Generate unique ID"""
        timestamp = str(int(time.time()))
        hash_obj = hashlib.md5(f"{prefix}_{timestamp}_{random.random()}".encode())
        return f"{prefix}_{hash_obj.hexdigest()[:8]}"
    
    def _track_render(self, template_id: str, variant_id: str):
        """Track template render for analytics"""
        # This could be expanded to track more detailed analytics
        pass
    
    def _load_templates(self):
        """Load templates from storage"""
        try:
            templates_file = self.storage_path / "templates.json"
            if templates_file.exists():
                with open(templates_file, 'r') as f:
                    data = json.load(f)
                    
                    # Load content blocks
                    for block_data in data.get("content_blocks", []):
                        block = ContentBlock(**block_data)
                        block.created_at = datetime.fromisoformat(block.created_at)
                        self.content_blocks[block.id] = block
                    
                    # Load templates
                    self.templates = data.get("templates", {})
                    
                    # Load variants
                    for variant_data in data.get("variants", []):
                        variant = TemplateVariant(**variant_data)
                        self.variants[variant.id] = variant
                    
                    # Load A/B tests
                    for test_data in data.get("ab_tests", []):
                        test = ABTestConfig(**test_data)
                        test.start_date = datetime.fromisoformat(test.start_date)
                        if test.end_date:
                            test.end_date = datetime.fromisoformat(test.end_date)
                        self.ab_tests[test.test_id] = test
                
                logger.info(f"Loaded {len(self.templates)} templates, {len(self.content_blocks)} blocks")
                
        except Exception as e:
            logger.error(f"Failed to load templates: {e}")
    
    def _load_metrics(self):
        """Load metrics from storage"""
        try:
            metrics_file = self.storage_path / "metrics.json"
            if metrics_file.exists():
                with open(metrics_file, 'r') as f:
                    data = json.load(f)
                    
                    for metrics_data in data.get("metrics", []):
                        metrics = TemplateMetrics(**metrics_data)
                        metrics.last_updated = datetime.fromisoformat(metrics.last_updated)
                        key = f"{metrics.template_id}_{metrics.variant_id}"
                        self.metrics[key] = metrics
                
                logger.info(f"Loaded metrics for {len(self.metrics)} template variants")
                
        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")
    
    def _save_templates(self):
        """Save templates to storage"""
        try:
            data = {
                "content_blocks": [],
                "templates": self.templates,
                "variants": [],
                "ab_tests": []
            }
            
            # Convert content blocks
            for block in self.content_blocks.values():
                block_data = {
                    "id": block.id,
                    "name": block.name,
                    "content": block.content,
                    "variables": block.variables,
                    "weight": block.weight,
                    "tags": block.tags,
                    "created_at": block.created_at.isoformat()
                }
                data["content_blocks"].append(block_data)
            
            # Convert variants
            for variant in self.variants.values():
                variant_data = {
                    "id": variant.id,
                    "template_id": variant.template_id,
                    "name": variant.name,
                    "content_blocks": variant.content_blocks,
                    "variables": variant.variables,
                    "weight": variant.weight,
                    "is_control": variant.is_control,
                    "performance": variant.performance
                }
                data["variants"].append(variant_data)
            
            # Convert A/B tests
            for test in self.ab_tests.values():
                test_data = {
                    "test_id": test.test_id,
                    "name": test.name,
                    "template_id": test.template_id,
                    "variants": test.variants,
                    "traffic_split": test.traffic_split,
                    "start_date": test.start_date.isoformat(),
                    "end_date": test.end_date.isoformat() if test.end_date else None,
                    "min_sample_size": test.min_sample_size,
                    "confidence_level": test.confidence_level,
                    "status": test.status
                }
                data["ab_tests"].append(test_data)
            
            with open(self.storage_path / "templates.json", 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save templates: {e}")
    
    def _save_metrics(self):
        """Save metrics to storage"""
        try:
            data = {
                "metrics": []
            }
            
            for metrics in self.metrics.values():
                metrics_data = {
                    "template_id": metrics.template_id,
                    "variant_id": metrics.variant_id,
                    "sends": metrics.sends,
                    "successes": metrics.successes,
                    "failures": metrics.failures,
                    "replies": metrics.replies,
                    "clicks": metrics.clicks,
                    "conversion_rate": metrics.conversion_rate,
                    "avg_response_time": metrics.avg_response_time,
                    "last_updated": metrics.last_updated.isoformat()
                }
                data["metrics"].append(metrics_data)
            
            with open(self.storage_path / "metrics.json", 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    def _start_analytics_processor(self):
        """Start background analytics processing"""
        def analytics_worker():
            while not self._stop_analytics.wait(300):  # Run every 5 minutes
                try:
                    self._process_analytics()
                except Exception as e:
                    logger.error(f"Analytics processing failed: {e}")
        
        self._analytics_thread = threading.Thread(target=analytics_worker, daemon=True)
        self._analytics_thread.start()
    
    def _process_analytics(self):
        """Process analytics and update recommendations"""
        with self._lock:
            # Update performance cache
            for metrics_key, metrics in self.metrics.items():
                template_id = metrics.template_id
                self._performance_cache[template_id] = metrics.conversion_rate
            
            # Clear recommendation cache periodically
            if datetime.now() - self._cache_timestamp > timedelta(hours=1):
                self._recommendation_cache.clear()
                self._cache_timestamp = datetime.now()
    
    def get_engine_stats(self) -> Dict[str, Any]:
        """Get engine statistics"""
        with self._lock:
            return {
                "content_blocks": len(self.content_blocks),
                "templates": len(self.templates),
                "variants": len(self.variants),
                "ab_tests": len(self.ab_tests),
                "metrics_tracked": len(self.metrics),
                "cache_size": len(self._performance_cache),
                "last_analytics_update": self._cache_timestamp.isoformat()
            }
    
    def close(self):
        """Cleanup and save data"""
        self._stop_analytics.set()
        if self._analytics_thread and self._analytics_thread.is_alive():
            self._analytics_thread.join(timeout=5)

        if self._ephemeral_storage:
            shutil.rmtree(self.storage_path, ignore_errors=True)
            logger.info("Advanced Template Engine closed (ephemeral storage removed)")
            return

        self._save_templates()
        self._save_metrics()
        logger.info("Advanced Template Engine closed")
