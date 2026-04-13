import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Conversation,
  Message,
  AnalyticsOverview,
  Prompt,
  ZaloTokenStatus,
  ZaloUser,
  MonitoringHealth,
  MonitoringHealthDetail,
  MonitoringMetrics,
  MonitoringMetricsTrend,
  MonitoringWorkers,
  MonitoringQueues,
  QueuePeekMessages,
  PlaygroundModels,
  BenchmarkResult,
  BenchmarkItem,
  PkceResponse,
} from "@/types/api";

// Conversations
export function useConversations(params?: Record<string, string>) {
  const queryStr = params ? "?" + new URLSearchParams(params).toString() : "";
  return useQuery<{ items: Conversation[]; total: number; page: number }>({
    queryKey: ["conversations", params],
    queryFn: () => api.get("/admin/conversations" + queryStr),
    refetchInterval: 30000,
  });
}

export function useConversation(id: string) {
  return useQuery<Conversation & { messages: Message[] }>({
    queryKey: ["conversation", id],
    queryFn: () => api.get(`/admin/conversations/${id}`),
    enabled: !!id,
  });
}

export function useConversationMessages(conversationId: string, pageSize = 20) {
  return useInfiniteQuery({
    queryKey: ["conversation-messages", conversationId],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => {
      const url = `/admin/conversations/${conversationId}/messages?limit=${pageSize}`;
      return api.get<{ messages: Message[]; has_more: boolean; next_before: string | null }>(
        pageParam ? `${url}&before=${encodeURIComponent(pageParam)}` : url
      );
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.next_before : undefined,
    maxPages: 100,
  });
}

export function useConversationStats() {
  return useQuery<{ total: number; active: number }>({
    queryKey: ["conversation-stats"],
    queryFn: () => api.get("/admin/conversations/stats"),
    refetchInterval: 30000,
  });
}

// Analytics
export function useAnalyticsOverview(start: string, end: string) {
  return useQuery<AnalyticsOverview>({
    queryKey: ["analytics", "overview", start, end],
    queryFn: () => api.get(`/admin/analytics/overview?start=${start}&end=${end}`),
    refetchInterval: 30000,
  });
}

export function useMessageVolume(start: string, end: string, interval = "day") {
  return useQuery<{ buckets: { date: string; count: number }[] }>({
    queryKey: ["analytics", "messages", start, end, interval],
    queryFn: () => api.get(`/admin/analytics/messages?start=${start}&end=${end}&interval=${interval}`),
    refetchInterval: 60000,
  });
}

export function useLatencyPercentiles(start: string, end: string) {
  return useQuery<{ p50: number | null; p95: number | null; p99: number | null }>({
    queryKey: ["analytics", "latency", start, end],
    queryFn: () => api.get(`/admin/analytics/latency?start=${start}&end=${end}`),
    refetchInterval: 60000,
  });
}

export function useToolUsage(start: string, end: string) {
  return useQuery<{ tools: { name: string; count: number }[] }>({
    queryKey: ["analytics", "tools", start, end],
    queryFn: () => api.get(`/admin/analytics/tools?start=${start}&end=${end}`),
    refetchInterval: 60000,
  });
}

export function useFallbackRates(start: string, end: string) {
  return useQuery<{ total: number; errors: number; rate: number }>({
    queryKey: ["analytics", "fallbacks", start, end],
    queryFn: () => api.get(`/admin/analytics/fallbacks?start=${start}&end=${end}`),
    refetchInterval: 60000,
  });
}

export function useTokenUsage(start: string, end: string) {
  return useQuery<{ total_input_tokens: number; total_output_tokens: number; message_count: number }>({
    queryKey: ["analytics", "tokens", start, end],
    queryFn: () => api.get(`/admin/analytics/tokens?start=${start}&end=${end}`),
    refetchInterval: 60000,
  });
}

// Prompts
export function usePrompts() {
  return useQuery<Prompt[]>({
    queryKey: ["prompts"],
    queryFn: () => api.get<Prompt[]>("/admin/prompts"),
    refetchInterval: 60000,
  });
}

export function usePrompt(name: string) {
  return useQuery<Prompt>({
    queryKey: ["prompt", name],
    queryFn: () => api.get(`/admin/prompts/${name}`),
    enabled: !!name,
  });
}

export function useCreatePrompt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string; template: string }) =>
      api.post("/admin/prompts", body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["prompts"] }),
  });
}

export function useUpdatePrompt(name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { template: string; description?: string }) =>
      api.put(`/admin/prompts/${name}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      queryClient.invalidateQueries({ queryKey: ["prompt", name] });
    },
  });
}

export function useDeletePrompt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.delete(`/admin/prompts/${name}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["prompts"] }),
  });
}

export function useActivatePromptVersion(name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (version: number) => api.post(`/admin/prompts/${name}/activate`, { version }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      queryClient.invalidateQueries({ queryKey: ["prompt", name] });
      queryClient.invalidateQueries({ queryKey: ["prompt-versions", name] });
    },
  });
}

export function useCreatePromptVersion(name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { template?: string }) =>
      api.post(`/admin/prompts/${name}/versions`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      queryClient.invalidateQueries({ queryKey: ["prompt", name] });
      queryClient.invalidateQueries({ queryKey: ["prompt-versions", name] });
    },
  });
}

// Playground
export function usePlaygroundModels() {
  return useQuery<PlaygroundModels>({
    queryKey: ["playground-models"],
    queryFn: () => api.get("/admin/playground/models"),
    refetchInterval: 300000,
  });
}

export function usePlaygroundComplete() {
  return useMutation({
    mutationFn: (body: {
      model_provider: string;
      model_name: string;
      system_prompt: string;
      messages: { role: string; content: string }[];
      temperature?: number;
      max_tokens?: number;
    }) => api.post<{ content: string; usage?: unknown; latency_ms?: number }>("/admin/playground/complete", body),
  });
}

export function usePlaygroundChat() {
  return useMutation({
    mutationFn: (body: {
      system_prompt: string;
      messages: { role: string; content: string }[];
      user_message: string;
      temperature?: number;
    }) => api.post<{ content: string; usage?: unknown; latency_ms?: number; tool_calls?: { id: string; name: string; input: Record<string, unknown>; output: Record<string, unknown>; success: boolean; latency_ms: number }[] }>("/admin/playground/chat", body),
  });
}

export function useRunBenchmark() {
  return useMutation({
    mutationFn: (body: {
      name: string;
      test_prompts: { name: string; messages: { role: string; content: string }[] }[];
      models: { provider: string; name: string }[];
      iterations: number;
    }) => api.post<BenchmarkResult>("/admin/playground/benchmark", body),
  });
}

export function useBenchmark(id: string) {
  return useQuery<BenchmarkResult>({
    queryKey: ["benchmark", id],
    queryFn: () => api.get(`/admin/playground/benchmark/${id}`),
    enabled: !!id,
    refetchInterval: 5000,
  });
}

export function useBenchmarkResults(id: string) {
  return useQuery<BenchmarkItem[]>({
    queryKey: ["benchmark-results", id],
    queryFn: () => api.get(`/admin/playground/benchmark/${id}/results`),
    enabled: !!id,
  });
}

// Tokens
export function useZaloTokenStatus() {
  return useQuery<ZaloTokenStatus>({
    queryKey: ["zalo-token-status"],
    queryFn: () => api.get("/admin/zalo-tokens/status"),
    refetchInterval: 30000,
  });
}

export function useRefreshToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/admin/zalo-tokens/refresh"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["zalo-token-status"] }),
  });
}

export function useInitiatePkce() {
  return useMutation({
    mutationFn: () => api.post<PkceResponse>("/admin/zalo-tokens/pkce"),
  });
}

export function useRevokeToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete("/admin/zalo-tokens"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["zalo-token-status"] }),
  });
}

// Zalo Users
export function useZaloUsers() {
  return useQuery<ZaloUser[]>({
    queryKey: ["zalo-users"],
    queryFn: () => api.get("/admin/zalo-users"),
    refetchInterval: 60000,
  });
}

export function useZaloUser(userId: string) {
  return useQuery<ZaloUser>({
    queryKey: ["zalo-user", userId],
    queryFn: () => api.get(`/admin/zalo-users/${userId}`),
    enabled: !!userId,
  });
}

// Monitoring
export function useMonitoringHealth(options?: { enabled?: boolean }) {
  return useQuery<MonitoringHealth>({
    queryKey: ["monitoring-health"],
    queryFn: () => api.get("/admin/monitoring/health"),
    refetchInterval: 10000,
    ...options,
  });
}

export function useMonitoringHealthDetail(options?: { enabled?: boolean }) {
  return useQuery<MonitoringHealthDetail>({
    queryKey: ["monitoring-health-detail"],
    queryFn: () => api.get("/admin/monitoring/health-detail"),
    refetchInterval: 10000,
    ...options,
  });
}

export function useMonitoringMetrics(options?: { enabled?: boolean }) {
  return useQuery<MonitoringMetrics>({
    queryKey: ["monitoring-metrics"],
    queryFn: () => api.get("/admin/monitoring/metrics"),
    refetchInterval: 30000,
    ...options,
  });
}

export function useMonitoringMetricsTrend(options?: { enabled?: boolean }) {
  return useQuery<MonitoringMetricsTrend>({
    queryKey: ["monitoring-metrics-trend"],
    queryFn: () => api.get("/admin/monitoring/metrics-trend"),
    refetchInterval: 10000,
    ...options,
  });
}

export function useMonitoringWorkers(options?: { enabled?: boolean }) {
  return useQuery<MonitoringWorkers>({
    queryKey: ["monitoring-workers"],
    queryFn: () => api.get("/admin/monitoring/workers"),
    refetchInterval: 10000,
    ...options,
  });
}

export function useMonitoringQueues(options?: { enabled?: boolean }) {
  return useQuery<MonitoringQueues>({
    queryKey: ["monitoring-queues"],
    queryFn: () => api.get("/admin/monitoring/queues"),
    refetchInterval: 15000,
    ...options,
  });
}

export function useQueuePeek(vhost: string, queueName: string, count = 10) {
  return useQuery<QueuePeekMessages>({
    queryKey: ["queue-peek", vhost, queueName, count],
    queryFn: () =>
      api.get(`/admin/monitoring/queues/${encodeURIComponent(vhost)}/${encodeURIComponent(queueName)}/messages?count=${count}`),
    enabled: !!vhost && !!queueName,
    refetchInterval: 5000,
  });
}

// Evaluations
export interface EvaluationTestCase {
  id: string;
  question: string;
  expected_answer: string;
  actual_answer: string | null;
  passed: boolean | null;
  judgment: string | null;
  latency_ms: number | null;
  error: string | null;
}

export interface Evaluation {
  id: string;
  name: string;
  prompt_name: string;
  status: string;
  total: number | null;
  passed: number | null;
  failed: number | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  test_cases: EvaluationTestCase[];
}

export function useEvaluations() {
  return useQuery<Evaluation[]>({
    queryKey: ["evaluations"],
    queryFn: () => api.get("/admin/evaluations"),
    refetchInterval: 30000,
  });
}

export function useEvaluation(id: string) {
  return useQuery<Evaluation>({
    queryKey: ["evaluation", id],
    queryFn: () => api.get(`/admin/evaluations/${id}`),
    enabled: !!id,
  });
}

export function useCreateEvaluation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; prompt_name: string; test_cases: { question: string; expected_answer: string }[] }) =>
      api.post<{ id: string; name: string; status: string }>("/admin/evaluations", body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["evaluations"] }),
  });
}

export function useDeleteEvaluation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<{ ok: boolean }>(`/admin/evaluations/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["evaluations"] }),
  });
}

export function useAddEvaluationTestCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ evaluationId, body }: { evaluationId: string; body: { question: string; expected_answer: string } }) =>
      api.post<{ id: string }>(`/admin/evaluations/${evaluationId}/test-cases`, body),
    onSuccess: (_data, vars) => queryClient.invalidateQueries({ queryKey: ["evaluation", vars.evaluationId] }),
  });
}

export function useDeleteEvaluationTestCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ evaluationId, tcId }: { evaluationId: string; tcId: string }) =>
      api.delete<{ ok: boolean }>(`/admin/evaluations/${evaluationId}/test-cases/${tcId}`),
    onSuccess: (_data, vars) => queryClient.invalidateQueries({ queryKey: ["evaluation", vars.evaluationId] }),
  });
}

export function useRunEvaluation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (evaluationId: string) =>
      api.post<{ id: string; status: string; total: number | null; passed: number | null; failed: number | null; error: string | null }>(`/admin/evaluations/${evaluationId}/run`, {}),
    onSuccess: (_data, vars) => queryClient.invalidateQueries({ queryKey: ["evaluation", vars] }),
  });
}
