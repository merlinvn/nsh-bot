"use client";
import { useState } from "react";
import { useZaloTokenStatus, useRefreshToken, useRevokeToken, useInitiatePkce } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function TokensPage() {
  const { data, isLoading } = useZaloTokenStatus();
  const refreshMutation = useRefreshToken();
  const revokeMutation = useRevokeToken();
  const pkceMutation = useInitiatePkce();
  const [authUrl, setAuthUrl] = useState<string | null>(null);

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
          {authUrl && (
            <div className="p-3 bg-gray-100 rounded text-sm break-all">
              <p className="font-medium mb-1">Authorization URL:</p>
              <a href={authUrl} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
                {authUrl}
              </a>
            </div>
          )}
          <div className="flex gap-2">
            <Button
              onClick={async () => {
                const result = await pkceMutation.mutateAsync();
                setAuthUrl(result.authorization_url);
              }}
              disabled={pkceMutation.isPending}
            >
              Get Authorization URL
            </Button>
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
