import { useState } from "react";
import { exportFullReportPdf, exportSummaryPdf } from "../api/client";
import { Button } from "./ui/button";
import { Copy } from "lucide-react";
import type { RecommendationOutput } from "../api/client";

export interface ReportPanelsProps {
  analysisId: string | null;
  exportLocked: boolean;
  recommendationOutput: RecommendationOutput | null;
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
  onSave,
}: ReportPanelsProps) {
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [exportLoading, setExportLoading] = useState<"summary" | "full" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const clientParagraph = recommendationOutput?.recommendations?.realistic?.client_paragraph ?? "";

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

  if (!clientParagraph && !analysisId) return null;

  return (
    <div className="flex flex-col gap-6">
      {clientParagraph && (
        <div>
          <h3 className="text-[14px] font-medium text-foreground mb-3">Client Ready Paragraph</h3>
          <div className="rounded-md border border-border bg-[#111111] p-4 relative">
            <Button
              variant="ghost"
              size="icon"
              onClick={handleCopyParagraph}
              className="absolute top-2 right-2 h-8 w-8 text-muted-foreground hover:text-foreground"
              title="Copy to clipboard"
            >
              <Copy className="h-4 w-4" />
            </Button>
            <div className="text-[13px] text-[#a1a1aa] pr-8 leading-relaxed">
              {clientParagraph}
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <Button
          variant="outline"
          onClick={handleExportSummary}
          disabled={!analysisId || exportLocked || exportLoading !== null}
          className="text-[13px] bg-transparent text-foreground border-border hover:bg-accent"
        >
          {exportLoading === "summary" ? "Exporting…" : "Export Summary PDF"}
        </Button>
        <Button
          variant="outline"
          onClick={handleExportFull}
          disabled={!analysisId || exportLocked || exportLoading !== null}
          className="text-[13px] bg-transparent text-foreground border-border hover:bg-accent"
        >
          {exportLoading === "full" ? "Exporting…" : "Export Full Report PDF"}
        </Button>
        <Button
          onClick={() => setSaveDialogOpen(true)}
          className="text-[13px] bg-primary text-primary-foreground hover:bg-primary/90"
        >
          Save Report
        </Button>
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
              className="mt-2 h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setSaveDialogOpen(false);
                  setSaveName("");
                }}
              >
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={!saveName.trim()}>
                Save
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
