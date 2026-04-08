"use client";
import { useState } from "react";
import { usePlaygroundComplete, usePlaygroundModels, useRunBenchmark, useBenchmark, useBenchmarkResults } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function PlaygroundPage() {
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState("claude-sonnet-4-20250514");
  const [systemPrompt, setSystemPrompt] = useState("You are a helpful assistant.");
  const [messages, setMessages] = useState("");
  const [response, setResponse] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // Benchmark state
  const [benchmarkName, setBenchmarkName] = useState("my-benchmark");
  const [benchmarkIterations, setBenchmarkIterations] = useState(5);
  const [benchmarkBenchmarkId, setBenchmarkBenchmarkId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: models } = usePlaygroundModels();
  const completeMutation = usePlaygroundComplete();
  const runBenchmarkMutation = useRunBenchmark();

  const { data: benchmark, isLoading: benchmarkLoading } = useBenchmark(benchmarkBenchmarkId ?? "");
  const { data: benchmarkResults, isLoading: resultsLoading } = useBenchmarkResults(benchmarkBenchmarkId ?? "");

  const handleProviderChange = (p: string | null) => {
    if (!p) return;
    setProvider(p);
    if (models) {
      const defaultModel = models[p as keyof typeof models]?.[0] || "";
      setModel(defaultModel);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!messages.trim()) return;
    setIsLoading(true);
    setResponse("");
    try {
      const result = await completeMutation.mutateAsync({
        model_provider: provider,
        model_name: model,
        system_prompt: systemPrompt,
        messages: [{ role: "user", content: messages }],
      });
      setResponse(result.content);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setResponse(`Error: ${msg}`);
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRunBenchmark = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const result = await runBenchmarkMutation.mutateAsync({
        name: benchmarkName,
        test_prompts: [
          { name: "greeting", messages: [{ role: "user", content: "Say hello briefly" }] },
          { name: "question", messages: [{ role: "user", content: "What is 2+2?" }] },
        ],
        models: [
          { provider: "anthropic", name: "claude-sonnet-4-20250514" },
          { provider: "openai-compat", name: "llama3.2" },
        ],
        iterations: benchmarkIterations,
      });
      setBenchmarkBenchmarkId(result.id);
      queryClient.invalidateQueries({ queryKey: ["benchmark", result.id] });
      toast.success("Benchmark started");
    } catch {
      toast.error("Failed to start benchmark");
    }
  };

  const handleClearBenchmark = () => {
    setBenchmarkBenchmarkId(null);
    setResponse("");
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">LLM Playground</h1>

      {/* Single Completion */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Complete</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <Label>Provider</Label>
                  <Select value={provider} onValueChange={handleProviderChange}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="anthropic">Anthropic</SelectItem>
                      <SelectItem value="openai-compat">OpenAI Compatible</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label>Model</Label>
                  <Input
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    list="model-list"
                  />
                  <datalist id="model-list">
                    {models?.[provider as keyof typeof models]?.map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                </div>
              </div>
              <div className="space-y-1">
                <Label>System Prompt</Label>
                <Textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={3} />
              </div>
              <div className="space-y-1">
                <Label>User Message</Label>
                <Textarea
                  value={messages}
                  onChange={(e) => setMessages(e.target.value)}
                  rows={4}
                  placeholder="Say hello in 5 words or less"
                />
              </div>
              <Button type="submit" disabled={isLoading || !messages.trim()}>
                {isLoading ? "Generating..." : "Generate"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Response</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm">{response || "Response will appear here"}</pre>
          </CardContent>
        </Card>
      </div>

      {/* Benchmark */}
      <Card>
        <CardHeader>
          <CardTitle>Benchmark</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {benchmarkBenchmarkId ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <StatusBadge status={benchmark?.status ?? "pending"} />
                <span className="text-sm text-gray-500">{benchmark?.name}</span>
                {benchmark?.status !== "completed" && benchmark?.status !== "failed" && (
                  <button
                    onClick={() => queryClient.invalidateQueries({ queryKey: ["benchmark", benchmarkBenchmarkId] })}
                    className="ml-auto text-gray-400 hover:text-gray-600"
                    title="Refresh"
                  >
                    <RefreshCw className="h-4 w-4" />
                  </button>
                )}
                <button onClick={handleClearBenchmark} className="text-gray-400 hover:text-red-500" title="Clear">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              {benchmark?.error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
                  {benchmark.error}
                </div>
              )}

              {benchmark?.status === "completed" && benchmarkResults && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left">
                        <th className="py-2 pr-4 font-medium">Provider</th>
                        <th className="py-2 pr-4 font-medium">Model</th>
                        <th className="py-2 pr-4 font-medium text-right">Avg Latency</th>
                        <th className="py-2 pr-4 font-medium text-right">P95 Latency</th>
                        <th className="py-2 pr-4 font-medium text-right">Avg Input Tokens</th>
                        <th className="py-2 font-medium text-right">Avg Output Tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {benchmarkResults.map((item) => (
                        <tr key={item.id} className="border-b last:border-0">
                          <td className="py-2 pr-4">{item.model_provider}</td>
                          <td className="py-2 pr-4 font-mono text-xs">{item.model_name}</td>
                          <td className="py-2 pr-4 text-right">
                            {item.avg_latency_ms != null ? `${Math.round(item.avg_latency_ms)}ms` : "—"}
                          </td>
                          <td className="py-2 pr-4 text-right">
                            {item.p95_latency_ms != null ? `${Math.round(item.p95_latency_ms)}ms` : "—"}
                          </td>
                          <td className="py-2 pr-4 text-right">
                            {item.avg_input_tokens ?? "—"}
                          </td>
                          <td className="py-2 text-right">
                            {item.avg_output_tokens ?? "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <form onSubmit={handleRunBenchmark} className="grid grid-cols-3 gap-4 items-end">
              <div className="space-y-1">
                <Label>Benchmark Name</Label>
                <Input
                  value={benchmarkName}
                  onChange={(e) => setBenchmarkName(e.target.value)}
                  placeholder="my-benchmark"
                />
              </div>
              <div className="space-y-1">
                <Label>Iterations</Label>
                <Input
                  type="number"
                  value={benchmarkIterations}
                  onChange={(e) => setBenchmarkIterations(Number(e.target.value))}
                  min={1}
                  max={50}
                />
              </div>
              <Button type="submit" disabled={runBenchmarkMutation.isPending}>
                {runBenchmarkMutation.isPending ? "Starting..." : "Run Benchmark"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
