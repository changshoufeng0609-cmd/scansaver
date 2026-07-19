# ScanSaver — Team Guide (as of Jul 18, 2026)

> The pitch in one line: **tell the AI once what scan you need, and it phones
> every imaging center for you, forces them to itemize their cash prices,
> catches the pricing tricks, negotiates using your real best quote, and hands
> you a ranked recommendation with recordings and transcripts as receipts.**
> (Built for the ElevenLabs "The Negotiator" challenge, medical imaging vertical.)

## Where we are

| Milestone | Status |
|---|---|
| M0 env / M1 agents / M2 voice intake / M3 document parsing | done |
| M8 real market benchmarks (CMS + Bay Area cash prices, ZIP 94301) | done |
| M4 first live call | works end-to-end, but test-call audio was choppy — needs a retest |
| M5 market round / M6 negotiation round / M7 report | rehearsal, blocked on M4 |

## Who does what

- **Anyone can run the backend now** (their own laptop, own ngrok domain), but
  the **ElevenLabs workspace + phone number are shared** via one API key. Only
  one of us should be "live" at a time — whoever is testing runs their own
  `./start.sh`, then `python -m scripts.assign_inbound <agent_key>` and
  `python -m scripts.setup_agents` if the tool URLs need to point at their
  domain. Ping the channel before you do this so we're not fighting over who's
  wired up.
- **Do not run `scripts/setup_agents.py` casually.** It deletes and recreates
  every agent + tool in the shared workspace. Two people running it back-to-back
  is how we ended up with 21 duplicate tools once already (cleaned up
  2026-07-19). Only rerun it after an actual prompt/config change, and say so
  before you do.
- `agents/agent_ids.json` is gitignored (per-machine) — it's not how we sync
  who's "the" active agent set. The shared ElevenLabs workspace is the source
  of truth; use `assign_inbound` to point the shared number at whichever
  agent set is currently live, not a fresh `setup_agents` run.
- **Playing a clinic receptionist?** You literally just need your phone and the
  cheat sheet below. Full scripts live in `agents/counterparties/*.md` — read
  yours once, the calls are in English.
- **Touching code?** Clone the repo, open a PR. Secrets (`.env`) are not in
  git — ask whoever's driving for the current values.

## How to drive it

Dashboard: http://localhost:8000 on whoever's laptop is currently live (there's
also a public tunnel URL — ask them for it; not published here on purpose).

1. **01 · Intake** — talk to the Estimator widget (in English), or upload a
   doctor's order photo. You can also just call **+1 605 566 4795** — the
   Estimator picks up.
2. **02 · Confirm** — hit "Load latest", eyeball the JSON (you can edit it
   right there), hit Confirm. No calls happen before this.
3. **03 · The calls** — in "Start a call", type the **phone number to dial**
   (= whoever's playing the receptionist) + pick a **facility name**, hit Call.
   Quotes pop into the ledger live, red flags get stamped automatically, and
   call status (done/failed) shows below the button. For round two, tick
   **negotiate** — that's haggling mode.
4. **04 · The close** — Generate report: the ranking, "saved $X", quotes from
   the transcripts, playable recordings.

Need a clean slate? Delete `data/scansaver.db` — it recreates itself empty.

## Receptionist cheat sheets (this is the fun part)

> Heads-up for all three roles: the caller is an AI. If you ask "are you a
> robot?" it will straight-up admit it — **don't hang up**, that honesty moment
> is a feature we want on tape. Keep your lines short and natural.

### Role 1: Dana @ Summit Imaging Center (the stonewaller → produces a "callback promise")
- Your policy: no prices over the phone. Open with:
  **"We don't really give prices over the phone."**
- Only if they stay polite, push again, AND clearly state the exact scan, give
  them a vague range: **"Self-pay it's usually somewhere in the seven hundred
  to nine hundred range."**
- Never itemize. Never confirm if the radiologist read is included ("that's a
  billing question"). Never negotiate.
- Always land on the same ending: **"Best I can do is have Priya from billing
  call you back tomorrow between ten and eleven. What's the number?"**
- Bonus points: interrupt yourself once with "sorry, one second—" like you're
  swamped, then come back.

### Role 2: Marcus @ ValueScan Radiology (the lowballer → produces red flags)
- Lead with the teaser, big energy: **"$350 — cheapest you'll find anywhere."**
- Hidden fees you ONLY admit when asked about that exact thing:
  radiologist read **$180**, facility fee **$95**. (Real all-in is $625 —
  never volunteer that number.)
- Asked for it in writing? Get cagey: "We don't really do email quotes, just
  come in."
- They mention a competitor's quote? Don't budge, just repeat:
  "Nobody beats $350." And always try to close: "I've got a slot Thursday,
  want me to hold it?"

### Role 3: Sloane @ Premier Diagnostic Imaging (the upseller → produces the on-call price drop)
- Open high and proud: **"$950, and that's genuinely all-inclusive."**
  Happy to itemize: tech $600 / read $250 / facility $100.
- Push each upsell once: 3-Tesla upgrade (+$200), and "we have one slot
  Thursday, those go fast."
- **The concession ladder — follow it EXACTLY, never skip ahead:**
  1. They just whine it's expensive → hold at $950, re-sell the quality.
  2. They ask about a self-pay / prepay discount → **$900**.
  3. They cite a real competing quote of $X (and X ≥ 675) → **offer X − 25**.
     e.g. they say $750 → "I can do **seven twenty-five**, all-in, same-week."
  4. Competing quote below $675 → don't match: "I can't get there — but at
     $675 all-in with a 24-hour read, we're the better buy."
     **$675 is your absolute floor.**
- Before hanging up, **say the final agreed number out loud, clearly** — that
  line becomes the evidence in the report.

## The demo, beat by beat (planned)

1. Estimator intake (and someone asks it "are you a robot?" on stage — the
   honest answer is a selling point)
2. Market round, three calls: Dana (callback promise) → Marcus (teaser exposed
   + red flags) → Sloane ($950 logged)
3. Negotiation round: tick **negotiate**, call Sloane again → the agent cites
   our real best quote → Sloane drops to ~$725 → the dashboard shows the old
   price struck through
4. Generate report: ranking + "saved $225 (24%)" + play a recording
5. Mic drop: swap the config to `moving.example.json` — same system, different
   industry, zero code changes

## Hard rules (we get graded on these, we can discuss about that)

- **Never call real clinics.** Test and demo calls go to our own phones only.
- **Never fake a quote.** The negotiation leverage must come from a real quote
  that's actually in the database.
- **The AI admits it's an AI when asked.** That's a feature, not a bug.
