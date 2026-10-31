import { useState } from "react";
import { useManifest } from "./data/hooks";
import EmptyState from "./components/EmptyState";
import ResponsibleUseBanner from "./components/ResponsibleUseBanner";
import RegulatoryAlertsStrip from "./components/RegulatoryAlertsStrip";
import StatusLegend from "./components/legend/StatusLegend";
import Landing from "./components/Landing";
import { SelectionProvider, useSelection } from "./state/selection";
import CurrentRiskOverview from "./components/panels/CurrentRiskOverview";
import AttentionQueue from "./components/panels/AttentionQueue";
import ScenarioBuilder from "./components/panels/ScenarioBuilder";
import RecommendedActionPanel from "./components/panels/RecommendedActionPanel";
import ExplanationEvidencePanel from "./components/panels/ExplanationEvidencePanel";
import VulnerablePopulationLens from "./components/panels/VulnerablePopulationLens";
import PolicyComparison from "./components/panels/PolicyComparison";
import PathogenExplorer from "./components/panels/PathogenExplorer";
import EmergingSignals from "./components/panels/EmergingSignals";
import SupplierMonitor from "./components/panels/SupplierMonitor";
import OneHealthInsights from "./components/panels/OneHealthInsights";
import VulnerableCommunities from "./components/panels/VulnerableCommunities";
import type { Manifest } from "./types/artifacts";

/**
 * App shell with top-level tabbed navigation (Req 12, 13).
 *
 *  - "Overview" renders the marketing/explainer Landing page.
 *  - "Dashboard" renders the five mandatory panels wired to the artifacts.
 *
 * The responsible-use banner and the always-visible Regulatory Alerts strip
 * stay mounted across tabs so a verified recall is never hidden by navigation.
 */

type Tab = "overview" | "dashboard" | "explorer" | "emerging" | "supplier" | "onehealth" | "communities";



function Header({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "dashboard", label: "Dashboard" },
    { id: "explorer", label: "Pathogen Explorer" },
    { id: "emerging", label: "Emerging Signals" },
    { id: "supplier", label: "Supplier Monitor" },
    { id: "onehealth", label: "One Health Insights" },
    { id: "communities", label: "Vulnerable Communities" },


  ];
  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-navy text-white shadow-sm">
      <div className="mx-auto flex max-w-7xl flex-col gap-2 px-6 py-3">
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setTab("overview")}
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
                aria-current={tab === t.id ? "page" : undefined}
                onClick={() => setTab(t.id)}
                className={`rounded-md px-3 py-1.5 text-sm font-semibold transition ${
                  tab === t.id ? "bg-white text-navy" : "text-white/80 hover:bg-white/10"
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

function PanelGrid() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CurrentRiskOverview />
        <VulnerablePopulationLens />
        <AttentionQueue />
        <ScenarioBuilder />
        <RecommendedActionPanel />
        <ExplanationEvidencePanel />
        <PolicyComparison />
      </div>
    </main>
  );
}

function Dashboard() {
  const { data: manifest, loading, error } = useManifest();
  return (
    <>
      <RegulatoryAlertsStrip />
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
      <PanelGrid />
      <StatusLegend />
    </>
  );
}

function AppBody() {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="min-h-full">
      <Header tab={tab} setTab={setTab} />
      <ResponsibleUseBanner />
      {tab === "overview" ? (
        <Landing onEnter={() => setTab("dashboard")} />
      ) : tab === "explorer" ? (
        <PathogenExplorer />
      ) : tab === "emerging" ? (
        <EmergingSignals />
      ) : tab === "supplier" ? (
        <SupplierMonitor />
      ) : tab === "onehealth" ? (
        <OneHealthInsights />
      ) : tab === "communities" ? (
        <VulnerableCommunities />
      ) : (
        <Dashboard />
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
