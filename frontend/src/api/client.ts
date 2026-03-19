const env = (import.meta as { env?: Record<string, string> }).env;
const browserHost =
  typeof window !== "undefined" && window.location?.hostname
    ? window.location.hostname
    : "localhost";
const API_BASE = env?.VITE_API_URL ?? `http://${browserHost}:8000`;
const WS_BASE = env?.VITE_WS_URL ?? `ws://${browserHost}:8000`;

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
  harvester_output: HarvesterOutput | null;
  parser_output: ParserOutput | null;
  scenario_output: unknown;
  recommendation_output: RecommendationOutput | null;
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

export interface BeneficiaryFundCandidate {
  fund_name: string;
  confidence: string;
  relation_type: string;
  evidence?: string[];
}

export interface PreIpoBeneficiaryFunds {
  candidates: BeneficiaryFundCandidate[];
  methodology?: string;
}

export interface ScenarioRecommendation {
  recommended_positioning: string;
  conviction: string;
  rationale: string;
  risk_warning: string;
  client_paragraph: string;
}

export interface RetailActionIdeas {
  conservative: string;
  tactical: string;
  risk_control: string;
}

export interface RetailSummary {
  verdict_line: string;
  what_i_see_now: string[];
  why_that_matters: string[];
  the_good: string[];
  the_risk: string[];
  simple_conclusion: string;
  key_data_points: string[];
  action_ideas: RetailActionIdeas;
  is_preliminary: boolean;
}

export interface RecommendationOutput {
  company_name: string;
  decision?: "buy" | "watch" | "avoid" | null;
  decision_scope?: "pre_ipo_fund" | "post_ipo_direct" | "no_trade" | null;
  entry_triggers?: string[];
  watch_triggers?: string[];
  kill_criteria?: string[];
  sizing_guidance?: string;
  decision_rationale?: string;
  decision_evidence?: string[];
  pre_ipo_beneficiary_funds: PreIpoBeneficiaryFunds;
  recommendations: {
    pessimistic: ScenarioRecommendation;
    realistic: ScenarioRecommendation;
    optimistic: ScenarioRecommendation;
  };
  plain_english_summary?: string;
  investment_action?: string;
  funds_to_consider?: string[];
  what_to_watch?: string[];
  retail_summary?: RetailSummary;
  generated_at?: string;
}

export interface ParserOutput {
  financials?: { revenue?: number; revenue_growth_yoy?: number; burn_rate_monthly?: number; cash_runway_months?: number };
  float_details?: { total_shares_offered?: number; insider_shares?: number; public_float?: number; greenshoe_option?: boolean };
  demand_signals?: { institutional_interest?: string; roadshow_sentiment?: string; anchor_investors?: string[] };
  offering_type?: string;
  lockup_period_days?: number;
  insider_selling_percentage?: number;
  data_confidence?: string;
  flagged_sections?: Array<{ section?: string; reason?: string; verify_at?: string }>;
}

export interface HarvesterOutput {
  sources_active?: string[];
  sources_failed?: Array<{ source?: string; reason?: string }>;
  harvested_at?: string;
  twitter_data?: { sentiment_score?: { positive?: number; negative?: number; neutral?: number } };
}

export interface AnalysisFlag {
  flag_id?: string;
  section?: string;
  severity?: string;
  reason?: string;
  source_reference?: string;
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
