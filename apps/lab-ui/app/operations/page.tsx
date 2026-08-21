import type { Metadata } from "next";
import OperationsDashboard from "./OperationsDashboard";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Pokemon Player Operations",
  description: "Private remote supervision for local Pokemon Player runs.",
};

export default function OperationsPage() {
  return <OperationsDashboard />;
}
