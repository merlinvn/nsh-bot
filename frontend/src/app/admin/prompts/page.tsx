"use client";
import { useState } from "react";
import { usePrompts, useCreatePrompt, useDeletePrompt } from "@/hooks/useApi";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { toast } from "sonner";

const PROMPT_TYPES = [
  { value: "system", label: "System Prompt", desc: "Main agent prompt — loaded at runtime", badge: "default" as const },
  { value: "tool_policy", label: "Tool Policy", desc: "Tool usage guidelines", badge: "secondary" as const },
  { value: "fallback", label: "Fallback", desc: "Response when agent fails", badge: "outline" as const },
];

export default function PromptsPage() {
  const { data, isLoading } = usePrompts();
  const createMutation = useCreatePrompt();
  const deleteMutation = useDeletePrompt();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newTemplate, setNewTemplate] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ name: string } | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName || !newTemplate.trim()) return;
    try {
      await createMutation.mutateAsync({
        name: newName,
        template: newTemplate.trim(),
      });
      toast.success(`Prompt "${newName}" created`);
      setShowCreate(false);
      setNewName("");
      setNewTemplate("");
    } catch {
      toast.error("Failed to create prompt");
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteMutation.mutateAsync(deleteTarget.name);
      toast.success(`Prompt "${deleteTarget.name}" deleted`);
      setDeleteTarget(null);
    } catch {
      toast.error("Failed to delete prompt");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Prompts</h1>
        <Button onClick={() => setShowCreate(true)}>Create Prompt</Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-12 bg-gray-100 rounded animate-pulse" />
              ))}
            </div>
          ) : data && data.length > 0 ? (
            <table className="w-full">
              <thead>
                <tr className="border-b bg-gray-50 text-left">
                  <th className="px-4 py-3 text-sm font-medium text-gray-500">Name</th>
                  <th className="px-4 py-3 text-sm font-medium text-gray-500">Type</th>
                  <th className="px-4 py-3 text-sm font-medium text-gray-500">Active Version</th>
                  <th className="px-4 py-3 text-sm font-medium text-gray-500">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.map((prompt) => {
                  const typeMeta = PROMPT_TYPES.find(t => t.value === prompt.name);
                  return (
                    <tr key={prompt.name} className="border-b hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <Link href={`/admin/prompts/${prompt.name}`} className="font-medium hover:underline">
                          {prompt.name}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        {typeMeta ? (
                          <Badge variant={typeMeta.badge}>{typeMeta.label}</Badge>
                        ) : (
                          <span className="text-sm text-gray-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm">v{prompt.active_version}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Link href={`/admin/prompts/${prompt.name}`}>
                            <Button variant="ghost" size="sm">Edit</Button>
                          </Link>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-500 hover:text-red-600"
                            onClick={() => setDeleteTarget({ name: prompt.name })}
                          >
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="p-8 text-center text-gray-400">No prompts yet. Create one to get started.</div>
          )}
        </CardContent>
      </Card>

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Prompt</DialogTitle>
            <DialogDescription>
              Only system, tool_policy, and fallback prompts are loaded by the conversation worker.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="name">Prompt Type</Label>
              <select
                id="name"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                required
              >
                <option value="">Select prompt type...</option>
                {PROMPT_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label} — {t.desc}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="template">Template</Label>
              <Textarea
                id="template"
                value={newTemplate}
                onChange={e => setNewTemplate(e.target.value)}
                rows={8}
                className="font-mono text-sm"
                placeholder="You are a helpful assistant..."
                required
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowCreate(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending || !newName || !newTemplate.trim()}>
                {createMutation.isPending ? "Creating..." : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Prompt</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &quot;{deleteTarget?.name}&quot;? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-red-500 hover:bg-red-600"
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
