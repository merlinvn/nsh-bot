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

export interface Prompt {
  name: string;
  description: string | null;
  active_version: number;
}

export interface ZaloTokenStatus {
  has_token: boolean;
  expires_at: string | null;
  refreshed_at?: string;
}

export interface MonitoringHealth {
  database: string;
  redis: string;
  rabbitmq: string;
}

export interface MonitoringMetrics {
  total_conversations: number;
  total_messages: number;
  avg_latency_ms: number | null;
}

export interface MonitoringQueues {
  queues: {
    name: string;
    messages: number;
    consumers: number;
    state: string;
  }[];
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
  code_verifier: string | null;
  code_challenge: string | null;
  state?: string;
  oauth_url: string | null;
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
