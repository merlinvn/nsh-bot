"use client";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { LogOut, Menu } from "lucide-react";

interface HeaderProps {
  onMenuClick?: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const { user, logout } = useAuth();
  return (
    <header className="flex h-14 items-center justify-between border-b bg-white px-4 gap-4">
      <div className="flex items-center gap-3">
        {/* Mobile hamburger */}
        <button
          onClick={onMenuClick}
          className="rounded-lg p-2 hover:bg-gray-100 transition-colors md:hidden"
          aria-label="Mở menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="text-sm text-gray-500">
          <span className="hidden sm:inline">Xin chào, </span>
          <span className="font-medium text-gray-900">{user?.username}</span>
        </div>
      </div>
      <Button variant="ghost" size="sm" onClick={logout} className="text-gray-500 hover:text-gray-900">
        <LogOut className="h-4 w-4 sm:mr-2" />
        <span className="hidden sm:inline">Đăng xuất</span>
      </Button>
    </header>
  );
}
