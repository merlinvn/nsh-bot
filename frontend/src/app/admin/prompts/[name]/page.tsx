"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useParams } from "next/navigation";
import { PromptForm } from "@/components/forms/PromptForm";
import { Button } from "@/components/ui/button";
import { useState } from "react";

export default function PromptDetailPage() {
  const params = useParams();
  const name = params.name as string;
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["prompt", name],
    queryFn: () => api.get<{ name: string; description: string | null; active_version: number }>(`/admin/prompts/${name}`),
  });

  const { data: versions } = useQuery({
    queryKey: ["prompt-versions", name],
    queryFn: () => api.get<{ version: number; created_at: string }[]>(`/admin/prompts/${name}/versions`),
    enabled: !!name && isEditing,
  });

  const updateMutation = useMutation({
    mutationFn: (template: string) => api.put(`/admin/prompts/${name}`, { template }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      queryClient.invalidateQueries({ queryKey: ["prompt", name] });
      setIsEditing(false);
    },
  });

  const activateMutation = useMutation({
    mutationFn: (version: number) => api.post(`/admin/prompts/${name}/activate`, { version }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      queryClient.invalidateQueries({ queryKey: ["prompt", name] });
      queryClient.invalidateQueries({ queryKey: ["prompt-versions", name] });
    },
  });

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Prompt: {name}</h1>
        {!isEditing && (
          <Button onClick={() => setIsEditing(true)}>Edit Template</Button>
        )}
      </div>
      {data && (
        <p className="text-gray-500">{data.description || "No description"}</p>
      )}
      {isEditing ? (
        <PromptForm
          onSubmit={(template) => updateMutation.mutate(template)}
          isLoading={updateMutation.isPending}
        />
      ) : (
        <div className="text-gray-400">Click &quot;Edit Template&quot; to modify this prompt</div>
      )}
      {versions && versions.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-lg font-medium">Version History</h2>
          {versions.map((v) => (
            <div key={v.version} className="flex items-center justify-between border rounded p-3">
              <div>
                <span className="font-medium">Version {v.version}</span>
                <span className="ml-2 text-sm text-gray-500">{new Date(v.created_at).toLocaleString()}</span>
              </div>
              {data && v.version !== data.active_version && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => activateMutation.mutate(v.version)}
                  disabled={activateMutation.isPending}
                >
                  Activate
                </Button>
              )}
              {data && v.version === data.active_version && (
                <span className="text-sm text-green-600 font-medium">Active</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
