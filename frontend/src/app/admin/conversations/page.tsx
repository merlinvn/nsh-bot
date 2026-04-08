"use client";
import { useState } from "react";
import { useConversations } from "@/hooks/useApi";
import { DataTable } from "@/components/admin/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

export default function ConversationsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string>("");
  const pageSize = 20;
  const { data, isLoading, isError } = useConversations(
    status ? { page: String(page), size: String(pageSize), status } : { page: String(page), size: String(pageSize) }
  );

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;

  if (isError) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Conversations</h1>
        <div className="p-8 text-center text-red-500">Failed to load conversations. Please try again.</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Conversations</h1>
        <div className="flex items-center gap-2">
          <select
            className="border rounded px-2 py-1 text-sm"
            value={status}
            onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          >
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="closed">Closed</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="h-14 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      ) : (
        <>
          <DataTable
            data={data?.items || []}
            columns={[
              {
                header: "ID",
                accessor: (row) => (
                  <Link href={`/admin/conversations/${row.id}`} className="font-mono text-sm hover:underline">
                    {row.id.slice(0, 8)}
                  </Link>
                ),
              },
              { header: "User ID", accessor: (row) => row.external_user_id },
              { header: "Status", accessor: (row) => <Badge>{row.status}</Badge> },
              { header: "Created", accessor: (row) => new Date(row.created_at).toLocaleString() },
            ]}
          />
          {data && totalPages > 1 && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500">
                Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, data.total)} of {data.total}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-sm py-1 px-2">
                  Page {page} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
