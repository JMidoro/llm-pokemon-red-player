import { NextResponse } from "next/server";
import { updatePromotionReview } from "@/lib/repo";
import type { PromotionRecord } from "@/lib/types";

type PromotionStatusRequest = {
  promotionId?: string;
  status?: PromotionRecord["status"];
  reviewedBy?: string;
  notes?: string;
};

const validStatuses = new Set(["verified", "candidate", "needed", "blocked"]);

export async function POST(request: Request) {
  const body = (await request.json()) as PromotionStatusRequest;
  if (!body.promotionId || !body.status) {
    return NextResponse.json({ error: "promotionId and status are required" }, { status: 400 });
  }
  if (!validStatuses.has(body.status)) {
    return NextResponse.json({ error: "Invalid promotion status" }, { status: 400 });
  }

  try {
    const catalog = await updatePromotionReview({
      promotionId: body.promotionId,
      status: body.status,
      reviewedBy: body.reviewedBy || "Joey",
      notes: body.notes || "",
    });
    return NextResponse.json(catalog);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Promotion review update failed" },
      { status: 500 },
    );
  }
}
