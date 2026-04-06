"use client";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface StatusBadgeProps {
  status: string;
  variant?: "default" | "success" | "warning" | "destructive" | "outline";
}

export function StatusBadge({ status, variant = "default" }: StatusBadgeProps) {
  const getVariant = (): "default" | "secondary" | "destructive" | "outline" => {
    switch (status.toLowerCase()) {
      case "active":
      case "ok":
      case "completed":
      case "success":
        return "default";
      case "pending":
      case "running":
        return "secondary";
      case "failed":
      case "error":
      case "destructive":
        return "destructive";
      default:
        return "outline";
    }
  };

  return (
    <Badge variant={getVariant()} className={cn(variant === "destructive" && "bg-red-500")}>
      {status}
    </Badge>
  );
}
