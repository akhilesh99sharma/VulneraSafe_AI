import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

/**
 * Interactive landing / story page. Pure presentational React with inline SVG
 * art (no external image origins, so the app stays fully static). It opens on
 * the PROBLEM, introduces the VULNERABLE GROUPS, shows the SCALE, then
 * transitions into WHAT WE DO (the overview) and hands off to the dashboard.
 */

/* --------------------------------- hooks -------------------------------- */
/** Reveal-on-scroll: adds `is-in` when the element enters the viewport. */
function useReveal<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setShown(true)),
      { threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return { ref, shown };
}

function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const { ref, shown } = useReveal<HTMLDivElement>();
  return (
    <div
      ref={ref}
      className={`transition-all duration-700 ${shown ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0"} ${className}`}
    >
      {children}
    </div>
  );
}

/* ------------------------------ SVG artwork ----------------------------- */
function PathogenArt() {
  return (
    <svg viewBox="0 0 400 300" className="h-full w-full" role="img" aria-label="Foodborne pathogens illustration">
      <defs>
        <radialGradient id="dish" cx="50%" cy="45%" r="60%">
          <stop offset="0%" stopColor="#0f9b8e" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#0f2742" stopOpacity="0.05" />
        </radialGradient>
      </defs>
      <circle cx="200" cy="150" r="120" fill="url(#dish)" stroke="#0f2742" strokeOpacity="0.2" strokeWidth="3" />
      <circle cx="200" cy="150" r="120" fill="none" stroke="#14b8a6" strokeOpacity="0.4" strokeWidth="1.5" strokeDasharray="4 6" />
      {[
        [150, 110, 10], [250, 130, 14], [180, 200, 8], [230, 190, 11],
        [160, 160, 6], [210, 110, 7], [270, 170, 9], [140, 185, 7],
      ].map(([cx, cy, r], i) => (
        <g key={i}>
          <ellipse cx={cx} cy={cy} rx={r} ry={r * 0.6} fill="#0f9b8e" fillOpacity="0.65" transform={`rotate(${i * 25} ${cx} ${cy})`} />
          <line x1={cx - r - 4} y1={cy} x2={cx + r + 4} y2={cy} stroke="#0f2742" strokeOpacity="0.5" strokeWidth="1.5" transform={`rotate(${i * 25} ${cx} ${cy})`} />
        </g>
      ))}
    </svg>
  );
}

/** A simple human silhouette used across the vulnerable-group cards. */
function PersonIcon({ variant }: { variant: "pregnant" | "child" | "elder" }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (variant === "child") {
    return (
      <svg viewBox="0 0 100 100" className="h-14 w-14" aria-hidden>
        <circle cx="50" cy="26" r="14" {...common} />
        <path d="M50 40 V70 M50 70 L38 90 M50 70 L62 90 M32 54 H68" {...common} />
      </svg>
    );
  }
  if (variant === "elder") {
    return (
      <svg viewBox="0 0 100 100" className="h-14 w-14" aria-hidden>
        <circle cx="46" cy="22" r="12" {...common} />
        <path d="M46 34 V64 M46 64 L36 92 M46 64 L58 90 M46 42 H70 M74 30 V94" {...common} />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 100 100" className="h-14 w-14" aria-hidden>
      <circle cx="44" cy="22" r="12" {...common} />
      <path d="M44 34 C44 34 44 60 44 64 C60 66 66 54 64 44 M44 64 L36 94 M44 64 L54 94" {...common} />
    </svg>
  );
}

/* ------------------------------ components ------------------------------ */
function VulnerableCard({
  variant, title, who, risk, evidence, accent,
}: {
  variant: "pregnant" | "child" | "elder";
  title: string; who: string; risk: string; evidence: string; accent: string;
}) {
  return (
    <Reveal className="h-full">
      <div className="group flex h-full flex-col gap-3 rounded-2xl border border-navy/10 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
        <div className="flex items-center gap-3">
          <div className="rounded-xl p-2 text-white transition group-hover:scale-110" style={{ backgroundColor: accent }}>
            <PersonIcon variant={variant} />
          </div>
          <div>
            <h3 className="text-base font-bold text-navy">{title}</h3>
            <p className="text-[11px] font-medium uppercase tracking-wide text-navy/50">{who}</p>
          </div>
        </div>
        <div className="rounded-lg bg-surface-muted p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-navy/50">Primary pathogen concern</p>
          <p className="text-sm font-bold" style={{ color: accent }}>{risk}</p>
        </div>
        <p className="text-xs leading-relaxed text-navy/70">{evidence}</p>
      </div>
    </Reveal>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <Reveal>
      <div className="rounded-xl border border-navy/10 bg-white p-5 text-center shadow-sm">
        <div className="bg-gradient-to-r from-teal to-navy bg-clip-text text-3xl font-extrabold text-transparent">{value}</div>
        <div className="mt-1 text-[11px] font-medium uppercase tracking-wide text-navy/60">{label}</div>
      </div>
    </Reveal>
  );
}

function Pathway({ icon, title, body, status, tone }: {
  icon: ReactNode; title: string; body: string; status: string; tone: "ok" | "partial" | "gap";
}) {
  const toneClass = tone === "ok" ? "bg-teal/10 text-teal-700 border-teal/30"
    : tone === "partial" ? "bg-slate-100 text-slate-700 border-slate-300"
    : "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <Reveal className="h-full">
      <div className="flex h-full flex-col gap-2 rounded-xl border border-navy/10 bg-white p-5 shadow-sm transition hover:shadow-md">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-navy/5 text-xl">{icon}</div>
        <h3 className="text-sm font-bold text-navy">{title}</h3>
        <p className="text-xs leading-relaxed text-navy/70">{body}</p>
        <span className={`mt-1 inline-block w-fit rounded-full border px-2 py-0.5 text-[10px] font-semibold ${toneClass}`}>{status}</span>
      </div>
    </Reveal>
  );
}

export default function Landing({ onEnter }: { onEnter: () => void }) {
  return (
    <div className="flex flex-col">
      {/* 1 — PROBLEM hero */}
      <section className="relative overflow-hidden bg-gradient-to-br from-navy via-navy-600 to-teal-600">
        <div aria-hidden className="pointer-events-none absolute inset-0 opacity-25"
          style={{ backgroundImage: "radial-gradient(circle at 15% 20%, #14b8a6 0, transparent 40%), radial-gradient(circle at 85% 70%, #0f9b8e 0, transparent 45%)" }} />
        <div className="relative mx-auto grid max-w-6xl items-center gap-8 px-6 py-16 sm:py-20 lg:grid-cols-2">
          <div>
            <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
              One Health Food-Safety Decision Support
            </span>
            <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight text-white sm:text-5xl">
              Foodborne pathogens strike{" "}
              <span className="bg-gradient-to-r from-teal-500 to-white bg-clip-text text-transparent">the most vulnerable</span> first.
            </h1>
            <p className="mt-4 max-w-xl text-sm leading-relaxed text-white/80 sm:text-base">
              Salmonella, Listeria, and STEC send hundreds of thousands of
              people to hospital every year in the US. Pregnant people,
              newborns, young children, and older adults bear the worst
              outcomes. The surveillance data exists — but it rarely becomes a
              signal anyone can act on in time.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button type="button" onClick={onEnter}
                className="rounded-lg bg-teal px-5 py-2.5 text-sm font-bold text-white shadow-lg transition hover:bg-teal-500">
                Open the live dashboard →
              </button>
              <a href="#who" className="rounded-lg border border-white/30 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10">
                See who&rsquo;s at risk
              </a>
            </div>
          </div>
          <div className="mx-auto h-64 w-64 sm:h-80 sm:w-80">
            <PathogenArt />
          </div>
        </div>
        <div className="relative mx-auto max-w-6xl px-6 pb-10">
          <p className="text-xs font-semibold uppercase tracking-widest text-white/50">Scroll to explore ↓</p>
        </div>
      </section>

      {/* 2 — WHO is most at risk */}
      <section id="who" className="mx-auto max-w-6xl px-6 py-16">
        <Reveal>
          <h2 className="text-center text-3xl font-bold text-navy">Who&rsquo;s most at risk</h2>
          <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-navy/70">
            Vulnerability is not evenly distributed. VulneraSafe lets you view risk through the lens of the groups who suffer the most severe outcomes.
          </p>
        </Reveal>
        <div className="mt-8 grid gap-5 md:grid-cols-3">
          <VulnerableCard variant="pregnant" accent="#0f9b8e"
            title="Pregnancy & newborns" who="Expectant parents · infants"
            risk="Listeria monocytogenes"
            evidence="Listeriosis in pregnancy can cause miscarriage, stillbirth, and severe newborn infection — ready-to-eat foods are the key exposure route." />
          <VulnerableCard variant="child" accent="#14b8a6"
            title="Children under five" who="Young children"
            risk="STEC · Salmonella"
            evidence="Young children face higher rates of severe STEC complications (including hemolytic uremic syndrome) and salmonellosis hospitalization." />
          <VulnerableCard variant="elder" accent="#1b3a5b"
            title="Adults 65 and older" who="Older adults"
            risk="Multiple pathogens"
            evidence="Weakened immunity and more comorbidities drive higher hospitalization and death rates across Salmonella, Listeria, and STEC." />
        </div>
        <Reveal>
          <p className="mx-auto mt-6 max-w-3xl text-center text-[11px] italic text-navy/50">
            Population vulnerability and food-access context are shown separately from actual exposure. Regional demographics cannot establish who consumed a product or became ill.
          </p>
        </Reveal>
      </section>

      {/* 3 — SCALE */}
      <section className="bg-navy py-16">
        <div className="mx-auto max-w-6xl px-6">
          <Reveal><h2 className="text-center text-3xl font-bold text-white">The scale of what we model</h2></Reveal>
          <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat value="3" label="Pathogens modeled" />
            <Stat value="~823K" label="FSIS lab samples" />
            <Stat value="FY2014–26" label="Fiscal-year coverage" />
            <Stat value="46–49" label="States with weather" />
          </div>
          <Reveal>
            <p className="mx-auto mt-6 max-w-2xl text-center text-xs text-white/60">
              All figures come from real USDA FSIS establishment sampling data. Nothing on this page is fabricated.
            </p>
          </Reveal>
        </div>
      </section>

      {/* 4 — WHAT WE DO (transition to overview) */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <Reveal>
          <div className="text-center">
            <span className="inline-block rounded-full bg-teal/10 px-3 py-1 text-xs font-semibold text-teal-700">Our response</span>
            <h2 className="mt-3 text-3xl font-bold text-navy">Predict the hazard. Protect the vulnerable.</h2>
            <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-navy/70">
              VulneraSafe AI connects five One Health data pathways into one honest decision-support flow — from observed surveillance, to a validated forward-looking risk estimate, to vulnerability-aware and safety-constrained retailer action.
            </p>
          </div>
        </Reveal>
        <Reveal>
          <div className="mx-auto mt-8 max-w-3xl rounded-2xl border border-navy/10 bg-white p-6 shadow-sm">
            <h3 className="text-sm font-bold uppercase tracking-wide text-teal-700">The decision we support</h3>
            <dl className="mt-3 space-y-2 text-sm text-navy/80">
              <div><dt className="inline font-semibold text-navy">Who: </dt><dd className="inline">a regional grocery chain’s Food Safety Operations Director.</dd></div>
              <div><dt className="inline font-semibold text-navy">What: </dt><dd className="inline">where to focus limited food-safety attention, and which safe action to take — prioritize testing, hold for review, isolate a confirmed-recall lot, or allocate compliant replacement — while protecting access for high-need communities.</dd></div>
              <div><dt className="inline font-semibold text-navy">When: </dt><dd className="inline">one period ahead — monthly for Salmonella, quarterly for Listeria and STEC.</dd></div>
            </dl>
          </div>
        </Reveal>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Pathway tone="ok" title="Food / animal" status="Primary · complete" icon={<span>🧪</span>}
            body="USDA FSIS establishment lab sampling — the surveillance backbone for Salmonella, Listeria, and STEC." />
          <Pathway tone="partial" title="Environmental" status="Integrated · minor lift" icon={<span>🌦️</span>}
            body="NOAA nClimDiv state-month climate, national coverage. Honestly reported: a small, pathogen-dependent lift (Salmonella +0.021, STEC +0.005 PR-AUC; Listeria slightly negative) — not a headline driver." />
          <Pathway tone="partial" title="Human health" status="Corroboration only" icon={<span>🧑‍⚕️</span>}
            body="CDC NORS outbreaks/illnesses joined with a 365-day availability lag — historical context, not a real-time feature." />
          <Pathway tone="ok" title="Food security" status="Complete" icon={<span>🥫</span>}
            body="US Census ACS and USDA Food Access Atlas provide community vulnerability and access context." />
          <Pathway tone="gap" title="Supply chain" status="Simulated" icon={<span>🚚</span>}
            body="A clearly-labeled SIMULATED retailer network drives the decision optimizer — no real retailer data exists." />
          <Pathway tone="ok" title="Regulatory recalls" status="Real (openFDA)" icon={<span>📋</span>}
            body="Real openFDA food-enforcement recalls (FDA jurisdiction) as independent regulatory evidence. The USDA FSIS meat/poultry feed is blocked here — an honest gap, not fabricated." />
        </div>
      </section>

      {/* 5 — Flow + CTA */}
      <section className="bg-gradient-to-br from-surface to-surface-muted py-16">
        <div className="mx-auto max-w-5xl px-6">
          <Reveal><h2 className="text-center text-2xl font-bold text-navy">From data to a safe decision</h2></Reveal>
          <div className="mt-8 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
            {[
              ["Observed", "FSIS surveillance", "#0f9b8e"],
              ["Predicted", "Next-period risk", "#0f2742"],
              ["Context", "Vulnerability + access", "#14b8a6"],
              ["Simulated", "Safe retailer action", "#64748b"],
              ["Compared", "Policy A/B/C", "#1b3a5b"],
            ].map(([tag, label, color], i, arr) => (
              <div key={tag} className="flex flex-1 items-center gap-3">
                <div className="flex-1 rounded-xl border border-navy/10 bg-white px-3 py-3 text-center shadow-sm">
                  <div className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: color as string }}>{tag}</div>
                  <div className="text-sm font-semibold text-navy">{label}</div>
                </div>
                {i < arr.length - 1 ? <span className="hidden text-navy/30 sm:inline">→</span> : null}
              </div>
            ))}
          </div>
          <Reveal>
            <div className="mt-10 text-center">
              <button type="button" onClick={onEnter}
                className="rounded-lg bg-navy px-6 py-3 text-sm font-bold text-white shadow-lg transition hover:bg-navy-600">
                Explore the live dashboard →
              </button>
              <p className="mx-auto mt-6 max-w-3xl text-xs leading-relaxed text-navy/50">
                <span className="font-semibold text-navy/70">Scientific integrity:</span>{" "}
                surveillance and model values are real USDA FSIS data and saved out-of-time predictions; operational networks and outcomes are SIMULATED and labeled. No observed illness reductions, verified recalls, or operational results are fabricated. Decision support only — not a regulatory determination.
              </p>
            </div>
          </Reveal>
        </div>
      </section>
    </div>
  );
}
