"use client";
import { useConversations } from "@/hooks/useApi";
import { DataTable } from "@/components/admin/DataTable";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";

export default function ConversationsPage() {
  const { data, isLoading, isError } = useConversations();

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
      <h1 className="text-2xl font-bold">Conversations</h1>
      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="h-14 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      ) : (
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
      )}
    </div>
  );
}
