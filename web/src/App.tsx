import { useState } from "react";
import { useManifest } from "./data/hooks";
import EmptyState from "./components/EmptyState";
import ResponsibleUseBanner from "./components/ResponsibleUseBanner";
import RegulatoryAlertsStrip from "./components/RegulatoryAlertsStrip";
import Landing from "./components/Landing";
import { SelectionProvider, useSelection } from "./state/selection";
import { SectionTabs } from "./components/ui";
import type { SectionTab } from "./components/ui";
import RiskDashboard from "./components/panels/RiskDashboard";
import VulnerablePopulationLens from "./components/panels/VulnerablePopulationLens";
import ScenarioBuilder from "./components/panels/ScenarioBuilder";
import RecommendedActionPanel from "./components/panels/RecommendedActionPanel";
import ExplanationEvidencePanel from "./components/panels/ExplanationEvidencePanel";
import PolicyComparison from "./components/panels/PolicyComparison";
import PathogenExplorer from "./components/panels/PathogenExplorer";
import EmergingSignals from "./components/panels/EmergingSignals";
import OneHealthInsights from "./components/panels/OneHealthInsights";
import Communities from "./components/panels/Communities";
import Facilities from "./components/panels/Facilities";
import SurveillanceActions from "./components/panels/SurveillanceActions";
import SeasonalHazard from "./components/panels/SeasonalHazard";
import type { Manifest } from "./types/artifacts";

/**
 * App shell with a two-level navigation model (Req 12, 13).
 *
 * Seven top-level SECTIONS replace the previous flat eleven-tab strip. Sections
 * that hold more than one view render a secondary <SectionTabs/> sub-tab strip:
 *
 *  1. Overview            -> Landing (onEnter -> Risk Dashboard)
 *  2. Risk Dashboard      -> RegulatoryAlertsStrip + Controls + manifest + RiskDashboard
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

function Controls({ manifest }: { manifest: Manifest | null }) {
  const { pathogen, setPathogen, region, setRegion } = useSelection();
  const pathogens = manifest ? Object.keys(manifest.pathogens) : [];
  return (
    <nav
      aria-label="Pathogen and region controls"
      className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-6 py-3"
    >
      <label className="flex items-center gap-2 text-xs font-semibold text-navy">
        Pathogen
        <select
          id="pathogen-select"
          name="pathogen"
          data-testid="pathogen-select"
          value={pathogen ?? ""}
          onChange={(e) => setPathogen(e.target.value === "" ? null : e.target.value)}
          className="rounded border border-navy/20 bg-white px-2 py-1 text-xs text-navy focus:outline-none focus:ring-2 focus:ring-teal"
        >
          <option value="">All pathogens</option>
          {pathogens.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </label>
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
      <Controls manifest={manifest} />
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
 * Decision Actions section: the full decision layer, including the three
 * mandatory decision panels (Scenario Builder, Recommended Action Panel,
 * Explanation / Evidence Panel). The Population Lens — which sets the shared
 * vulnerable-population lens that drove the old DecisionTools stack — leads the
 * sub-tab strip so it stays reachable.
 */
function DecisionActionsSection() {
  const subtabs: SectionTab[] = [
    { id: "lens", label: "Population Lens" },
    { id: "surveillance", label: "Surveillance Actions" },
    { id: "scenario", label: "Scenario Builder" },
    { id: "recommended", label: "Recommended Actions" },
    { id: "evidence", label: "Evidence & Explanation" },
    { id: "policy", label: "Policy Comparison" },
  ];
  const [sub, setSub] = useState<string>("surveillance");
  return (
    <>
      <SectionTabs tabs={subtabs} active={sub} onChange={setSub} />
      {sub === "lens" ? (
        <VulnerablePopulationLens />
      ) : sub === "scenario" ? (
        <ScenarioBuilder />
      ) : sub === "recommended" ? (
        <RecommendedActionPanel />
      ) : sub === "evidence" ? (
        <ExplanationEvidencePanel />
      ) : sub === "policy" ? (
        <PolicyComparison />
      ) : (
        <SurveillanceActions />
      )}
    </>
  );
}

function AppBody() {
  const [section, setSection] = useState<Section>("overview");
  return (
    <div className="min-h-full">
      <Header section={section} setSection={setSection} />
      <ResponsibleUseBanner />
      {/* Hoisted so a verified recall is visible on every section, not hidden
          behind navigation. */}
      {section !== "overview" ? <RegulatoryAlertsStrip /> : null}
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
