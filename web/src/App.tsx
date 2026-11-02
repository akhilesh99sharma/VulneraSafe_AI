import { useState } from "react";
import { useManifest } from "./data/hooks";
import EmptyState from "./components/EmptyState";
import ResponsibleUseBanner from "./components/ResponsibleUseBanner";
import Landing from "./components/Landing";
import { SelectionProvider, useSelection } from "./state/selection";
import { SectionTabs } from "./components/ui";
import type { SectionTab } from "./components/ui";
import RiskDashboard from "./components/panels/RiskDashboard";
import DecisionActions from "./components/panels/DecisionActions";
import PathogenExplorer from "./components/panels/PathogenExplorer";
import EmergingSignals from "./components/panels/EmergingSignals";
import OneHealthInsights from "./components/panels/OneHealthInsights";
import Communities from "./components/panels/Communities";
import Facilities from "./components/panels/Facilities";
import SeasonalHazard from "./components/panels/SeasonalHazard";

/**
 * App shell with a two-level navigation model (Req 12, 13).
 *
 * Seven top-level SECTIONS replace the previous flat eleven-tab strip. Sections
 * that hold more than one view render a secondary <SectionTabs/> sub-tab strip:
 *
 *  1. Overview            -> Landing (onEnter -> Risk Dashboard)
 *  2. Risk Dashboard      -> Controls + manifest + RiskDashboard
 *  3. Pathogens           -> Product & Program / Emerging Signals / Seasonal Patterns
 *  4. Communities         -> unified Communities with a State ⇄ County toggle
 *  5. Facilities          -> unified Facilities with a List ⇄ Map view toggle
 *  6. Decision Actions    -> Population Lens / Surveillance Actions / Scenario Builder /
 *                            Recommended Actions / Evidence & Explanation / Policy Comparison
 *  7. One Health & Data   -> OneHealthInsights (S05)
 *
 * No content merges or panel-internal changes happen here — every panel renders
 * exactly as before, only regrouped. The responsible-use banner and the
 * always-visible Regulatory Alerts strip stay mounted across all sections so a
 * verified recall is never hidden by navigation.
 */

type Section =
  | "overview"
  | "dashboard"
  | "pathogens"
  | "communities"
  | "facilities"
  | "actions"
  | "onehealth";

function Header({ section, setSection }: { section: Section; setSection: (s: Section) => void }) {
  const tabs: Array<{ id: Section; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "dashboard", label: "Risk Dashboard" },
    { id: "pathogens", label: "Pathogens" },
    { id: "communities", label: "Communities" },
    { id: "facilities", label: "Facilities" },
    { id: "actions", label: "Decision Actions" },
    { id: "onehealth", label: "One Health & Data" },
  ];
  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-navy text-white shadow-sm">
      <div className="mx-auto flex max-w-7xl flex-col gap-2 px-6 py-3">
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setSection("overview")}
            className="flex items-center gap-2 text-left"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded bg-teal text-sm font-black text-white">V</span>
            <span className="text-lg font-bold tracking-tight">VulneraSafe AI</span>
            <span className="hidden rounded bg-teal/20 px-2 py-0.5 text-[10px] font-semibold text-teal-500 sm:inline">
              One Health Food-Safety Decision Support
            </span>
          </button>
          <nav aria-label="Primary" className="flex gap-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                data-testid={`tab-${t.id}`}
                aria-current={section === t.id ? "page" : undefined}
                onClick={() => setSection(t.id)}
                className={`rounded-md px-3 py-1.5 text-sm font-semibold transition ${
                  section === t.id ? "bg-white text-navy" : "text-white/80 hover:bg-white/10"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </div>
    </header>
  );
}

function Controls() {
  const { region, setRegion } = useSelection();
  return (
    <nav
      aria-label="Region controls"
      className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-6 py-3"
    >
      <span className="text-xs font-semibold text-navy/60">Pathogen &amp; region are set on the dashboard below.</span>
      {region ? (
        <button
          type="button"
          data-testid="clear-region"
          onClick={() => setRegion(null)}
          className="rounded border border-navy/20 px-2 py-1 text-xs text-navy hover:bg-surface-muted"
        >
          Region: <span className="font-semibold">{region}</span> ✕
        </button>
      ) : null}
    </nav>
  );
}

/**
 * Risk Dashboard section: the manifest-driven controls + the Risk Dashboard
 * panel (Current Risk Overview + Prioritized Attention Queue live inside it).
 * The decision-tool panels that previously stacked below here have moved to the
 * "Decision Actions" section.
 */
function RiskDashboardSection() {
  const { data: manifest, loading, error } = useManifest();
  return (
    <>
      {/* Retains the manifest-driven pathogen select + region clear control
          alongside the dashboard's own pathogen pills; both drive the shared
          selection. */}
      <Controls />
      {error ? (
        <div className="mx-auto max-w-7xl px-6 pt-2">
          <EmptyState
            title="Could not load the data manifest"
            detail={`${error.message} Panels still render their own data where available.`}
          />
        </div>
      ) : null}
      {manifest ? (
        <p className="mx-auto max-w-7xl px-6 text-xs text-gray-500">
          Artifact version {manifest.artifact_version} · generated {manifest.generated_at}
          {loading ? " · loading…" : ""}
        </p>
      ) : null}
      <RiskDashboard />
    </>
  );
}

/** Pathogens section: three views over the pathogen-facing artifacts. */
function PathogensSection() {
  const subtabs: SectionTab[] = [
    { id: "product", label: "Product & Program" },
    { id: "emerging", label: "Emerging Signals" },
    { id: "seasonal", label: "Seasonal Patterns" },
  ];
  const [sub, setSub] = useState<string>("product");
  return (
    <>
      <SectionTabs tabs={subtabs} active={sub} onChange={setSub} />
      {sub === "emerging" ? (
        <EmergingSignals />
      ) : sub === "seasonal" ? (
        <SeasonalHazard />
      ) : (
        <PathogenExplorer />
      )}
    </>
  );
}

/**
 * Decision Actions section -> the DecisionActions panel, a guided three-step
 * flow (Act / Decide / Plan). The three mandatory decision panels (Scenario
 * Builder, Recommended Action Panel, Explanation / Evidence Panel) all live
 * inside it; the standalone Population Lens tab was removed (its global lens
 * had no live surface here - lens exploration lives on the Communities section).
 */
function DecisionActionsSection() {
  return <DecisionActions />;
}

function AppBody() {
  const [section, setSection] = useState<Section>("overview");
  return (
    <div className="min-h-full">
      <Header section={section} setSection={setSection} />
      <ResponsibleUseBanner />
      {section === "overview" ? (
        <Landing onEnter={() => setSection("dashboard")} />
      ) : section === "pathogens" ? (
        <PathogensSection />
      ) : section === "communities" ? (
        <Communities />
      ) : section === "facilities" ? (
        <Facilities />
      ) : section === "actions" ? (
        <DecisionActionsSection />
      ) : section === "onehealth" ? (
        <OneHealthInsights />
      ) : (
        <RiskDashboardSection />
      )}
    </div>
  );
}

export default function App() {
  return (
    <SelectionProvider>
      <AppBody />
    </SelectionProvider>
  );
}
