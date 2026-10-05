// A browser copy of the order in which agent/app/graph.py decides a dispute, so this page can run it: fraud first, then
// whether exactly one charge matches, then the charge's status, then its amount. The model never appears in this file.
// Left out on purpose: the classifier's low-confidence abstention and the rule that a vague report is proposed back to
// the customer before it is closed.
export type Status = "Declined" | "Reversed" | "Approved" | "Pending";
export type Matches = "one" | "several" | "none";
export type Outcome = "resolves" | "asks" | "person";
export type AgentId = "understand" | "decide" | "act" | "verify" | "escalate" | "respond";

export const THRESHOLD_USD = 500;
export const ORDER: AgentId[] = ["understand", "decide", "act", "verify", "escalate", "respond"];

export type Decision = {
  outcome: Outcome;
  stamp: string;
  reason: string;
  short: string;
  fraud: boolean;
  path: AgentId[];
};

export function decide(input: { status: Status; amount: number; matches: Matches; fraud: boolean }): Decision {
  const person = (reason: string, short: string): Decision => ({
    outcome: "person",
    stamp: "A person takes it",
    reason,
    short,
    fraud: input.fraud,
    path: ["understand", "decide", "escalate", "respond"],
  });

  if (input.fraud) return person("The customer says someone else used the card. Suspected fraud always goes to a person.", "Fraud reported: a person.");

  if (input.matches !== "one") {
    return {
      outcome: "asks",
      stamp: "Asks first",
      reason: input.matches === "none" ? "No charge matches the message, so it asks which one." : "Several charges match the message, so it asks which one.",
      short: input.matches === "none" ? "No match: it asks which." : "Several match: it asks which.",
      fraud: false,
      path: ["understand", "decide", "respond"],
    };
  }

  if (input.status === "Approved" || input.status === "Pending") {
    return person(`The charge is ${input.status}, so the money may have moved. A person decides.`, `${input.status}: a person.`);
  }

  if (input.amount >= THRESHOLD_USD) {
    return person(`USD ${input.amount.toFixed(2)} is at or over the USD ${THRESHOLD_USD} limit. A person decides.`, "Over USD 500: a person.");
  }

  return {
    outcome: "resolves",
    stamp: "Resolved",
    reason: `${input.status}, one charge, under USD ${THRESHOLD_USD}. Safe to close.`,
    short: "Safe: it can close.",
    fraud: false,
    path: ["understand", "decide", "act", "verify", "respond"],
  };
}
