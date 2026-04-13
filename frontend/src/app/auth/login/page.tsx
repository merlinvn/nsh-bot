"use client";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { LoginForm } from "@/components/forms/LoginForm";
import { MessageSquare } from "lucide-react";

export default function LoginPage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/admin/analytics");
    }
  }, [user, isLoading, router]);

  if (isLoading) return null;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-sm">
            <MessageSquare className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">NeoChat Admin</h1>
          <p className="mt-1 text-gray-500 text-sm">Đăng nhập để quản lý hệ thống</p>
        </div>
        <LoginForm />
      </div>
    </div>
  );
}
