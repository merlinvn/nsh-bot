"use client";
import { useState } from "react";
import { usePlaygroundComplete, usePlaygroundModels } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function PlaygroundPage() {
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState("claude-sonnet-4-20250514");
  const [systemPrompt, setSystemPrompt] = useState("You are a helpful assistant.");
  const [messages, setMessages] = useState("");
  const [response, setResponse] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const { data: models } = usePlaygroundModels();

  const completeMutation = usePlaygroundComplete();

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
      setResponse(`Error: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">LLM Playground</h1>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Complete</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Provider</Label>
                  <Select value={provider} onValueChange={handleProviderChange}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="anthropic">Anthropic</SelectItem>
                      <SelectItem value="openai-compat">OpenAI Compatible</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
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
              <div>
                <Label>System Prompt</Label>
                <Textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={3} />
              </div>
              <div>
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
    </div>
  );
}
