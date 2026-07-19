# ScanSaver — Demo Script & Pre-Stage Checklist

Target: ~5 minutes live + Q&A. One laptop on the projector (dashboard), one
phone in the presenter's hand, two teammates on standby phones.

## Cast

| Person | Role | Phone |
|---|---|---|
| Presenter (Shou-Feng) | narrates + plays **Sloane** (Premier, the upseller) | own phone |
| Teammate A | **Dana** (Summit, the stonewaller) | their phone |
| Teammate B | **Marcus** (ValueScan, the lowballer) | their phone |

Everyone keeps their cheat sheet (TEAM_GUIDE.md) open. Script numbers only:
Dana ~$700–900 range + callback · Marcus $350 teaser · Sloane $950 → floor $675.

## The script, beat by beat

**Beat 0 — cold open (30s).** Slide or just say it:
> "An MRI on the same machine, in the same city, costs $400 at one door and
> $4,000 at another. Nobody has time to phone ten imaging centers and
> interrogate them about hidden fees. So we built a negotiator that does."

**Beat 1 — one phone call in (90s).** Dashboard on screen, section 01–02
visible. Presenter dials **the ScanSaver number** on speaker:
- Do the intake: *"I need an MRI of my right knee, no contrast, paying cash,
  I have a doctor's order, ZIP nine-four-three-zero-one, flexible."*
- **Ask it: "Wait — are you a robot?"** → it admits it honestly. Say to the
  audience: "Honesty is graded. It never pretends to be human."
- Verbally confirm. The agent says it's starting to call around and **hangs up
  by itself**. Point at the screen: spec appeared and self-confirmed — zero
  clicks.

**Beat 2 — the fan-out (≈3 min, overlaps with narration).** The moment intake
ends, **three phones ring at once** (teammates hold them up). While calls run:
- Show the **autopilot log** ticking and the **live transcript** link on a call.
- Narrate the market: "One receptionist stonewalls, one quotes a teaser price
  that hides the radiologist fee, one quotes premium. Watch the ledger."
- As quotes land: point at **red-flag stamps** ("not itemized", "read billed
  separately") and the **benchmark line** ("market median for this scan is
  $625 — real CMS + Bay Area data, sources in the repo").

**Beat 3 — the money moment (auto).** After round 1, autopilot dials Premier
back on its own. Presenter answers **as Sloane**, on speaker if audio allows:
- The agent cites the real logged best quote. Sloane concedes per the ladder:
  *"If they're really at three-fifty… I can do **seven twenty-five**, all-in."*
- Dashboard: Premier's card shows the **struck-through $950 → price moved**.
- Line for the audience: "It never bluffs. That leverage is a real quote from
  ninety seconds ago — fabricating one is against its rules."

**Beat 4 — the receipt (45s).** Report auto-generates when the run ends:
- Ranked list ("clean quotes outrank flagged ones — cheapest isn't first if
  it hides fees"), **saved $X (Y%)**, a verbatim transcript quote, and the
  call recordings — play 5 seconds of one.

**Beat 5 — mic drop (20s).**
> "Nothing medical is hardcoded. Swap one config file—" (show
> `moving.example.json`) "—and the same system price-shops moving companies
> tomorrow. Questions?"

## Fallbacks (decide in 5 seconds, don't debug on stage)

- **A teammate's phone fails** → presenter's phone is the fallback for any
  facility: use the market row's Call button with a corrected number in
  "Call another number…".
- **Live calls die entirely** → restore the rehearsal database
  (`cp data/demo-backup.db data/scansaver.db`, refresh) and walk through the
  ledger + report + recordings from the successful rehearsal. The evidence is
  real; say so.
- **Widget breaks** → the phone number IS the product; never debug the widget
  on stage.
- **Autopilot stalls mid-run** → market rows have manual Call/Negotiate
  buttons; keep the show moving by hand.

## Pre-stage checklist (T-30 minutes)

- [ ] Laptop: power connected, auto-sleep OFF, notifications OFF (Focus mode)
- [ ] `./start.sh` — dashboard loads at localhost:8000, public URL returns 200
- [ ] `GET /api/config` shows agent ids; widget button renders
- [ ] **Autopilot toggle: ON** · inbound answered by: **estimator**
- [ ] Market rows show all three numbers; teammates confirmed reachable
- [ ] Teammates: cheat sheets open, phones loud, in quiet rooms
- [ ] Fresh DB for the live run (`rm data/scansaver.db`) — **after** verifying
      `data/demo-backup.db` exists from rehearsal
- [ ] Twilio balance > $5 · ElevenLabs credits comfortable
- [ ] Presenter phone: charged, on speaker-test with the hall mic
- [ ] One rehearsal run completed today with THIS checklist

## Rehearsal note

Run the full loop at least once with everyone, script numbers only. When the
run is clean: `cp data/scansaver.db data/demo-backup.db` — that file is the
stage insurance.
