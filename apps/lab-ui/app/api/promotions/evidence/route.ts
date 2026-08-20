import { NextResponse } from "next/server";
import { addPromotionEvidence } from "@/lib/repo";

type PromotionEvidenceRequest = {
  promotionId?: string;
  reference?: {
    id?: string;
    label?: string;
    kind?: string;
    metadataPath?: string | null;
    statePath?: string | null;
    screenshotPath?: string | null;
    captureCommand?: string | null;
    expectedObservation?: string;
    notes?: string | null;
  };
};

export async function POST(request: Request) {
  const body = (await request.json()) as PromotionEvidenceRequest;
  if (!body.promotionId || !body.reference?.label) {
    return NextResponse.json({ error: "promotionId and reference.label are required" }, { status: 400 });
  }

  try {
    const catalog = await addPromotionEvidence({
      promotionId: body.promotionId,
      reference: {
        ...body.reference,
        label: body.reference.label,
        kind: body.reference.kind || "reference",
      },
    });
    return NextResponse.json(catalog);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Promotion evidence update failed" },
      { status: 500 },
    );
  }
}
