"use client";
import { useZaloTokenStatus, useRefreshToken, useRevokeToken, useInitiatePkce } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

export default function TokensPage() {
  const { data, isLoading, isError } = useZaloTokenStatus();
  const refreshMutation = useRefreshToken();
  const revokeMutation = useRevokeToken();
  const pkceMutation = useInitiatePkce();

  if (isError) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Zalo Token Management</h1>
        <div className="p-8 text-center text-red-500">Failed to load token status.</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Zalo Token Management</h1>
      <Card>
        <CardHeader>
          <CardTitle>Current Token Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <div className="space-y-2">
              <div className="h-6 w-32 bg-gray-200 rounded animate-pulse" />
              <div className="h-10 w-64 bg-gray-200 rounded animate-pulse" />
            </div>
          ) : (
            <>
              <div className="flex items-center gap-4">
                <Badge variant={data?.has_token ? "default" : "destructive"}>
                  {data?.has_token ? "Token Active" : "No Token"}
                </Badge>
                {data?.expires_at && (
                  <span className="text-sm text-gray-500">
                    Expires: {new Date(data.expires_at).toLocaleString()}
                  </span>
                )}
                {data?.oa_id && (
                  <span className="text-sm text-gray-400">OA: {data.oa_id}</span>
                )}
              </div>

              <div className="flex gap-2">
                <Button
                  onClick={async () => {
                    try {
                      const result = await pkceMutation.mutateAsync();
                      if (result.error) {
                        toast.error(result.error);
                        return;
                      }
                      if (result.oauth_url) {
                        window.open(result.oauth_url, "_blank");
                        toast.success("Authorization page opened. After authorizing, the token will be stored automatically.");
                      }
                    } catch {
                      toast.error("Failed to generate authorization URL");
                    }
                  }}
                  disabled={pkceMutation.isPending}
                >
                  {pkceMutation.isPending ? "Generating..." : "Get Authorization URL"}
                </Button>
                <Button
                  onClick={() => {
                    refreshMutation.mutate(undefined, {
                      onSuccess: () => toast.success("Token refreshed"),
                      onError: () => toast.error("Failed to refresh token"),
                    });
                  }}
                  disabled={refreshMutation.isPending || !data?.has_token}
                >
                  {refreshMutation.isPending ? "Refreshing..." : "Refresh Token"}
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => {
                    revokeMutation.mutate(undefined, {
                      onSuccess: () => toast.success("Token revoked"),
                      onError: () => toast.error("Failed to revoke token"),
                    });
                  }}
                  disabled={revokeMutation.isPending || !data?.has_token}
                >
                  {revokeMutation.isPending ? "Revoking..." : "Revoke Token"}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
