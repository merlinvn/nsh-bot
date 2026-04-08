"use client";
import { useState } from "react";
import {
  useMonitoringHealthDetail,
  useMonitoringMetricsTrend,
  useMonitoringQueues,
  useMonitoringWorkers,
} from "@/hooks/useApi";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Pause, Play, RefreshCw } from "lucide-react";

// Thresholds from spec
const QUEUE_WARNING = 100;
const QUEUE_CRITICAL = 500;
const HEALTH_DEGRADED_MS = 200;
const HEALTH_DOWN_MS = 1000;

// Queue color dot
function QueueDot({ count }: { count: number }) {
  if (count === 0) return <span className="size-2 rounded-full bg-gray-400 inline-block" />;
  if (count >= QUEUE_CRITICAL) return <span className="size-2 rounded-full bg-red-500 inline-block" />;
  if (count >= QUEUE_WARNING) return <span className="size-2 rounded-full bg-yellow-500 inline-block" />;
  return <span className="size-2 rounded-full bg-green-500 inline-block" />;
}

// Queue message color
function QueueMessageCount({ count }: { count: number }) {
  if (count === 0) return <span className="text-gray-400">0</span>;
  if (count >= QUEUE_CRITICAL) return <span className="text-red-600 font-medium">{count}</span>;
  if (count >= QUEUE_WARNING) return <span className="text-yellow-600 font-medium">{count}</span>;
  return <span className="text-green-600 font-medium">{count}</span>;
}

// Health dot
function HealthDot({ status }: { status: "ok" | "degraded" | "error" | undefined }) {
  if (!status) return <span className="size-2 rounded-full bg-gray-400 inline-block" />;
  if (status === "ok") return <span className="size-2 rounded-full bg-green-500 inline-block" />;
  if (status === "degraded") return <span className="size-2 rounded-full bg-yellow-500 inline-block" />;
  return <span className="size-2 rounded-full bg-red-500 inline-block" />;
}

// Worker dot
function WorkerDot({ status }: { status: "alive" | "stale" | "dead" | undefined }) {
  if (status === "alive") return <span className="size-2 rounded-full bg-green-500 inline-block" />;
  if (status === "stale") return <span className="size-2 rounded-full bg-yellow-500 inline-block" />;
  return <span className="size-2 rounded-full bg-red-500 inline-block" />;
}

// Human-readable age
function AgeLabel({ ageSeconds }: { ageSeconds: number | null }) {
  if (ageSeconds === null) return <span className="text-red-500">never</span>;
  if (ageSeconds < 60) return <span>{ageSeconds}s ago</span>;
  if (ageSeconds < 3600) return <span>{Math.floor(ageSeconds / 60)}m ago</span>;
  return <span>{Math.floor(ageSeconds / 3600)}h ago</span>;
}

// Trend arrow
function TrendArrow({ current, previous }: { current: number | null; previous: number | null }) {
  if (current === null || previous === null) return null;
  const diff = current - previous;
  if (Math.abs(diff) < 1) return <span className="text-gray-400 ml-1">→</span>;
  if (diff > 0) return <span className="text-red-500 ml-1">↑</span>;
  return <span className="text-green-500 ml-1">↓</span>;
}

export default function MonitoringPage() {
  const [paused, setPaused] = useState(false);
  const queryClient = useQueryClient();

  const { data: healthDetail } = useMonitoringHealthDetail({ enabled: !paused });
  const { data: metricsTrend } = useMonitoringMetricsTrend({ enabled: !paused });
  const { data: queues } = useMonitoringQueues({ enabled: !paused });
  const { data: workers } = useMonitoringWorkers({ enabled: !paused });

  // Alert: any service error or any queue >= 500
  const hasAlert =
    healthDetail?.services.some((s) => s.status === "error") ||
    queues?.queues.some((q) => q.messages >= QUEUE_CRITICAL);

  const current = metricsTrend?.current;
  const previous = metricsTrend?.previous;

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ["monitoring-health-detail"] });
    queryClient.invalidateQueries({ queryKey: ["monitoring-metrics-trend"] });
    queryClient.invalidateQueries({ queryKey: ["monitoring-queues"] });
    queryClient.invalidateQueries({ queryKey: ["monitoring-workers"] });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold">System Monitoring</h1>
          {hasAlert && (
            <span className="size-2.5 rounded-full bg-red-500 inline-block" title="Alert: service down or queue critical" />
          )}
        </div>
        <div className="flex gap-1 ml-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={refreshAll}
            title="Manual refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPaused((p) => !p)}
            title={paused ? "Resume auto-refresh" : "Pause auto-refresh"}
          >
            {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            {paused ? "Resume" : "Pause"}
          </Button>
        </div>
      </div>

      {/* Health Checks */}
      <Card>
        <CardContent className="pt-4">
          <div className="grid gap-0 divide-x divide-gray-200 md:grid-cols-3">
            {(healthDetail?.services ?? []).map((svc) => {
              const latency = svc.latency_ms;
              const isDegraded = latency !== null && latency > HEALTH_DEGRADED_MS;
              const isDown = latency === null || latency > HEALTH_DOWN_MS || svc.status === "error";
              return (
                <div key={svc.name} className="flex items-center gap-3 px-4 first:pl-0">
                  <span className="text-xs font-medium text-gray-500 uppercase">{svc.name}</span>
                  {latency !== null && (
                    <span className="text-xs text-gray-400">{latency}ms</span>
                  )}
                  <HealthDot status={isDown ? "error" : isDegraded ? "degraded" : "ok"} />
                  <span className="text-xs">
                    {isDown ? "error" : isDegraded ? "slow" : "ok"}
                  </span>
                </div>
              );
            })}
            {!healthDetail && (
              <div className="col-span-3 text-sm text-gray-400 px-4 py-2">Loading...</div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Metrics */}
      {current && (
        <Card>
          <CardContent className="pt-4">
            <div className="flex gap-8 text-sm flex-wrap">
              <div className="flex items-center gap-1">
                <span className="text-gray-500">Conversations</span>
                <span className="font-medium">{current.total_conversations.toLocaleString()}</span>
                <TrendArrow
                  current={current.total_conversations}
                  previous={previous?.total_conversations ?? null}
                />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-gray-500">Messages</span>
                <span className="font-medium">{current.total_messages.toLocaleString()}</span>
                <TrendArrow
                  current={current.total_messages}
                  previous={previous?.total_messages ?? null}
                />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-gray-500">Avg Latency</span>
                <span className="font-medium">
                  {current.avg_latency_ms !== null ? `${Math.round(current.avg_latency_ms)}ms` : "N/A"}
                </span>
                <TrendArrow
                  current={current.avg_latency_ms}
                  previous={previous?.avg_latency_ms ?? null}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Queue Depths */}
      <Card>
        <CardHeader>
          <CardTitle>Queue Depths</CardTitle>
        </CardHeader>
        <CardContent>
          {queues && queues.queues.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="py-2 pr-4 font-medium">Queue</th>
                    <th className="py-2 pr-4 font-medium text-right">Messages</th>
                    <th className="py-2 pr-4 font-medium text-right">Consumers</th>
                    <th className="py-2 font-medium">State</th>
                  </tr>
                </thead>
                <tbody>
                  {queues.queues.map((q) => (
                    <tr key={q.name} className="border-b last:border-0">
                      <td className="py-2 pr-4 font-mono text-xs">{q.name}</td>
                      <td className="py-2 pr-4 text-right">
                        <span className="inline-flex items-center gap-2">
                          <QueueDot count={q.messages} />
                          <QueueMessageCount count={q.messages} />
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-right">{q.consumers}</td>
                      <td className="py-2 text-xs text-gray-500">{q.state}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : queues && queues.queues.length === 0 ? (
            <div className="text-gray-400 text-sm py-4">No queues found.</div>
          ) : (
            <div className="text-gray-400 text-sm py-4">Loading...</div>
          )}
        </CardContent>
      </Card>

      {/* Workers */}
      <Card>
        <CardHeader>
          <CardTitle>Workers</CardTitle>
        </CardHeader>
        <CardContent>
          {workers && workers.workers.length > 0 ? (
            <div className="space-y-2">
              {workers.workers.map((w) => (
                <div key={w.name} className="flex items-center gap-3 text-sm">
                  <span className="font-mono text-xs">{w.name}</span>
                  <WorkerDot status={w.status} />
                  <span className="text-xs">
                    {w.status === "alive" ? "alive" : w.status === "stale" ? "stale" : "dead"}
                  </span>
                  <span className="text-xs text-gray-400 ml-auto">
                    <AgeLabel ageSeconds={w.age_seconds} />
                  </span>
                </div>
              ))}
            </div>
          ) : workers && workers.workers.length === 0 ? (
            <div className="text-gray-400 text-sm py-4">No workers registered.</div>
          ) : (
            <div className="text-gray-400 text-sm py-4">Loading...</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
