import { NextResponse } from "next/server";
import { loadStateRecord } from "@/lib/repo";
import type { InterrogationAnswer } from "@/lib/types";

type InterrogateRequest = {
  stateId?: string;
  question?: string;
};

export async function POST(request: Request) {
  const body = (await request.json()) as InterrogateRequest;
  if (!body.stateId || !body.question) {
    return NextResponse.json({ error: "stateId and question are required" }, { status: 400 });
  }

  const state = await loadStateRecord(body.stateId);
  if (!state) {
    return NextResponse.json({ error: "State not found" }, { status: 404 });
  }

  const question = body.question.toLowerCase();
  if (question.includes("pokedex") || question.includes("seen")) {
    const answer: InterrogationAnswer = {
      status: "deferred",
      phase: "Phase 1 state-surface extension plus Phase 2 address promotion",
      answer:
        "Pokedex seen/owned bits are not part of the promoted state inspector yet, so this app cannot answer that safely.",
      evidence: [
        "Current snapshots expose map, mode, party, inventory, money, badges, facts, and warnings.",
        "TODO.md tracks Pokedex seen/owned reads as a lab UI follow-up.",
      ],
    };
    return NextResponse.json(answer);
  }

  const answer: InterrogationAnswer = {
    status: "answered",
    phase: "Phase 1 state summary",
    answer: "This state can answer basic inspected facts. Pokedex-specific questions are deferred.",
    evidence: [
      `Location: ${state.snapshot.position?.map_name ?? "unknown"}`,
      `Mode: ${state.snapshot.mode}`,
      `Party: ${state.snapshot.party.map((member) => member.species_name).join(", ") || "none"}`,
    ],
  };
  return NextResponse.json(answer);
}
