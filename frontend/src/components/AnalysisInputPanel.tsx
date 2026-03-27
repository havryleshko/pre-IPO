import { useState } from "react";
import { createAnalysis, type ComplexityTier } from "../api/client";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";

export interface AnalysisInputPanelProps {
  onAnalysisStarting?: () => void;
  onAnalysisCreated?: (data: {
    analysisId: string;
    companyName: string;
    complexityTier: ComplexityTier;
  }) => void;
  complexityTier?: ComplexityTier | null;
}

export function AnalysisInputPanel({ onAnalysisStarting, onAnalysisCreated, complexityTier }: AnalysisInputPanelProps) {
  const [companyName, setCompanyName] = useState("");
  const [createdComplexityTier, setCreatedComplexityTier] = useState<ComplexityTier | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    const trimmed = companyName.trim();
    if (!trimmed || loading) return;
    setError(null);
    setCreatedComplexityTier(null);
    setLoading(true);
    onAnalysisStarting?.();
    try {
      const res = await createAnalysis(trimmed);
      setCreatedComplexityTier(res.complexity_tier);
      onAnalysisCreated?.({
        analysisId: res.analysis_id,
        companyName: res.company_name,
        complexityTier: res.complexity_tier,
      });
      setCompanyName(""); // Clear input on success
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create analysis");
    } finally {
      setLoading(false);
    }
  }

  const displayedComplexityTier = complexityTier ?? createdComplexityTier;

  function getBadgeColor(tier: ComplexityTier) {
    switch (tier) {
      case "simple":
        return "bg-slate-100 hover:bg-slate-200 text-slate-700 border-none shadow-none font-medium";
      case "standard":
        return "bg-blue-100 hover:bg-blue-200 text-blue-700 border-none shadow-none font-medium";
      case "complex":
        return "bg-orange-100 hover:bg-orange-200 text-orange-700 border-none shadow-none font-medium";
      default:
        return "bg-secondary text-secondary-foreground border-none shadow-none font-medium";
    }
  }

  return (
    <div className="flex items-center gap-3">
      <div className="relative flex items-center w-full max-w-sm">
        <input
          type="text"
          placeholder="Search company..."
          value={companyName}
          onChange={(e) => setCompanyName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
          disabled={loading}
          className="h-9 w-full rounded-full border border-border bg-muted/30 px-4 py-1 pr-24 text-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:bg-background disabled:cursor-not-allowed disabled:opacity-50"
        />
        <Button
          size="sm"
          onClick={handleGenerate}
          disabled={!companyName.trim() || loading}
          className="absolute right-1 h-7 rounded-full px-3 text-xs font-medium"
        >
          {loading ? "..." : "Generate"}
        </Button>
      </div>
      {displayedComplexityTier && (
        <Badge className={getBadgeColor(displayedComplexityTier)}>
          {displayedComplexityTier.charAt(0).toUpperCase() + displayedComplexityTier.slice(1)}
        </Badge>
      )}
      {error && (
        <p className="absolute top-14 text-xs text-destructive font-medium" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
