import { useState } from "react";
import { confirmFlags } from "../api/client";
import { Button } from "./ui/button";

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
      <ul className="flex flex-col gap-4">
        {flags.map((f, i) => (
          <li
            key={f.flag_id ?? i}
            className="border-l-4 border-amber-500 pl-3 text-sm"
          >
            <div className="font-medium text-foreground">
              {f.section ?? "Unknown"} {f.severity ? `(${f.severity})` : ""}
            </div>
            <div className="mt-1 text-[#a1a1aa]">{f.reason ?? "—"}</div>
            {f.source_reference && (
              <div className="mt-1 text-[12px] text-muted-foreground">Verify at: {f.source_reference}</div>
            )}
          </li>
        ))}
      </ul>
      {exportLocked && (
        <>
          <Button
            variant="outline"
            onClick={handleConfirm}
            disabled={loading || !analysisId}
            className="w-full border-amber-500 text-amber-500 hover:bg-amber-500/10 hover:text-amber-500"
          >
            {loading ? "Confirming…" : "Confirm flags"}
          </Button>
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
