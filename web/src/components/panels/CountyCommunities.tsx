import { useMemo, useState } from "react";
import { useArtifact } from "../../data/hooks";
import type { CountyCommunityImpactRecord } from "../../types/artifacts";
import { formatNumber, formatRisk } from "../../types/viewModels";
import StatusTag from "../StatusTag";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * County Communities (S07). The county-resolution companion to S06
 * (Vulnerable Communities). It overlays REAL county-level vulnerability
 * (Census ACS + USDA Food Access Atlas, aggregated to 5-digit county FIPS)
 * with each county's STATE-level FSIS surveillance hazard.
 *
 * The two sides of the join have different native resolutions, and that
 * mismatch is held honestly and prominently throughout: vulnerability is
 * county-measured, but the hazard shown for a county is its STATE's
 * surveillance positivity — identical for every county in the same
 * state+pathogen and NEVER a county-measured hazard. S07 never implies a
 * county contamination, a county infection, or a county-measured hazard.
 * `resolution_label` ("county vulnerability x state-level hazard") carries
 * this on every record and is surfaced as a high-visibility banner here.
 *
 * Switching the population lens reprioritizes attention but NEVER changes the
 * hazard. Under-5 and pregnancy lenses are not in the ACS extraction and are
 * shown as unavailable, never fabricated. Affected-population figures are
 * illustrative (people who could be affected IF exposed), never illness or
 * observed-exposure counts. Every value is OBSERVED.
 *
 * jsdom note: the county selector reuses the MapView fallback-grid idea — an
 * accessible grid of selectable county buttons — rather than a map, because no
 * county GeoJSON is bundled (only web/public/geo/us-states.json exists). This
 * keeps the substance (the ranked list) front and center and stays testable
 * when WebGL is mocked in setupTests.
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

/** How many ranked counties to show at most (~3,000 counties exist nationwide). */
const MAX_VISIBLE = 40;

function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-navy/10" aria-hidden>
      <div className="h-full rounded-full" style={{ width: `${Math.min(100, value * 100)}%`, backgroundColor: color }} />
    </div>
  );
}

export function CountyCommunities() {
  const state = useArtifact<CountyCommunityImpactRecord[]>("county_community_impact");
  const [pathogen, setPathogen] = useState<Pathogen>("Salmonella");
  const [lens, setLens] = useState<string>("elderly_65plus");

  return (
    <div data-testid="county-communities" className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-5 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-10 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          Food safety + food security · County-resolution companion to Vulnerable Communities
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">County Communities</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/80">
          County-level population vulnerability, ranked against each county's state surveillance hazard.
          Vulnerability context reprioritizes attention — it never changes the underlying hazard.
          These are overlays, not claims about who was exposed or who became ill.
        </p>
      </section>

      {/* PROMINENT resolution-mismatch banner (Req 1.5 / 1.6). This text is
          intentionally present in the DOM and high-visibility. */}
      <div
        data-testid="resolution-label"
        className="mb-5 rounded-xl border-2 border-teal/40 bg-teal/5 px-5 py-4 text-sm leading-relaxed text-navy"
      >
        <p className="text-xs font-bold uppercase tracking-wide text-teal-700">
          County vulnerability × state-level hazard
        </p>
        <p className="mt-1">
          The hazard shown for a county is its <span className="font-semibold">STATE's</span> surveillance positivity —{" "}
          <span className="font-semibold">identical for every county in a state</span>, not a county-measured hazard.
          County vulnerability is real county-level ACS + USDA Atlas data. Every value is{" "}
          <span className="font-semibold">OBSERVED</span>; this is not a county contamination or illness claim.
        </p>
      </div>

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
        <span className="font-semibold text-teal-700">state-level hazard</span> is the food-safety surveillance signal —
        it is READ-ONLY, shared by every county in a state, and does not change when you switch the population lens. The{" "}
        <span className="font-semibold text-navy">county vulnerability</span> lens reweights which counties rise to the
        top of the <span className="font-semibold">priority</span> list (hazard weighted 0.6, vulnerability 0.4).{" "}
        <span className="italic">
          Vulnerability is county-measured; the hazard is its state's value, not county-measured. Demographics never
          establish who was exposed or became ill.
        </span>
      </div>

      <PanelShell
        title={`${pathogen} — county vulnerability × state-level hazard`}
        subtitle="OBSERVED · county vulnerability · state-level hazard read-only (lens reprioritizes only)"
        info="Vulnerability is county-level (ACS + USDA Atlas). The hazard is the county's STATE-level surveillance positivity (read-only, identical across counties in a state, never county-measured). The lens reweights the priority ranking only. No county contamination or human-illness claim."
      >
        <ArtifactBody
          state={state}
          artifactName="county_community_impact"
          isEmpty={(rows) => rows.length === 0}
          emptyTitle="No county-community data available"
          emptyDetail="The county_community_impact artifact is present but empty. Run: python -m src.analysis.county_community_impact && python -m src.artifacts.exporter"
          render={(rows) => <CountyBody rows={rows} pathogen={pathogen} lens={lens} />}
        />
      </PanelShell>
    </div>
  );
}

function CountyBody({
  rows,
  pathogen,
  lens,
}: {
  rows: CountyCommunityImpactRecord[];
  pathogen: Pathogen;
  lens: string;
}) {
  const forPathogen = useMemo(() => rows.filter((r) => r.pathogen === pathogen), [rows, pathogen]);

  // A per-pathogen "(all)" style unavailable sentinel: a county_fips that is not
  // a resolvable 5-digit FIPS but marks the whole pathogen as unavailable.
  const pathogenUnavailable = forPathogen.find(
    (r) => r.availability_status === "unavailable" && (r.county_fips === "(all)" || !r.county_fips),
  );
  const available = useMemo(
    () => forPathogen.filter((r) => r.availability_status === "available"),
    [forPathogen],
  );
  const unavailableCounties = useMemo(
    () => forPathogen.filter((r) => r.availability_status === "unavailable" && r.county_fips && r.county_fips !== "(all)"),
    [forPathogen],
  );

  if (pathogenUnavailable && available.length === 0 && unavailableCounties.length === 0) {
    return (
      <EmptyState
        title={`${pathogen} — not available`}
        detail={pathogenUnavailable.unavailable_reason ?? "County ranking unavailable."}
      />
    );
  }
  if (available.length === 0 && unavailableCounties.length === 0) {
    return <EmptyState title="No data for this pathogen" detail={`No counties with a vulnerability profile for ${pathogen}.`} />;
  }

  // Lens availability — inspect the first available record's lens entry.
  const lensEntry = (r: CountyCommunityImpactRecord) => r.lenses.find((l) => l.lens === lens);
  const sampleLens = available.length > 0 ? lensEntry(available[0]) : undefined;
  const lensUnavailable = sampleLens ? !sampleLens.available : true;

  // Per-pathogen disclosures (identical across rows; take the first available).
  const sensitivity = available.find((r) => r.weight_sensitivity)?.weight_sensitivity ?? null;
  const acsVintage = available.find((r) => r.acs_vintage)?.acs_vintage ?? null;
  const atlasVintage = available.find((r) => r.atlas_vintage)?.atlas_vintage ?? null;
  const ctxNote = available[0]?.contextual_count_note ?? "";

  // Map county_fips -> county_name for resolving weight-sensitivity FIPS lists.
  const nameByFips = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of forPathogen) {
      if (r.county_fips && r.county_name) m.set(r.county_fips, r.county_name);
    }
    return m;
  }, [forPathogen]);
  const resolveFips = (fips: string) => {
    const name = nameByFips.get(fips);
    return name ? `${name} (${fips})` : fips;
  };

  // Ranked counties by the selected lens's priority_score desc.
  const ranked = useMemo(
    () =>
      [...available]
        .map((r) => ({ r, L: lensEntry(r) }))
        .filter((x) => x.L && x.L.available && x.L.priority_score !== null)
        .sort((a, b) => (b.L!.priority_score ?? 0) - (a.L!.priority_score ?? 0)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [available, lens],
  );

  const totalAvailable = ranked.length;
  const visible = ranked.slice(0, MAX_VISIBLE);

  // Unavailable breakdown by reason (honest, not hidden) (Req 5.5).
  const noHazard = unavailableCounties.filter((r) =>
    (r.unavailable_reason ?? "").toLowerCase().includes("hazard"),
  ).length;
  const noVuln = unavailableCounties.filter((r) => {
    const reason = (r.unavailable_reason ?? "").toLowerCase();
    return reason.includes("vulnerab") || reason.includes("profile") || reason.includes("acs") || reason.includes("atlas");
  }).length;
  const otherUnavailable = unavailableCounties.length - noHazard - noVuln;

  return (
    <div className="flex flex-col gap-5">
      {/* side-by-side legends */}
      <div className="flex flex-wrap items-center gap-3 text-[10px]">
        <span className="flex items-center gap-1 rounded-full bg-teal/10 px-2 py-0.5 font-semibold text-teal-700">
          <span className="inline-block h-2 w-2 rounded-full bg-teal" /> State-level hazard (read-only)
        </span>
        <span className="flex items-center gap-1 rounded-full bg-navy/10 px-2 py-0.5 font-semibold text-navy/70">
          <span className="inline-block h-2 w-2 rounded-full bg-navy" /> County vulnerability (this lens)
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
        <>
          {/* County selector grid (fallback-grid pattern; the substance is the
              ranked list below, so the grid itself is the accessible selector).
              Reuses the MapView data-testid="map-view" container so WebGL-mocked
              jsdom tests can target it, with per-county data-testid="county-row"
              buttons. */}
          <div className="rounded-lg border border-navy/10 bg-white p-4">
            <div className="mb-1 flex items-center justify-between gap-2">
              <h3 className="text-sm font-bold text-navy">
                Priority ranking — {LENSES.find((l) => l.id === lens)?.label}
              </h3>
              <span className="text-[10px] text-navy/40">
                showing top {visible.length} of {totalAvailable} available nationwide
              </span>
            </div>
            <p className="mb-3 text-[11px] text-navy/50">
              Ranked by priority (0.6 × state-level hazard + 0.4 × this county's vulnerability on this lens). The hazard
              bar is the county's STATE value — identical for every county in a state and unchanged no matter which lens
              is selected; only the ordering changes.
            </p>

            <RankedCountyGrid
              rows={visible}
              lensEntry={lensEntry}
              ctxNote={ctxNote}
            />
          </div>
        </>
      )}

      {/* Unavailable counties summary — honest, by reason (Req 5.5). */}
      {unavailableCounties.length > 0 ? (
        <div className="rounded-lg border border-navy/10 bg-white p-4">
          <h3 className="mb-1 text-sm font-bold text-navy">Counties not shown (retained, not hidden)</h3>
          <p className="text-[11px] leading-relaxed text-navy/70">
            {unavailableCounties.length} counties are unavailable for {pathogen} and are not dropped or fabricated:{" "}
            <span className="font-semibold text-navy">{noHazard}</span> have no state-level hazard for this pathogen,{" "}
            <span className="font-semibold text-navy">{noVuln}</span> have no county vulnerability profile
            {otherUnavailable > 0 ? (
              <>
                , and <span className="font-semibold text-navy">{otherUnavailable}</span> for another stated reason
              </>
            ) : null}
            .
          </p>
        </div>
      ) : null}

      {/* Weight sensitivity (Req 7). default_top / alt_top hold county FIPS;
          resolve to county names where possible, else show the FIPS. */}
      {sensitivity ? (
        <div className="rounded-lg border border-navy/10 bg-white p-4">
          <h3 className="mb-1 text-sm font-bold text-navy">How sensitive is this to the weights?</h3>
          <p className="text-[11px] leading-relaxed text-navy/70">
            Top counties under the default weighting (hazard 0.6 / vulnerability 0.4):{" "}
            <span className="font-semibold text-navy">
              {sensitivity.default_top.map(resolveFips).join(", ") || "N/A"}
            </span>
            . Under a more equity-forward weighting (0.4 / 0.6):{" "}
            <span className="font-semibold text-navy">
              {sensitivity.alt_top.map(resolveFips).join(", ") || "N/A"}
            </span>
            .{" "}
            <span className="italic text-navy/50">
              The top set {sensitivity.rank_stable ? "is stable" : "shifts"} between weightings — no single weighting is
              definitive. {sensitivity.note}
            </span>
          </p>
        </div>
      ) : null}

      <p className="text-[10px] italic text-navy/50">
        OBSERVED state-level hazard (USDA FSIS surveillance, read-only) overlaid with county ACS {acsVintage ?? "2022"} /
        USDA Food Access Atlas {atlasVintage ?? "2019"} vulnerability context. {ctxNote} The population lens never
        changes the hazard; it only reprioritizes. The hazard is state-level while the vulnerability is county-level —
        the "county vulnerability × state-level hazard" mismatch. No county/tract contamination or individual
        human-illness estimate. Under-5 and pregnancy lenses are not in the current ACS extraction and are shown as
        unavailable, never fabricated.
      </p>
    </div>
  );
}

/**
 * Accessible grid of the top ranked counties as selectable buttons. Selecting a
 * county opens a small detail line beneath the grid. Each button carries
 * data-testid="county-row" and data-county={county_fips}. The container reuses
 * data-testid="map-view" so WebGL-mocked jsdom tests find the selector where the
 * MapView would otherwise sit.
 */
function RankedCountyGrid({
  rows,
  lensEntry,
  ctxNote,
}: {
  rows: Array<{ r: CountyCommunityImpactRecord; L: CountyCommunityImpactRecord["lenses"][number] | undefined }>;
  lensEntry: (r: CountyCommunityImpactRecord) => CountyCommunityImpactRecord["lenses"][number] | undefined;
  ctxNote: string;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const selectedRow = rows.find((x) => x.r.county_fips === selected) ?? null;

  return (
    <div className="flex flex-col gap-3">
      <ul
        data-testid="map-view"
        role="group"
        aria-label="County priority ranking (vulnerability × state-level hazard)"
        className="flex flex-col gap-2"
      >
        {rows.map(({ r, L }, i) => {
          const on = r.county_fips === selected;
          return (
            <li key={r.county_fips}>
              <button
                type="button"
                data-testid="county-row"
                data-county={r.county_fips}
                aria-pressed={on}
                onClick={() => setSelected(on ? null : r.county_fips)}
                className={`grid w-full grid-cols-[1.75rem,1fr,auto] items-center gap-x-3 rounded-lg border px-3 py-2 text-left transition focus:outline-none focus:ring-2 focus:ring-teal ${
                  on ? "border-teal bg-teal/5" : "border-navy/10 bg-white hover:border-navy/25"
                }`}
              >
                <span className="text-[10px] font-bold text-navy/40">#{i + 1}</span>
                <div className="flex min-w-0 flex-col gap-1">
                  <span className="truncate text-xs font-bold text-navy">
                    {r.county_name ?? r.county_fips}
                    {r.state ? <span className="font-normal text-navy/50">, {r.state}</span> : null}
                    <span className="ml-1 text-[9px] font-normal text-navy/30">{r.county_fips}</span>
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="w-24 text-[9px] uppercase tracking-wide text-teal-700">state-level hazard</span>
                    <Bar value={r.hazard_component ?? 0} color="#0d9488" />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-24 text-[9px] uppercase tracking-wide text-navy/60">vulnerability</span>
                    <Bar value={L?.vulnerability_component ?? 0} color="#1e3a5f" />
                  </div>
                </div>
                <div className="text-right text-xs">
                  <span className="font-bold text-navy">{formatRisk(L?.priority_score ?? null)}</span>
                  <div className="text-[9px] text-navy/40">priority</div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>

      {selectedRow ? (
        <div className="rounded-lg border border-teal/30 bg-teal/5 px-4 py-3 text-[11px] leading-relaxed text-navy">
          <p>
            <span className="font-bold text-navy">
              {selectedRow.r.county_name ?? selectedRow.r.county_fips}
              {selectedRow.r.state ? `, ${selectedRow.r.state}` : ""}
            </span>{" "}
            — state-level hazard positivity {formatRisk(selectedRow.r.hazard_positivity)} (its state's value, not
            county-measured); vulnerability {formatRisk(lensEntry(selectedRow.r)?.vulnerability_component ?? null)};
            priority {formatRisk(lensEntry(selectedRow.r)?.priority_score ?? null)}.
          </p>
          <p className="mt-1">
            Affected-population context:{" "}
            <span className="font-semibold text-navy">
              {formatNumber(selectedRow.r.affected_population_context, 0)}
            </span>{" "}
            people could be affected IF exposed.{" "}
            <span className="italic text-navy/50">{ctxNote || "Illustrative only — never observed exposure or illness."}</span>
          </p>
        </div>
      ) : (
        <p className="text-[10px] italic text-navy/40">Select a county above to see its affected-population context.</p>
      )}
    </div>
  );
}

export default CountyCommunities;
