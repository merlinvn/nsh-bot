"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  Play,
  Key,
  Activity,
} from "lucide-react";

const navItems = [
  { href: "/admin/analytics", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/conversations", label: "Conversations", icon: MessageSquare },
  { href: "/admin/prompts", label: "Prompts", icon: FileText },
  { href: "/admin/playground", label: "Playground", icon: Play },
  { href: "/admin/tokens", label: "Tokens", icon: Key },
  { href: "/admin/monitoring", label: "Monitoring", icon: Activity },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-64 flex-col border-r bg-white">
      <div className="border-b p-4">
        <h1 className="text-lg font-bold">NeoChat Admin</h1>
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive ? "bg-gray-100 text-gray-900" : "text-gray-600 hover:bg-gray-50"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
