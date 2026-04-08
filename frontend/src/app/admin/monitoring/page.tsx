"use client";
import { useMonitoringHealth, useMonitoringMetrics, useMonitoringQueues } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

export default function MonitoringPage() {
  const { data: health, isLoading: healthLoading } = useMonitoringHealth();
  const { data: metrics } = useMonitoringMetrics();
  const { data: queues, isLoading: queuesLoading } = useMonitoringQueues();
  const queryClient = useQueryClient();

  const statusBadge = (status: string) => (
    <Badge variant={status === "ok" ? "default" : "destructive"}>{status}</Badge>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold">System Monitoring</h1>
        <button
          onClick={() => {
            queryClient.invalidateQueries({ queryKey: ["monitoring-health"] });
            queryClient.invalidateQueries({ queryKey: ["monitoring-metrics"] });
            queryClient.invalidateQueries({ queryKey: ["monitoring-queues"] });
          }}
          className="text-gray-400 hover:text-gray-600"
          title="Refresh all"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {/* Health Checks */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Database</CardTitle>
          </CardHeader>
          <CardContent>{health ? statusBadge(health.database) : "—"}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Redis</CardTitle>
          </CardHeader>
          <CardContent>{health ? statusBadge(health.redis) : "—"}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">RabbitMQ</CardTitle>
          </CardHeader>
          <CardContent>{health ? statusBadge(health.rabbitmq) : "—"}</CardContent>
        </Card>
      </div>

      {/* Metrics */}
      {metrics && (
        <Card>
          <CardHeader>
            <CardTitle>Metrics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Total Conversations</span>
              <span className="font-medium">{metrics.total_conversations.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Total Messages</span>
              <span className="font-medium">{metrics.total_messages.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Avg Latency</span>
              <span className="font-medium">
                {metrics.avg_latency_ms ? `${Math.round(metrics.avg_latency_ms)}ms` : "N/A"}
              </span>
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
          {queuesLoading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-12 bg-gray-100 rounded animate-pulse" />
              ))}
            </div>
          ) : queues && queues.queues.length > 0 ? (
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
                        {q.messages > 0 ? (
                          <span className="text-orange-600 font-medium">{q.messages}</span>
                        ) : (
                          <span className="text-gray-400">0</span>
                        )}
                      </td>
                      <td className="py-2 pr-4 text-right">{q.consumers}</td>
                      <td className="py-2">
                        <StatusBadge status={q.state} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-gray-400 text-sm py-4">No queue data available. Check RabbitMQ management plugin is enabled.</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
