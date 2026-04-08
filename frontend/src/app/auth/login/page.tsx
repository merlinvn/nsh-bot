"use client";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { LoginForm } from "@/components/forms/LoginForm";

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
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold">NeoChat Admin</h1>
          <p className="text-gray-500">Sign in to your admin account</p>
        </div>
        <LoginForm />
      </div>
    </div>
  );
}
