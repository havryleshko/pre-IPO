import { useCallback, useEffect, useState } from "react";
import { getAnalysis, type AnalysisOutputsResponse } from "./api/client";
import { AgentProgressPanel } from "./components/AgentProgressPanel";
import { AnalysisInputPanel } from "./components/AnalysisInputPanel";
import { FlagsPanel, type Flag } from "./components/FlagsPanel";
import { ReportPanels } from "./components/ReportPanels";
import { RecommendationSummaryPanel } from "./components/RecommendationSummaryPanel";
import { EvidencePanel } from "./components/EvidencePanel";

import { Separator } from "./components/ui/separator";

const POLL_INTERVAL_MS = 2000;

export function App() {
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisOutputsResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const fetchAnalysis = useCallback(async (id: string) => {
    try {
      setAnalysisError(null);
      const data = await getAnalysis(id);
      setAnalysis(data);
      return data;
    } catch (e) {
      setAnalysisError(e instanceof Error ? e.message : "Failed to fetch analysis");
      return null;
    }
  }, []);

  useEffect(() => {
    if (!analysisId) return;
    void fetchAnalysis(analysisId);
  }, [analysisId, fetchAnalysis]);

  useEffect(() => {
    if (!analysisId || !analysis) return;
    const status = analysis.status;
    if (status !== "pending" && status !== "running") return;
    const t = setInterval(() => void fetchAnalysis(analysisId), POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [analysisId, analysis?.status, fetchAnalysis]);

  function handleAnalysisCreated(data: { analysisId: string }) {
    setAnalysisId(data.analysisId);
  }

  function handleFlagsConfirm() {
    if (analysisId) void fetchAnalysis(analysisId);
  }

  const flags = (analysis?.flags ?? []) as Flag[];

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="flex w-[30%] min-w-0 flex-col gap-6 bg-card p-[24px]">
        <h1 className="text-[12px] font-medium uppercase tracking-wider text-muted-foreground">
          IPO Intelligence
        </h1>
        <AnalysisInputPanel onAnalysisCreated={handleAnalysisCreated} />
        <Separator className="bg-border" />
        <AgentProgressPanel
          analysisId={analysisId}
          lastCompletedAgent={analysis?.last_completed_agent}
        />
        <Separator className="bg-border" />
        <FlagsPanel
          analysisId={analysisId}
          flags={flags}
          exportLocked={analysis?.export_locked ?? true}
          onConfirm={handleFlagsConfirm}
        />
      </aside>
      <main className="flex w-[70%] min-w-0 flex-col gap-6 p-[24px]">
        <RecommendationSummaryPanel
          recommendationOutput={analysis?.recommendation_output ?? null}
          parserOutput={analysis?.parser_output ?? null}
        />
        <EvidencePanel
          parserOutput={analysis?.parser_output ?? null}
          recommendationOutput={analysis?.recommendation_output ?? null}
          harvesterOutput={analysis?.harvester_output ?? null}
          flags={flags}
        />
        <ReportPanels
          analysisId={analysisId}
          exportLocked={analysis?.export_locked ?? true}
          recommendationOutput={analysis?.recommendation_output ?? null}
        />
        {analysisError && (
          <p className="text-sm text-destructive" role="alert">
            {analysisError}
          </p>
        )}
      </main>
    </div>
  );
}
