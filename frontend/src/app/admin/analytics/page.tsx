"use client";
import { useState } from "react";
import { useAnalyticsOverview, useMessageVolume, useLatencyPercentiles, useToolUsage, useTokenUsage } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from "recharts";
import { format, subDays } from "date-fns";

type DateRange = "7d" | "14d" | "30d";

function getDateRange(range: DateRange) {
  const end = new Date();
  const start = subDays(end, range === "7d" ? 7 : range === "14d" ? 14 : 30);
  return { start: start.toISOString(), end: end.toISOString() };
}

function OverviewCards({ start, end }: { start: string; end: string }) {
  const { data, isLoading } = useAnalyticsOverview(start, end);
  if (isLoading || !data) return <OverviewCardsSkeleton />;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-gray-500">Total Messages</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{data.total_messages.toLocaleString()}</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-gray-500">Total Conversations</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{data.total_conversations.toLocaleString()}</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-gray-500">Avg Latency</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {data.avg_latency_ms ? `${Math.round(data.avg_latency_ms)}ms` : "N/A"}
          </div>
          {data.p95_latency_ms && (
            <p className="text-xs text-gray-400 mt-1">p95: {Math.round(data.p95_latency_ms)}ms</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-gray-500">Fallback Rate</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {`${(data.fallback_rate * 100).toFixed(2)}%`}
          </div>
          <Badge variant={data.fallback_rate > 0.1 ? "destructive" : "default"}>
            {data.fallback_rate > 0.1 ? "High" : "Normal"}
          </Badge>
        </CardContent>
      </Card>
    </div>
  );
}

function OverviewCardsSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <Card key={i}>
          <CardHeader className="pb-2">
            <div className="h-4 w-24 bg-gray-200 rounded animate-pulse" />
          </CardHeader>
          <CardContent>
            <div className="h-8 w-16 bg-gray-200 rounded animate-pulse" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function MessageVolumeChart({ start, end }: { start: string; end: string }) {
  const { data, isLoading } = useMessageVolume(start, end);
  const chartData = data?.buckets.map((b) => ({ date: format(new Date(b.date), "MMM dd"), messages: b.count })) ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Message Volume</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-48 bg-gray-100 rounded animate-pulse" />
        ) : chartData.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-gray-400">No message data</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="messages" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

function LatencyChart({ start, end }: { start: string; end: string }) {
  const { data, isLoading } = useLatencyPercentiles(start, end);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Latency Percentiles</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-48 bg-gray-100 rounded animate-pulse" />
        ) : !data ? (
          <div className="h-48 flex items-center justify-center text-gray-400">No latency data</div>
        ) : (
          <div className="space-y-4">
            {[
              { label: "P50", value: data.p50 },
              { label: "P95", value: data.p95 },
              { label: "P99", value: data.p99 },
            ].map(({ label, value }) => (
              <div key={label} className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="font-medium">{label}</span>
                  <span className="text-gray-500">{value != null ? `${Math.round(value)}ms` : "N/A"}</span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full"
                    style={{ width: `${Math.min((value ?? 0) / (data.p99 ?? 1) * 100, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ToolUsageChart({ start, end }: { start: string; end: string }) {
  const { data, isLoading } = useToolUsage(start, end);
  const chartData = data?.tools ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tool Usage</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-48 bg-gray-100 rounded animate-pulse" />
        ) : chartData.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-gray-400">No tool data</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="name" tick={{ fontSize: 11, angle: chartData.length > 3 ? -30 : 0, textAnchor: chartData.length > 3 ? 'end' : 'middle' }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#10b981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

function TokenUsageCard({ start, end }: { start: string; end: string }) {
  const { data, isLoading } = useTokenUsage(start, end);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Token Usage</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => <div key={i} className="h-6 bg-gray-100 rounded animate-pulse" />)}
          </div>
        ) : !data ? (
          <div className="text-gray-400">No token data</div>
        ) : (
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Input Tokens</span>
              <span className="font-medium">{data.total_input_tokens.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Output Tokens</span>
              <span className="font-medium">{data.total_output_tokens.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Messages</span>
              <span className="font-medium">{data.message_count.toLocaleString()}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function AnalyticsPage() {
  const [range, setRange] = useState<DateRange>("7d");
  const { start, end } = getDateRange(range);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Analytics Dashboard</h1>
        <Select value={range} onValueChange={(v) => setRange(v as DateRange)}>
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7d">Last 7 days</SelectItem>
            <SelectItem value="14d">Last 14 days</SelectItem>
            <SelectItem value="30d">Last 30 days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <OverviewCards start={start} end={end} />

      <div className="grid gap-4 md:grid-cols-2">
        <MessageVolumeChart start={start} end={end} />
        <LatencyChart start={start} end={end} />
        <ToolUsageChart start={start} end={end} />
        <TokenUsageCard start={start} end={end} />
      </div>
    </div>
  );
}
