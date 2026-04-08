"use client";
import { useMonitoringHealth, useMonitoringMetrics } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function MonitoringPage() {
  const { data: health, isLoading: healthLoading } = useMonitoringHealth();
  const { data: metrics } = useMonitoringMetrics();

  if (healthLoading) return <div>Loading...</div>;

  const statusBadge = (status: string) => (
    <Badge variant={status === "ok" ? "default" : "destructive"}>{status}</Badge>
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">System Monitoring</h1>
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
      {metrics && (
        <Card>
          <CardHeader>
            <CardTitle>Metrics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>Total Conversations: {metrics.total_conversations.toLocaleString()}</p>
            <p>Total Messages: {metrics.total_messages.toLocaleString()}</p>
            <p>Avg Latency: {metrics.avg_latency_ms ? `${Math.round(metrics.avg_latency_ms)}ms` : "N/A"}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
