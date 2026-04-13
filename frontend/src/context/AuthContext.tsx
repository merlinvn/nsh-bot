"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AdminUser } from "@/types/api";

interface AuthContextValue {
  user: AdminUser | null;
  csrfToken: string | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    api.get<AdminUser>("/api/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    const res = await api.post<{ ok: boolean; user: AdminUser; csrf_token: string }>(
      "/api/auth/login",
      { username, password }
    );
    setUser(res.user);
    setCsrfToken(res.csrf_token);
  };

  const logout = async () => {
    await api.post("/api/auth/logout");
    setUser(null);
    setCsrfToken(null);
  };

  return (
    <AuthContext.Provider value={{ user, csrfToken, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
