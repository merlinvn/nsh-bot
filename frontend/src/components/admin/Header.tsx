"use client";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { LogOut } from "lucide-react";

export function Header() {
  const { user, logout } = useAuth();
  return (
    <header className="flex h-14 items-center justify-between border-b bg-white px-6">
      <div className="text-sm text-gray-500">Welcome, {user?.username}</div>
      <Button variant="ghost" size="sm" onClick={logout}>
        <LogOut className="mr-2 h-4 w-4" />
        Logout
      </Button>
    </header>
  );
}
