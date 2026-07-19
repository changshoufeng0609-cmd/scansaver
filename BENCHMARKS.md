# Market Benchmarks — what they do and where the numbers come from

Updated 2026-07-18 · demo ZIP: **94301 (Palo Alto, CA)** · lives in
`config/medical_imaging.json → benchmarks.by_cpt`

## Why benchmarks exist in this system

Every quote that gets logged mid-call is instantly compared against real market
data. That comparison powers three things:

1. **Red flags** — a quote more than 30% below the market low gets stamped
   "too good to be true" (per the challenge brief); the dashboard also shows
   each quote as "+X% vs market median".
2. **Negotiation context** — the Caller agent receives the benchmark line as a
   dynamic variable on every call, so it knows what "expensive" means.
3. **The report** — rankings and the plain-language recommendation cite the
   band so the advice is defensible.

The challenge brief grades honesty: the scaffold shipped with made-up example
numbers, and M8 replaced them with sourced, real ones. The sources are also
noted inside the config itself (`benchmarks._warning`), so anyone opening the
config sees where each number comes from.

## The numbers

| CPT | Study | Medicare floor¹ | Cash low | Cash median | Cash high |
|---|---|---:|---:|---:|---:|
| 73721 | MRI lower-extremity joint (knee/ankle), no contrast | $230 | $385 | $625 | $1,550 |
| 72148 | MRI lumbar spine, no contrast | $205 | $350 | $800 | $2,800 |
| 70450 | CT head/brain, no contrast | $107 | $225 | $500 | $1,400 |
| 73610 | X-ray ankle, complete (3+ views) | $37 | $60 | $140 | $400 |

¹ National non-facility **global** rate (technical + professional component).

## Sources & method

**Medicare floor** — CMS Physician Fee Schedule, CY2026, national non-facility
global payment at the standard conversion factor ($33.40):

- CMS PFS lookup tool: https://www.cms.gov/medicare/physician-fee-schedule/search/overview
- Cross-checked via aggregators: https://payerprice.com/rates/73721-CPT-fee-schedule ,
  https://claimmaxrcm.com/cpt-code-72148-mri-lumbar-spine-billing-guide-2026/

This is the "floor" because Medicare is roughly the lowest price any provider
routinely accepts — a cash quote *below* it is a strong tell that something is
missing from the quote.

**Cash low / median / high** — Bay Area self-pay prices from price-transparency
aggregators and published cash rates:

- NewChoiceHealth, Palo Alto lower-extremity MRI: median **$614**, low **$440**,
  area MRI average $1,214 —
  https://www.newchoicehealth.com/places/california/palo-alto/mri/mri-foot-ankle-leg-hip-lower-extremity
- Radiology Assist, Mountain View: self-pay MRI **from $385** —
  https://radiologyassist.com/facility-locations-rates/locations-by-city/mri/mountain-view-ca-mri/
- Sidecar Health cash-price browser (CA radiology):
  https://cost.sidecarhealth.com/browse/radiology-services-costs
- KQED price-check reporting: the same back MRI ranged **$255–$3,700** across
  the Bay Area —
  https://www.kqed.org/stateofhealth/20464/pricecheck-how-much-for-a-back-mri-in-the-bay-area-255-or-3700

Method: take the independent-imaging-center self-pay rates as the low end,
aggregator medians as the median, and hospital-affiliated pricing (e.g.
Stanford-area) as the high end, rounded to demo-friendly figures. The point is
a defensible *band*, not cent-level precision — the spread itself (4x between
low and high for the same scan) IS the product's reason to exist.

## Why the demo numbers make sense against this band

- Sloane (upseller) opens at **$950** → visibly above the $625 median: the
  audience sees the markup.
- The negotiated **~$725** is a realistic landing spot, and the report shows
  "saved $225 (24%)".
- Marcus's **$350** teaser sits *above* the too-good-to-be-true threshold
  (70% × $385 ≈ $270), so his red flag correctly comes from the **unbundled
  radiologist read**, not from a price alarm — which is exactly the lesson his
  persona teaches.

## Swapping verticals

Nothing above is hardcoded: `VERTICAL_CONFIG=config/moving.example.json`
retargets the whole system. A new vertical just needs its own benchmark table
(same shape) with its own sources in `_warning`.
