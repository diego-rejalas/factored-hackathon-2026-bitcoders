import CustomerApp from "@/components/CustomerApp";
import WakeGate from "@/components/WakeGate";

// Runtime (not build-time) agent URL: the page renders per request so the
// same image works against Railway or GCP — just set AGENT_URL on the host.
export const dynamic = "force-dynamic";

export default function Home() {
  const agentUrl = process.env.AGENT_URL || process.env.NEXT_PUBLIC_AGENT_URL || "http://localhost:8001";
  // WAKER_URL is set only where the demo sleeps (the waker behind the load balancer); empty means no waiting screen.
  const wakerUrl = (process.env.WAKER_URL || "").replace(/\/$/, "");
  return (
    <WakeGate wakerUrl={wakerUrl} agentUrl={agentUrl.replace(/\/$/, "")}>
      <CustomerApp agentUrl={agentUrl} />
    </WakeGate>
  );
}
