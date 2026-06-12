"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { apiRequest } from "@/lib/api-client";
import type { AuthStatus, CurrentUser } from "@/lib/auth-types";

interface AuthContextValue {
  status: AuthStatus;
  currentUser: CurrentUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  hasAnyRole: (...roles: string[]) => boolean;
  setCurrentUser: (user: CurrentUser | null) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [currentUser, setCurrentUserState] = useState<CurrentUser | null>(null);
  const requestId = useRef(0);

  function commitSession(user: CurrentUser | null) {
    requestId.current += 1;
    const authenticatedUser = user?.authenticated ? user : null;
    setCurrentUserState(authenticatedUser);
    setStatus(authenticatedUser ? "authenticated" : "unauthenticated");
  }

  useEffect(() => {
    const controller = new AbortController();
    const currentRequest = ++requestId.current;
    apiRequest<CurrentUser>("/api/auth/me", { signal: controller.signal })
      .then((user) => {
        if (!controller.signal.aborted && requestId.current === currentRequest) commitSession(user);
      })
      .catch(() => {
        if (!controller.signal.aborted && requestId.current === currentRequest) commitSession(null);
      });
    return () => controller.abort();
  }, []);

  return (
    <AuthContext.Provider value={{
      status,
      currentUser,
      isLoading: status === "loading",
      isAuthenticated: status === "authenticated" && currentUser?.authenticated === true,
      hasAnyRole: (...roles) => roles.some((role) => currentUser?.roles.includes(role)),
      setCurrentUser: commitSession
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
