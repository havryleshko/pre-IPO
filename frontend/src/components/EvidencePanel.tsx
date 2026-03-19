import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import type {
  ParserOutput,
  RecommendationOutput,
  HarvesterOutput,
  AnalysisFlag,
} from "../api/client";

export interface EvidencePanelProps {
  parserOutput: ParserOutput | null;
  recommendationOutput: RecommendationOutput | null;
  harvesterOutput: HarvesterOutput | null;
  flags: AnalysisFlag[];
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[14px] font-medium text-foreground mb-3 pb-2 border-b border-border/50">
      {children}
    </h3>
  );
}

function DataRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-center py-1">
      <span className="text-[13px] text-muted-foreground">{label}</span>
      <span className="text-[13px] font-medium text-foreground">{value ?? "—"}</span>
    </div>
  );
}

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "—";
  if (val >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
  return `$${val.toLocaleString()}`;
}

function formatNumber(val: number | null | undefined): string {
  if (val == null) return "—";
  if (val >= 1e9) return `${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `${(val / 1e6).toFixed(2)}M`;
  return val.toLocaleString();
}

function formatPct(val: number | null | undefined): string {
  if (val == null) return "—";
  return `${val.toFixed(1)}%`;
}

function isMeaningfulNumber(val: number | null | undefined): boolean {
  return val != null && val !== 0;
}

function humanizeDecisionEvidence(ev: string): string {
  const cleaned = ev.replace(/^parser:/, "").replace(/^harvester:/, "");
  if (cleaned.startsWith("data_confidence=")) {
    return `Data confidence: ${cleaned.split("=")[1] ?? "unknown"}`;
  }
  if (cleaned.startsWith("offering_type=")) {
    return `Offering type: ${cleaned.split("=")[1] ?? "unknown"}`;
  }
  if (cleaned.startsWith("lockup_period_days=")) {
    return `Lock-up period: ${cleaned.split("=")[1] ?? "n/a"} days`;
  }
  if (cleaned.startsWith("sec_filings_count=")) {
    return `SEC filings checked: ${cleaned.split("=")[1] ?? "0"}`;
  }
  if (cleaned.startsWith("news_articles_count=")) {
    return `News articles checked: ${cleaned.split("=")[1] ?? "0"}`;
  }
  if (cleaned.includes("=")) {
    const [left, right] = cleaned.split("=", 2);
    return `${left.replace(/\./g, " ").replace(/_/g, " ")}: ${right}`;
  }
  return cleaned.replace(/\./g, " ").replace(/_/g, " ");
}

export function EvidencePanel({
  parserOutput,
  recommendationOutput,
  harvesterOutput,
  flags = [],
}: EvidencePanelProps) {
  if (!parserOutput && !recommendationOutput && !harvesterOutput) return null;

  const decisionEvidence = recommendationOutput?.decision_evidence ?? [];
  const f = parserOutput?.financials;
  const float = parserOutput?.float_details;
  const demand = parserOutput?.demand_signals;
  const funds = recommendationOutput?.pre_ipo_beneficiary_funds?.candidates ?? [];
  const sources = harvesterOutput?.sources_active ?? [];
  const parserFlags = parserOutput?.flagged_sections ?? [];
  const sourcesFailed = harvesterOutput?.sources_failed ?? [];
  const hasFinancialEvidence =
    isMeaningfulNumber(f?.revenue) ||
    isMeaningfulNumber(f?.burn_rate_monthly) ||
    f?.revenue_growth_yoy != null ||
    f?.cash_runway_months != null;
  const hasFloatEvidence =
    isMeaningfulNumber(float?.total_shares_offered) ||
    isMeaningfulNumber(float?.public_float) ||
    isMeaningfulNumber(float?.insider_shares);
  const usableFunds = funds.filter(
    (fund) =>
      fund.relation_type !== "insufficient_evidence" &&
      !fund.fund_name.toLowerCase().includes("not resolved")
  );

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <Card className="border-border bg-card shadow-sm md:col-span-2">
        <CardHeader className="pb-2">
          <CardTitle className="text-[15px]">Decision Evidence</CardTitle>
        </CardHeader>
        <CardContent>
          {decisionEvidence.length > 0 ? (
            <ul className="list-disc list-inside text-[13px] leading-relaxed text-foreground space-y-1">
              {decisionEvidence.map((ev, idx) => (
                <li key={idx}>{humanizeDecisionEvidence(ev)}</li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] leading-relaxed text-muted-foreground">
              No structured decision evidence was provided yet.
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="border-border bg-card shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-[15px]">Company & Offering Facts</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div>
            <SectionTitle>Financials</SectionTitle>
            {hasFinancialEvidence ? (
              <>
                <DataRow label="Revenue" value={formatCurrency(f?.revenue)} />
                <DataRow
                  label="YoY Growth"
                  value={f?.revenue_growth_yoy != null ? formatPct(f.revenue_growth_yoy * 100) : "—"}
                />
                <DataRow label="Monthly Burn" value={formatCurrency(f?.burn_rate_monthly)} />
                <DataRow label="Cash Runway" value={f?.cash_runway_months ? `${f.cash_runway_months} mos` : "—"} />
              </>
            ) : (
              <p className="text-[13px] leading-relaxed text-muted-foreground">
                No filing-derived financial metrics were extracted with enough confidence to show here yet.
              </p>
            )}
          </div>

          <div>
            <SectionTitle>Offering Structure</SectionTitle>
            <DataRow
              label="Offering Type"
              value={parserOutput?.offering_type === "unknown" ? "Not extracted yet" : parserOutput?.offering_type}
            />
            <DataRow label="Lockup Period" value={parserOutput?.lockup_period_days ? `${parserOutput.lockup_period_days} days` : "—"} />
            <DataRow label="Insider Selling" value={formatPct(parserOutput?.insider_selling_percentage)} />
            {hasFloatEvidence ? (
              <>
                <DataRow label="Shares Offered" value={formatNumber(float?.total_shares_offered)} />
                <DataRow label="Public Float" value={formatNumber(float?.public_float)} />
                <DataRow label="Greenshoe Option" value={float?.greenshoe_option ? "Yes" : "No"} />
              </>
            ) : (
              <p className="text-[13px] leading-relaxed text-muted-foreground">
                Share count and float mechanics were not extracted cleanly from the filing.
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-6">
        <Card className="border-border bg-card shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-[15px]">Demand & Market Context</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {harvesterOutput?.twitter_data?.sentiment_score && (() => {
              const sentiment = harvesterOutput.twitter_data.sentiment_score;
              const pos = sentiment.positive ?? 0;
              const neg = sentiment.negative ?? 0;
              const neu = sentiment.neutral ?? 0;
              const total = pos + neg + neu || 1;
              return (
                <div className="mb-2">
                  <span className="block text-[13px] text-muted-foreground mb-2">X/Twitter Sentiment</span>
                  <div className="flex items-center gap-3">
                    <div className="flex h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                      <div className="bg-green-500" style={{ width: `${(pos / total) * 100}%` }} title={`Positive ${((pos / total) * 100).toFixed(0)}%`} />
                      <div className="bg-gray-400" style={{ width: `${(neu / total) * 100}%` }} title={`Neutral ${((neu / total) * 100).toFixed(0)}%`} />
                      <div className="bg-red-500" style={{ width: `${(neg / total) * 100}%` }} title={`Negative ${((neg / total) * 100).toFixed(0)}%`} />
                    </div>
                    <div className="text-[12px] text-muted-foreground whitespace-nowrap w-12 text-right">
                      {((pos / total) * 100).toFixed(0)}% Pos
                    </div>
                  </div>
                </div>
              );
            })()}
            <div>
              <span className="block text-[13px] text-muted-foreground mb-1">Institutional Interest</span>
              <p className="text-[13px] text-foreground leading-relaxed">
                {demand?.institutional_interest && demand.institutional_interest !== "unknown"
                  ? demand.institutional_interest
                  : "Not established from current evidence"}
              </p>
            </div>
            <div>
              <span className="block text-[13px] text-muted-foreground mb-1">Roadshow Sentiment</span>
              <p className="text-[13px] text-foreground leading-relaxed">
                {demand?.roadshow_sentiment ?? "—"}
              </p>
            </div>
            {demand?.anchor_investors && demand.anchor_investors.length > 0 && (
              <div>
                <span className="block text-[13px] text-muted-foreground mb-1">Anchor Investors</span>
                <div className="flex flex-wrap gap-2">
                  {demand.anchor_investors.map((inv, idx) => (
                    <span key={idx} className="px-2 py-1 bg-secondary text-secondary-foreground rounded text-[12px]">
                      {inv}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-border bg-card shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-[15px]">Fund Exposure</CardTitle>
          </CardHeader>
          <CardContent>
            {usableFunds.length === 0 ? (
              <div className="flex flex-col gap-2">
                <p className="text-[13px] text-muted-foreground">
                  No defensible public fund exposure was identified from the current parser, SEC, Crunchbase, and news evidence.
                </p>
                {funds[0]?.evidence?.[0] && (
                  <p className="text-[12px] text-muted-foreground">{funds[0].evidence[0]}</p>
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                {usableFunds.map((fund, idx) => (
                  <div key={idx} className="flex flex-col gap-1 border-b border-border/50 pb-3 last:border-0 last:pb-0">
                    <div className="flex justify-between items-start">
                      <span className="text-[13px] font-medium text-foreground">{fund.fund_name}</span>
                      <span className="text-[11px] px-2 py-0.5 bg-secondary text-secondary-foreground rounded">
                        {fund.confidence} Confidence
                      </span>
                    </div>
                    <span className="text-[12px] text-muted-foreground">{fund.relation_type}</span>
                    {fund.evidence && fund.evidence.length > 0 && (
                      <ul className="mt-1 list-disc list-inside text-[12px] text-muted-foreground">
                        {fund.evidence.map((ev, i) => (
                          <li key={i}>{ev}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {(sources.length > 0 || sourcesFailed.length > 0 || Boolean(harvesterOutput?.harvested_at)) && (
          <Card className="border-border bg-card shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-[15px]">Source Metadata</CardTitle>
            </CardHeader>
            <CardContent>
              {sources.length > 0 ? (
                <div className="flex flex-wrap gap-2 mb-2">
                  {sources.map((src, i) => (
                    <span key={i} className="px-2 py-1 bg-secondary text-secondary-foreground rounded text-[12px]">
                      {src}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="text-[12px] text-muted-foreground">No active sources completed successfully.</div>
              )}
              {harvesterOutput?.harvested_at && (
                <div className="text-[11px] text-muted-foreground">
                  Last updated: {new Date(harvesterOutput.harvested_at).toLocaleString()}
                </div>
              )}
              {sourcesFailed.length > 0 && (
                <div className="mt-3 flex flex-col gap-1">
                  {sourcesFailed.map((source, index) => (
                    <div key={index} className="text-[12px] text-muted-foreground">
                      Source issue: {source.source ?? "unknown"}{source.reason ? ` - ${source.reason}` : ""}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {(flags.length > 0 || parserFlags.length > 0) && (
          <Card className="border-border bg-card shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-[15px]">Data Quality Notes</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {flags.map((flag, index) => (
                <div key={flag.flag_id ?? `judge-${index}`} className="rounded-md border border-amber-500/20 bg-amber-500/10 p-3">
                  <div className="text-[13px] font-medium text-foreground">
                    {flag.section ?? "Validation flag"}{flag.severity ? ` (${flag.severity})` : ""}
                  </div>
                  <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{flag.reason ?? "—"}</p>
                  {flag.source_reference && (
                    <p className="mt-1 text-[11px] text-muted-foreground">Reference: {flag.source_reference}</p>
                  )}
                </div>
              ))}
              {parserFlags.map((flag, index) => (
                <div key={`${flag.section}-${index}`} className="rounded-md border border-border p-3">
                  <div className="text-[13px] font-medium text-foreground">{flag.section}</div>
                  <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{flag.reason}</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">Reference: {flag.verify_at}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
