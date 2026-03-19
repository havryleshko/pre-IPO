import { useEffect, useState } from "react";
import { connectProgress, type AgentStatusMessage } from "../api/client";
import { Circle, Loader2, CheckCircle, XCircle } from "lucide-react";

const AGENT_ORDER = [
  "lead_orchestrator",
  "data_harvester",
  "prospectus_parser",
  "scenario_builder",
  "recommendation_engine",
  "judge_agent",
] as const;

const AGENT_LABELS: Record<string, string> = {
  lead_orchestrator: "Lead Orchestrator",
  data_harvester: "Data Harvester",
  prospectus_parser: "Prospectus Parser",
  scenario_builder: "Scenario Builder",
  recommendation_engine: "Recommendation Engine",
  judge_agent: "Judge Agent",
};

type AgentStatus = "pending" | "running" | "completed" | "failed";

function toKey(name: string): string {
  return name.toLowerCase().replace(/\s+/g, "_");
}

export interface AgentProgressPanelProps {
  analysisId: string | null;
  lastCompletedAgent?: string | null;
}

export function AgentProgressPanel({ analysisId, lastCompletedAgent }: AgentProgressPanelProps) {
  const [agentState, setAgentState] = useState<Record<string, { status: AgentStatus; toolCall: string | null }>>(
    () => {
      const init: Record<string, { status: AgentStatus; toolCall: string | null }> = {};
      for (const a of AGENT_ORDER) {
        init[a] = { status: "pending", toolCall: null };
      }
      return init;
    }
  );

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
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3">
        {AGENT_ORDER.map((key) => {
          const { status, toolCall } = agentState[key] ?? { status: "pending" as AgentStatus, toolCall: null };
          const label = AGENT_LABELS[key] ?? key;
          return (
            <li key={key} className="flex flex-col gap-1 text-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="shrink-0" aria-hidden="true">
                    {renderIcon(status)}
                  </span>
                  <span className="min-w-0 truncate font-medium">{label}</span>
                </div>
                <span className="text-xs text-muted-foreground capitalize">{status}</span>
              </div>
              {status === "running" && toolCall && (
                <div className="pl-6 text-[12px] text-[#52525b] truncate" title={toolCall}>
                  {toolCall}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
