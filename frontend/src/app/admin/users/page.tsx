"use client";
import { useZaloUsers } from "@/hooks/useApi";
import { DataTable } from "@/components/admin/DataTable";
import { Badge } from "@/components/ui/badge";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function UsersPage() {
  const { data, isLoading, isError, refetch, isFetching } = useZaloUsers();

  if (isError) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Zalo Users</h1>
        <div className="p-8 text-center text-red-500">Failed to load users. Please try again.</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Zalo Users</h1>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`size-4 mr-1 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="h-14 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      ) : (
        <>
          <p className="text-sm text-gray-500">{data?.length || 0} users</p>
          <DataTable
            data={data || []}
            columns={[
              {
                header: "User",
                accessor: (row) => (
                  <div className="flex items-center gap-3">
                    {row.avatar ? (
                      <img
                        src={row.avatar}
                        alt={row.display_name || ""}
                        className="w-8 h-8 rounded-full object-cover"
                      />
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-sm font-medium">
                        {row.display_name ? row.display_name[0]?.toUpperCase() : "?"}
                      </div>
                    )}
                    <div>
                      <div className="font-medium">{row.display_name || "—"}</div>
                      <div className="text-xs text-gray-400">{row.user_alias || row.user_id}</div>
                    </div>
                  </div>
                ),
              },
              { header: "Zalo ID", accessor: (row) => <span className="font-mono text-sm">{row.user_id}</span> },
              {
                header: "User ID (App)",
                accessor: (row) => row.user_id_by_app ? <span className="font-mono text-sm">{row.user_id_by_app}</span> : "—",
              },
              {
                header: "External ID",
                accessor: (row) => row.user_external_id ? <span className="font-mono text-sm">{row.user_external_id}</span> : "—",
              },
              {
                header: "Shared Info",
                accessor: (row) => {
                  if (!row.shared_info) return "—";
                  const si = row.shared_info as Record<string, string>;
                  const parts = [
                    si.name,
                    si.phone,
                    si.address,
                  ].filter(Boolean);
                  return parts.length > 0 ? <span className="text-sm">{parts.join(" • ")}</span> : "—";
                },
              },
              {
                header: "Follower",
                accessor: (row) => (
                  <Badge variant={row.user_is_follower ? "default" : "secondary"}>
                    {row.user_is_follower ? "Yes" : "No"}
                  </Badge>
                ),
              },
              {
                header: "Last Interaction",
                accessor: (row) =>
                  row.user_last_interaction_date
                    ? new Date(row.user_last_interaction_date).toLocaleDateString("vi-VN")
                    : "—",
              },
              {
                header: "Sensitive",
                accessor: (row) =>
                  row.is_sensitive === null ? "—" : row.is_sensitive ? "Yes" : "No",
              },
              {
                header: "Added",
                accessor: (row) => new Date(row.created_at).toLocaleDateString("vi-VN"),
              },
            ]}
          />
        </>
      )}
    </div>
  );
}
