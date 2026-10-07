import AdminApp from "@/components/admin/AdminApp";
import WakeGate from "@/components/WakeGate";

export const dynamic = "force-dynamic";

export default function AdminPage() {
  const agentUrl = process.env.AGENT_URL || process.env.NEXT_PUBLIC_AGENT_URL || "http://localhost:8001";
  const wakerUrl = (process.env.WAKER_URL || "").replace(/\/$/, "");
  return (
    <WakeGate wakerUrl={wakerUrl} agentUrl={agentUrl.replace(/\/$/, "")}>
      <AdminApp agentUrl={agentUrl.replace(/\/$/, "")} />
    </WakeGate>
  );
}
