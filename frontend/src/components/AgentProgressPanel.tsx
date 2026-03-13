import { useEffect, useState } from "react";
import { connectProgress, type AgentStatusMessage } from "../api/client";

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
  const [activityFeed, setActivityFeed] = useState<Array<{ agent: string; toolCall: string; ts: number }>>([]);

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
        if (msg.tool_call) {
          setActivityFeed((prev) =>
            [...prev, { agent: msg.agent_name, toolCall: msg.tool_call!, ts: Date.now() }].slice(-20)
          );
        }
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

  function icon(status: AgentStatus) {
    switch (status) {
      case "pending":
        return "○";
      case "running":
        return "…";
      case "completed":
        return "✓";
      case "failed":
        return "✗";
      default:
        return "○";
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="text-sm font-medium">Agent progress</div>
      <ul className="flex flex-col gap-1.5">
        {AGENT_ORDER.map((key) => {
          const { status, toolCall } = agentState[key] ?? { status: "pending" as AgentStatus, toolCall: null };
          const label = AGENT_LABELS[key] ?? key;
          return (
            <li key={key} className="flex items-center gap-2 text-sm">
              <span className="shrink-0" aria-hidden>
                {icon(status)}
              </span>
              <span className="min-w-0 truncate">{label}</span>
              {toolCall && (
                <span className="truncate text-muted-foreground" title={toolCall}>
                  {toolCall}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {activityFeed.length > 0 && (
        <div className="mt-2">
          <div className="text-xs font-medium text-muted-foreground">Active tool calls</div>
          <ul className="mt-1 max-h-24 overflow-y-auto text-xs text-muted-foreground">
            {[...activityFeed].reverse().map((item, i) => (
              <li key={`${item.ts}-${i}`}>
                {item.agent}: {item.toolCall}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
