# VulneraSafe AI — The Dashboard, Explained in Plain Words

This guide walks through **everything** you see on the Dashboard page, one piece
at a time, in very simple language with examples. No technical background needed.
If you can read a weather app, you can read this.

> **The one big idea to remember.** This tool is a *helper that suggests where to
> look* — like a smoke detector that beeps "check the kitchen." It never says
> "there is a fire" and it never says "everything is safe." A human always decides
> what to actually do.

---

## Who is this dashboard for, and what does it do?

Imagine you are the **Food Safety Manager for a chain of grocery stores**. Every
week you have limited time, limited inspectors, and limited budget. You cannot
test everything everywhere. You have to choose: *where should I focus this week?*

VulneraSafe AI looks at years of real government food-testing data (plus weather,
population, and food-access data) and gives you a ranked, explained answer to
that question — while being very honest about what it does and doesn't know.

The three germs it watches:
- **Salmonella** (mainly in raw chicken/poultry)
- **Listeria** (in ready-to-eat deli-style meats)
- **STEC**, a dangerous kind of *E. coli* (in raw beef)

---

## How to read the whole page at a glance

The page is built from stacked sections. From top to bottom:

1. A **top bar** with the app name and two tabs: **Overview** and **Dashboard**.
2. A thin **green notice bar** (the "decision support only" reminder).
3. A **"Regulatory Recalls" band** (official recalls — the most trustworthy info).
4. A small **controls row** (pick a germ; see/clear the state you clicked).
5. A one-line note telling you **how fresh the data is**.
6. The main **grid of panels** (the heart of the dashboard).
7. A **Legend** at the very bottom explaining the color/label code.

Let's go through each one.

---

## 1. The top bar (header)

A dark navy strip that stays stuck to the top as you scroll.

- On the left: a small teal **"V" logo** and the name **VulneraSafe AI**, plus a
  little label "One Health Food-Safety Decision Support."
- On the right: two buttons, **Overview** and **Dashboard**. The one you're on is
  highlighted in white. Click to switch.
  - **Overview** = the welcome/explainer page (the story of the problem).
  - **Dashboard** = the working tool (what this guide is about).

*Example:* Click "Overview" to show a colleague why this matters, then click
"Dashboard" to get to work.

---

## 2. The green "Decision support only" notice

A calm green bar just under the header. It says, in plain terms:

> This tool is **not** an official ruling and **not** an outbreak announcement. A
> model alert never proves a product is contaminated. A prediction never declares
> a product safe or unsafe. **Every serious action needs a human to review it
> first.**

Why it's always there: so nobody — not even someone glancing for two seconds —
mistakes a suggestion for an official decision. It's green (a calm "information"
color) on purpose, never red.

---

## 3. The "Regulatory Recalls" band (the most trustworthy section)

A band marked **"Regulatory Recalls — Verified official source."** This is the
one place on the page showing **real, official government recalls** (not model
guesses).

Each recall appears as a **card** with a red left edge, showing:
- A **"Regulatory Recall"** badge (dark navy with a red stripe) and a status tag.
- A **recall ID** (the official reference number).
- The **product name** in bold.
- **Classification** (how serious), shown in red.
- The **date**.
- The **affected lot numbers** (specific batches), each in a little gray chip.
- A **"View official source"** link to the real government page.

Three things make this band special:
- **It never gets hidden.** It stays on both tabs, always visible.
- **It is completely independent of the AI.** Even if every model on the page
  failed to load, a real recall would still show here. Official safety info is
  never blocked by a computer problem.
- **When there are no recalls**, it shows a calm message: *"No active regulatory
  recalls."* — not a scary error.

*Example:* If the government recalls "Brand X deli turkey, lot 55A," you'd see a
red-edged card with that product, lot 55A in a chip, and a link to the official
notice — regardless of what the AI predicts.

---

## 4. The controls row (pick a germ, see your selected state)

A simple row with:

- **Pathogen dropdown** — choose *All pathogens*, *Salmonella*, *Listeria*, or
  *STEC*. Picking one filters the whole dashboard to just that germ.
- **Region chip** — appears only *after* you click a state on the map. It reads
  something like **"Region: KS X."** Click the X to deselect that state.

*Example:* Choose "Salmonella" from the dropdown, click Kansas on the map, and now
the page focuses on Salmonella risk in Kansas (KS).

---

## 5. The "data freshness" line

A tiny gray sentence like:

> *Artifact version 1 - generated 2026-10-30*

It tells you **which batch of computed results you're looking at** and **when it
was produced**. If something is still loading, it adds "loading...". If the index
of data cannot load, a small box explains that panels will still show whatever they
can individually — one broken part never takes down the whole page.

---

## 6. The main panel grid — the heart of the dashboard

Below the controls is a grid of **seven panels**. Each panel is a white "card"
with rounded corners and a title bar.

### How every panel looks and behaves (shared design)

- **Title** (bold) at the top, sometimes with a short gray **subtitle**.
- A little round **"i" button** next to many titles. Hover or tab to it and a dark
  tooltip pops up with a one-sentence plain explanation.
- Some panels show a **status tag** in the corner (explained in the Legend below).
- Panels **fail gracefully**. If a panel's data is loading, it says "Loading...".
  If it cannot load, it says so politely. If there's simply nothing to show, it
  shows a friendly "empty state" message instead of a blank or a crash.

Now, the seven panels in order:

---

### Panel A — Current Risk Overview (the map + the trend line)

**What it's for:** the big picture — *which states look risky right now, and how
has one state's risk changed over time?* This is the widest panel (spans two
columns).

**The "i" tooltip says:** each state is shaded by its *predicted* chance of
elevated germ-testing positivity next period (teal = higher). It's a "look here
first" signal, not proof of contamination. Click a state to see its history with
an uncertainty band.

**Left side — the map (choropleth):**
- A real map of the US states. Each state is **shaded teal** — the darker/greener
  the teal, the higher the predicted risk. Lighter = lower.
- Each state shows its **two-letter code** (KS, NY, CA...) in the middle.
- **Hover** over a state and a little tooltip shows the state and its risk, e.g.
  *"KS: 41.0%."* "No data" appears if a state has none.
- **Click** a state to select it (a dark outline marks it) — this drives the trend
  line on the right and the vulnerability panel.
- A **color key** under the map reads "Lower risk ... Higher risk."
- *Backup plan:* if the fancy map cannot draw (old browser, etc.), it automatically
  shows the same information as a **grid of colored tiles**, sorted highest-risk
  first. You lose nothing.

**Above the map — a label block** with six must-have facts, so a risk map is never
shown without context:
1. **Pathogen** (which germ)
2. **Geography** (e.g. "48 regions" or the state you clicked)
3. **Reporting period** (e.g. "2026-06")
4. **Status** (OBSERVED / PREDICTED / SIMULATED tag)
5. **Uncertainty** (e.g. "+/- 8.0%")
6. **Data freshness** (how recent the underlying data is)
If any one of these is unknown, it shows a dash "-" meaning *not available* — it
never makes up a number.

**Right side — the trend line (time-series):**
- Before you click a state, it politely says **"Select a region."**
- After you click, say, Kansas, it draws Kansas's **risk over time** as a teal line.
- The **shaded area around the line** is the **95% uncertainty band** — think of it
  as "the true value is very likely somewhere in this ribbon." A wide ribbon means
  "less sure"; a narrow ribbon means "more sure."
- The **up-and-down axis** is labeled "Elevated-risk probability" and marked in
  percentages (0%, 25%, 50%, 75%, 100%).
- The **left-to-right axis** shows time periods (months or quarters).
- A legend distinguishes **"Predicted risk"** (the line) from **"95% uncertainty"**
  (the ribbon). Hover a dot to see that period's exact value. Below, it also prints
  the first period, the **latest value**, and the last period.
- If there's no dated data for your pick, it says exactly that, naming the state
  (and germ) — instead of drawing a misleading empty chart.

*Example:* Pick Salmonella, click Kansas -> the map highlights KS, and the right
side shows KS's Salmonella risk climbing from ~20% to ~45% over the last year,
with a ribbon showing how confident the model is.

---

### Panel B — Vulnerable-Population Lens (who is most at risk)

**What it's for:** to re-frame the view around the **people** most endangered by
these germs — *without changing any risk prediction.* Also a wide panel.

**Very important honesty rule:** choosing a lens here **does not change the hazard
numbers anywhere**. It only (1) highlights which germs matter most for that group
and (2) shows real community context. "Who is vulnerable" is kept separate from
"what is actually risky."

**The three lens buttons (pick one):**
- **Pregnancy & newborns** -> emphasizes **Listeria** (it can cause miscarriage,
  stillbirth, severe newborn infection; ready-to-eat foods are the key route).
- **Children under 5** -> emphasizes **STEC** and **Salmonella** (young kids face
  higher rates of severe complications).
- **Adults 65+** -> emphasizes **Listeria, Salmonella, and STEC** (weaker immunity
  -> more hospitalizations and deaths).

When you pick a lens, two boxes appear:
- **"Most relevant pathogens for [group]"** — clickable germ chips (clicking one
  sets the page's germ filter) plus a sentence explaining *why* that group is
  vulnerable. A note repeats: this is emphasis only, it doesn't change the model.
- **"Community context - [state]"** — real numbers for the state you clicked on the
  map, drawn from the US Census (ACS) and the USDA Food Access Atlas:
  - **Total population**
  - **Adults 65+ share**
  - **Children under 5 share**
  - **Low-income tracts** (share of neighborhoods)
  - **Low-income & low-access** (share that are both poor *and* far from a grocery)
  - A footnote names the data vintage (e.g. "ACS 2022") and plainly states that
    **pregnancy counts and the under-5 share are "not available"** rather than
    guessed. (You'll literally see the words "not available.")

If you haven't clicked a state yet, it asks you to pick one on the map. If you
haven't picked a lens, it invites you to.

*Example:* Pick the Pregnancy lens -> it spotlights Listeria and explains the
pregnancy risk; then click New York -> the right box shows NY's population, its 65+
share, its low-income-and-low-access share, with "not available" shown honestly for
the pregnancy and under-5 figures.

---

### Panel C — Prioritized Attention Queue (the ranked to-do list)

**What it's for:** a simple **ranked worklist** — "if you only have time for a few
things, do these first." Highest predicted risk at the top.

**The "i" tooltip says:** it's a ranked list of state+time cells by predicted risk;
it's a prioritization aid, never a claim that a specific product is contaminated.

**What you see:**
- A count line: *"Showing 5 of 48"* and a pill reading **"ranked by predicted risk."**
- A numbered list of cards (1, 2, 3...). Each card shows:
  - A **rank number** in a navy circle.
  - **Germ - State** (e.g. "Salmonella - KS") and a smaller line describing the
    item's type.
  - The **risk percentage** (e.g. "44.8%") and a **status tag**.
  - A thin **teal risk meter bar** — a longer bar means higher risk (quick to scan).
  - A short **"triggering condition"** line explaining *why* it's on the list.
- By default it shows the **top 5**. A **"Load 10 more"** button reveals more (and
  tells you how many remain). Once expanded, a **"Show top 5 only"** button collapses
  it again.
- Picking a germ in the dropdown filters this list (and resets it to the top 5).

*Example:* With Salmonella selected, #1 might be "Salmonella - KS - 44.8%" with a
nearly-full teal bar and a note like "positivity trending above baseline."

---

### Panel D — Scenario Builder (the what-if sliders)

**What it's for:** a **what-if playground**. Adjust operating assumptions to think
through trade-offs. (These operational inputs/outputs are **simulated** — made-up
practice data, clearly labeled, because no real store's private data is used.)

**Four controls (each a number box showing its allowed range):**
- **Inspection budget (top-K)** — how many top items you can inspect. Range 0-100.
- **Inventory supply** — how much stock you have, as a fraction. Range 0-1.
- **Delays** — reporting/logistics delay in days. Range 0-60 days.
- **Food-access weighting** — how strongly to favor high-need communities. Range 0-1.

**How it behaves:**
- It starts with sensible defaults (budget 20, supply 0.8, delay 7 days, access 0.5).
- Type new values and click **"Apply scenario."**
- **If you enter something out of range** (say, budget 999), the tool **rejects just
  that entry**, shows a red message naming the accepted range, and **keeps your last
  good values** — nothing silently breaks.
- A small line at the bottom shows the currently applied settings.

*Example:* Set "Inspection budget" to 150 and click Apply -> it turns that box red
with "Accepted range: 0-100." and keeps your previous budget. Fix it to 30 -> it
accepts and records "K=30."

---

### Panel E — Recommended Action Panel (concrete suggested steps)

**What it's for:** turns risk into **specific suggested actions** a retailer could
take — each one explained and, when serious, flagged for human sign-off.

**The "i" tooltip says:** model-prioritization actions are *predicted* (with
uncertainty and evidence); operational actions are *simulated* by the
safety-constrained optimizer. A model suggestion lacking evidence or uncertainty is
**withheld**, not shown.

**Each recommendation card shows:**
- The **action** in bold (e.g. "Prioritize testing for this lot").
- Two badges: a **source badge** — **"Regulatory Recall"** (official) or **"Model
  Alert"** (AI suggestion) — and a **status tag**.
- The **target** it applies to.
- **Rationale** — why this is suggested.
- **Governing constraints** — the hard rules it must obey (e.g. "never distribute a
  recalled lot"). Shown as a bullet list, or "None recorded."
- **Supporting evidence** — the data backing it up, as a bullet list.
- **Uncertainty** — e.g. "+/- 10.0%."
- A clear **human-review flag**: either a warning strip **"Human review required
  before action"** or a quiet "Human review not required."
- Click a card to **select** it; the next panel (Explanation/Evidence) then shows
  its full backstory.

**The safety guardrail you can trust:** if a *model* suggestion doesn't have both
real evidence and a real uncertainty number, it is **withheld** — never shown as a
recommendation. The panel is honest about it with a line like: *"Showing 6
actionable recommendations. 180 model-generated recommendations were withheld for
insufficient evidence or uncertainty."* (Official regulatory items are always shown
— they don't depend on model uncertainty.)

*Example:* You might see "Isolate recalled lot 55A" tagged **Regulatory Recall**
with a human-review warning strip, alongside "Request supplier documentation" tagged
**Model Alert** with its evidence and "+/- 9%" uncertainty.

---

### Panel F — Explanation / Evidence Panel (the "show your work" panel)

**What it's for:** the **audit trail** behind one recommendation. It answers *"why
should I trust this?"*

**How it works:**
- Until you **click a recommendation** in Panel E, it says **"Select a
  recommendation."**
- Once selected, it shows, for that action:
  - **Source data** — each dataset behind it, with **coverage** (where/when),
    **access date**, and **license**. If a reference cannot be matched to a known
    source, it says so plainly.
  - **Uncertainty** — the same honest +/- number.
  - **Limitations** — the known weaknesses and caveats (pulled only from recorded
    facts, never invented).
- If the selected item was one of the *withheld* model suggestions, this panel
  shows the same honest "withheld — insufficient evidence/uncertainty" note instead
  of pretending to explain it.

*Example:* Click "Request supplier documentation" -> this panel shows it's based on
"USDA FSIS lab sampling (US states, FY2014-2026), accessed 2026-10-28, public
domain," with "+/- 9%" uncertainty and limitations like "no serotype/strain detail."

---

### Panel G — Policy Comparison (A / B / C side by side)

**What it's for:** compares **three ways of operating** on the **exact same
simulated situation**, so you can see the trade-offs instead of guessing. Wide panel.

The three policies:
- **A - Business-as-usual** — the baseline (what you'd do without the tool).
- **B - Model-informed safety** — use the model to guide safety effort.
- **C - Safety + food-access** — policy B, but also steer help toward high-need
  communities.

**How to read it:**
- **Tabs at the top** let you switch scenarios (one per germ). It opens on the
  scenario where the policies actually *differ*, so the value is visible immediately.
- A **table** lists outcome measures down the side — inspection workload,
  priority-review coverage, retrospective positive-test capture, inventory
  availability, compliant food delivered, supply disruptions, high-need community
  service — and the three policies across the top.
- **Each cell** shows the number, and (for B and C) **how it compares to A**:
  a teal up-triangle or amber down-triangle with the size of the change, e.g.
  "up 16 vs A." Below that, a small **[low, high]** 95% uncertainty range. A measure
  that cannot be validly computed shows **"not valid."**
- **Sometimes all three tie** (identical columns). That's not a bug — the panel
  explains it: some scenarios are dominated by a **mandatory recall isolation** that
  every policy must do the same way (safety is never traded away). The policies
  differ where *optional* effort matters, like the Salmonella limited-inspection
  scenario.
- A footnote repeats the honesty rules: **all outcomes are simulated, A is the
  comparison baseline, brackets are uncertainty ranges, no illness reduction is
  claimed, and safety is never relaxed for cost or access.**

*Example:* On the Salmonella scenario you might see Policy C adds "up 16" inspection
workload and "up 1.0" priority-review coverage versus A — showing the equity-aware
choice does more targeted checking. On the Listeria recall scenario, A/B/C tie,
with the explanation banner telling you why.

---

## 7. The Legend (the color and label key) — at the very bottom

A footer strip titled **"Legend"** that decodes the two visual systems used all
over the page.

**The three status tags** (you'll see these little badges on values everywhere):
- **OBSERVED** (navy badge) = **real measured data** from surveillance. "This
  actually happened."
- **PREDICTED** (teal badge) = **a model's estimate** of the future. "This is a
  forecast."
- **SIMULATED** (gray dashed badge) = **made-up practice data** for what-if
  scenarios. "This is not a real observation."

Every number that matters carries exactly one of these, so you always know whether
you're looking at a fact, a forecast, or a simulation.

**The alert color rule:**
- **Orange/red appears only on a genuine alert** — a verified recall, a required
  human review, or a true high-risk threshold. It is **never** used for decoration.
  So if you see red, it means "pay attention," every time.

---

## The promises this dashboard keeps (why you can trust what you see)

- **Facts, forecasts, and simulations are always labeled** (the three tags) so you
  never confuse them.
- **Official recalls are never hidden** and never depend on the AI working.
- **Weak model suggestions are withheld**, not dressed up — and the count is shown.
- **Missing values say "not available"** — the tool never invents a number.
- **Serious actions are flagged for human review.** The computer suggests; a person
  decides.
- **Safety is never traded for cost or convenience** in any policy comparison.

---

## A 60-second walkthrough (putting it together)

1. Open the **Dashboard** tab. Glance at **Regulatory Recalls** — any official
   recalls today?
2. Pick **Salmonella** in the dropdown.
3. On the **map**, the darkest-teal states are the model's top concerns. Click the
   darkest one (say **KS**).
4. The **trend line** shows KS's Salmonella risk rising, with an uncertainty ribbon.
5. The **Attention Queue** confirms KS near the top of the ranked list.
6. Turn on the **Adults 65+ lens** -> it spotlights the germs worst for seniors and
   shows KS's real senior-population and food-access context (with honest "not
   available" where data is missing).
7. Read the **Recommended Actions** for KS — note which need **human review** —
   and click one to see its **Evidence** (source data, uncertainty, limitations).
8. Open **Policy Comparison** to see whether a model-informed, equity-aware approach
   would meaningfully change inspection effort — all clearly marked **simulated**.

That's the whole dashboard. Every shaded state, every badge, every +/- number, and
every "not available" is there to help a busy human make a safer, fairer call —
while always leaving the final decision to that human.
