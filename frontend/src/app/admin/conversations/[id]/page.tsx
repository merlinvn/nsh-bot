"use client";
import React, { useRef, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  RotateCcw, CheckCircle, XCircle, Clock, Wrench,
  ChevronDown, ChevronRight, ArrowDown, Loader2,
  ChevronsUpDown,
} from "lucide-react";
import type { Message, ToolCall, DeliveryAttempt } from "@/types/api";

function ToolCallRow({ tc }: { tc: ToolCall }) {
  return (
    <div className="pl-4 border-l-2 border-gray-200 my-2">
      <div className="flex items-center gap-2">
        <Wrench className="size-3 text-gray-400" />
        <span className="font-medium text-sm">{tc.tool_name}</span>
        {tc.success
          ? <CheckCircle className="size-3 text-green-500" />
          : <XCircle className="size-3 text-red-500" />}
        <span className="text-xs text-gray-400">{tc.latency_ms}ms</span>
      </div>
      {tc.error && (
        <div className="mt-1 text-xs text-red-600 bg-red-50 border border-red-200 rounded p-1.5">{tc.error}</div>
      )}
    </div>
  );
}

function DeliveryAttemptRow({ da }: { da: DeliveryAttempt }) {
  return (
    <div className="pl-4 border-l-2 border-orange-200 my-2">
      <div className="flex items-center gap-2">
        {da.status === "delivered"
          ? <CheckCircle className="size-3 text-green-500" />
          : da.status === "failed"
          ? <XCircle className="size-3 text-red-500" />
          : <Clock className="size-3 text-yellow-500" />}
        <span className="text-sm font-medium">Attempt {da.attempt_no}</span>
        <Badge
          variant={da.status === "delivered" ? "default" : da.status === "failed" ? "destructive" : "secondary"}
          className="text-xs"
        >
          {da.status}
        </Badge>
        {da.error && <span className="text-xs text-red-600">{da.error}</span>}
      </div>
    </div>
  );
}

function MessageRow({
  msg,
  isExpanded,
  onToggle,
}: {
  msg: Message;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const hasDetails = msg.tool_calls.length > 0 || msg.delivery_attempts.length > 0 || !!msg.error;
  const hasError = !!msg.error;

  return (
    <div className="border rounded-lg bg-white">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
        disabled={!hasDetails}
      >
        <span className="text-gray-300 shrink-0">
          {hasDetails ? (isExpanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />) : null}
        </span>
        <Badge variant={msg.direction === "inbound" ? "default" : "secondary"} className="shrink-0">
          {msg.direction === "inbound" ? "IN" : "OUT"}
        </Badge>
        <span className={`flex-1 text-sm truncate ${hasError ? "text-red-600" : "text-gray-700"}`}>
          {msg.text}
        </span>
        {msg.latency_ms && (
          <span className="text-xs text-gray-400 shrink-0">{Math.round(msg.latency_ms)}ms</span>
        )}
        {hasError && <XCircle className="size-3 text-red-500 shrink-0" />}
        <span className="text-xs text-gray-400 shrink-0">
          {new Date(msg.created_at).toLocaleTimeString()}
        </span>
      </button>

      {isExpanded && hasDetails && (
        <div className="px-4 pb-4 border-t">
          <p className="whitespace-pre-wrap text-sm mt-3">{msg.text}</p>
          {msg.error && (
            <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-600">
              Error: {msg.error}
            </div>
          )}

          {msg.tool_calls.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mt-3 mb-1">TOOL CALLS</p>
              {msg.tool_calls.map((tc) => <ToolCallRow key={tc.id} tc={tc} />)}
            </div>
          )}

          {msg.delivery_attempts.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mt-3 mb-1">DELIVERY</p>
              {msg.delivery_attempts.map((da) => <DeliveryAttemptRow key={da.id} da={da} />)}
            </div>
          )}
        </div>
      )}

      {!isExpanded && hasDetails && (
        <div className="px-4 pb-3 flex items-center gap-4">
          {msg.tool_calls.length > 0 && (
            <span className="text-xs text-gray-400 flex items-center gap-1">
              <Wrench className="size-3" /> {msg.tool_calls.length}
            </span>
          )}
          {msg.delivery_attempts.length > 0 && (
            <span className="text-xs text-gray-400 flex items-center gap-1">
              <Clock className="size-3" /> {msg.delivery_attempts.length}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

const PAGE_SIZE = 20;

export default function ConversationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = React.use(params);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [allExpanded, setAllExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const initialized = useRef(false);

  // Initial load - only runs once per conversation
  React.useEffect(() => {
    if (!id || initialized.current) return;
    initialized.current = true;
    setIsInitialLoading(true);

    api.get<{ messages: Message[]; has_more: boolean; next_before: string | null }>(
      `/admin/conversations/${id}/messages?limit=${PAGE_SIZE}`
    ).then((data) => {
      setMessages(data.messages);
      setHasMore(data.has_more);
      setNextBefore(data.next_before);
    }).catch(() => {}).finally(() => setIsInitialLoading(false));
  }, [id]);

  const loadMore = useCallback(async () => {
    if (!hasMore || !nextBefore || isFetching) return;
    setIsFetching(true);
    try {
      const data = await api.get<{ messages: Message[]; has_more: boolean; next_before: string | null }>(
        `/admin/conversations/${id}/messages?limit=${PAGE_SIZE}&before=${encodeURIComponent(nextBefore)}`
      );
      // Prepend because each page is older than the previous one
      setMessages((prev) => [...data.messages, ...prev]);
      setHasMore(data.has_more);
      setNextBefore(data.next_before);
    } finally {
      setIsFetching(false);
    }
  }, [hasMore, nextBefore, isFetching, id]);

  const toggle = (msgId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(msgId)) next.delete(msgId);
      else next.add(msgId);
      return next;
    });
  };

  const expandAll = () => {
    setExpandedIds(new Set(messages.map((m) => m.id)));
    setAllExpanded(true);
  };

  const collapseAll = () => {
    setExpandedIds(new Set());
    setAllExpanded(false);
  };

  const jumpToLatest = () => {
    if (messages.length === 0) return;
    const lastId = messages[messages.length - 1].id;
    setExpandedIds(new Set([lastId]));
    setAllExpanded(false);
    setTimeout(() => {
      document.getElementById(`msg-${lastId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 50);
  };

  const replayMutation = useMutation({
    mutationFn: () => api.post(`/admin/conversations/${id}/replay`),
    onSuccess: () => toast.success("Replay queued. Check back for results."),
    onError: (err: unknown) => {
      toast.error(`Replay failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    },
  });

  if (isInitialLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
        <div className="space-y-3">
          {[0, 1, 2].map((i) => <div key={i} className="h-16 bg-gray-100 rounded animate-pulse" />)}
        </div>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Conversation {id?.slice(0, 8)}</h1>
        <div className="p-8 text-center text-gray-400">No messages in this conversation.</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Conversation {id?.slice(0, 8)}</h1>
          <span className="text-sm text-gray-500">{messages.length} msgs</span>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => allExpanded ? collapseAll() : expandAll()}
          >
            <ChevronsUpDown className="mr-1 h-4 w-4" />
            {allExpanded ? "Collapse all" : "Expand all"}
          </Button>
          <Button variant="outline" size="sm" onClick={jumpToLatest}>
            <ArrowDown className="mr-1 h-4 w-4" />Bottom
          </Button>
          <Button variant="outline" size="sm" disabled>
            <RotateCcw className="mr-1 h-4 w-4" />
            Replay (soon)
          </Button>
        </div>
      </div>

      {hasMore && (
        <div className="flex justify-center">
          <Button
            variant="outline"
            size="sm"
            onClick={loadMore}
            disabled={isFetching}
          >
            {isFetching ? (
              <><Loader2 className="mr-1 h-4 w-4 animate-spin" />Loading...</>
            ) : (
              <>Load more ({messages.length} loaded)</>
            )}
          </Button>
        </div>
      )}

      <div className="space-y-1">
        {messages.map((msg) => (
          <div key={msg.id} id={`msg-${msg.id}`}>
            <MessageRow
              msg={msg}
              isExpanded={allExpanded || expandedIds.has(msg.id)}
              onToggle={() => toggle(msg.id)}
            />
          </div>
        ))}
      </div>

      <div ref={scrollAnchorRef} />
    </div>
  );
}
