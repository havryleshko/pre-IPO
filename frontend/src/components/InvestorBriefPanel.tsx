import type { InvestorBrief } from "../api/client";
import { Separator } from "./ui/separator";

export interface InvestorBriefPanelProps {
  investorBrief: InvestorBrief | null;
}

export function InvestorBriefPanel({ investorBrief }: InvestorBriefPanelProps) {
  if (!investorBrief) return null;

  return (
    <div className="flex flex-col gap-10 max-w-3xl mx-auto px-4 pb-16 pt-4">
      {/* Title Header */}
      <header className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <span className="rounded-full bg-primary/5 px-2.5 py-1 text-[11px] font-semibold text-primary/80 uppercase tracking-wide">
            {investorBrief.sector_theme}
          </span>
          <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-widest">
            Pre-IPO Research Brief
          </span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-foreground">
          {investorBrief.company_name}
        </h1>
      </header>

      {/* Primary Idea Card */}
      <div className="rounded-2xl border border-primary/10 bg-primary/5 p-6 sm:p-8">
        <h3 className="mb-4 text-xs font-bold tracking-widest uppercase text-primary/60">Primary Idea</h3>
        <div className="flex flex-col sm:flex-row sm:items-baseline gap-2 mb-3">
          <span className="text-2xl font-bold text-foreground">{investorBrief.primary_instrument.name}</span>
          {investorBrief.primary_instrument.ticker && (
            <span className="text-sm font-mono bg-background border border-border px-2 py-0.5 rounded-md text-muted-foreground shadow-sm">
              {investorBrief.primary_instrument.ticker}
            </span>
          )}
        </div>
        <p className="text-base text-foreground/80 leading-relaxed font-medium">
          {investorBrief.primary_instrument.rationale_one_liner}
        </p>
      </div>

      {/* Alternates */}
      {investorBrief.alternates && investorBrief.alternates.length > 0 && (
        <div className="flex flex-col gap-4">
          <h3 className="text-xs font-bold tracking-widest uppercase text-muted-foreground">Alternates</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {investorBrief.alternates.map((alt, i) => (
              <div key={i} className="rounded-xl border border-border/60 bg-background p-5 shadow-sm transition-all hover:shadow-md">
                <div className="flex flex-wrap items-baseline gap-2 mb-2">
                  <span className="text-base font-semibold text-foreground">{alt.name}</span>
                  {alt.ticker && (
                    <span className="text-xs font-mono bg-muted/50 px-1.5 py-0.5 rounded text-muted-foreground">
                      {alt.ticker}
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {alt.rationale_one_liner}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <Separator className="bg-border/40" />

      {/* Overview Narrative */}
      <div className="flex flex-col gap-6">
        <div className="prose prose-slate max-w-none prose-p:leading-relaxed prose-p:text-[15px] prose-p:text-foreground/90 prose-headings:font-semibold prose-a:text-primary prose-a:font-medium prose-a:underline-offset-4 hover:prose-a:text-primary/80">
          {investorBrief.overview_markdown}
        </div>
      </div>

      <Separator className="bg-border/40" />

      {/* References */}
      <div className="flex flex-col gap-4">
        <h3 className="text-xs font-bold tracking-widest uppercase text-muted-foreground">Sources</h3>
        <ul className="text-sm text-muted-foreground space-y-3">
          {investorBrief.references.map((ref) => (
            <li key={ref.id} className="flex items-start gap-3">
              <span className="font-mono text-xs mt-0.5 opacity-60">[{ref.id}]</span>
              <div className="flex flex-col gap-0.5">
                {ref.url ? (
                  <a href={ref.url} target="_blank" rel="noreferrer" className="font-medium text-foreground/70 hover:text-foreground hover:underline underline-offset-4 transition-colors">
                    {ref.label}
                  </a>
                ) : (
                  <span className="font-medium text-foreground/70">{ref.label}</span>
                )}
                {ref.source_hint && <span className="text-xs opacity-60">{ref.source_hint}</span>}
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* Disclaimer */}
      <div className="mt-8 rounded-lg bg-muted/30 p-4 text-center">
        <p className="text-[11px] leading-relaxed text-muted-foreground/80 max-w-xl mx-auto">
          {investorBrief.disclaimer_short}
        </p>
      </div>
    </div>
  );
}
