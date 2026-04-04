from prometheus_client import Counter, Gauge, Histogram

# Conversation worker metrics
messages_processed_total = Counter(
    "messages_processed_total",
    "Total number of messages processed",
    ["direction", "status"],  # direction: inbound/outbound, status: success/failure
)

llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "LLM API call latency in seconds",
    buckets=(0.5, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0),
)

tool_calls_total = Counter(
    "tool_calls_total",
    "Total number of tool calls",
    ["tool_name", "success"],
)

retries_total = Counter(
    "retries_total",
    "Total number of message retries",
    ["queue", "reason"],
)

# Outbound worker metrics
messages_sent_total = Counter(
    "messages_sent_total",
    "Total number of messages sent to Zalo",
    ["status"],  # success/failure
)

delivery_latency_seconds = Histogram(
    "delivery_latency_seconds",
    "Time from queue publish to delivery confirmation",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

# Dead-letter queue
dlq_depth = Gauge(
    "dlq_depth",
    "Current depth of the dead-letter queue",
    ["queue"],
)

# Queue depth gauges
queue_depth = Gauge(
    "queue_depth",
    "Current number of messages in a queue",
    ["queue", "worker"],
)

# Worker health
worker_up = Gauge(
    "worker_up",
    "Whether a worker is up (1) or down (0)",
    ["worker_type", "instance"],
)

# Token usage
token_usage_total = Counter(
    "token_usage_total",
    "Total tokens used",
    ["type"],  # input/output
)
