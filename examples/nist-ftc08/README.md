# Example: NIST FTC-08 as a parametric Grasshopper 2 definition

NIST's PMI test model **FTC-08** is a billet-machined tray with a flange, cavity, deck cut-outs, a recessed slot and an
engraved logo. Claude rebuilt it with the `step-to-gh2` skill. The rebuild matches all 247 faces of the STEP to 0.0019 mm.

| File | What |
|---|---|
| `FTC-08 parametric.ghz` | GH2 definition: 63 sliders in inches, 12 colour-coded feature groups, result = "FTC-08 RESULT" |
| `Machinability - FTC-08.md` | 3-axis machinability report of the part (values in mm) |

To see all 63 sliders without opening Rhino: `python tools/ghz_sliders.py "examples/nist-ftc08/FTC-08 parametric.ghz"`.

How it was built (measurements, build order, every problem hit and its fix): [`skills/step-to-gh2/examples/nist_ftc08.md`](../../skills/step-to-gh2/examples/nist_ftc08.md).

## Get the STEP
The STEP is not included. NIST publishes it free on its
[MBE PMI test models page](https://www.nist.gov/ctl/smart-connected-systems-division/smart-connected-manufacturing-systems-group/mbe-pmi-0):
the [PMI STEP files](https://www.nist.gov/document/nist-pmi-step-files) package holds the FTC-08 STEP (AP242/AP203), and the
[FTC-08 CAD model](https://www.nist.gov/document/nist-cad-model-ftc-08) page has the drawing.

## Try it
1. Rhino 9 (WIP): new document in **inches** with the absolute tolerance set to **0.0001 in**
   (Document Properties → Units). This is a modelling tolerance, not the part's spec. The flange round is R0.1199 next to
   an R0.12 corner, and at the inch template's default of 0.001 Rhino treats the two as equal, so the fillet fails
   silently and you get 239 faces instead of 247. Import the STEP onto a layer `REF FTC-08 (STEP)` and lock it.
2. Open `FTC-08 parametric.ghz` in Grasshopper 2 and move sliders. Each group is dimensioned the way the drawing does it
   (offsets, insets, pitches, mirrored ± positions). The logo outline is fixed artwork taken from the STEP; its position and
   depth are sliders.
3. Bake with `FCBake` (see [`tools/FeatureContext`](../../tools/FeatureContext/README.md)) and pick faces with `FeatureContext`.
4. To check the rebuild yourself, run `skills/step-to-gh2/scripts/compare_to_ref.py` with the "FTC-08 RESULT" output and the STEP's id.

## Verification
| Check | Result |
|---|---|
| Faces | 247 (STEP 247) |
| Solid / valid | yes / yes |
| Volume | 30.7338 in³ (STEP 30.7336) |
| Max deviation, both ways | 0.000076 in = 0.0019 mm (~175,000 true-surface samples) |
| Area | +0.0018 % |
| Slider tests | 15 changes across 9 sliders: all valid solids |

The FTC-08 model is published by NIST (U.S. government work). This repo only links to it.
