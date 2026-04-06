"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

interface PromptFormProps {
  onSubmit: (template: string) => void;
  initialValue?: string;
  isLoading?: boolean;
}

export function PromptForm({ onSubmit, initialValue = "", isLoading }: PromptFormProps) {
  const [template, setTemplate] = useState(initialValue);

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="template">Prompt Template</Label>
        <Textarea
          id="template"
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          rows={10}
          className="font-mono text-sm"
        />
      </div>
      <Button onClick={() => onSubmit(template)} disabled={isLoading}>
        {isLoading ? "Saving..." : "Save New Version"}
      </Button>
    </div>
  );
}
