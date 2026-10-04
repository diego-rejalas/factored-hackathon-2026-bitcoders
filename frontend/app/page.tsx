import CustomerApp from "@/components/CustomerApp";

// Runtime (not build-time) agent URL: the page renders per request so the
// same image works against Railway or GCP — just set AGENT_URL on the host.
export const dynamic = "force-dynamic";

export default function Home() {
  const agentUrl = process.env.AGENT_URL || process.env.NEXT_PUBLIC_AGENT_URL || "http://localhost:8001";
  return <CustomerApp agentUrl={agentUrl} />;
}
