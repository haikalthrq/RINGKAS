import { AdminRoleGuard } from "@/components/protected-guard";

export default function AdminPage() {
  return <AdminRoleGuard><section className="page-card"><p className="eyebrow">Admin</p><h1>Admin access</h1><p>Only admin and system maintainer roles can view this route.</p></section></AdminRoleGuard>;
}
