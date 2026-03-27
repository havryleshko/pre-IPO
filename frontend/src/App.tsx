import { useCallback, useEffect, useRef, useState } from "react";
import { getAnalysis, type AnalysisOutputsResponse } from "./api/client";
import { AgentProgressPanel } from "./components/AgentProgressPanel";
import { AnalysisInputPanel } from "./components/AnalysisInputPanel";
import { InvestorBriefPanel } from "./components/InvestorBriefPanel";

import { Separator } from "./components/ui/separator";

const POLL_INTERVAL_MS = 2000;

export function App() {
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisOutputsResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const activeAnalysisIdRef = useRef<string | null>(null);

  const fetchAnalysis = useCallback(async (id: string) => {
    try {
      if (activeAnalysisIdRef.current === id) {
        setAnalysisError(null);
      }
      const data = await getAnalysis(id);
      if (activeAnalysisIdRef.current === id) {
        setAnalysis(data);
      }
      return data;
    } catch (e) {
      if (activeAnalysisIdRef.current === id) {
        setAnalysisError(e instanceof Error ? e.message : "Failed to fetch analysis");
      }
      return null;
    }
  }, []);

  useEffect(() => {
    activeAnalysisIdRef.current = analysisId;
    if (!analysisId) {
      setAnalysis(null);
      setAnalysisError(null);
      return;
    }
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
    activeAnalysisIdRef.current = data.analysisId;
    setAnalysis(null);
    setAnalysisError(null);
    setAnalysisId(data.analysisId);
  }

  function handleAnalysisStarting() {
    activeAnalysisIdRef.current = null;
    setAnalysisId(null);
    setAnalysis(null);
    setAnalysisError(null);
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="sticky top-0 z-10 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-14 max-w-5xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded bg-primary text-primary-foreground flex items-center justify-center font-bold text-xs">
              P
            </div>
            <h1 className="text-sm font-semibold tracking-tight">
              pre-IPO
            </h1>
          </div>
          <div className="flex-1 max-w-md mx-8">
            <AnalysisInputPanel
              onAnalysisStarting={handleAnalysisStarting}
              onAnalysisCreated={handleAnalysisCreated}
              complexityTier={analysis?.complexity_tier ?? null}
            />
          </div>
          <div className="w-8"></div> {/* Spacer for symmetry */}
        </div>
      </header>

      <main className="flex-1 container mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
        {!analysisId && !analysisError && (
          <div className="flex h-[50vh] flex-col items-center justify-center text-center text-muted-foreground fade-in animate-in">
            <div className="h-12 w-12 rounded-xl bg-muted/50 flex items-center justify-center mb-4">
              <span className="text-xl font-semibold opacity-50">?</span>
            </div>
            <h2 className="text-lg font-medium text-foreground mb-2">Ready to analyze</h2>
            <p className="max-w-sm text-sm">
              Search for a company above to generate a concise pre-IPO research brief.
            </p>
          </div>
        )}

        {analysisId && (
          <div className="fade-in animate-in slide-in-from-bottom-4 duration-500">
            {(!analysis || analysis.status === "pending" || analysis.status === "running") ? (
              <div className="mb-12">
                <AgentProgressPanel
                  key={`agents-${analysisId}`}
                  analysisId={analysisId}
                  lastCompletedAgent={analysis?.last_completed_agent}
                />
              </div>
            ) : null}

            {analysis?.status === "failed" && (
              <div className="mb-12 rounded-lg border border-destructive/20 bg-destructive/5 p-6 text-center">
                <h3 className="text-sm font-bold tracking-widest uppercase text-destructive mb-2">Generation Failed</h3>
                <p className="text-sm font-medium text-destructive/80">
                  The analysis pipeline encountered an error. Please check your backend logs or API keys.
                </p>
              </div>
            )}

            <InvestorBriefPanel
              key={`summary-${analysisId}`}
              investorBrief={analysis?.investor_brief ?? null}
            />
          </div>
        )}

        {analysisError && (
          <div className="mt-8 rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-center">
            <p className="text-sm font-medium text-destructive" role="alert">
              {analysisError}
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
