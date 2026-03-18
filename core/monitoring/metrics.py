"""
SmartSafe V27 - Prometheus Metrics
Provides metrics collection for monitoring and alerting.
"""

from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time

# Message metrics
messages_sent_total = Counter(
    "smartsafe_messages_sent_total", "Total messages sent", ["account", "status"]
)

messages_received_total = Counter(
    "smartsafe_messages_received_total", "Total messages received", ["account"]
)

api_requests_total = Counter(
    "smartsafe_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)

api_request_duration = Histogram(
    "smartsafe_api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"],
)

# Flow engine metrics
flows_executed_total = Counter(
    "smartsafe_flows_executed_total", "Total flows executed", ["flow_id", "status"]
)

flow_execution_duration = Histogram(
    "smartsafe_flow_execution_duration_seconds",
    "Flow execution duration in seconds",
    ["flow_id"],
)

# Cache metrics
cache_hits_total = Counter(
    "smartsafe_cache_hits_total", "Total cache hits", ["cache_type"]
)

cache_misses_total = Counter(
    "smartsafe_cache_misses_total", "Total cache misses", ["cache_type"]
)

# Active connections
active_connections = Gauge(
    "smartsafe_active_connections", "Number of active connections", ["type"]
)

# Error metrics
errors_total = Counter("smartsafe_errors_total", "Total errors", ["type", "component"])


def start_metrics_server(port: int = 8001):
    """Start Prometheus metrics server."""
    start_http_server(port)
    print(f"Prometheus metrics server started on port {port}")


def record_message_sent(account: str, status: str = "success"):
    """Record a message sent."""
    messages_sent_total.labels(account=account, status=status).inc()


def record_message_received(account: str):
    """Record a message received."""
    messages_received_total.labels(account=account).inc()


def record_api_request(method: str, endpoint: str, status: int, duration: float):
    """Record an API request."""
    api_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
    api_request_duration.labels(method=method, endpoint=endpoint).observe(duration)


def record_flow_execution(flow_id: str, status: str, duration: float):
    """Record a flow execution."""
    flows_executed_total.labels(flow_id=flow_id, status=status).inc()
    flow_execution_duration.labels(flow_id=flow_id).observe(duration)


def record_cache_hit(cache_type: str):
    """Record a cache hit."""
    cache_hits_total.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str):
    """Record a cache miss."""
    cache_misses_total.labels(cache_type=cache_type).inc()


def update_active_connections(conn_type: str, count: int):
    """Update active connections count."""
    active_connections.labels(type=conn_type).set(count)


def record_error(error_type: str, component: str):
    """Record an error."""
    errors_total.labels(type=error_type, component=component).inc()
