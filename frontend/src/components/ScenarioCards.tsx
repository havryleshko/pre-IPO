interface ScenarioDetails {
  probability?: number;
  drivers?: string[];
  key_risks?: string[];
  price_targets?: { "30_days"?: number; "90_days"?: number; "1_year"?: number };
  weighting_rationale?: string;
}

interface ScenarioRecommendation {
  recommended_positioning?: string;
  rationale?: string;
  risk_warning?: string;
}

interface ScenarioSet {
  pessimistic?: ScenarioDetails;
  realistic?: ScenarioDetails;
  optimistic?: ScenarioDetails;
}

interface ScenarioData {
  scenarios?: ScenarioSet;
}

interface RecommendationData {
  recommendations?: {
    pessimistic?: ScenarioRecommendation;
    realistic?: ScenarioRecommendation;
    optimistic?: ScenarioRecommendation;
  };
}

export interface ScenarioCardsProps {
  scenarioOutput?: ScenarioData | null;
  recommendationOutput?: RecommendationData | null;
}

function fmt(val: number | undefined): string {
  if (val === undefined || val === null) return "—";
  return Number.isInteger(val) ? String(val) : val.toFixed(2);
}

function fmtPct(val: number | undefined): string {
  if (val === undefined || val === null) return "—";
  return `${Math.round(val)}%`;
}

export function ScenarioCards({ scenarioOutput, recommendationOutput }: ScenarioCardsProps) {
  const s = scenarioOutput?.scenarios;
  const scenarios = s?.pessimistic ? (["pessimistic", "realistic", "optimistic"] as const) : [];
  const labels = { pessimistic: "Pessimistic", realistic: "Realistic", optimistic: "Optimistic" };

  if (scenarios.length === 0) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-border bg-card p-4 text-muted-foreground">
          No scenario data available.
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {scenarios.map((key) => {
        const scenario = s?.[key];
        const rec = recommendationOutput?.recommendations?.[key];
        const label = labels[key as keyof typeof labels];
        const pct = fmtPct(scenario?.probability);
        const pt = scenario?.price_targets;
        const targets = pt ? `${fmt(pt["30_days"])} / ${fmt(pt["90_days"])} / ${fmt(pt["1_year"])}` : "—";

        return (
          <div
            key={key}
            className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 shadow-sm"
          >
            <div className="border-b border-border pb-2 text-sm font-semibold">
              {label} {pct}
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Drivers</div>
              <ul className="mt-1 list-inside list-disc text-sm">
                {(scenario?.drivers ?? []).slice(0, 5).map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
                {(!scenario?.drivers || scenario.drivers.length === 0) && <li>—</li>}
              </ul>
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Key risks</div>
              <ul className="mt-1 list-inside list-disc text-sm">
                {(scenario?.key_risks ?? []).slice(0, 5).map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
                {(!scenario?.key_risks || scenario.key_risks.length === 0) && <li>—</li>}
              </ul>
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">30d / 90d / 1yr</div>
              <div className="mt-1 text-sm">{targets}</div>
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Positioning</div>
              <div className="mt-1 text-sm">{rec?.recommended_positioning ?? "—"}</div>
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Rationale</div>
              <div className="mt-1 text-sm">{rec?.rationale ?? "—"}</div>
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Risk warning</div>
              <div className="mt-1 text-sm">{rec?.risk_warning ?? "—"}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
