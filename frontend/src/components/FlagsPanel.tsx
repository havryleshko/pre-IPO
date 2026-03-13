import { useState } from "react";
import { confirmFlags } from "../api/client";

export interface Flag {
  flag_id?: string;
  section?: string;
  severity?: string;
  reason?: string;
  source_reference?: string;
}

export interface FlagsPanelProps {
  analysisId: string | null;
  flags: Flag[];
  exportLocked: boolean;
  onConfirm?: () => void;
}

export function FlagsPanel({ analysisId, flags, exportLocked, onConfirm }: FlagsPanelProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    if (!analysisId || loading) return;
    const ids = flags.map((f) => f.flag_id).filter((id): id is string => !!id);
    if (ids.length === 0) return;
    setError(null);
    setLoading(true);
    try {
      await confirmFlags(analysisId, ids);
      onConfirm?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to confirm flags");
    } finally {
      setLoading(false);
    }
  }

  if (flags.length === 0) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="text-sm font-medium">Flags</div>
      <ul className="flex flex-col gap-2">
        {flags.map((f, i) => (
          <li
            key={f.flag_id ?? i}
            className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/30"
          >
            <div className="font-medium">
              {f.section ?? "Unknown"} {f.severity ? `(${f.severity})` : ""}
            </div>
            <div className="mt-1 text-muted-foreground">{f.reason ?? "—"}</div>
            {f.source_reference && (
              <div className="mt-1 text-xs text-muted-foreground">Verify at: {f.source_reference}</div>
            )}
          </li>
        ))}
      </ul>
      {exportLocked && (
        <>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={loading || !analysisId}
            className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
          >
            {loading ? "Confirming…" : "Confirm flags"}
          </button>
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
        </>
      )}
    </div>
  );
}
