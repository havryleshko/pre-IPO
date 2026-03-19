import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import type { RecommendationOutput, ParserOutput } from "../api/client";
import { AlertTriangle, TrendingUp, Eye, Target } from "lucide-react";

export interface RecommendationSummaryPanelProps {
  recommendationOutput: RecommendationOutput | null;
  parserOutput: ParserOutput | null;
}

export function RecommendationSummaryPanel({
  recommendationOutput,
  parserOutput,
}: RecommendationSummaryPanelProps) {
  if (!recommendationOutput) {
    return (
      <Card className="border-border bg-card">
        <CardContent className="pt-6 text-muted-foreground">
          Awaiting recommendation data...
        </CardContent>
      </Card>
    );
  }

  const realistic = recommendationOutput.recommendations.realistic;
  const conviction = realistic.conviction;
  const dataConfidence = parserOutput?.data_confidence || "Unknown";
  const flaggedSections = parserOutput?.flagged_sections ?? [];
  const missingSectionsCount = flaggedSections.length;
  const summary =
    dataConfidence.toLowerCase() === "low"
      ? `Preliminary recommendation only. Best current positioning is ${realistic.recommended_positioning}, but critical IPO evidence is still missing or weakly extracted. ${missingSectionsCount > 0 ? `${missingSectionsCount} filing sections need manual verification before treating this as client-ready.` : "Treat this as a watchlist view until stronger filing or demand evidence arrives."}`
      : recommendationOutput.plain_english_summary ?? "";

  const decision = recommendationOutput.decision ?? null;
  const decisionScope = recommendationOutput.decision_scope ?? null;
  const decisionRationale = recommendationOutput.decision_rationale ?? "";
  const whyNow = decisionRationale || recommendationOutput.plain_english_summary || summary;
  const retailSummary = recommendationOutput.retail_summary;

  const vehicle =
    decisionScope === "pre_ipo_fund"
      ? recommendationOutput.funds_to_consider?.[0] ?? "Pre-IPO fund (vehicle evidence pending)"
      : decisionScope === "post_ipo_direct"
        ? "Post-IPO direct positioning"
        : decisionScope === "no_trade"
          ? "No trade (conditions not met)"
          : "";

  const entryTriggers = recommendationOutput.entry_triggers ?? [];
  const killCriteria = recommendationOutput.kill_criteria ?? [];

  const getConvictionColor = (c: string) => {
    const lower = c.toLowerCase();
    if (lower.includes("high")) return "bg-green-500/10 text-green-500 border-green-500/20";
    if (lower.includes("medium")) return "bg-yellow-500/10 text-yellow-500 border-yellow-500/20";
    if (lower.includes("low")) return "bg-red-500/10 text-red-500 border-red-500/20";
    return "bg-secondary text-secondary-foreground";
  };

  return (
    <Card className="border-border bg-card shadow-sm">
      <CardHeader className="pb-4 border-b border-border bg-card/50">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <div className="text-[12px] font-medium uppercase tracking-wider text-muted-foreground">
              Primary Recommendation
            </div>
            <CardTitle className="text-2xl font-semibold text-foreground">
              {realistic.recommended_positioning}
            </CardTitle>
            <p className="text-[13px] text-muted-foreground">{realistic.rationale}</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Badge variant="outline" className={getConvictionColor(conviction)}>
              Conviction: {conviction}
            </Badge>
            {dataConfidence !== "Unknown" && (
              <span className="text-[11px] text-muted-foreground">
                Data Confidence: {dataConfidence}
              </span>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-6 pt-6">
        {dataConfidence.toLowerCase() === "low" && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
            <div className="text-[13px] font-medium text-amber-500">Low-confidence / preliminary read</div>
            <p className="mt-1 text-[13px] leading-relaxed text-amber-100/80">
              The pipeline completed, but the extracted filing evidence is thin. Use the recommendation as a monitored posture, not a firm client conclusion.
            </p>
          </div>
        )}
        {retailSummary && (
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="text-[14px] font-medium text-foreground mb-2">Simple Investor View</h3>
            <p className="text-[14px] leading-relaxed text-foreground">{retailSummary.verdict_line}</p>

            {retailSummary.what_i_see_now.length > 0 && (
              <div className="mt-4">
                <h4 className="text-[13px] font-medium text-foreground mb-2">What I See Now</h4>
                <ul className="list-disc list-inside text-[14px] leading-relaxed text-muted-foreground space-y-1">
                  {retailSummary.what_i_see_now.map((item, idx) => (
                    <li key={`see-${idx}`}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            {retailSummary.why_that_matters.length > 0 && (
              <div className="mt-4">
                <h4 className="text-[13px] font-medium text-foreground mb-2">Why That Matters</h4>
                <ul className="list-disc list-inside text-[14px] leading-relaxed text-muted-foreground space-y-1">
                  {retailSummary.why_that_matters.map((item, idx) => (
                    <li key={`matters-${idx}`}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <h4 className="text-[13px] font-medium text-foreground mb-2">The Good</h4>
                <ul className="list-disc list-inside text-[14px] leading-relaxed text-muted-foreground space-y-1">
                  {retailSummary.the_good.map((item, idx) => (
                    <li key={`good-${idx}`}>{item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="text-[13px] font-medium text-foreground mb-2">The Risk</h4>
                <ul className="list-disc list-inside text-[14px] leading-relaxed text-muted-foreground space-y-1">
                  {retailSummary.the_risk.map((item, idx) => (
                    <li key={`risk-${idx}`}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="mt-4">
              <h4 className="text-[13px] font-medium text-foreground mb-1">Simple Conclusion</h4>
              <p className="text-[14px] leading-relaxed text-foreground">{retailSummary.simple_conclusion}</p>
            </div>

            {retailSummary.key_data_points.length > 0 && (
              <div className="mt-4">
                <h4 className="text-[13px] font-medium text-foreground mb-2">Key Data Points Used</h4>
                <ul className="list-disc list-inside text-[14px] leading-relaxed text-muted-foreground space-y-1">
                  {retailSummary.key_data_points.map((item, idx) => (
                    <li key={`data-${idx}`}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-4">
              <h4 className="text-[13px] font-medium text-foreground mb-2">Short Action Ideas</h4>
              <ul className="list-disc list-inside text-[14px] leading-relaxed text-foreground space-y-1">
                <li>{retailSummary.action_ideas.conservative}</li>
                <li>{retailSummary.action_ideas.tactical}</li>
                <li>{retailSummary.action_ideas.risk_control}</li>
              </ul>
            </div>
          </div>
        )}
        {decision && decisionScope ? (
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-[14px] font-medium text-foreground mb-2">Decision</h3>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{decision.toUpperCase()}</Badge>
                  <Badge variant="secondary">{decisionScope.replace(/_/g, " ")}</Badge>
                </div>
              </div>
            </div>

            <div className="mt-4 flex flex-col gap-4">
              <div>
                <h4 className="text-[13px] font-medium text-foreground mb-1">Vehicle</h4>
                <p className="text-[14px] leading-relaxed text-muted-foreground">{vehicle}</p>
              </div>

              <div>
                <h4 className="text-[13px] font-medium text-foreground mb-1">Why Now</h4>
                <p className="text-[14px] leading-relaxed text-muted-foreground">{whyNow}</p>
              </div>

              {entryTriggers.length > 0 && (
                <div>
                  <h4 className="text-[13px] font-medium text-foreground mb-2">Entry Triggers</h4>
                  <ul className="list-disc list-inside text-[14px] leading-relaxed text-foreground space-y-1">
                    {entryTriggers.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {killCriteria.length > 0 && (
                <div>
                  <h4 className="text-[13px] font-medium text-foreground mb-2">Kill Criteria</h4>
                  <ul className="list-disc list-inside text-[14px] leading-relaxed text-foreground space-y-1">
                    {killCriteria.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div>
            <h3 className="text-[14px] font-medium text-foreground mb-2">Summary</h3>
            <p className="text-[14px] leading-relaxed text-muted-foreground">{summary}</p>
          </div>
        )}

        {recommendationOutput.investment_action && (
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
            <div className="flex items-start gap-3">
              <Target className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              <div>
                <h4 className="text-[13px] font-medium text-foreground mb-1">Investment Action</h4>
                <p className="text-[14px] leading-relaxed text-foreground">
                  {recommendationOutput.investment_action}
                </p>
              </div>
            </div>
          </div>
        )}

        {recommendationOutput.funds_to_consider && recommendationOutput.funds_to_consider.length > 0 && (
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-start gap-3">
              <TrendingUp className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
              <div>
                <h4 className="text-[13px] font-medium text-foreground mb-2">Funds to Consider</h4>
                <ul className="list-disc list-inside text-[14px] leading-relaxed text-foreground space-y-1">
                  {recommendationOutput.funds_to_consider.map((fund, idx) => (
                    <li key={idx}>{fund}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {recommendationOutput.what_to_watch && recommendationOutput.what_to_watch.length > 0 && (
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-start gap-3">
              <Eye className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
              <div>
                <h4 className="text-[13px] font-medium text-foreground mb-2">What to Watch</h4>
                <ul className="list-disc list-inside text-[14px] leading-relaxed text-foreground space-y-1">
                  {recommendationOutput.what_to_watch.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {realistic.risk_warning && (
          <div className="flex items-start gap-3 rounded-lg border border-destructive/20 bg-destructive/10 p-4">
            <AlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
            <div className="flex flex-col gap-1">
              <h4 className="text-[13px] font-medium text-destructive">Key Risk Warning</h4>
              <p className="text-[13px] leading-relaxed text-destructive/80">
                {realistic.risk_warning}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
