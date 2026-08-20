import { NextResponse } from "next/server";
import { updateGeneratedApproval } from "@/lib/repo";

type ApprovalRequest = {
  reportPath?: string;
  status?: "approved" | "rejected";
  approvedBy?: string;
  notes?: string;
};

export async function POST(request: Request) {
  const body = (await request.json()) as ApprovalRequest;
  if (!body.reportPath || !body.status) {
    return NextResponse.json({ error: "reportPath and status are required" }, { status: 400 });
  }

  try {
    const state = await updateGeneratedApproval(body.reportPath, {
      status: body.status,
      approvedBy: body.approvedBy || "Joey",
      notes: body.notes || "",
    });
    return NextResponse.json(state);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Approval update failed" },
      { status: 500 },
    );
  }
}
