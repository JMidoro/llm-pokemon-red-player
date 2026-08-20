import { NextResponse } from "next/server";
import { loadStateRecord } from "@/lib/repo";

type StateRecordRequest = {
  stateId?: string;
};

export async function POST(request: Request) {
  const body = (await request.json()) as StateRecordRequest;
  if (!body.stateId) {
    return NextResponse.json({ error: "stateId is required" }, { status: 400 });
  }
  const state = await loadStateRecord(body.stateId);
  if (!state) {
    return NextResponse.json({ error: "State not found" }, { status: 404 });
  }
  return NextResponse.json(state);
}
