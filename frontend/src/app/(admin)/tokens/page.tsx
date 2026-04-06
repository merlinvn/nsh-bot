"use client";
import { useZaloTokenStatus, useRefreshToken, useRevokeToken } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function TokensPage() {
  const { data, isLoading } = useZaloTokenStatus();
  const refreshMutation = useRefreshToken();
  const revokeMutation = useRevokeToken();

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Zalo Token Management</h1>
      <Card>
        <CardHeader>
          <CardTitle>Current Token Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <Badge variant={data?.has_token ? "default" : "destructive"}>
              {data?.has_token ? "Token Active" : "No Token"}
            </Badge>
            {data?.expires_at && (
              <span className="text-sm text-gray-500">
                Expires: {new Date(data.expires_at).toLocaleString()}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              onClick={() => refreshMutation.mutate()}
              disabled={refreshMutation.isPending || !data?.has_token}
            >
              Refresh Token
            </Button>
            <Button
              variant="destructive"
              onClick={() => revokeMutation.mutate()}
              disabled={revokeMutation.isPending || !data?.has_token}
            >
              Revoke Token
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
