"use client";
import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useUpdatePrompt, useActivatePromptVersion } from "@/hooks/useApi";
import { PromptForm } from "@/components/forms/PromptForm";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import type { PromptVersion } from "@/types/api";

export default function PromptDetailPage() {
  const params = useParams();
  const name = params.name as string;
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<PromptVersion | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["prompt", name],
    queryFn: () => api.get<{ name: string; description: string | null; active_version: number }>(`/admin/prompts/${name}`),
  });

  const { data: versions } = useQuery({
    queryKey: ["prompt-versions", name],
    queryFn: () => api.get<PromptVersion[]>(`/admin/prompts/${name}/versions`),
  });

  const updatePrompt = useUpdatePrompt(name);
  const activateVersion = useActivatePromptVersion(name);

  const handleUpdate = async (template: string) => {
    try {
      await updatePrompt.mutateAsync({ template });
      toast.success("New version created");
      setIsEditing(false);
    } catch {
      toast.error("Failed to update prompt");
    }
  };

  const handleActivate = async (version: number) => {
    try {
      await activateVersion.mutateAsync(version);
      toast.success(`Version ${version} activated`);
    } catch {
      toast.error("Failed to activate version");
    }
  };

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{name}</h1>
          {data?.description && (
            <p className="text-gray-500 mt-1">{data.description}</p>
          )}
        </div>
        <Button onClick={() => setIsEditing(!isEditing)} variant={isEditing ? "outline" : "default"}>
          {isEditing ? "Cancel" : "Edit Template"}
        </Button>
      </div>

      {isEditing && (
        <Card>
          <CardHeader>
            <CardTitle>Create New Version</CardTitle>
          </CardHeader>
          <CardContent>
            <PromptForm
              onSubmit={handleUpdate}
              initialValue={versions?.find(v => v.active)?.template}
              isLoading={updatePrompt.isPending}
            />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Version History</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {!versions || versions.length === 0 ? (
            <div className="p-6 text-center text-gray-400">No version history</div>
          ) : (
            <div className="divide-y">
              {[...versions].reverse().map((v) => (
                <div
                  key={v.version}
                  className={`p-4 hover:bg-gray-50 cursor-pointer ${selectedVersion?.version === v.version ? "bg-gray-50" : ""}`}
                  onClick={() => setSelectedVersion(selectedVersion?.version === v.version ? null : v)}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">Version {v.version}</span>
                      {v.active && <Badge variant="default" className="text-xs">Active</Badge>}
                      <span className="text-sm text-gray-400">
                        {new Date(v.created_at).toLocaleString()}
                      </span>
                    </div>
                    {!v.active && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleActivate(v.version);
                        }}
                        disabled={activateVersion.isPending}
                      >
                        Activate
                      </Button>
                    )}
                  </div>
                  {selectedVersion?.version === v.version && (
                    <div className="mt-3 p-3 bg-gray-900 rounded-md">
                      <pre className="text-sm text-gray-100 whitespace-pre-wrap font-mono overflow-x-auto">
                        {v.template}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
