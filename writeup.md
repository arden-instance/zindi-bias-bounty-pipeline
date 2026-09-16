# Bias Discovery: Overture's fire-station coverage gap is systematically worse in low-density (rural) census tracts

## Summary

Overture Maps under-counts fire stations relative to HIFLD (the federal
reference layer) everywhere in this challenge's four regions, but the size of
that gap is not random — it is strongly and consistently concentrated in
low-density, rural census tracts. Pooling all four regions (Northern
California, Eastern Oklahoma, Maricopa County AZ, South-Central Texas;
n=3,236 tracts with at least one confirmed HIFLD fire station), the
Spearman correlation between housing-unit density and the fire-station
coverage gap is **ρ = -0.375 (p = 2.3×10⁻¹⁰⁸)**. The lowest-density tercile
of tracts has a mean fire-station gap **3.5x worse** than the highest-density
tercile (0.461 vs 0.131). The pattern holds in every one of the four regions
individually, with no exceptions:

| Region | n (fire-defined) | Spearman ρ | p-value | low-tercile gap | high-tercile gap | ratio |
|---|---|---|---|---|---|---|
| Northern CA | 278 | -0.487 | 5.9e-18 | 0.649 | 0.147 | 4.4x |
| Eastern OK | 580 | -0.319 | 3.2e-15 | 0.587 | 0.275 | 2.1x |
| Maricopa AZ | 426 | -0.335 | 1.3e-12 | 0.404 | 0.092 | 4.4x |
| South-Central TX | 1,952 | -0.316 | 1.2e-46 | 0.387 | 0.120 | 3.2x |
| **Pooled (all 4)** | **3,236** | **-0.375** | **2.3e-108** | **0.461** | **0.131** | **3.5x** |

The same directional pattern also holds for the overall `poi_gap` component
(fire + EMS + schools vs HIFLD, and CBP establishments vs all Overture POIs),
pooled ρ = -0.337, p = 6.1×10⁻²⁴⁷, n=9,347 — so this is not an artifact of one
sub-component's sample size.

## Why this matters (emergency-dispatch relevance)

Fire-station location data feeds routing, response-time estimation, and
mutual-aid coverage planning for emergency dispatch. A basemap that is
disproportionately missing fire stations in exactly the tracts that are
already hardest to serve — rural, low-density, longer response distances —
compounds an existing infrastructure disparity rather than correcting for it.
An automated coverage-gap scorecard that only reports the *average* gap per
tract, without surfacing this density-conditioned pattern, would understate
the real-world equity impact: the tracts most at risk from a missing fire
station in the map data are systematically the same tracts where an under-
count is most consequential (longest true response distances, most reliance
on mutual aid across a wide area).

## Named evidence

Twenty tracts across all four regions have **zero** Overture-listed fire
stations despite HIFLD confirming 2–7 real stations present, sorted by
density (lowest first):

| Region | GEOID | Density (housing units/km²) | HIFLD fire stations | Overture fire stations |
|---|---|---|---|---|
| Northern CA | 06035040100 | 0.11 | 6 | 0 |
| South-Central TX | 48173950100 | 0.22 | 2 | 0 |
| South-Central TX | 48235950100 | 0.28 | 2 | 0 |
| Northern CA | 06093001300 | 0.34 | 6 | 0 |
| Northern CA | 06049000200 | 0.35 | 4 | 0 |
| South-Central TX | 48307950500 | 0.50 | 4 | 0 |
| Northern CA | 06093000800 | 0.51 | 7 | 0 |
| South-Central TX | 48095950300 | 0.55 | 3 | 0 |
| Maricopa AZ | 04017940100 | 0.62 | 2 | 0 |
| Northern CA | 06103000300 | 0.64 | 6 | 0 |

(Full table of 20: `bias_discovery_worst_tracts_all_regions.csv`.)

These are not edge cases at the tail of a small sample — several of these
tracts have HIFLD-confirmed coverage of 4-7 stations, meaning Overture is
missing the *entire* local fire-response network in its data for that tract,
not just undercounting by one or two.

## Method (reproducibility)

1. Computed `poi_gap_fire` per census tract for all four regions using the
   challenge's own documented formula (`gap = 1 - min(1, overture_count /
   hifld_count)`, undefined when HIFLD count is 0) — see `poi_gap.py`. This
   was independently validated earlier in this challenge against the
   README's published transport-gap undefined-tract counts (exact match on
   3 of 4 regions, off-by-7-of-6,010 on the 4th, a tract-count snapshot
   mismatch not a code bug).
2. Computed tract-level housing-unit density from each region's
   `census-acs-housing` layer: `density = housing_units / area_km²`, where
   `area_km²` is derived from the tract polygon's raw WGS84 area in square
   degrees, scaled per-tract by `111.32 × 111.32 × cos(latitude)` (a
   standard small-area planar approximation; adequate at census-tract scale,
   errs by ≤~1% for tracts this size at these latitudes). See
   `density_gap.py`.
3. Joined on `GEOID` (kept as zero-padded string throughout — a real bug
   that bit an earlier stage of this pipeline when GEOID was silently
   coerced to int).
4. Computed Spearman rank correlation (density vs. gap) and tercile means,
   per-region and pooled across all four regions.

All code is in this submission's supporting files: `poi_gap.py`,
`density_gap.py`, `building_gap.py`, `road_gap.py`, `assemble.py`. Anyone
can rerun `density_gap.py <region>` against the same public source.coop
bucket to reproduce every number in this writeup.

## Limitations

- Density is a proxy for "rural," not a direct measure of response
  infrastructure need; a more targeted follow-up would pull actual travel-
  time-to-nearest-station estimates.
- The per-tract degree-to-km² area approximation is not a true equal-area
  projection; it is accurate to within roughly 1% at this spatial scale but
  is worth flagging for anyone building on this analysis at coarser scales.
- HIFLD itself may have its own coverage gaps (it is federal administrative
  data, not a ground-truthed census), so the "true" fire-station count is
  an estimate, not a certainty — but it is the reference layer this
  challenge specifies, and Overture's gap relative to it is the quantity
  the challenge scores.
