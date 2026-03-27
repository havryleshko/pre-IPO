import { useEffect, useState } from "react";
import { connectProgress, type AgentStatusMessage } from "../api/client";
import { Circle, Loader2, CheckCircle, XCircle } from "lucide-react";

const AGENT_ORDER = [
  "lead_orchestrator",
  "data_harvester",
  "prospectus_parser",
  "scenario_builder",
  "investor_brief_synthesizer",
] as const;

const AGENT_LABELS: Record<string, string> = {
  lead_orchestrator: "Lead Orchestrator",
  data_harvester: "Data Harvester",
  prospectus_parser: "Prospectus Parser",
  scenario_builder: "Scenario Builder",
  investor_brief_synthesizer: "Research Brief",
};

type AgentStatus = "pending" | "running" | "completed" | "failed";

function toKey(name: string): string {
  return name.toLowerCase().replace(/\s+/g, "_");
}

function createInitialAgentState(): Record<string, { status: AgentStatus; toolCall: string | null }> {
  const init: Record<string, { status: AgentStatus; toolCall: string | null }> = {};
  for (const a of AGENT_ORDER) {
    init[a] = { status: "pending", toolCall: null };
  }
  return init;
}

export interface AgentProgressPanelProps {
  analysisId: string | null;
  lastCompletedAgent?: string | null;
}

export function AgentProgressPanel({ analysisId, lastCompletedAgent }: AgentProgressPanelProps) {
  const [agentState, setAgentState] = useState<Record<string, { status: AgentStatus; toolCall: string | null }>>(
    () => createInitialAgentState()
  );

  useEffect(() => {
    setAgentState(createInitialAgentState());
  }, [analysisId]);

  useEffect(() => {
    if (!analysisId) return;
    const ws = connectProgress(
      analysisId,
      (msg: AgentStatusMessage) => {
        const key = toKey(msg.agent_name);
        setAgentState((prev) => {
          const next = { ...prev };
          if (!(key in next)) next[key] = { status: "pending", toolCall: null };
          next[key] = {
            status: msg.status as AgentStatus,
            toolCall: msg.tool_call ?? null,
          };
          return next;
        });
      },
      () => {}
    );
    return () => ws.close();
  }, [analysisId]);

  useEffect(() => {
    if (!lastCompletedAgent) return;
    const key = toKey(lastCompletedAgent);
    const idx = AGENT_ORDER.indexOf(key as (typeof AGENT_ORDER)[number]);
    if (idx < 0) return;
    setAgentState((prev) => {
      const next = { ...prev };
      for (let i = 0; i <= idx; i++) {
        const k = AGENT_ORDER[i];
        if (k in next) next[k] = { ...next[k], status: "completed" };
      }
      return next;
    });
  }, [lastCompletedAgent]);

  function renderIcon(status: AgentStatus) {
    switch (status) {
      case "pending":
        return <Circle className="h-4 w-4 text-muted-foreground" />;
      case "running":
        return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "failed":
        return <XCircle className="h-4 w-4 text-destructive" />;
      default:
        return <Circle className="h-4 w-4 text-muted-foreground" />;
    }
  }

  return (
    <div className="flex flex-col items-center justify-center p-8 border border-border/50 rounded-xl bg-muted/10 shadow-sm">
      <h3 className="text-sm font-medium mb-6 text-foreground/80">Generating Research Brief</h3>
      <div className="flex w-full max-w-lg items-center justify-between">
        {AGENT_ORDER.map((key, index) => {
          const { status, toolCall } = agentState[key] ?? { status: "pending" as AgentStatus, toolCall: null };
          const label = AGENT_LABELS[key] ?? key;
          const isLast = index === AGENT_ORDER.length - 1;
          
          return (
            <div key={key} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-2 w-24">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-background border border-border/50 shadow-sm relative">
                  {renderIcon(status)}
                  {status === "running" && (
                    <span className="absolute -bottom-6 w-32 text-center text-[10px] text-muted-foreground truncate" title={toolCall ?? ""}>
                      {toolCall || "Working..."}
                    </span>
                  )}
                </div>
                <span className={`text-[10px] font-medium text-center ${status === "pending" ? "text-muted-foreground" : "text-foreground/90"}`}>
                  {label}
                </span>
              </div>
              {!isLast && (
                <div className="flex-1 mx-2 h-px bg-border/60 relative">
                  {status === "completed" && <div className="absolute inset-0 bg-primary h-px" />}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
