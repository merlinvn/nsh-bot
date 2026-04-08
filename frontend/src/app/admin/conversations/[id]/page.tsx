"use client";
import React from "react";
import { useConversation } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function ConversationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = React.use(params);
  const { data, isLoading } = useConversation(id);

  if (isLoading) return <div>Loading...</div>;
  if (!data) return <div>Conversation not found</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Conversation {data.id.slice(0, 8)}</h1>
        <Badge>{data.status}</Badge>
      </div>
      <div className="space-y-4">
        {data.messages.map((msg) => (
          <Card key={msg.id}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Badge variant={msg.direction === "inbound" ? "default" : "secondary"}>
                  {msg.direction}
                </Badge>
                {msg.model && <span className="text-gray-400 text-xs">{msg.model}</span>}
                {msg.latency_ms && <span className="text-gray-400 text-xs">{Math.round(msg.latency_ms)}ms</span>}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap">{msg.text}</p>
              {msg.error && <p className="mt-2 text-sm text-red-500">Error: {msg.error}</p>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
