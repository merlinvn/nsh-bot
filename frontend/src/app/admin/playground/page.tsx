"use client";
import { useState, useEffect } from "react";
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
  const [isGenerating, setIsGenerating] = useState(false);

  const { data: prompts, isLoading: promptsLoading } = usePrompts();
  const { data: promptDetail, isLoading: promptDetailLoading } = usePrompt(selectedPromptName);
  const chatMutation = usePlaygroundChat();

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
      setSystemPrompt(promptDetail.template || "");
    }
  }, [selectedVersion, promptDetail, selectedPromptName]);

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
              <CardContent className="space-y-3 max-h-64 overflow-y-auto">
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

          {/* Response */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Phản hồi</CardTitle>
                {latencyMs !== null && (
                  <span className="text-xs text-gray-400">{Math.round(latencyMs)}ms</span>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {isGenerating ? (
                <div className="flex items-center gap-2 text-gray-400">
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  <span className="text-sm">Đang xử lý...</span>
                </div>
              ) : response ? (
                <pre className="whitespace-pre-wrap text-sm">{response}</pre>
              ) : (
                <p className="text-gray-400 text-sm">Phản hồi sẽ xuất hiện ở đây</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
