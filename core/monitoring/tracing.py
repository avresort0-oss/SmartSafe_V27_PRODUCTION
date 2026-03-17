"""
SmartSafe V27 - APM Tracing with Jaeger
Provides distributed tracing for performance monitoring.
"""

from jaeger_client import Config
import opentracing
from opentracing import tags
import logging

logger = logging.getLogger(__name__)

_tracer = None


def init_tracer(service_name: str = "smartsafe"):
    """Initialize Jaeger tracer."""
    global _tracer
    config = Config(
        config={
            "sampler": {
                "type": "const",
                "param": 1,
            },
            "logging": True,
        },
        service_name=service_name,
    )
    _tracer = config.initialize_tracer()
    opentracing.set_global_tracer(_tracer)
    logger.info("Jaeger tracer initialized")


def get_tracer():
    """Get the global tracer."""
    return _tracer


def create_span(operation_name: str, tags_dict: dict = None):
    """Create a new span."""
    if not _tracer:
        return None
    span = _tracer.start_span(operation_name)
    if tags_dict:
        for key, value in tags_dict.items():
            span.set_tag(key, value)
    return span


def trace_function(operation_name: str, tags_dict: dict = None):
    """Decorator to trace a function."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            span = create_span(operation_name, tags_dict)
            if span:
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    span.finish()
            else:
                return func(*args, **kwargs)

        return wrapper

    return decorator
