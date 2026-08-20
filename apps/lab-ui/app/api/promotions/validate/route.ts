import { NextResponse } from "next/server";
import { validatePromotionManifest } from "@/lib/repo";

type PromotionValidationRequest = {
  promotionId?: string;
};

export async function POST(request: Request) {
  const body = (await request.json()) as PromotionValidationRequest;

  try {
    const result = await validatePromotionManifest(body.promotionId);
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Promotion validation failed" },
      { status: 500 },
    );
  }
}
