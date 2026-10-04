"use client";

import { useState } from "react";
import Chat from "@/components/Chat";
import Login from "@/components/Login";

export default function CustomerApp({ agentUrl }: { agentUrl: string }) {
  const [session, setSession] = useState<{ token: string; firstName?: string } | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  if (!session) {
    return (
      <Login
        agentUrl={agentUrl.replace(/\/$/, "")}
        sessionExpired={sessionExpired}
        onLogin={(token, firstName) => {
          setSession({ token, firstName });
          setSessionExpired(false);
        }}
      />
    );
  }

  return (
    <Chat
      agentUrl={agentUrl.replace(/\/$/, "")}
      token={session.token}
      firstName={session.firstName}
      onLogout={(expired = false) => {
        setSession(null);
        setSessionExpired(expired);
      }}
    />
  );
}
