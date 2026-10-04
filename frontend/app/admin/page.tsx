import AdminApp from "@/components/admin/AdminApp";

export const dynamic = "force-dynamic";

export default function AdminPage() {
  const agentUrl = process.env.AGENT_URL || process.env.NEXT_PUBLIC_AGENT_URL || "http://localhost:8001";
  return <AdminApp agentUrl={agentUrl.replace(/\/$/, "")} />;
}
