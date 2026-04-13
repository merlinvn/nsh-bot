export interface AdminUser {
  username: string;
  is_active: boolean;
}

export interface LoginResponse {
  ok: boolean;
  user: AdminUser;
  csrf_token: string;
}

export interface Conversation {
  id: string;
  external_user_id: string;
  status: string;
  created_at: string;
}

export interface Message {
  id: string;
  direction: "inbound" | "outbound";
  text: string;
  error: string | null;
  model: string | null;
  latency_ms: number | null;
  prompt_version: string | null;
  token_usage: Record<string, number> | null;
  created_at: string;
  tool_calls: ToolCall[];
  delivery_attempts: DeliveryAttempt[];
}

export interface ToolCall {
  id: string;
  tool_name: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  success: boolean;
  error: string | null;
  latency_ms: number;
  created_at: string;
}

export interface DeliveryAttempt {
  id: string;
  attempt_no: number;
  status: string;
  response: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
}

export interface AnalyticsOverview {
  period: { start: string; end: string };
  total_messages: number;
  total_conversations: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  fallback_rate: number;
}

export interface PromptVersion {
  version: number;
  template: string;
  created_at: string;
  active: boolean;
}

export interface Prompt {
  name: string;
  description: string | null;
  active_version: number;
}

export interface ZaloTokenStatus {
  has_token: boolean;
  expires_at: string | null;
  refreshed_at?: string;
  oa_id?: string;
}

export interface MonitoringHealth {
  database: string;
  redis: string;
  rabbitmq: string;
}

export interface MonitoringHealthDetail {
  services: {
    name: string;
    status: "ok" | "degraded" | "error";
    latency_ms: number | null;
  }[];
}

export interface MonitoringMetrics {
  total_conversations: number;
  total_messages: number;
  avg_latency_ms: number | null;
}

export interface MonitoringMetricsTrend {
  current: {
    total_conversations: number;
    total_messages: number;
    avg_latency_ms: number | null;
  };
  previous: {
    total_conversations: number;
    total_messages: number;
    avg_latency_ms: number | null;
  };
}

export interface MonitoringWorkers {
  workers: {
    name: string;
    status: "alive" | "stale" | "dead";
    last_seen: number | null;
    age_seconds: number | null;
  }[];
}

export interface MonitoringQueues {
  queues: {
    name: string;
    messages: number;
    consumers: number;
    state: string;
    publish_rate: number;
    deliver_rate: number;
    oldest_message_age_ms: number | null;
  }[];
}

export interface QueuePeekMessages {
  messages: {
    routing_key: string;
    message_id: string;
    timestamp: number | null;
    payload: unknown;
  }[];
  error?: string;
}

export interface PlaygroundModels {
  anthropic: string[];
  "openai-compat": string[];
}

export interface BenchmarkResult {
  id: string;
  name: string;
  status: string;
  error: string | null;
  created_at: string;
}

export interface PkceResponse {
  oauth_url: string | null;
  callback_url?: string;
  error?: string;
}

export interface BenchmarkItem {
  id: string;
  model_provider: string;
  model_name: string;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  avg_input_tokens: number | null;
  avg_output_tokens: number | null;
}
