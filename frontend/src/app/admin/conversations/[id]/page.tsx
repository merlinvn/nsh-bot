"use client";
import React from "react";
import { useConversation } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { RotateCcw } from "lucide-react";

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
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Badge variant={msg.direction === "inbound" ? "default" : "secondary"}>
                    {msg.direction}
                  </Badge>
                  {msg.model && <span className="text-gray-400 text-xs">{msg.model}</span>}
                  {msg.latency_ms && (
                    <span className="text-gray-400 text-xs">{Math.round(msg.latency_ms)}ms</span>
                  )}
                  <span className="ml-auto text-xs text-gray-400">
                    {new Date(msg.created_at).toLocaleString()}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm">{msg.text}</p>
                {msg.error && (
                  <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-600">
                    Error: {msg.error}
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
