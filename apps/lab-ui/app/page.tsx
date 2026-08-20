import { Dashboard } from "@/components/Dashboard";
import {
  loadDirectiveDeck,
  loadPromotionCatalog,
  loadSkillCatalog,
  loadSkillStateRecords,
  loadStateRecords,
} from "@/lib/repo";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [directiveDeck, states, skillCatalog, skillStates, promotionCatalog] = await Promise.all([
    loadDirectiveDeck(),
    loadStateRecords(),
    loadSkillCatalog(),
    loadSkillStateRecords(),
    loadPromotionCatalog(),
  ]);

  return (
    <Dashboard
      directiveDeck={directiveDeck}
      states={states}
      skillCatalog={skillCatalog}
      skillStates={skillStates}
      promotionCatalog={promotionCatalog}
    />
  );
}
