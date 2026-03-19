import { useState } from "react";
import { createAnalysis, type ComplexityTier } from "../api/client";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";

export interface AnalysisInputPanelProps {
  onAnalysisCreated?: (data: {
    analysisId: string;
    companyName: string;
    complexityTier: ComplexityTier;
  }) => void;
}

export function AnalysisInputPanel({ onAnalysisCreated }: AnalysisInputPanelProps) {
  const [companyName, setCompanyName] = useState("");
  const [complexityTier, setComplexityTier] = useState<ComplexityTier | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    const trimmed = companyName.trim();
    if (!trimmed || loading) return;
    setError(null);
    setLoading(true);
    try {
      const res = await createAnalysis(trimmed);
      setComplexityTier(res.complexity_tier);
      onAnalysisCreated?.({
        analysisId: res.analysis_id,
        companyName: res.company_name,
        complexityTier: res.complexity_tier,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create analysis");
    } finally {
      setLoading(false);
    }
  }

  function getBadgeColor(tier: ComplexityTier) {
    switch (tier) {
      case "simple":
        return "bg-slate-500 hover:bg-slate-600 text-white";
      case "standard":
        return "bg-blue-500 hover:bg-blue-600 text-white";
      case "complex":
        return "bg-orange-500 hover:bg-orange-600 text-white";
      default:
        return "bg-secondary text-secondary-foreground";
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <input
        type="text"
        placeholder="Company name"
        value={companyName}
        onChange={(e) => setCompanyName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
        disabled={loading}
        className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      />
      <Button
        onClick={handleGenerate}
        disabled={!companyName.trim() || loading}
        className="w-full bg-primary text-primary-foreground hover:bg-primary/90"
      >
        {loading ? "Generating…" : "Generate Analysis"}
      </Button>
      {complexityTier && (
        <div className="flex justify-center">
          <Badge className={getBadgeColor(complexityTier)}>
            {complexityTier.charAt(0).toUpperCase() + complexityTier.slice(1)}
          </Badge>
        </div>
      )}
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
