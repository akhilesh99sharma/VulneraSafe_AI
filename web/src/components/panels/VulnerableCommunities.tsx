import { useMemo, useState } from "react";
import { useArtifact } from "../../data/hooks";
import type { CommunityImpactRecord } from "../../types/artifacts";
import { formatRisk } from "../../types/viewModels";
import StatusTag from "../StatusTag";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Vulnerable Communities (S06). Overlays READ-ONLY state food-safety hazard with
 * community-vulnerability context (ACS 2022 / USDA Atlas 2019) into a documented
 * priority ranking. Switching the population lens reprioritizes attention but
 * NEVER changes the hazard. State-level only — no county/tract infection claim.
 * Under-5 and pregnancy lenses are unavailable (not in the ACS extraction) and
 * are shown as such, never fabricated. Affected-population figures are
 * contextual (could be affected IF exposed), never illness counts.
 */

const PATHOGENS = ["Salmonella", "Listeria", "STEC"] as const;
type Pathogen = (typeof PATHOGENS)[number];

const LENSES: Array<{ id: string; label: string }> = [
  { id: "elderly_65plus", label: "Adults 65+" },
  { id: "low_income", label: "Low-income tracts" },
  { id: "low_access", label: "Low food-access tracts" },
  { id: "under5", label: "Children under 5" },
  { id: "pregnancy", label: "Pregnancy / newborn" },
];

export function VulnerableCommunities() {
  const state = useArtifact<CommunityImpactRecord[]>("community_impact");
  const [pathogen, setPathogen] = useState<Pathogen>("Salmonella");
  const [lens, setLens] = useState<string>("elderly_65plus");
  // Live hazard weight (vulnerability = 1 - this). Default 0.6 matches the
  // artifact\u2019s own priority_score weighting; the slider only re-weights
  // values already in the data (hazard_component + vulnerability_component).
  const [weightHazard, setWeightHazard] = useState(0.6);

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-5 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-6 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          Food safety + food security · Vulnerability-aware prioritization
        </span>
        <h1 className="mt-3 text-2xl font-extrabold tracking-tight sm:text-3xl">Vulnerable Communities</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/80">
          Where does elevated food-safety surveillance risk coincide with high-need populations?
          Vulnerability context reprioritizes attention — it never changes the underlying hazard.
          These are state-level overlays, not claims about who was exposed or who became ill.
        </p>
      </section>

      {/* Pathogen selector */}
      <div className="mb-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy/60">Select a pathogen</p>
        <div className="flex flex-wrap gap-2">
          {PATHOGENS.map((p) => {
            const on = p === pathogen;
            return (
              <button
                key={p}
                type="button"
                aria-pressed={on}
                onClick={() => setPathogen(p)}
                className={`rounded-lg border px-4 py-2 text-sm font-semibold transition ${
                  on ? "border-teal bg-teal text-white" : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
                }`}
              >
                {p === "STEC" ? "STEC (E. coli)" : p}
              </button>
            );
          })}
        </div>
      </div>

      {/* Population lens tabs */}
      <div className="mb-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy/60">Population lens</p>
        <div className="flex flex-wrap gap-2">
          {LENSES.map((l) => {
            const on = l.id === lens;
            return (
              <button
                key={l.id}
                type="button"
                aria-pressed={on}
                onClick={() => setLens(l.id)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                  on ? "border-navy bg-navy text-white" : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
                }`}
              >
                {l.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* How to read this */}
      <div className="mb-5 rounded-lg border border-navy/10 bg-surface-muted px-4 py-3 text-[11px] leading-relaxed text-navy/70">
        <span className="font-semibold text-navy">How to read this:</span> the{" "}
        <span className="font-semibold text-teal-700">hazard</span> is the food-safety surveillance signal — it is
        READ-ONLY and does not change when you switch the population lens. The{" "}
        <span className="font-semibold text-navy">vulnerability</span> lens reweights which states rise to the top of
        the <span className="font-semibold">priority</span> list, so attention can favor high-need communities while
        food safety stays the hard constraint (hazard weighted 0.6, vulnerability 0.4).{" "}
        <span className="italic">State-level only; demographics never establish who was exposed or became ill.</span>
      </div>

      <PanelShell
        title={`${pathogen} — hazard × community vulnerability`}
        subtitle="OBSERVED · state level · hazard read-only (lens reprioritizes only)"
        info="Hazard is the read-only surveillance signal (never changed by the lens). The vulnerability lens reweights the priority ranking only. State-level; no county/tract or human-illness claim."
      >
        <ArtifactBody
          state={state}
          artifactName="community_impact"
          isEmpty={(rows) => rows.length === 0}
          emptyTitle="No community-impact data available"
          emptyDetail="The community_impact artifact is present but empty. Run: python -m src.analysis.community_impact && python -m src.artifacts.exporter"
          render={(rows) => (
            <CommunitiesBody
              rows={rows}
              pathogen={pathogen}
              lens={lens}
              weightHazard={weightHazard}
              onWeight={setWeightHazard}
            />
          )}
        />
      </PanelShell>
    </div>
  );
}

function CommunitiesBody({
  rows,
  pathogen,
  lens,
  weightHazard,
  onWeight,
}: {
  rows: CommunityImpactRecord[];
  pathogen: Pathogen;
  lens: string;
  weightHazard: number;
  onWeight: (w: number) => void;
}) {
  const forPathogen = useMemo(() => rows.filter((r) => r.pathogen === pathogen), [rows, pathogen]);
  const unavailable = forPathogen.find((r) => r.availability_status === "unavailable" && r.region === "(all)");
  const available = useMemo(
    () => forPathogen.filter((r) => r.availability_status === "available"),
    [forPathogen],
  );

  if (unavailable && available.length === 0) {
    return <EmptyState title={`${pathogen} — not available`} detail={unavailable.unavailable_reason ?? "Ranking unavailable."} />;
  }
  if (available.length === 0) {
    return <EmptyState title="No data for this pathogen" detail={`No states with vulnerability profile for ${pathogen}.`} />;
  }

  // Is the selected lens a data-backed one? Check the first record's lens entry.
  const lensEntry = (r: CommunityImpactRecord) => r.lenses.find((l) => l.lens === lens);
  const sampleLens = lensEntry(available[0]);
  const lensUnavailable = sampleLens ? !sampleLens.available : true;

  // Weight sensitivity (same across records; take the first available).
  const sensitivity = available.find((r) => r.weight_sensitivity)?.weight_sensitivity ?? null;
  const acsVintage = available.find((r) => r.acs_vintage)?.acs_vintage ?? null;
  const atlasVintage = available.find((r) => r.atlas_vintage)?.atlas_vintage ?? null;
  const ctxNote = available[0]?.contextual_count_note ?? "";

  // LIVE priority = w*hazard + (1-w)*vulnerability, re-weighting ONLY the
  // hazard_component + vulnerability_component already in the data (no fabrication).
  // At the default w=0.6 this equals the artifact's own priority_score.
  const priorityOf = (rec: CommunityImpactRecord, L: ReturnType<typeof lensEntry>) =>
    weightHazard * (rec.hazard_component ?? 0) + (1 - weightHazard) * (L?.vulnerability_component ?? 0);
  const ranked = [...available]
    .map((rec) => ({ r: rec, L: lensEntry(rec) }))
    .filter((x) => x.L && x.L.available && x.L.priority_score !== null)
    .map((x) => ({ ...x, P: priorityOf(x.r, x.L) }))
    .sort((a, b) => b.P - a.P);

  const top = ranked[0];
  return (
    <div className="flex flex-col gap-5">
      {top ? (
        <div className="rounded-xl border border-teal/20 bg-teal/5 px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-teal-700">Top priority</p>
          <p className="mt-0.5 text-[13px] leading-relaxed text-navy/80">
            <span className="font-bold text-navy">{top.r.region}</span> ranks highest for this lens
            at the current {Math.round(weightHazard * 100)}/{100 - Math.round(weightHazard * 100)} hazard/vulnerability weighting
            (priority {formatRisk(top.P)}). Attention, not a contamination claim.
          </p>
        </div>
      ) : null}
      <div className="flex flex-col gap-2 rounded-lg border border-navy/10 bg-surface-muted px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold text-navy">Balance hazard vs vulnerability</span>
          <button
            type="button"
            onClick={() => onWeight(0.6)}
            className="rounded border border-navy/20 px-2 py-0.5 text-[10px] font-semibold text-navy/70 hover:bg-navy/5"
          >
            Reset to default (60/40)
          </button>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(weightHazard * 100)}
          onChange={(e) => onWeight(Number(e.target.value) / 100)}
          aria-label="Hazard weight percent"
          className="h-1.5 w-full cursor-pointer accent-teal"
        />
        <div className="flex justify-between text-[10px] text-navy/60">
          <span className="font-semibold text-teal-700">hazard {Math.round(weightHazard * 100)}%</span>
          <span className="font-semibold text-navy/70">vulnerability {100 - Math.round(weightHazard * 100)}%</span>
        </div>
      </div>
      {/* side-by-side legends */}
      <div className="flex flex-wrap items-center gap-3 text-[10px]">
        <span className="flex items-center gap-1 rounded-full bg-teal/10 px-2 py-0.5 font-semibold text-teal-700">
          <span className="inline-block h-2 w-2 rounded-full bg-teal" /> Hazard (read-only surveillance)
        </span>
        <span className="flex items-center gap-1 rounded-full bg-navy/10 px-2 py-0.5 font-semibold text-navy/70">
          <span className="inline-block h-2 w-2 rounded-full bg-navy" /> Vulnerability (this lens)
        </span>
        <StatusTag status="OBSERVED" />
        {acsVintage ? <span className="text-navy/40">ACS {acsVintage}</span> : null}
        {atlasVintage ? <span className="text-navy/40">· Atlas {atlasVintage}</span> : null}
      </div>

      {lensUnavailable ? (
        <div className="rounded-lg border border-dashed border-navy/20 bg-white p-4">
          <h3 className="text-sm font-bold text-navy">This lens is not available</h3>
          <p className="mt-1 text-xs italic text-navy/60">
            {sampleLens?.unavailable_reason ??
              "This population lens is not supported by the current ACS extraction and is not fabricated."}{" "}
            The hazard and the data-backed lenses (65+, low-income, low food-access) remain available.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-navy/10 bg-white p-4">
          <div className="mb-1 flex items-center justify-between gap-2">
            <h3 className="text-sm font-bold text-navy">
              Priority ranking — {LENSES.find((l) => l.id === lens)?.label}
            </h3>
            <span className="text-[10px] text-navy/40">{ranked.length} states</span>
          </div>
          <p className="mb-3 text-[11px] text-navy/50">
            Ranked by a live priority score blending {Math.round(weightHazard * 100)}% hazard with{" "}
            {100 - Math.round(weightHazard * 100)}% vulnerability. Hazard is identical no matter which
            lens is selected; the slider and lens only re-order the list.
          </p>
          <ul className="flex flex-col gap-2.5">
            {ranked.slice(0, 15).map(({ r, L, P }, i) => {
              const haz = r.hazard_component ?? 0;
              const vul = L!.vulnerability_component ?? 0;
              const hazPart = weightHazard * haz;
              const vulPart = (1 - weightHazard) * vul;
              const total = Math.max(hazPart + vulPart, 0.0001);
              const hazPct = (hazPart / total) * 100;
              return (
                <li key={r.region} className="grid grid-cols-[2.25rem,1fr,auto] items-center gap-x-3">
                  <span className="flex items-center gap-1.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-navy text-[10px] font-bold text-white">{i + 1}</span>
                    <span className="text-[13px] font-bold text-navy">{r.region}</span>
                  </span>
                  <div className="flex h-3 w-full overflow-hidden rounded-full bg-navy/10" title={`hazard ${formatRisk(haz)} * ${Math.round(weightHazard * 100)}% + vulnerability ${formatRisk(vul)} * ${100 - Math.round(weightHazard * 100)}%`}>
                    <div className="h-full bg-teal" style={{ width: `${hazPct}%` }} />
                    <div className="h-full bg-navy" style={{ width: `${100 - hazPct}%` }} />
                  </div>
                  <div className="text-right">
                    <span className="text-[13px] font-bold text-navy">{formatRisk(P)}</span>
                    <div className="text-[9px] text-navy/40">priority</div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Weight sensitivity */}
      {sensitivity ? (
        <div className="rounded-lg border border-navy/10 bg-white p-4">
          <h3 className="mb-1 text-sm font-bold text-navy">How sensitive is this to the weights?</h3>
          <p className="text-[11px] leading-relaxed text-navy/70">
            Top states under the default weighting (hazard 0.6 / vulnerability 0.4):{" "}
            <span className="font-semibold text-navy">{sensitivity.default_top.join(", ")}</span>. Under a more
            equity-forward weighting (0.4 / 0.6):{" "}
            <span className="font-semibold text-navy">{sensitivity.alt_top.join(", ")}</span>.{" "}
            <span className="italic text-navy/50">
              The top set {sensitivity.rank_stable ? "is stable" : "shifts"} between weightings — no single weighting
              is definitive; this is for the 65+ lens.
            </span>
          </p>
        </div>
      ) : null}

      <p className="text-[10px] italic text-navy/50">
        OBSERVED state hazard (USDA FSIS surveillance, read-only) overlaid with ACS {acsVintage ?? "2022"} /
        USDA Food Access Atlas {atlasVintage ?? "2019"} vulnerability context. {ctxNote} The population lens never
        changes the hazard; it only reprioritizes. State-level only — no county/tract or individual human-illness
        estimate. Under-5 and pregnancy lenses are not in the current ACS extraction and are shown as unavailable,
        never fabricated.
      </p>
    </div>
  );
}

export default VulnerableCommunities;
