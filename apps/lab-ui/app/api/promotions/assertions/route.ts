import { NextResponse } from "next/server";
import { validatePromotionAssertions } from "@/lib/repo";

type PromotionAssertionRequest = {
  promotionId?: string;
};

export async function POST(request: Request) {
  const body = (await request.json()) as PromotionAssertionRequest;

  try {
    const result = await validatePromotionAssertions(body.promotionId);
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Promotion assertion validation failed" },
      { status: 500 },
    );
  }
}
