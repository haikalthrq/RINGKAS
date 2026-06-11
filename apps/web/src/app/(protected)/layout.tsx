import type { ReactNode } from "react";
import { ProtectedGuard } from "@/components/protected-guard";

export default function ProtectedLayout({ children }: { children: ReactNode }) {
  return <ProtectedGuard>{children}</ProtectedGuard>;
}
