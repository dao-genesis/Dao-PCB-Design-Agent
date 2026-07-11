# LCEDA EXTAPI Defects & Workarounds

Discovered through deep fusion testing with real-world IoT PCB builds.

## DEFECT-001: C10418 USB Micro breaks importChanges()

**Severity:** Critical (blocks schematic-to-PCB sync entirely)
**Component:** `pcb_Document.importChanges(pcb_uuid)`
**Discovery method:** Binary search isolation across 11 BOM component types

**Symptoms:**
- `importChanges()` returns `False` (raw API level)
- 0 components appear in PCB after sync
- No error message — silent failure
- All other schematic operations (place, wire, save) succeed normally

**Root cause:** LCSC part C10418 (USB Micro-B SMD connector) has internal footprint/symbol
incompatibility that causes `importChanges()` to silently fail. The failure is per-component-type,
not per-instance — any schematic containing C10418 will fail to sync.

**Isolation proof:** 10/11 BOM types return `True` from importChanges; only C10418 returns `False`.
Tested individually: STM32 (C8734), ESP-12F (C82891), AMS1117 (C6186), crystal (C12674),
caps (C1525/C19702/C1555), LEDs (C72043), resistors (C25744/C11702) — all pass.

**Workaround:** Replace C10418 with C2907 (2-pin header, compatible with importChanges).

---

## DEFECT-002: createNetClass() never persists

**Severity:** Medium (net class feature unusable via API)
**Component:** `pcb_Drc.createNetClass(name)`

**Symptoms:**
- Returns `null` (no ID created)
- `getAllNetClasses()` always returns `[]`
- `addNetToNetClass()` returns `False`

**Note:** Differential pairs (`createDifferentialPair`) work correctly via the same DRC namespace.
Net rules (`getNetRules/overwriteNetRules`) also work. Only the net class feature is broken.

---

## DEFECT-003: Programmatic routing clearance (34 violations on 16-component board)

**Severity:** Low (prototype-acceptable; production would use commercial autorouter)
**Component:** Escape-corridor routing algorithm in `pcb_route_layers()`

**Analysis of 34 violations (all Clearance Error):**
- Track-to-Track: 6 (escape corridors from different nets on same layer)
- SMD Pad-to-Track: 17 (long power net traces crossing component footprints)
- Track-to-Via: 1 (bottom-layer via too close to top-layer trace)
- Board Outline-to-Track: 2 (escape corridors extending past board edge)
- SMD Pad-to-Via: 3 (vias placed at pin coordinates overlap adjacent pins)
- Hole-to-Track/Pad: 5 (through-hole pad clearance)

**Root cause:** Sequential pin-chaining for GND (16 pins) and VCC_3V3 (9 pins) creates
long traces that traverse multiple component footprints. Real autorouters use maze/channel
routing; our escape-corridor approach is a linear algorithm.

**DRC optimization history:** 80 → 69 → 37 → 34 (grid layout + 2-layer escape + net sorting)

**Mitigation:** Commercial LCEDA autorouter or Freerouting integration would reduce to 0.
