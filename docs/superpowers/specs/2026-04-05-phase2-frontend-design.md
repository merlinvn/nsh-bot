# Phase 2 Frontend Architecture Design

**Date:** 2026-04-05
**Author:** Frontend Architect
**Status:** Draft

---

## 1. Tech Stack Recommendation

### Recommendation: Next.js 14+ with App Router

**Rationale:**

| Criteria | Next.js | React (Vite) |
|----------|---------|--------------|
| SSR/SEO | Yes (good for admin, optional) | No (SPA only) |
| File-based routing | Yes (reduces boilerplate) | Manual setup |
| API routes | Built-in (can proxy to backend) | Needs separate Express/FastAPI |
| Team DX | Excellent (monorepo friendly) | Good |
| Deployment | Vercel, Docker, any Node host | Any static host + proxy |
| Auth helpers | NextAuth.js ecosystem | Auth0, custom |

**Selected Stack:**
- **Framework:** Next.js 14+ (App Router)
- **Language:** TypeScript (strict mode)
- **Styling:** Tailwind CSS 3.4+ + shadcn/ui components
- **State Management:** Zustand (lightweight) + React Query (server state)
- **Forms:** React Hook Form + Zod validation
- **Charts:** Recharts or Tremor
- **HTTP Client:** Built-in fetch with custom wrapper

**Why not pure React + Vite:**
- Next.js API routes can handle admin API proxy in same deployment
- File-based routing reduces boilerplate for 6+ page types
- Server Components for analytics dashboard (less client JS)
- Built-in image optimization, font loading, etc.

---

## 2. Component Architecture

### Folder Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── (auth)/            # Auth layout group
│   │   │   ├── login/
│   │   │   └── layout.tsx
│   │   ├── (admin)/           # Protected admin layout group
│   │   │   ├── layout.tsx     # Sidebar + main content
│   │   │   ├── promps/        # Prompt management
│   │   │   ├── conversations/ # Conversation management
│   │   │   ├── analytics/     # Dashboard
│   │   │   ├── playground/    # LLM playground
│   │   │   ├── tokens/        # Zalo token management
│   │   │   └── monitoring/   # Metrics
│   │   ├── api/              # API route proxies (optional)
│   │   ├── layout.tsx        # Root layout
│   │   └── page.tsx          # Redirect to /conversations or /login
│   ├── components/
│   │   ├── ui/               # shadcn/ui base components
│   │   ├── admin/             # Shared admin components
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Header.tsx
│   │   │   ├── DataTable.tsx
│   │   │   ├── StatusBadge.tsx
│   │   │   └── ConfirmDialog.tsx
│   │   └── forms/             # Form-specific components
│   ├── lib/
│   │   ├── api.ts             # API client wrapper
│   │   ├── auth.ts            # Auth utilities
│   │   └── utils.ts           # Helpers (cn, formatDate, etc.)
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useApi.ts
│   │   └── useMediaQuery.ts
│   ├── stores/
│   │   └── authStore.ts       # Zustand auth state
│   ├── types/
│   │   └── api.ts             # Shared API types
│   └── styles/
│       └── globals.css
├── public/
├── .env.local                  # NEXT_PUBLIC_API_URL, etc.
└── package.json
```

### State Management Strategy

**Server State (React Query):**
- Conversation lists with pagination
- Prompt versions
- Analytics data
- Any data from `/admin/*` endpoints

**Client State (Zustand):**
- Auth session (token, user info)
- UI preferences (sidebar collapsed, theme)
- Form draft states

**URL State:**
- Filters, pagination, search params (via nuqs or Next.js searchParams)

---

## 3. UI/UX Design Direction

### Design System

- **Base:** shadcn/ui + Tailwind CSS
- **Theme:** Dark mode default (admin panels are typically used in dark mode), light mode toggle
- **Colors:** Zinc slate palette, accent color configurable
- **Typography:** Inter font family, monospace for code/token displays
- **Icons:** Lucide React

### Layout Approach

```
┌─────────────────────────────────────────────────────────────┐
│  Logo    "NeoChat Admin"                    User ▾  [⚙️]   │  ← Header (h-14)
├──────────┬──────────────────────────────────────────────────┤
│          │                                                  │
│  Nav     │           Main Content Area                      │
│  Items   │           (scrollable)                           │
│          │                                                  │
│  ───     │                                                  │
│  [?]     │                                                  │
│          │                                                  │
└──────────┴──────────────────────────────────────────────────┘
   w-64              flex-1
```

- **Sidebar:** Fixed left, collapsible (icon-only mode), 64px expanded
- **Header:** Fixed top, shows breadcrumb, user menu, notifications
- **Content:** Scrollable, max-width container for readability on large screens
- **Responsive:**
  - Desktop (≥1024px): Full sidebar
  - Tablet (768-1023px): Collapsible sidebar (hamburger)
  - Mobile (<768px): Bottom tab navigation OR hamburger-only

### Navigation Items

1. **Dashboard** (icon: LayoutDashboard) → Analytics overview
2. **Conversations** (icon: MessageSquare) → List/filter conversations
3. **Prompts** (icon: FileText) → Prompt management
4. **Playground** (icon: Sparkles) → LLM chat interface
5. **Tokens** (icon: Key) → Zalo OAuth tokens
6. **Monitoring** (icon: Activity) → System metrics

### Accessibility

- ARIA labels on all interactive elements
- Keyboard navigation support
- Focus trap in modals
- Color contrast WCAG AA compliant

---

## 4. Auth Flow

### Login Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Login Page  │────▶│  POST /auth  │────▶│   Redirect    │
│  /login      │     │   login      │     │  /conversations
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  Set Cookie  │
                     │  httpOnly    │
                     └──────────────┘
```

### Auth Implementation

**Backend (existing FastAPI):**
- `POST /admin/auth/login` → { username, password } → returns httpOnly session cookie or JWT
- `POST /admin/auth/logout` → clears cookie
- `GET /admin/auth/me` → returns current user info

**Frontend:**
- NextAuth.js with Credentials provider (NOT OAuth)
- Session stored in httpOnly cookie (never localStorage)
- Middleware protects all `/admin/*` routes
- `useAuth()` hook exposes `user`, `login()`, `logout()`

### Protected Route Flow

```
Request → Middleware → Check session cookie → Valid? → Yes → Render page
                                                    │
                                                    No → Redirect /login
```

### Session Refresh

- Silent refresh before expiry (handled by NextAuth)
- Force re-login after 24h inactivity

---

## 5. Admin Panel Layout

### Page Layout Template

```tsx
// app/(admin)/layout.tsx
export default function AdminLayout({ children }) {
  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

### Sidebar Navigation

```tsx
const navItems = [
  { label: 'Dashboard', href: '/admin', icon: LayoutDashboard },
  { label: 'Conversations', href: '/admin/conversations', icon: MessageSquare },
  { label: 'Prompts', href: '/admin/prompts', icon: FileText },
  { label: 'Playground', href: '/admin/playground', icon: Sparkles },
  { label: 'Tokens', href: '/admin/tokens', icon: Key },
  { label: 'Monitoring', href: '/admin/monitoring', icon: Activity },
];
```

### Responsive Behavior

| Breakpoint | Sidebar | Navigation |
|------------|---------|------------|
| ≥1024px | Fixed expanded (256px) | Top nav bar |
| 768-1023px | Collapsible (64px icons) | Hamburger menu |
| <768px | Hidden | Bottom tab bar |

---

## 6. Key Pages/Views

### 6.1 Dashboard (Analytics)

**Purpose:** At-a-glance metrics overview

**Components:**
- Metric cards (4-grid): Messages today, Avg latency, Fallback rate, Active conversations
- Charts:
  - Message volume (line chart, 7-day trend)
  - Latency distribution (histogram)
  - Tool usage breakdown (pie/bar chart)
  - Fallback rate trend (line chart)
- Recent conversations list (last 10)

**Data:** Fetched via React Query from `/admin/analytics/*`

### 6.2 Conversation Management

**Purpose:** Browse, search, investigate conversations

**List View (`/admin/conversations`):**
- Filters: date range, status, has fallback, has error
- Search: by external_user_id, conversation_id
- Table columns: ID, User, Status, Messages, Last message, Created
- Pagination: 25/50/100 per page

**Detail View (`/admin/conversations/[id]`):**
- Conversation metadata header
- Message thread (chat bubble UI, bot vs user differentiated)
- Tool calls panel (expandable per message)
- Replay button (triggers `/admin/conversations/[id]/replay`)

### 6.3 Prompt Management

**Purpose:** CRUD for prompt templates

**List View (`/admin/prompts`):**
- Table: Name, Description, Active version, Updated at
- Actions: Edit, View versions, Set active, Duplicate

**Edit View (`/admin/prompts/[id]`):**
- Version selector dropdown
- Prompt template editor (monospace textarea with line numbers)
- Variables sidebar (shows available variables)
- Preview panel (renders with sample variables)
- Save as new version button

### 6.4 LLM Playground

**Purpose:** Test prompts interactively

**Layout:**
- Left: Prompt template editor (with variables)
- Right: Chat interface (user/assistant messages)
- Bottom: Model selector, temperature, max_tokens sliders
- Actions: Send, Clear, Copy response

**Features:**
- Stream responses (SSE or WebSocket)
- History of playground sessions (localStorage)
- Save prompt to library

### 6.5 Token Management (Zalo OAuth)

**Purpose:** Manage Zalo OAuth tokens

**View (`/admin/tokens`):**
- Current token status card (valid/expired/revoked)
- Token metadata: issued, expires, scopes
- Actions: Refresh token, Revoke, Re-authorize
- OAuth flow UI (PKCE):
  - "Connect Zalo" button → redirects to Zalo OAuth
  - Callback handler stores tokens

### 6.6 Monitoring

**Purpose:** System health and metrics

**Components:**
- Health indicators (green/yellow/red): API, Database, Redis, RabbitMQ
- Metrics charts:
  - Request rate (requests/second)
  - Error rate (5xx/4xx)
  - Queue depth
  - Worker status
- Logs viewer (last 100 lines, filterable)

---

## 7. Integration Points

### API Client

```typescript
// lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function apiRequest<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    credentials: 'include', // Send httpOnly cookie
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new ApiError(res.status, error.detail);
  }

  return res.json();
}

// Typed API methods
export const api = {
  auth: {
    login: (body: { username: string; password: string }) =>
      apiRequest('/admin/auth/login', { method: 'POST', body: JSON.stringify(body) }),
    logout: () => apiRequest('/admin/auth/logout', { method: 'POST' }),
    me: () => apiRequest<User>('/admin/auth/me'),
  },
  conversations: {
    list: (params: ConversationFilters) =>
      apiRequest<ConversationList>(`/admin/conversations?${new URLSearchParams(params)}`),
    get: (id: string) => apiRequest<Conversation>(`/admin/conversations/${id}`),
    replay: (id: string) => apiRequest(`/admin/conversations/${id}/replay`, { method: 'POST' }),
  },
  prompts: {
    list: () => apiRequest<Prompt[]>('/admin/prompts'),
    get: (id: string) => apiRequest<Prompt>(`/admin/prompts/${id}`),
    create: (body: CreatePrompt) => apiRequest<Prompt>('/admin/prompts', { method: 'POST', body: JSON.stringify(body) }),
    update: (id: string, body: UpdatePrompt) => apiRequest(`/admin/prompts/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    setActive: (id: string, version: number) =>
      apiRequest(`/admin/prompts/${id}/activate`, { method: 'POST', body: JSON.stringify({ version }) }),
  },
  analytics: {
    dashboard: () => apiRequest<DashboardMetrics>('/admin/analytics/dashboard'),
    trends: (period: string) => apiRequest<TrendsData>(`/admin/analytics/trends?period=${period}`),
  },
  tokens: {
    getStatus: () => apiRequest<TokenStatus>('/admin/tokens/status'),
    refresh: () => apiRequest('/admin/tokens/refresh', { method: 'POST' }),
    revoke: () => apiRequest('/admin/tokens/revoke', { method: 'POST' }),
    getAuthUrl: () => apiRequest<{ url: string }>('/admin/tokens/auth-url'),
  },
};
```

### WebSocket (Optional for real-time)

For live monitoring, consider WebSocket upgrade on the API:
- `ws://localhost:8000/ws/monitoring` → real-time metrics stream

### API Error Handling

```typescript
// Centralized error handling
class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// In React Query
const { data, error, isLoading } = useQuery({
  queryKey: ['conversations'],
  queryFn: () => api.conversations.list(filters),
});
```

---

## 8. Component Priority Order

### Phase 1 (MVP - 2 weeks)

1. **Auth + Shell**
   - Login page
   - Admin layout with sidebar
   - Protected route middleware
   - Basic auth store

2. **Conversations (Read)**
   - Conversation list with filters
   - Conversation detail view
   - Message thread display

### Phase 2 (Core Features - 3 weeks)

3. **Prompts Management**
   - Prompt list
   - Version viewer
   - Template editor

4. **Analytics Dashboard**
   - Metric cards
   - Charts (Recharts)
   - Date range picker

### Phase 3 (Advanced - 2 weeks)

5. **LLM Playground**
   - Chat interface
   - Model configuration
   - Streaming responses

6. **Token Management**
   - Status display
   - OAuth flow UI
   - Refresh/revoke actions

### Phase 4 (Polish - 1 week)

7. **Monitoring Dashboard**
   - Health checks
   - Metrics charts
   - Logs viewer

8. **Polish & Edge Cases**
   - Responsive fixes
   - Error boundaries
   - Loading skeletons
   - Empty states

---

## 9. Technical Considerations

### CORS Configuration

Backend FastAPI needs CORS for dev (or proxy via Next.js API routes):

```python
# Backend CORS (for development only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

For production: Next.js API routes act as proxy (no CORS needed).

### Environment Variables

```env
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Deployment Options

1. **Vercel** (recommended for Next.js)
   - Environment variables configured in dashboard
   - Automatic preview deployments

2. **Docker**
   - Multi-stage build
   - Serve `next export` statically OR run Node server

3. **Existing infrastructure**
   - Deploy as Node.js service behind nginx reverse proxy

---

## 10. Dependencies

```json
{
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "@tanstack/react-query": "^5.28.0",
    "zustand": "^4.5.0",
    "react-hook-form": "^7.51.0",
    "zod": "^3.22.0",
    "@hookform/resolvers": "^3.3.0",
    "recharts": "^2.12.0",
    "lucide-react": "^0.363.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.2.0",
    "date-fns": "^3.6.0",
    "nuqs": "^1.17.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "@types/node": "^20.11.0",
    "@types/react": "^18.3.0",
    "tailwindcss": "^3.4.0",
    "eslint": "^8.57.0",
    "eslint-config-next": "^14.2.0"
  }
}
```

---

## 11. File Naming Conventions

- **Pages:** `kebab-case.tsx` (e.g., `conversation-list.tsx`)
- **Components:** `PascalCase.tsx` (e.g., `ConversationTable.tsx`)
- **Utilities:** `camelCase.ts` (e.g., `formatDate.ts`)
- **Types:** `kebab-case.types.ts` or `types.ts`

---

## 12. Testing Strategy

- **Unit:** Vitest for utility functions, components
- **Component:** React Testing Library
- **E2E:** Playwright for critical flows (login, conversation view)
- **CI:** Run on PR, block on failure

---

## 13. Future Considerations (Out of Scope)

- Mobile native app
- Real-time collaboration on prompts
- A/B testing for prompts
- Multi-tenant support (Phase 5)
- SSO/SAML integration

---

**Document Version:** 1.0
**Next Review:** After Phase 2 backend API design finalization
