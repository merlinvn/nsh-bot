"use client";
import React from "react";
import { useConversation } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { RotateCcw, CheckCircle, XCircle, Clock, Wrench } from "lucide-react";

function ToolCallRow({ tc }: { tc: { tool_name: string; input: Record<string, unknown>; output: Record<string, unknown>; success: boolean; error: string | null; latency_ms: number; created_at: string } }) {
  return (
    <div className="pl-4 border-l-2 border-gray-200 my-2">
      <div className="flex items-center gap-2">
        <Wrench className="size-3 text-gray-400" />
        <span className="font-medium text-sm">{tc.tool_name}</span>
        {tc.success ? (
          <CheckCircle className="size-3 text-green-500" />
        ) : (
          <XCircle className="size-3 text-red-500" />
        )}
        <span className="text-xs text-gray-400">{tc.latency_ms}ms</span>
      </div>
      {tc.error && (
        <div className="mt-1 text-xs text-red-600 bg-red-50 border border-red-200 rounded p-1.5">{tc.error}</div>
      )}
    </div>
  );
}

function DeliveryAttemptRow({ da }: { da: { attempt_no: number; status: string; response: Record<string, unknown> | null; error: string | null; created_at: string } }) {
  return (
    <div className="pl-4 border-l-2 border-orange-200 my-2">
      <div className="flex items-center gap-2">
        {da.status === "delivered" ? (
          <CheckCircle className="size-3 text-green-500" />
        ) : da.status === "failed" ? (
          <XCircle className="size-3 text-red-500" />
        ) : (
          <Clock className="size-3 text-yellow-500" />
        )}
        <span className="text-sm font-medium">Attempt {da.attempt_no}</span>
        <Badge variant={da.status === "delivered" ? "default" : da.status === "failed" ? "destructive" : "secondary"} className="text-xs">
          {da.status}
        </Badge>
        {da.error && (
          <span className="text-xs text-red-600">{da.error}</span>
        )}
      </div>
    </div>
  );
}

export default function ConversationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = React.use(params);
  const { data, isLoading, isError } = useConversation(id);
  const queryClient = useQueryClient();

  const replayMutation = useMutation({
    mutationFn: () => api.post(`/admin/conversations/${id}/replay`),
    onSuccess: () => {
      toast.success("Replay queued. Check back for results.");
      queryClient.invalidateQueries({ queryKey: ["conversation", id] });
    },
    onError: (err: unknown) => {
      toast.error(`Replay failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-32 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Conversation</h1>
        <div className="p-8 text-center text-red-500">Conversation not found or failed to load.</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Conversation {data.id.slice(0, 8)}</h1>
          <Badge>{data.status}</Badge>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => replayMutation.mutate()}
          disabled={replayMutation.isPending}
        >
          <RotateCcw className="mr-2 h-4 w-4" />
          {replayMutation.isPending ? "Replaying..." : "Replay Last Message"}
        </Button>
      </div>

      <div className="space-y-4">
        {data.messages.length === 0 ? (
          <div className="p-8 text-center text-gray-400">No messages in this conversation.</div>
        ) : (
          data.messages.map((msg) => (
            <Card key={msg.id}>
              <CardHeader className="pb-2">
                <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge variant={msg.direction === "inbound" ? "default" : "secondary"}>
                    {msg.direction}
                  </Badge>
                  {msg.model && <span className="text-gray-400 text-xs">{msg.model}</span>}
                  {msg.prompt_version && <span className="text-gray-400 text-xs">v{msg.prompt_version}</span>}
                  {msg.latency_ms && (
                    <span className="text-gray-400 text-xs">{Math.round(msg.latency_ms)}ms</span>
                  )}
                  {msg.token_usage && (
                    <span className="text-gray-400 text-xs">
                      {msg.token_usage.input_tokens + msg.token_usage.output_tokens}tokens
                    </span>
                  )}
                  <span className="ml-auto text-xs text-gray-400">
                    {new Date(msg.created_at).toLocaleString()}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="whitespace-pre-wrap text-sm">{msg.text}</p>
                {msg.error && (
                  <div className="p-2 bg-red-50 border border-red-200 rounded text-sm text-red-600">
                    Error: {msg.error}
                  </div>
                )}

                {msg.tool_calls.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-gray-500 mb-1">TOOL CALLS</p>
                    {msg.tool_calls.map((tc) => (
                      <ToolCallRow key={tc.id} tc={tc} />
                    ))}
                  </div>
                )}

                {msg.delivery_attempts.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-gray-500 mb-1">DELIVERY</p>
                    {msg.delivery_attempts.map((da) => (
                      <DeliveryAttemptRow key={da.id} da={da} />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
