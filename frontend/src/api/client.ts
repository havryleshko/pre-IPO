const env = (import.meta as { env?: Record<string, string> }).env;
const API_BASE = env?.VITE_API_URL ?? "http://localhost:8000";
const WS_BASE = env?.VITE_WS_URL ?? "ws://localhost:8000";

export type ComplexityTier = "simple" | "standard" | "complex";
export type AnalysisStatus = "pending" | "running" | "completed" | "failed";

export interface CreateAnalysisResponse {
  analysis_id: string;
  company_name: string;
  status: AnalysisStatus;
  complexity_tier: ComplexityTier;
  created_at: string;
}

export interface AnalysisOutputsResponse {
  analysis_id: string;
  company_name: string;
  status: AnalysisStatus;
  complexity_tier: ComplexityTier;
  last_completed_agent: string | null;
  export_locked: boolean;
  created_at: string;
  harvester_output: unknown;
  parser_output: unknown;
  scenario_output: unknown;
  recommendation_output: unknown;
  judge_output: unknown;
  flags: Array<{ flag_id?: string; section?: string; severity?: string; reason?: string }>;
}

export interface ConfirmFlagsResponse {
  analysis_id: string;
  ifa_confirmed_flags: string[];
  export_locked: boolean;
}

export interface ExportLockResponse {
  analysis_id: string;
  export_locked: boolean;
}

export interface AgentStatusMessage {
  type: "agent_status";
  agent_name: string;
  status: string;
  tool_call?: string;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function createAnalysis(companyName: string): Promise<CreateAnalysisResponse> {
  return fetchJson<CreateAnalysisResponse>(`${API_BASE}/analyses`, {
    method: "POST",
    body: JSON.stringify({ company_name: companyName }),
  });
}

export async function getAnalysis(analysisId: string): Promise<AnalysisOutputsResponse> {
  return fetchJson<AnalysisOutputsResponse>(`${API_BASE}/analyses/${analysisId}`);
}

export async function confirmFlags(
  analysisId: string,
  flagIds: string[]
): Promise<ConfirmFlagsResponse> {
  return fetchJson<ConfirmFlagsResponse>(`${API_BASE}/analyses/${analysisId}/confirm-flags`, {
    method: "POST",
    body: JSON.stringify({ flag_ids: flagIds }),
  });
}

export async function getExportLock(analysisId: string): Promise<ExportLockResponse> {
  return fetchJson<ExportLockResponse>(`${API_BASE}/analyses/${analysisId}/export/lock`);
}

export async function exportSummaryPdf(analysisId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/analyses/${analysisId}/export/summary`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Export error ${res.status}: ${body || res.statusText}`);
  }
  return res.blob();
}

export async function exportFullReportPdf(analysisId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/analyses/${analysisId}/export/full`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Export error ${res.status}: ${body || res.statusText}`);
  }
  return res.blob();
}

export function connectProgress(
  analysisId: string,
  onMessage: (msg: AgentStatusMessage) => void,
  onClose?: () => void
): WebSocket {
  const url = `${WS_BASE}/analyses/${analysisId}/progress`;
  const ws = new WebSocket(url);
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as AgentStatusMessage;
      if (data?.type === "agent_status") {
        onMessage(data);
      }
    } catch {
      // ignore parse errors
    }
  };
  if (onClose) {
    ws.onclose = onClose;
  }
  return ws;
}
