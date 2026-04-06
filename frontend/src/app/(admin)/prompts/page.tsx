"use client";
import { usePrompts } from "@/hooks/useApi";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function PromptsPage() {
  const { data, isLoading } = usePrompts();

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Prompts</h1>
      </div>
      <Card>
        <CardContent className="p-0">
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
              {data?.map((prompt) => (
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
          {(!data || data.length === 0) && <div className="p-8 text-center text-gray-400">No prompts</div>}
        </CardContent>
      </Card>
    </div>
  );
}
