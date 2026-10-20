# Worked example: NIST PMI test part FTC-08 → GH2

Source: NIST "PMI Fully-Toleranced Test Case 8", ASME version (free download from NIST's
[MBE PMI test models](https://www.nist.gov/ctl/smart-connected-systems-division/smart-connected-manufacturing-systems-group/mbe-pmi-0)).
Units: inches, document tolerance 0.0001 in (0.001 in makes the R0.1199 flange round fail; see the nudge rule in SKILL.md). Process (user's answer): **machined from billet**, 3-axis, setups top / underside / +X side.

## Measured features (all inches)
| Group | Feature | Value |
|---|---|---|
| Flange | plate | 12.268 × 8.768 × 0.40, corners R0.12, top outer edge round R0.12 |
| | holes | 4 × Ø0.2375 at ±5.625, ±3.875 |
| Body | outline | 11.498 × 8.068, 45° chamfer leg 0.90, corners R0.12, height 1.90 |
| | rounds | top edge R0.12, wall-to-flange fillet R0.06 |
| Cavity | from below | outline offset by wall 0.25 (chamfer leg 0.9 − 0.25·(2−√2) = 0.7536), R0.12 corners, ceiling at 1.765, ceiling fillet R0.12 |
| Deck | thickness | 0.135 |
| | scalloped opening | x −4.25…1.25, 4.5 wide, R0.125; 10 R0.3 bosses (inset 0.06; long sides x0+1.0, pitch 1.75; short sides y ±1.0); blends R0.125; Ø0.213 holes |
| | square hole | 1.1 □ at (4.3, −1.95), R0.0625; Ø0.25 holes at ±1.125 in y |
| | round hole | Ø1.203 at (4.4, 2.5) + R0.125 key notch 0.5625 towards −X |
| | lobed cut-outs | at x 2.35, y ±1.825: two R0.3 lobes 0.65 apart + R0.2 side lobe (+X); the +Y one has a 0.2 × 0.5 key (R0.0625) to −X |
| | single holes | x 2.75: Ø0.228 at y −2.65/+1.0, Ø0.242 at y −1.0/+2.65 |
| | recessed slot | 0.5 × 6.25 at x −4.9, R0.125, 0.05 deep, floor fillet R0.03 |
| Wall | NIST logo | 0.1 deep on +X wall, outline from the STEP, lower-left corner at (y −1.1, z 1.0) |

## Build order (one GH2 group each)
1. Envelope: sharp-topped flange ∪ body (body starts at FlangeT/2: no coplanar bottoms). Body top round = `min(R, Rcorner−0.0001)`.
   Base fillet = concave edges at z = FlangeT, then flange top round = convex edges at z = FlangeT.
2. Cavity cutter (top edges filleted = ceiling fillet) → Solid Difference.
3. to 7. Deck profiles (regions and curves). Lobed cut-outs: `Region Union List` → `Explode Region` → `Simplify Curve`.
8. One Move (lift to the deck) → one Extrude through the deck → cutters.
9. Flange holes. 10. Slot cutter with a filleted floor. 11. Logo: internalised outline → Orient → extrude 0.1 + 0.05.
12. RESULT = Solid Difference (flattened subtrahends).

## Result
- 247 faces (STEP 247), closed valid solid, volume 30.7338 in³ (STEP 30.7336).
- Max deviation 0.000076 in (**0.0019 mm**) over ~175,000 true-surface samples both ways; area +0.0018 %.
- Slider tests: height, body L/W, wall, flange thickness, chamfer, opening width, lobe pitch, slot length all stay valid solids.
  Height 1.5 and BodyL 10.5 give 248 faces: the logo meets the top round, or the round hole meets the cavity fillet (legitimate).
- 224 GH2 objects, 63 sliders, 12 groups.

## What went wrong on the way (and the fixes, now in SKILL.md)
| Symptom | Cause | Fix |
|---|---|---|
| Edge round R0.12 on R0.12 corners: silently no change | kernel can't roll an equal-radius ball round the corner | `min(R, Rc−0.0001)` |
| Base fillet sometimes missing, result changed between solves | `Edges From Point` evaluated per point in parallel on one brep | single-call `Edges From Concavity` + geometric filter |
| Reading outputs right after `StartWait()` gave different results | another solution still running | `wait_idle()` / `solve_all()` |
| Height-filter kept 6 of 8 edges | `Plane Coordinates` default plane isn't WorldXY | set WorldXY explicitly |
| Base fillet failed at Height 2.3 | near-tangent seams from the 0.0001 trick classed as concave | filter edges by height (z = FlangeT) |
| One deck cutter null | region with two disjoint outlines | `Explode Region` |
| 238 faces instead of 247, but ~0 deviation | regions extrude as one kinked NURBS face | `Simplify Curve` before extruding |
| Deviation check passed while faces were wrong | vertex samples on thin-plate holes sit on the rims | surface (face-centre) samples + face grouping diff |
| Machinability report: "no stock tool" for everything | script assumed mm, part in inches | script now scales to mm |
