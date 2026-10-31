import { useArtifact } from "../../data/hooks";
import { useSelection } from "../../state/selection";
import type { PopulationLens } from "../../state/selection";
import type { VulnerabilityProfile } from "../../types/artifacts";
import { formatRisk, orNotAvailable } from "../../types/viewModels";
import { LENS_EMPHASIS } from "../../types/lens";
import StatusTag from "../StatusTag";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Vulnerable-Population Lens (Layer 2).
 *
 * A lens that re-frames the dashboard around a vulnerable group WITHOUT changing
 * any hazard prediction (Layer 1 is untouched). It (a) emphasizes the pathogens
 * most relevant to the selected group, citing severity context, and (b) shows
 * REAL ACS / Food Access Atlas vulnerability + food-access context for the
 * selected state. Fields the data does not provide (under-5 share, pregnancy
 * counts) are shown as "not available" — never fabricated. Population
 * vulnerability is explicitly separated from actual exposure.
 */

interface LensDef {
  id: Exclude<PopulationLens, null>;
  label: string;
  who: string;
  evidence: string;
  icon: string;
}

/**
 * Local presentation metadata for each lens (label / who / evidence / icon).
 * The emphasized pathogens are NOT stored here — they come from the shared
 * `LENS_EMPHASIS` map so the queue and the lens picker agree on one source of
 * truth (see `../../types/lens`).
 */
const LENSES: LensDef[] = [
  {
    id: "pregnancy",
    label: "Pregnancy & newborns",
    who: "Expectant parents · infants",
    evidence:
      "Listeriosis in pregnancy can cause miscarriage, stillbirth, and severe newborn infection; ready-to-eat foods are the key exposure route.",
    icon: "🤰",
  },
  {
    id: "under5",
    label: "Children under 5",
    who: "Young children",
    evidence:
      "Young children face higher rates of severe STEC complications (incl. hemolytic uremic syndrome) and salmonellosis hospitalization.",
    icon: "🧒",
  },
  {
    id: "elderly",
    label: "Adults 65+",
    who: "Older adults",
    evidence:
      "Weakened immunity and more comorbidities drive higher hospitalization and death rates across all three pathogens.",
    icon: "🧓",
  },
];

function Pct({ v }: { v: number | null }) {
  return <span>{v === null || v === undefined ? "not available" : formatRisk(v)}</span>;
}

export function VulnerablePopulationLens() {
  const { lens, setLens, pathogen, setPathogen, region } = useSelection();
  const state = useArtifact<VulnerabilityProfile[]>("vulnerability");
  const active = LENSES.find((l) => l.id === lens) ?? null;

  return (
    <PanelShell
      title="Vulnerable-Population Lens"
      subtitle="Who is most affected — context only, hazard prediction is unchanged"
      className="lg:col-span-2"
      info="Choose a vulnerable group to emphasize the pathogens and food-access context most relevant to them. Selecting a lens does NOT change any risk prediction — it only re-frames emphasis and shows real ACS / Food Access Atlas context (OBSERVED). Population vulnerability is separate from actual exposure."
    >
      <div className="flex flex-col gap-4">
        {/* Lens picker */}
        <div className="flex flex-wrap gap-2">
          {LENSES.map((l) => {
            const on = lens === l.id;
            return (
              <button
                key={l.id}
                type="button"
                aria-pressed={on}
                onClick={() => setLens(on ? null : l.id)}
                className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs transition ${
                  on
                    ? "border-teal bg-teal/10 text-navy"
                    : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
                }`}
              >
                <span className="text-lg" aria-hidden>{l.icon}</span>
                <span>
                  <span className="block font-bold">{l.label}</span>
                  <span className="block text-[10px] text-navy/50">{l.who}</span>
                </span>
              </button>
            );
          })}
          {lens ? (
            <button
              type="button"
              onClick={() => setLens(null)}
              className="rounded-lg border border-navy/15 px-3 py-2 text-xs text-navy/60 hover:bg-surface-muted"
            >
              Clear lens ✕
            </button>
          ) : null}
        </div>

        {active ? (
          <div className="grid gap-4 md:grid-cols-2">
            {/* Pathogen emphasis */}
            <div className="rounded-lg border border-navy/10 bg-surface-muted p-3">
              <h3 className="text-xs font-bold text-navy">
                Most relevant pathogens for {active.label.toLowerCase()}
              </h3>
              <div className="mt-2 flex flex-wrap gap-2">
                {LENS_EMPHASIS[active.id].map((pth) => (
                  <button
                    key={pth}
                    type="button"
                    onClick={() => setPathogen(pth)}
                    className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                      pathogen === pth
                        ? "border-teal bg-teal text-white"
                        : "border-teal/40 bg-teal/5 text-teal-700 hover:bg-teal/10"
                    }`}
                  >
                    {pth}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-navy/70">{active.evidence}</p>
              <p className="mt-2 text-[10px] italic text-navy/50">
                Severity emphasis only — this does not change the modeled hazard
                probability for any pathogen or region.
              </p>
            </div>

            {/* Real vulnerability / food-access context for the selected state */}
            <ArtifactBody
              state={state}
              artifactName="vulnerability"
              isEmpty={(v) => v.length === 0}
              emptyTitle="No vulnerability context available"
              emptyDetail="The vulnerability artifact is present but empty."
              render={(profiles) => {
                const prof = region
                  ? profiles.find((p) => p.region === region) ?? null
                  : null;
                if (!prof) {
                  return (
                    <div className="rounded-lg border border-dashed border-navy/20 bg-white p-3 text-xs text-navy/60">
                      Select a state on the map to see its community vulnerability
                      and food-access context.
                    </div>
                  );
                }
                return (
                  <div className="rounded-lg border border-navy/10 bg-white p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <h3 className="text-xs font-bold text-navy">
                        Community context · {prof.region}
                      </h3>
                      <StatusTag status={prof.status} />
                    </div>
                    <dl className="grid grid-cols-[1fr,auto] gap-x-3 gap-y-1 text-xs">
                      <dt className="text-navy/60">Total population (ACS)</dt>
                      <dd className="text-right font-semibold text-navy">
                        {prof.total_population === null
                          ? "not available"
                          : Math.round(prof.total_population).toLocaleString()}
                      </dd>
                      <dt className="text-navy/60">Adults 65+ share</dt>
                      <dd className="text-right font-semibold text-navy"><Pct v={prof.elderly_65plus_share} /></dd>
                      <dt className="text-navy/60">Children under 5 share</dt>
                      <dd className="text-right font-semibold text-navy/50"><Pct v={prof.under5_share} /></dd>
                      <dt className="text-navy/60">Low-income tracts</dt>
                      <dd className="text-right font-semibold text-navy"><Pct v={prof.low_income_tract_share} /></dd>
                      <dt className="text-navy/60">Low-income & low-access</dt>
                      <dd className="text-right font-semibold text-navy"><Pct v={prof.low_access_tract_share} /></dd>
                    </dl>
                    <p className="mt-2 text-[10px] italic text-navy/50">
                      ACS {orNotAvailable(prof.acs_vintage)} · Food Access Atlas{" "}
                      {orNotAvailable(prof.atlas_vintage)}. Pregnancy counts are not
                      derived and under-5 share is not in the current ACS pull —
                      shown as "not available" rather than estimated.
                    </p>
                  </div>
                );
              }}
            />
          </div>
        ) : (
          <p className="rounded-lg border border-dashed border-navy/20 bg-surface-muted p-4 text-center text-xs text-navy/60">
            Select a vulnerable group above to emphasize the most relevant
            pathogens and view real community food-access context. The underlying
            hazard predictions never change.
          </p>
        )}
      </div>
    </PanelShell>
  );
}

export default VulnerablePopulationLens;
