# Real-demo full-chain scoreboard

What the engine actually does on *real, public* KiCad projects — measured, not
claimed. Reproduce with `python scoreboard.py` (drives KiCad's bundled demos).

> Chain per board: export netlist (`kicad-cli`) → place real library footprints
> (existence-gated healing, never guessed) → freerouting headless autoroute →
> KiCad DRC. A board is **clean** only when DRC reports **0 violations and 0
> unconnected**. Nothing is hidden.

Environment: KiCad **10.0.4** · Temurin **JDK 25** · freerouting **2.2.4** (Windows).

## DNA templates
`verify_all.py`: **14/14 template boards DRC-clean**, 49/49 checks.

## KiCad official demos (schematic-driven)

| demo | parts | nets | tracks | DRC | note |
|------|------:|-----:|-------:|-----|------|
| ecc83 | 15 | 14 | 56 | **clean** | |
| pic_programmer | 63 | 112 | ~500 | **clean** | |
| complex_hierarchy | 68 | 53 | ~419 | **clean** | flaky 0–1 unconn run-to-run |
| sonde xilinx | 25 | 43 | 246 | **clean** | fixed by the space-path patch below |
| interf_u | 24 | 174 | ~1350 | 2 unconn | dense analog; was ~10–14, cut by the aspect-ratio sweep below |
| stickhub | 94 | 48 | ~900 | 1 viol + ~21 unconn | placement boundary |
| kit-dev-coldfire-xilinx_5213 | 160 | 279 | 3355 | 72 unconn @900s | heavy; placement boundary |
| video | multi-sheet | — | — | timeout | heavy multi-sheet |
| multichannel_mixer | ~90 | — | — | **gated** | 1 genuinely-custom vendor part (`CLIFF_FC68148`) has no stock equivalent — healer fixed all 90+ others and correctly refuses to *guess* the last |
| microwave | — | — | — | n/a | PCB-only demo, no schematic |

## Boundary found & fixed this round

**freerouting path-with-spaces bug.** freerouting 2.2.4's CLI re-splits the
`-de`/`-do` values on whitespace, so any board whose path contains a space
(`sonde xilinx`, `My Project/…`) was silently truncated (`'sonde xilinx.dsn'` →
`'xilinx.dsn'`) and never routed — a fast, misleading "no ses produced". Fixed
in `route.py` by routing inside a space-free temp dir and copying the SES back.
`sonde xilinx` went from **route-fail / 66 unconnected → clean (246 tracks)**.
Regression test: `tests/test_daokicad.py::test_route_dsn_handles_space_in_path`.

## Placement evolution this round — aspect-ratio co-optimisation

The placer already picked the best part *order* by simulated ratsnest. It now
also sweeps the board **aspect ratio** (row width ∈ {1.0, 1.25, 1.6, 2.0}×√area,
never below the widest part) and keeps the `(order, width)` pair with the lowest
simulated ratsnest — the old 1.25 ratio is in the sweep, so it can never do
worse in proxy cost. Measured effect: **interf_u 10–14 → 2 unconnected**, while
ecc83 / pic_programmer / complex_hierarchy stayed clean (no regression).

## Standing boundary (next frontier)

stickhub and kit-dev-coldfire still leave unconnected nets — the ceiling is
genuine 2D placement, not routing budget (raising freerouting passes just times
out). Next push: evolve from shelf/row packing toward legalized 2D floorplanning
(overlap-free force coordinates, edge-affinity for connectors) so the router
gets a layout it can finish.
