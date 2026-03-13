import { useState } from "react";
import { exportFullReportPdf, exportSummaryPdf } from "../api/client";

interface TwitterSentiment {
  positive?: number;
  negative?: number;
  neutral?: number;
}

interface HarvesterOutput {
  sources_active?: string[];
  harvested_at?: string;
  twitter_data?: { sentiment_score?: TwitterSentiment };
}

export interface ReportPanelsProps {
  analysisId: string | null;
  exportLocked: boolean;
  recommendationOutput?: { plain_english_summary?: string; recommendations?: { realistic?: { client_paragraph?: string } } } | null;
  harvesterOutput?: HarvesterOutput | null;
  onSave?: (customName: string) => void;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ReportPanels({
  analysisId,
  exportLocked,
  recommendationOutput,
  harvesterOutput,
  onSave,
}: ReportPanelsProps) {
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [exportLoading, setExportLoading] = useState<"summary" | "full" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const plainSummary = recommendationOutput?.plain_english_summary ?? "";
  const clientParagraph = recommendationOutput?.recommendations?.realistic?.client_paragraph ?? "";
  const twitterData = harvesterOutput?.twitter_data;
  const sentiment = twitterData?.sentiment_score;
  const sourcesActive = harvesterOutput?.sources_active ?? [];
  const harvestedAt = harvesterOutput?.harvested_at;

  async function handleExportSummary() {
    if (!analysisId || exportLocked) return;
    setExportError(null);
    setExportLoading("summary");
    try {
      const blob = await exportSummaryPdf(analysisId);
      downloadBlob(blob, "ipo_summary.pdf");
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExportLoading(null);
    }
  }

  async function handleExportFull() {
    if (!analysisId || exportLocked) return;
    setExportError(null);
    setExportLoading("full");
    try {
      const blob = await exportFullReportPdf(analysisId);
      downloadBlob(blob, "ipo_full_report.pdf");
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExportLoading(null);
    }
  }

  function handleCopyParagraph() {
    if (!clientParagraph) return;
    void navigator.clipboard.writeText(clientParagraph);
  }

  function handleSave() {
    const name = saveName.trim();
    if (name) {
      onSave?.(name);
      setSaveDialogOpen(false);
      setSaveName("");
    }
  }

  const pos = sentiment?.positive ?? 0;
  const neg = sentiment?.negative ?? 0;
  const neu = sentiment?.neutral ?? 0;
  const total = pos + neg + neu || 1;

  return (
    <div className="flex flex-col gap-4">
      {plainSummary && (
        <div>
          <button
            type="button"
            onClick={() => setSummaryOpen((o) => !o)}
            className="flex w-full items-center justify-between text-left text-sm font-medium"
          >
            Plain-English summary
            <span className="text-muted-foreground">{summaryOpen ? "−" : "+"}</span>
          </button>
          {summaryOpen && (
            <div className="mt-2 rounded-md border border-border bg-muted/30 p-3 text-sm">
              {plainSummary}
            </div>
          )}
        </div>
      )}

      {sentiment && (
        <div>
          <div className="mb-1 text-xs font-medium text-muted-foreground">X/Twitter sentiment</div>
          <div className="flex h-6 overflow-hidden rounded-md border border-border">
            <div
              className="bg-green-500"
              style={{ width: `${(pos / total) * 100}%` }}
              title={`Positive ${((pos / total) * 100).toFixed(0)}%`}
            />
            <div
              className="bg-gray-400"
              style={{ width: `${(neu / total) * 100}%` }}
              title={`Neutral ${((neu / total) * 100).toFixed(0)}%`}
            />
            <div
              className="bg-red-500"
              style={{ width: `${(neg / total) * 100}%` }}
              title={`Negative ${((neg / total) * 100).toFixed(0)}%`}
            />
          </div>
        </div>
      )}

      {clientParagraph && (
        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Client paragraph</span>
            <button
              type="button"
              onClick={handleCopyParagraph}
              className="text-xs text-primary hover:underline"
            >
              Copy
            </button>
          </div>
          <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">{clientParagraph}</div>
        </div>
      )}

      {(sourcesActive.length > 0 || harvestedAt) && (
        <div>
          <button
            type="button"
            onClick={() => setSourcesOpen((o) => !o)}
            className="flex w-full items-center justify-between text-left text-sm font-medium"
          >
            Data sources
            <span className="text-muted-foreground">{sourcesOpen ? "−" : "+"}</span>
          </button>
          {sourcesOpen && (
            <div className="mt-2 rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
              {sourcesActive.length > 0 && <div>{sourcesActive.join(", ")}</div>}
              {harvestedAt && <div className="mt-1 text-xs">Retrieved: {harvestedAt}</div>}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleExportSummary}
          disabled={!analysisId || exportLocked || exportLoading !== null}
          className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
        >
          {exportLoading === "summary" ? "Exporting…" : "Export Summary PDF"}
        </button>
        <button
          type="button"
          onClick={handleExportFull}
          disabled={!analysisId || exportLocked || exportLoading !== null}
          className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
        >
          {exportLoading === "full" ? "Exporting…" : "Export Full Report PDF"}
        </button>
        <button
          type="button"
          onClick={() => setSaveDialogOpen(true)}
          className="inline-flex h-9 items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow hover:bg-accent disabled:pointer-events-none disabled:opacity-50"
        >
          Save Report
        </button>
      </div>

      {exportError && (
        <p className="text-sm text-destructive" role="alert">
          {exportError}
        </p>
      )}

      {saveDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-sm rounded-lg border border-border bg-background p-4 shadow-lg">
            <div className="text-sm font-medium">Save Report</div>
            <input
              type="text"
              placeholder="Custom name"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSave()}
              className="mt-2 h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
            />
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setSaveDialogOpen(false);
                  setSaveName("");
                }}
                className="h-9 rounded-md border border-input px-3 text-sm"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={!saveName.trim()}
                className="h-9 rounded-md bg-primary px-3 text-sm text-primary-foreground disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
