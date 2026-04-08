# Monitoring Dashboard — Real-time Ops Spec

## Status
- **Completed** — implemented 2026-04-08

## Overview
Redesign `/admin/monitoring` into a real-time ops dashboard with auto-refresh, latency-aware health checks, visual queue urgency, and worker heartbeat age tracking.

## Design

### Data Layer

#### Health Section
Each service (Database, Redis, RabbitMQ) shows:
- **Status badge**: green (healthy), yellow (degraded), red (down)
- **Latency in ms**: e.g. "3ms"
- **Status text**: "ok", "slow", "error"

Latency thresholds:
- > 200ms → yellow (degraded)
- > 1000ms or unreachable → red (down)

#### Queue Depths
Each queue row:
- Queue name
- Message count with color dot:
  - 0 → gray/neutral
  - 1–99 → green
  - 100–499 → yellow (warning)
  - 500+ → red (critical)
- Consumer count
- State

#### Workers
From Redis heartbeat keys:
- Worker name
- Status badge:
  - 🟢 alive — seen < 60s
  - 🟡 stale — seen 60–300s
  - 🔴 dead — seen > 300s or missing heartbeat key
- Last seen as human-readable age ("3s ago", "2m ago")

#### Metrics
- Total conversations, total messages, avg latency — plain numbers
- Trend arrows: ↑ / ↓ / → vs previous refresh values

#### Alert Indicator
- Red dot on page title when any service is red OR any queue ≥ 500 messages

### UI Layout

```
┌─ System Monitoring ─────────────── ● ─┐  ← red dot if alert
│ [Pause] [Refresh]                    │
├──────────────────────────────────────┤
│ DATABASE    2ms  🟢ok │ REDIS    3ms 🟢ok │ RABBITMQ  5ms 🟢ok │
├──────────────────────────────────────┤
│ Metrics: 1,234 convs ↑  |  5,678 msgs →  |  142ms avg ↓  │
├──────────────────────────────────────┤
│ Queue Depths                             │
│ conversation.process   12 🟢  2cons  running │
│ outbound.send          487 🟡  1con   running │
│ dead-letter              0 ⚪  0cons  running │
├──────────────────────────────────────┤
│ Workers                                 │
│ conv-worker-1     🟢 alive  3s ago   │
│ outbound-worker-1 🟡 stale  2m ago    │
└──────────────────────────────────────┘
```

### Behavior

- **Auto-refresh interval**: 10 seconds
- **Pause/Resume button**: stops auto-refresh; user can manually refresh
- **Manual Refresh button**: forces immediate refetch of all data
- **Health latency**: fetched via `workers/shared/health.py` `check_all()` which returns per-service latency

### Alert Thresholds
Hardcoded defaults (configurable via `.env` in future):
- Queue warning: 100 messages
- Queue critical: 500 messages
- Health degraded: 200ms latency
- Health down: 1000ms latency or unreachable
- Worker stale: > 60s no heartbeat
- Worker dead: > 300s no heartbeat

## Backend Changes

### New endpoint: `GET /admin/monitoring/health-detail`
Returns per-service health with latency:
```json
{
  "services": [
    { "name": "postgres", "status": "ok", "latency_ms": 2 },
    { "name": "redis",    "status": "ok", "latency_ms": 3 },
    { "name": "rabbitmq", "status": "ok", "latency_ms": 5 }
  ]
}
```

Uses `workers/shared/health.py` `check_all()` which already runs `check_postgres()`, `check_redis()`, `check_rabbitmq()` with latency measurement.

### Updated endpoint: `GET /admin/monitoring/workers`
Adds human-readable `last_seen_age` field and derived `status` (alive/stale/dead).

### Updated endpoint: `GET /admin/monitoring/queues`
Returns message count as integer for color coding on frontend.

### New endpoint: `GET /admin/monitoring/metrics-trend`
Returns current metrics + previous values for trend comparison:
```json
{
  "current": { "total_conversations": 1234, "total_messages": 5678, "avg_latency_ms": 142 },
  "previous": { "total_conversations": 1230, "total_messages": 5670, "avg_latency_ms": 145 }
}
```

Previous values stored in Redis with key `monitoring:metrics:prev` — updated on each refresh.

## Frontend Changes

- New hook `useMonitoringHealthDetail()` — fetches health with latency
- New hook `useMonitoringMetricsTrend()` — fetches current + previous metrics
- `useMonitoringHealth()` updated to show latency alongside status
- `useMonitoringWorkers()` updated to compute `last_seen_age` and `status` from `last_seen` timestamp
- Auto-refresh via `refetchInterval: 10_000` on all monitoring queries
- Pause state managed in page component — pauses all queries simultaneously
- Alert dot rendered in page header when any service is `error` or queue count ≥ 500

## Implementation Notes
- No new dependencies
- Follows existing patterns (hooks in `useApi.ts`, page in `app/admin/monitoring/page.tsx`)
- Redis metrics trend key has TTL of 60s — stale data auto-expires
