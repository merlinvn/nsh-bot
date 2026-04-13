"use client";
import { useState, useEffect, useRef } from "react";
import { usePrompts, usePrompt, usePlaygroundChat } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { RefreshCw, Send, Trash2 } from "lucide-react";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export default function PlaygroundPage() {
  const [selectedPromptName, setSelectedPromptName] = useState<string>("");
  const [selectedVersion, setSelectedVersion] = useState<string>("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [userMessage, setUserMessage] = useState("");
  const [response, setResponse] = useState<string>("");
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [tokenUsage, setTokenUsage] = useState<{ input_tokens: number; output_tokens: number } | null>(null);
  const [toolCalls, setToolCalls] = useState<{ id: string; name: string; input: Record<string, unknown>; output: Record<string, unknown>; success: boolean; latency_ms: number }[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);

  const { data: prompts, isLoading: promptsLoading } = usePrompts();
  const { data: promptDetail, isLoading: promptDetailLoading } = usePrompt(selectedPromptName);
  const chatMutation = usePlaygroundChat();
  const chatHistoryRef = useRef<HTMLDivElement>(null);

  // When prompt changes, load active version's template
  useEffect(() => {
    if (promptDetail?.versions && promptDetail.versions.length > 0) {
      const activeVer = promptDetail.versions.find(
        (v: { version: number }) => v.version === promptDetail.active_version
      );
      if (activeVer) {
        setSelectedVersion(String(activeVer.version));
      } else {
        // Fallback to latest version
        const latest = promptDetail.versions.sort(
          (a: { version: number }, b: { version: number }) => b.version - a.version
        )[0];
        setSelectedVersion(String(latest.version));
      }
    }
  }, [promptDetail]);

  // Load template when version changes
  useEffect(() => {
    // Use default prompt when none available
    if (selectedPromptName === "__default__") {
      setSystemPrompt("Bạn là một trợ lý AI hữu ích. Trả lời ngắn gọn và lịch sự.");
      return;
    }
    if (!promptDetail?.versions || !selectedVersion) return;
    const ver = promptDetail.versions.find(
      (v: { version: number }) => v.version === Number(selectedVersion)
    );
    if (ver) {
      setSystemPrompt(ver.template || promptDetail.template || "");
    }
  }, [selectedVersion, promptDetail, selectedPromptName]);

  // Auto-scroll chat history to bottom when new message arrives
  useEffect(() => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
    }
  }, [chatHistory]);

  // Auto-select first prompt, or use default if none exist
  useEffect(() => {
    if (promptsLoading) return;
    if (prompts && prompts.length > 0 && !selectedPromptName) {
      setSelectedPromptName(prompts[0].name);
    } else if (prompts && prompts.length === 0 && !selectedPromptName) {
      setSelectedPromptName("__default__");
    }
  }, [prompts, promptsLoading, selectedPromptName]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userMessage.trim() || !systemPrompt.trim()) return;

    setIsGenerating(true);
    setResponse("");

    const userMsg = userMessage.trim();
    setUserMessage("");

    // Add user message to history
    setChatHistory((prev) => [...prev, { role: "user", content: userMsg }]);

    try {
      const result = await chatMutation.mutateAsync({
        system_prompt: systemPrompt,
        messages: chatHistory,
        user_message: userMsg,
      });
      setResponse(result.content);
      setLatencyMs(result.latency_ms ?? null);
      if (result.usage) {
        setTokenUsage(result.usage as { input_tokens: number; output_tokens: number });
      }
      setToolCalls(result.tool_calls || []);
      setChatHistory((prev) => [...prev, { role: "assistant", content: result.content }]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setResponse(`Lỗi: ${msg}`);
      toast.error(msg);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleClear = () => {
    setChatHistory([]);
    setResponse("");
    setLatencyMs(null);
    setTokenUsage(null);
    setToolCalls([]);
    setUserMessage("");
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Playground</h1>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left: Config + Input */}
        <Card>
          <CardHeader>
            <CardTitle>Cấu hình</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Prompt selector */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label>Prompt</Label>
                {promptsLoading ? (
                  <div className="h-9 bg-gray-100 rounded animate-pulse" />
                ) : prompts && prompts.length === 0 ? (
                  <div className="h-9 flex items-center text-sm text-gray-500 border rounded px-3">
                    Mặc định
                  </div>
                ) : (
                  <Select value={selectedPromptName} onValueChange={(v) => v && setSelectedPromptName(v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Chọn prompt" />
                    </SelectTrigger>
                    <SelectContent>
                      {prompts?.map((p) => (
                        <SelectItem key={p.name} value={p.name}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>

              <div className="space-y-1">
                <Label>Phiên bản</Label>
                {selectedPromptName === "__default__" ? (
                  <div className="h-9 flex items-center text-sm text-gray-500 border rounded px-3">
                    Mặc định
                  </div>
                ) : promptDetailLoading ? (
                  <div className="h-9 bg-gray-100 rounded animate-pulse" />
                ) : (
                  <Select value={selectedVersion} onValueChange={(v) => v && setSelectedVersion(v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Chọn phiên bản" />
                    </SelectTrigger>
                    <SelectContent>
                      {promptDetail?.versions
                        ?.slice()
                        .sort((a: { version: number }, b: { version: number }) => b.version - a.version)
                        .map((v: { version: number; created_at: string }) => (
                          <SelectItem key={v.version} value={String(v.version)}>
                            v{v.version} — {new Date(v.created_at).toLocaleDateString("vi-VN")}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>

            {/* System prompt */}
            <div className="space-y-1">
              <Label>System Prompt</Label>
              <Textarea
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                rows={8}
                placeholder="System prompt sẽ được tải từ prompt đã chọn..."
                className="font-mono text-sm"
              />
            </div>

            {/* User message */}
            <div className="space-y-1">
              <Label>Tin nhắn mới</Label>
              <Textarea
                value={userMessage}
                onChange={(e) => setUserMessage(e.target.value)}
                rows={3}
                placeholder="Nhập tin nhắn để test..."
              />
            </div>

            <div className="flex gap-2">
              <Button
                type="submit"
                disabled={isGenerating || !userMessage.trim() || !systemPrompt.trim()}
                onClick={handleSubmit}
              >
                {isGenerating ? (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                    Đang xử lý...
                  </>
                ) : (
                  <>
                    <Send className="mr-2 h-4 w-4" />
                    Gửi
                  </>
                )}
              </Button>
              <Button variant="outline" onClick={handleClear} disabled={isGenerating}>
                <Trash2 className="mr-2 h-4 w-4" />
                Xóa lịch sử
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Right: Chat history + Response */}
        <div className="space-y-4">
          {/* Chat history */}
          {chatHistory.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Lịch sử trò chuyện</CardTitle>
              </CardHeader>
              <CardContent ref={chatHistoryRef} className="space-y-3 max-h-64 overflow-y-auto">
                {chatHistory.map((msg, i) => (
                  <div
                    key={i}
                    className={`rounded-lg p-3 text-sm ${
                      msg.role === "user"
                        ? "bg-primary/10 ml-8"
                        : "bg-gray-50 mr-8 border"
                    }`}
                  >
                    <div className="text-xs font-medium text-gray-400 mb-1">
                      {msg.role === "user" ? "Bạn" : "Assistant"}
                    </div>
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Response info */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Thông tin</CardTitle>
            </CardHeader>
            <CardContent className="max-h-[70vh] overflow-y-auto">
              {isGenerating ? (
                <div className="flex items-center gap-2 text-gray-400">
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  <span className="text-sm">Đang xử lý...</span>
                </div>
              ) : latencyMs !== null || tokenUsage ? (
                <div className="space-y-2 text-sm">
                  {latencyMs !== null && (
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500 w-28 shrink-0">Latency:</span>
                      <span className="font-medium">{Math.round(latencyMs)}ms</span>
                    </div>
                  )}
                  {tokenUsage && (
                    <>
                      <div className="flex items-center gap-2">
                        <span className="text-gray-500 w-28 shrink-0">Input tokens:</span>
                        <span className="font-medium">{tokenUsage.input_tokens.toLocaleString()}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-gray-500 w-28 shrink-0">Output tokens:</span>
                        <span className="font-medium">{tokenUsage.output_tokens.toLocaleString()}</span>
                      </div>
                    </>
                  )}
                  {toolCalls.length > 0 && (
                    <div className="mt-3 pt-3 border-t space-y-2">
                      <div className="text-xs font-medium text-orange-600">Tool Calls ({toolCalls.length})</div>
                      {toolCalls.map((tc, i) => (
                        <div key={i} className={`border rounded p-2 text-xs ${tc.success ? "bg-orange-50 border-orange-200" : "bg-red-50 border-red-200"}`}>
                          <div className="flex items-center justify-between gap-2">
                            <span className={`font-medium truncate ${tc.success ? "text-orange-700" : "text-red-700"}`}>{tc.name}</span>
                            <span className="text-gray-400 text-xs shrink-0">{tc.latency_ms}ms</span>
                          </div>
                          <div className="mt-1">
                            <span className="text-gray-500">In: </span>
                            <pre className="text-orange-700 text-xs whitespace-pre-wrap overflow-y-auto max-h-24">{JSON.stringify(tc.input)}</pre>
                          </div>
                          <div className="mt-1">
                            <span className="text-gray-500">Out: </span>
                            {tc.success ? (
                              <pre className="text-green-700 text-xs whitespace-pre-wrap overflow-y-auto max-h-24">{JSON.stringify(tc.output)}</pre>
                            ) : (
                              <span className="text-red-600 text-xs">{JSON.stringify(tc.output)}</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-gray-400 text-sm">Gửi tin nhắn để xem thông tin</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
