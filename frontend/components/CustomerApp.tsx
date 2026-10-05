"use client";

import { useState } from "react";
import Chat from "@/components/Chat";
import Login from "@/components/Login";
import type { Language } from "@/lib/types";

export default function CustomerApp({ agentUrl }: { agentUrl: string }) {
  const [session, setSession] = useState<{ token: string; firstName?: string; language?: Language } | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  if (!session) {
    return (
      <Login
        agentUrl={agentUrl.replace(/\/$/, "")}
        sessionExpired={sessionExpired}
        onLogin={(token, firstName, language) => {
          setSession({ token, firstName, language });
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
      initialLanguage={session.language}
      onLogout={(expired = false) => {
        setSession(null);
        setSessionExpired(expired);
      }}
    />
  );
}
