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
  Users,
  X,
} from "lucide-react";

const navItems = [
  { href: "/admin/analytics", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/conversations", label: "Trò chuyện", icon: MessageSquare },
  { href: "/admin/prompts", label: "Prompts", icon: FileText },
  { href: "/admin/playground", label: "Playground", icon: Play },
  { href: "/admin/tokens", label: "Tokens", icon: Key },
  { href: "/admin/users", label: "Người dùng", icon: Users },
  { href: "/admin/monitoring", label: "Monitoring", icon: Activity },
];

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          "relative z-50 flex w-64 flex-col border-r bg-white transition-transform duration-300 ease-in-out",
          "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:h-screen",
          isOpen ? "max-md:translate-x-0" : "max-md:-translate-x-full"
        )}
      >
        {/* Mobile close button */}
        <div className="flex items-center justify-between border-b p-4 md:hidden">
          <h1 className="text-lg font-bold">NeoChat Admin</h1>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 hover:bg-gray-100 transition-colors"
            aria-label="Đóng menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Desktop logo */}
        <div className="hidden md:flex items-center border-b px-4 h-14">
          <h1 className="text-lg font-bold tracking-tight">NeoChat Admin</h1>
        </div>

        <nav className="flex-1 space-y-1 p-2 overflow-y-auto">
          {navItems.map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
