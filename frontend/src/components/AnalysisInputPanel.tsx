import { useState } from "react";
import { createAnalysis, type ComplexityTier } from "../api/client";

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
      <button
        type="button"
        onClick={handleGenerate}
        disabled={!companyName.trim() || loading}
        className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
      >
        {loading ? "Generating…" : "Generate Analysis"}
      </button>
      {complexityTier && (
        <span className="inline-flex w-fit items-center rounded-md border border-transparent bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground">
          {complexityTier.charAt(0).toUpperCase() + complexityTier.slice(1)}
        </span>
      )}
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
