"use client";
import { useState } from "react";
import { usePrompts, useCreatePrompt } from "@/hooks/useApi";
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
import Link from "next/link";

export default function PromptsPage() {
  const { data, isLoading } = usePrompts();
  const createMutation = useCreatePrompt();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newTemplate, setNewTemplate] = useState("");

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !newTemplate.trim()) return;
    await createMutation.mutateAsync({
      name: newName.trim(),
      description: newDescription.trim() || undefined,
      template: newTemplate.trim(),
    });
    setShowCreate(false);
    setNewName("");
    setNewDescription("");
    setNewTemplate("");
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
                  <th className="px-4 py-3 text-sm font-medium text-gray-500">Description</th>
                  <th className="px-4 py-3 text-sm font-medium text-gray-500">Active Version</th>
                  <th className="px-4 py-3 text-sm font-medium text-gray-500">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.map((prompt) => (
                  <tr key={prompt.name} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <Link href={`/admin/prompts/${prompt.name}`} className="font-medium hover:underline">
                        {prompt.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{prompt.description || "—"}</td>
                    <td className="px-4 py-3 text-sm">v{prompt.active_version}</td>
                    <td className="px-4 py-3">
                      <Link href={`/admin/prompts/${prompt.name}`}>
                        <Button variant="ghost" size="sm">Edit</Button>
                      </Link>
                    </td>
                  </tr>
                ))}
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
            <DialogDescription>Create a new prompt with an initial template.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g., customer-support"
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="description">Description (optional)</Label>
              <Input
                id="description"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="Brief description of this prompt"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="template">Template</Label>
              <Textarea
                id="template"
                value={newTemplate}
                onChange={(e) => setNewTemplate(e.target.value)}
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
              <Button type="submit" disabled={createMutation.isPending || !newName.trim() || !newTemplate.trim()}>
                {createMutation.isPending ? "Creating..." : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
