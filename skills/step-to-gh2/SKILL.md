---
name: step-to-gh2
description: Rebuild an imported STEP/brep part as a parametric Grasshopper 2 definition in Rhino 9 over the Rhino MCP. Measure the part, ask how it is manufactured, pick the sketch strategy from that, wire native GH2 components with named sliders, and verify against the original to <0.01 mm. Use when the user asks to "replicate", "rebuild", "make parametric" or "reverse-engineer" a STEP part in Grasshopper.
---

# STEP part → parametric Grasshopper 2 model

Goal: a native-component GH2 definition whose sliders reproduce the reference part exactly (same face count, max deviation
< 0.01 mm) and stay valid when the sliders move.
Worked example: `examples/nist_ftc08.md` (NIST PMI test part FTC-08, billet-machined tray, inches, 247 faces).

## 0. Session check
1. `list_slots` + `get_context`. Note the **doc path, units and Rhino version**. STEP imports often come in **metres**.
2. Never touch the user's working file. Build in a new document (or a separate Rhino 9 slot, `spawn_slot version=9`) and
   save it as a **new** file. Put the reference on a locked layer `REF <part> (STEP)`.
3. Units: build in the units the **drawing** uses, so sliders read like the drawing (an inch drawing gets inch sliders).
   **Set the document's absolute tolerance before building**, and ask the user for the tightest tolerance on the drawing.
   It must be (a) at least 10× finer than that, so the model never limits the part, and (b) finer than the smallest offset
   the build relies on (the nudges in §4, e.g. `R − 0.0001`). GH2 booleans and fillets run at the document
   tolerance. At 0.001 in, Rhino treats 0.1199 and 0.12 as equal and the FTC-08 flange round failed silently (239 faces
   instead of 247); 0.0001 in works. Defaults: 0.0001 in / 0.001 mm. Record the tolerance in the hand-off.
4. `g2_start` may reopen the last GH2 definition. Make a new one active instead:
   `Grasshopper2.Doc.Document.NewActiveDocument()` → `Editor.Instance.Documents.Push(nd, None)` (own tab, leaves other
   definitions alone). Save it straight away.
5. **MCP slot ids can be re-assigned** between calls (Rhino 8 / Rhino 9 swapped mid-session). Start every write script with
   `print(__rhino_doc__.Path or __rhino_doc__.Objects.Count)`. "Could not load Grasshopper2" means you are in a Rhino 8 window.

## 1. Measure the part (read-only)
`scripts/analyze_brep.py` (set `SRC_ID`, `AXIS`, `SECTIONS`): bbox, face census, and planar sections joined into loops with line/arc radii.
- Planar face bounding boxes are **untrimmed**. Read dimensions from sections, cylinder centres and arc radii.
- List every vertical cylinder (radius + centre) and every vertical plane above the main levels. Drawing-style values
  (0.125, 2.35 …) fall out directly.
- Read chamfers from sections stepped near the edge (z = 0.001, 0.1, 0.25 …), not from cone faces.
- Probe ambiguous shapes with `brep.IsPointInside(pt)` at a mid-plate z (e.g. is a side lobe cut out or left as material?).
- Look at anything odd (e.g. lots of tiny faces on one wall = an engraved logo) with a quick viewport capture.
- In `run_python` use `import Rhino.Geometry as G`, wrap sections in try/except and print once at the end.
Write the findings as a table (feature → value) before designing anything.

## 2. ASK how it is manufactured (always — AskUserQuestion)
| Process | Base sketch | Features |
|---|---|---|
| Extrusion + CNC | one profile extruded along the axis | machined = cutters; pocket corner radius = cutter radius; end chamfers = Chamfer Edges |
| Stock tube + CNC | same, but size/wall snap to stock sizes | same |
| Turned | half-profile revolved | grooves/threads as revolve cutters, cross holes as cutters |
| Machined from billet | envelope (extruded outlines) | pockets/holes as cutters per setup; edge rounds as fillets |
| Sheet metal | flat pattern + bends | flanges as thickness extrusions |
| Moulded | shell + draft | ribs/bosses added, wall = shell thickness |
| SLS / MJF printed | as the shape suggests | check walls with `scripts/sls_check.py` |
Also ask which features are in scope, and how fixed artwork (logos, text) should be handled. Recommended: take the outline
from the STEP as fixed curves, placed by sliders.

## 3. Plan the inputs with the user
List every slider (name, value, range, unit), grouped by feature. Dimension like a drawing (offsets, insets, pitch = length + gap,
counts, ±mirrors), not raw coordinates.
- Ask **what each feature serves** and drive it from that (e.g. slot count and pitch from the component they clear, so length follows).
  Look at mating parts in the source doc to find the driver.
- **Driven by bought-in parts:** section each part at the mating plane and compare its outline with the cutout. Cutout = measured
  outline + a clearance slider. Prefer one shared clearance; bonded or press-fit parts get their own fit slider (default 0).
  Moving switches: cutout = actuator + travel + 2·clearance.
- Ask which dimensions are **cosmetic** and label those sliders.
- Snap a slider to valid steps: `slider.InternalSlider.AddPreset(Decimal(n), label)` + `PresetRestrict = True`.

## 4. Build in GH2 (native components, small verified steps)
One `g2_apply_graph` per stage (`solve=false`), then constants via `scripts/gh2_helpers.py`, then solve and check the stage output
(face count, volume, solid) before the next stage. **Save the .ghz after every verified stage.** Wires to existing components:
`g2_connect_many` (`replace=false` to add a source; `replace=true` replaces ALL sources of that input, so re-list every source in
order in the same call).

### Several GH2 documents open
- Target a document **by its file path**, never "the active canvas": `Editor.Instance.Canvas.Document` can switch to another
  open .ghz between calls. Get it with `[s.Root for s in Editor.Instance.Documents.All if s.Root.File.Path.endswith(name)][0]`
  and assert it before any write. MCP `g2_*` tools act on the active canvas, so re-check `get_context` after idle time.
- **Never clear groups/objects generically** (`for g in doc.Objects.Groups: Remove(g)`). On the wrong document it deletes the
  user's work with no undo.

### Patterns
- Centred rectangle: `Interval From Middle` (Md 0, Δx ← slider with input expression `x/2`) ×2 → `Rectangle From Intervals` → `Fillet All`.
- **45° chamfered rectangle:** `Fillet All` (R = chamfer leg) → `Fillet Replacement` (**Type 0 = chamfer lines**) → `Fillet All` (corner R).
- **Wall offset of that outline:** dimensions − 2·wall, chamfer leg − wall·(2 − √2), so no curve offset is needed.
- Two-value maths: `Evaluate Expression` (`x-2*y`, `min(x,y-0.0001)`, `abs(x-y)>0.001`). Unused second argument: set it to 0.
  An **Ex list with N expressions** gives an N-item output (e.g. `x-y`, `x+y` = both hole positions of a pair).
  More than 2 variables: `comp.DoCreateParameter(Side.Input, comp.Parameters.InputCount, None)` then
  `VariableParameterMaintenance()`; names run x y z u v w a b c …; **every added input needs data** (feed unused ones 0) or the
  component silently outputs nothing.
- Mirrored/repeated positions: `Point XYZ` with **grafted X** and a 2-item Y list (several wires into one input) = cross product.
  Linear repeats: `Array Linear` (Range = `Interval From Limits` 0 … Count−1).
- 2D cut-outs: circles (`Circle From Normal`) and rounded rectangles → `Region Union List` / `Region Difference` → `Fillet All` for blends.
  D-shapes / flatted holes: `Region Intersection` (circle ∩ rectangle) → `Fillet All`.
- Lift every deck profile with ONE `Move` (flattened) → ONE `Extrude Linear` → all cutters → `Solid Difference` (Sb flattened).
- **Features on several walls, one sketch frame:** build each cutter in local XY (profile at z = +1, extrude −(depth+1), or
  −(wall+2) for through cuts) → `Orient` (source WorldXY, Shape flattened, Plane grafted) onto a `Plane From Axes` at each wall's
  outer face centre (local Z outward). Give positions relative to the face centre; the reference numbers then come out round.
- Placing at a computed z: `Offset Plane` (Of ← Evaluate Expression). Use Evaluate Expression rather than input expressions for
  **field**-typed inputs (Offset, axes, radii).
- Countersinks: `Line 2 Points` (u, v, +1) → (u, v, −csk/2) → `Cone From Axis` (radius csk/2 + 1, Cap true) → `Solid Difference`.
- Fixed artwork: inner loops of the STEP face (`BrepLoop.To3dCurve`) → transform into a local frame with a round-number origin →
  internalise in a `Curve` param (`param.Set(Array[Curve])`) → `Orient` (source WorldXY) to `Plane From Axes`
  (origin from sliders; axes are **field** inputs, set via `Field.op_Implicit(Vector3d)`) → extrude by depth.
- Recess with a floor fillet: fillet the **cutter's** bottom edges (`Edges From Faces`). Cap indices of a capped `Extrude Linear`:
  4-segment rectangle start 4 / end 5; 8-segment rounded rectangle start 8 / end 9; 16-segment chamfered outline 16 / 17.
  **With a negative span the caps swap.** Section the cutter to check the taper went the right way.
- **Toggles / variants:** `Item From Index` (List + Index ← a 0/1 slider). List order = **wire order**, so wire each list in ONE
  `g2_connect_many` call. Keep the old behaviour at index 0 and route every downstream input through the switch.
- `Solid Intersection List` intersects ALL inputs together. To clip one solid by several disjoint boxes, use `Solid Intersection`
  (A = solid, B = list of boxes).
- **No solid offset in GH2.** For a fit gap, inset the 2D profiles explicitly (`x-gap` on the intervals, fillet R − gap).
- `Mirror` of a **solid** comes out inside-out (negative volume) and poisons unions. Mirror the **curve**, then extrude.
- Cutters that meet a radiused feature must overrun it (end at feature + R + 1), or a sliver step remains.
- `Rotate About Axis` and other GH2 angle inputs take **degrees**.
- A GH2 Python script component is acceptable when a native chain gets unwieldy (e.g. long box lists), if the user agrees.

### The nudge rule: never let geometry exactly coincide
Rhino's kernel often fails, usually silently, when two things match exactly. Nudge one of them by a small epsilon and label
the slider or expression so it reads as a workaround, not a design value:
| Exactly matching | Nudge |
|---|---|
| Edge round radius = the corner radius it runs around | `min(R, Rcorner − 0.0001)` |
| Chamfer = the corner radius it runs over | chamfer strictly smaller |
| Coplanar faces in a union (flange and body both at z = 0) | start one inside the other (body at FlangeT/2) |
| A cutter cylinder on an existing hole of the same radius | stop the cutter short, or change its radius |
| Union members that just touch | overlap them (e.g. 0.1 into the neighbour) |
| Cutter ending exactly on a face | overrun it (z = +1, depth + 1) |
The nudge must be **larger than the document tolerance** (§0). At 0.001 in a 0.0001 nudge disappears, the kernel sees
coincident geometry again, and the feature fails (FTC-08: 239 faces instead of 247). Re-run the face-count check after
any change of tolerance or units.

### Fillets and edge selection (the hard part)
- **An edge round equal to the corner radius it runs around fails** (Rhino kernel, silently: same face count). Use
  `min(R_edge, R_corner − 0.0001)` and label it. You get the same face layout as the STEP and 0.0025 mm deviation.
  The offset only works if it is **larger than the document tolerance** (see §0); otherwise the kernel sees equal radii again.
- Doing corners and edges in one rolling-ball fillet gives patchy faces. Keep the profile corners and do the edge fillet afterwards.
- **Never select edges with per-item components on a shared brep** (e.g. `Edges From Point` fed many points). GH2 runs them
  in parallel, and the results changed from solve to solve (1 to 16 of 16 edges). Use single-call selectors
  (`Edges From Concavity`, `Edges From Faces`) and filter them geometrically:
  `Explode Surface` (edge list order = brep edge index) → `Item From Index` (indices) → `Evaluate At Length` (0.5, normalised)
  → `Plane Coordinates` (**set the plane to WorldXY explicitly; the default is not XY**) → `Evaluate Expression` → `Cull By Pattern`.
- The 0.0001 workaround leaves near-tangent seams that classify as concave (or convex) at some slider values. Filter fillet edges
  by **height**, e.g. base fillet = concave edges whose midpoint is at z = FlangeT, flange round = convex edges at z = FlangeT.
- Avoid **coplanar faces in unions** (e.g. flange and body both starting at z = 0). Start the body inside the flange (z = FlangeT/2).
- `Chamfer Edges`: the chamfer must be strictly smaller than the corner radius it runs over (equal fails silently: same face
  count and volume). Compare face counts before and after. A chamfer bigger than the corner radius: intersect the part with a
  sharp box whose edges are chamfered.
- Complex 2D blends: `Fillet Curve` (Locus = a point near the corner). A second Fillet Curve on an already-filleted curve can pick
  the wrong corner; for symmetric parts mirror the filleted region and `Region Union` it instead.

### Regions
- A region with **several disjoint outlines** fails in `Extrude Linear` (null). `Explode Region` first.
- A region outline extrudes as **one kinked NURBS side face**. Run `Simplify Curve` (Merge Consecutive = true) first, so you get
  one plane/cylinder per segment and the face count matches the STEP. Full-round slots (fillet R = W/2) give four quarter arcs;
  `Simplify Curve` merges them into two.

### Booleans
- Print `IsSolid` / volume at every boolean stage. A union member that comes out `IsSolid False` is silently dropped by the next union.
- **No coplanar contact** between union members: start them 0.1 into the neighbour.
- **No coincident cylinders** between a cutter and an existing hole of the same radius.
- Adding material inside a part: union a **solid** core first, other fills in a **second** union, subtract the new cut last.
- Solids unioned on **after** a cutter re-add material over that cut (a knife edge over the opening). Subtract the cutter from the
  fill pieces too, and section through the cut whenever a fill is added after it.
- When a result collapses, subtract each cutter on its own in run_python to find the bad one, and check the union output first.
- **Gate saves on the checks** (`if all probes ok and solid: save()`), so a broken state never overwrites a good one.

### A STEP part inside GH2
- Internalise the brep in the build frame (`param.Set(Array[Brep])`). Derive the frame from the part's **bbox to 1e-4**: a rounded
  frame (0.003–0.005 off) leaves slivers on every coplanar face later.
- Extending a STEP feature: section it (`BrepPlane` → `JoinCurves`), internalise the curve at z = 0 → `Move` → `Extrude`.
- STEP blocks are often in **metres** with nested blocks. Explode in memory with `InstanceObject.Explode(True)`, find a known part,
  build the block→assembly transform from it (check det = +1, not a mirror). Don't import hundreds of block definitions.

### GH2 API facts (run_python)
- Doc: `Grasshopper2.UI.Editor.Instance.Canvas.Document` (but see "Several GH2 documents open"); `doc.Objects.Find(Guid)`;
  inputs `comp.Parameters.Inputs`; outputs `list(comp.Parameters.Outputs)[i].State.Data.Tree().AllPears` → `.Item`.
- Constants: `param.Set(System.Array[T]([...]))`; Evaluate Expression args take `Object[]` (try `Double[]`, fall back on TypeError);
  planes `Array[Plane]`. Expressions: `param.ExpressionText = "x/2"`. Modifiers are immutable:
  `p.Modifiers = p.Modifiers.WithFlatten()` / `.WithGrafting()`. Flatten `Solid Union/Intersection List` and `Solid Difference.Sb`
  when several wires feed them.
- **Solve, then wait:** `StartWait()` can return while an auto-started solution is still running, so reads are stale. Use
  `solve_all()` / `wait_idle()` from `gh2_helpers.py` (poll `Solution.State.CurrentlyRunning is None` and `Phase == Completed`).
- `g2_solve_canvas` sometimes omits diagnostics. Read component `messages` from `g2_get_canvas_graph(include_data=false)`.
- Save: `DocumentIO(doc, True, True, False, True).Save(path, FileContents.All)` (via reflection on the Grasshopper2 assembly).
- Open a .ghz from a script: `g2_start` first (otherwise `Editor.Instance` is None), then
  `DocumentIO().Open(path, None, System.Action[Document](lambda d: None))` → `Editor.Instance.Canvas.Document = io.Document`.
- Sliders have no `.Parameters`. Slider value: `slider.InternalSlider.Values.Assign(Decimal(v)); slider.Expire()`.
- Reading an existing canvas: `scripts/gh2_describe.py` → `desc(guid)` lists inputs (sources, constants, expressions) and
  output targets. Delete with `g2_delete_component` only after checking the component has **no downstream wires**.
- After a crash, components still showing GH2 defaults (Evaluate Expression `sin(x) + cos(y)`) are an unwired skeleton.
  Delete and rebuild them rather than guessing their intent.
- Long `run_python` calls go to the background after 120 s; wait for the notification.

### Viewport captures
- `view.CaptureToBitmap(...)` **does draw the GH2 preview**: set `gdoc.Display.Enabled = False` during capture, restore after.
  For a picture of GH2 output, add a TEMP copy to the doc, capture, then delete it.
- Temp copies of objects you just hid inherit `Mode = Hidden`: set `attr.Mode = ObjectMode.Normal`.
- `doc.Objects.Delete(id, True)` **silently skips hidden objects**. Use `Delete(rhinoObject, True, True)` and count objects on
  temp layers after every capture run.
- Captures looking along +Z are mirrored (screen-right = −X). Label A/B sheets from the camera.
- Section images: a temporary clipping plane + parallel projection + `ZoomBoundingBox`; delete the clip in `finally`.
- Animation: rotate/modify temp copies per frame → `CaptureToBitmap` → Pillow GIF (`convert("P", ADAPTIVE, 128)`, ~70 ms).

### Canvas tidy-up (before hand-off)
1. Assign every component to one feature group; script a check that each id is in exactly one.
2. Lay each group out as a band: columns by data-flow depth (sliders left, result right), stacked rows. Bands go top to bottom.
3. `GroupObject(OpenColor.Family.X, Guid[])` (constructor via reflection), `UserName` = title, `doc.Objects.Add(grp)`.
   Families: Gray Red Pink Grape Violet Indigo Blue Cyan Teal Green Lime Yellow Orange.
   **Group bounds don't refresh after scripted moves**, so remove and re-create the groups. The family can't be read back,
   so keep your own title→colour map.
4. Name the key calculation components (`comp.UserName`), so the canvas reads like a drawing. Check no bounds overlap.
5. Previews: every component's Display = Hidden except the result; `scripts/gh2_preview_on_select.py` shows a component
   while it is selected (run it each session).
6. Canvas image: `canvas.DrawToBitmap(Eto.Drawing.RectangleF(region), w, h, True, True, False).Save(png, ImageFormat.Png)`.

## 5. Verify (required before reporting)
`scripts/compare_to_ref.py` (GH output id + REF id). Pass criteria:
- closed, valid solid; **face count equals the reference**;
- max deviation < 0.01 mm both ways, **including the surface-sample check**. Vertex checks miss holes through thin plates;
- area within 0.1 % (a STEP reference may be open, so compare area, not volume).
If the face count differs, group faces by plane equation / cylinder axis+radius on both sides and diff them. That tells
"same surface, split differently" (harmless; e.g. 0.1199 vs 0.12) from a genuinely missing feature.
Then move several sliders (overall size, wall, height, a pitch, a count), re-solve and check solid + face count each time.
A ±1 face change can be legitimate (a feature starts crossing a fillet), so look before "fixing" it. Reset afterwards.

**When the defaults differ from the reference on purpose** (e.g. cutouts = measured part + clearance): temporarily set the
inputs so the result should equal the reference, run the comparison, restore the nominal values, and report the intended
differences separately.

Check functional intent geometrically too, e.g. `brep.IsPointInside(pt)` at every hole/rib location, for every slider step.

## 5b. Manufacturability checks (run on every part before hand-off, and after every added feature)
**Machined parts:** `scripts/machinability_check.py` (TARGETS + setup approach vectors). It works in mm whatever the document units are.
- Excludes as-extruded faces on extrusions, so die radii don't count.
- Classifies each face (flat/ball/drill/chamfer mill), ray-tests access from each setup and flags **UNDERCUTS**, small bits (< D3),
  long reach (> 3×/5×D) and sharp internal corners on the tool axis (EDM). Prints the minimum tool set.
- Aim for **few tools, no small bits**: design radii to share one cutter, use standard drill sizes, and keep sections getting
  **wider going away from the setup face** (a narrower band behind a wider land is an undercut).
- A new boss can block the cutter path of an existing feature. Before suggesting a feature, ask which cutter path it sits in.
- For a reverse-engineered part the report describes the **original** design, which is useful for suggesting changes.

**SLS / MJF printed parts:** `scripts/sls_check.py` (set `BREP`, optional `LIMITS`, `ZONES`). Measures local wall thickness with
exact brep crossings and classifies thin clusters as supported / UNSUPPORTED / feather edge. End thread ridges and similar
features ≥ (root width / 2) below a face, or the check flags slivers.

## 5c. Assemblies and mating parts
Use `scripts/assembly_checks.py` (`gh_out`, `ov`, `min_gap`, `sweep` along the insertion path, slider helpers).
- **Check the assembly path, not just the final fit.** Sweep moving parts along their insertion direction in steps and
  boolean-test each position. Anything a part must pass through has to open out towards the insertion side.
- **Measure the real mating part before designing around it.** Section it every ~0.5 mm through the region of interest; check
  corner chamfers and flares that a simple envelope misses.
- Mating parts made by one machinist: drive the fit from **measured** inputs (MeasuredBore + Interference), then check
  BooleanIntersection(part, mate) is only the intended interference.
- **Clearance / creepage targets need three checks:** (1) zero overlap with every neighbour; (2) line of sight: every conductor
  point near metal must have its straight segment blocked by the insulator; (3) paths around edges and through cracks. A skirt
  that forces the path to climb works better than a taller wall. Report solid-insulation zones separately (they need a test, not geometry).
- **Moving parts (hinges, lids):** a relief cut at exactly the hinge radius gives 0.00 mm rubbing through the whole swing; cut to
  R − gap. Check with rotate-in-steps + boolean overlap **and** a mesh-vertex → closest-point minimum distance (booleans alone miss
  zero-gap rubbing), against every nearby object.
- **Offer variants instead of overwriting** (toggle sliders), and A/B them with baked copies and matching camera shots on one
  labelled sheet. For sub-mm differences, a section through the feature reads far better than viewport close-ups.

## 6. Hand-off
- Save the definition and build document as new files where the user confirms. Never touch production geometry or the user's
  open file. Rhino 9 `doc.SaveAs(newPath, 9)` switches the open document to the new path; number copies `_002`, `_003` … and
  never overwrite. `doc.SaveAs(path, 8)` writes a file Rhino 8 can open (without GH2 metadata).
- Bake only when asked, onto a new layer, and always through `fc_core.bake_parts(doc, [name])` from `tools/FeatureContext`
  (GH2-native `BakeContext`: stores the source component id + `fc.*` tags). A plain bake carries no provenance.
- Report: parameter table, verification numbers, anything that differed from the first measurement.

## FeatureContext: feature requests from picked faces
The user picks faces on a baked part with the `FeatureContext` command (see `tools/FeatureContext/README.md`). When they paste
a summary or say "see packet":
1. Read `latest.json` in `FeatureContext packets` next to the .3dm. Each pick has `trace.created_by` (the component that made the
   face), `trace.feature` (nearest named one), `trace.drivers` (sliders/constants per input) and the user's `note`. The PNG next to
   it shows the highlighted face.
2. If `trace.status` is STALE or missing, ask them to re-bake with `FCBake` (or call `fc_core.bake_parts` after asking).
3. Confirm the component on the canvas (`desc(id)`), propose the slider or wiring change, then apply → solve → re-check with the
   usual comparison and assembly scripts.

In run_python: `sys.path.insert(0, r"<path>\FeatureContext"); import fc_core`. `fc_core.trace_face` / `drivers` work on any
baked object that carries `G2ProcGuid`.
- Bake in place of an older object: `layer_path=<its layer>, obj_name=<its name>, replace_ids=[old id]`, after checking the new
  output matches (faces, volume, bbox).
- A/B copies: `extra_copy=True, tags={"fc.variant": ...}`. Copies moved side by side get user text `fc.offset = "dx,dy,dz"`; the
  trace subtracts it.

GH2 metadata and bake API:
- Every data item (`IPear`) has immutable `.Meta`. Add with `MetaData.Empty.Add(MetaName.Parse("fc.feature"), "x")` (a dotted name
  must go through `MetaName.Parse`) and attach with `Pear.WithMeta(pear, meta)`.
- `BakeContext(name, componentGuid, doc, attrs, userPattern, MetaPattern(True, True))` → `ctx.BakeObject(pear)`. It writes
  `G2ProcName` / `G2ProcGuid` / `G2ObjHash` and the metadata as `GH2:<name>` into **attr.UserDictionary**. `G2ProcGuid` is a Guid,
  so compare with `str()`.
- `UserPattern` has no usable constructor: use `RuntimeHelpers.GetUninitializedObject(UserPattern)`.
- `doc.Objects` iteration **skips hidden/locked layers**. Use `GetObjectList(ObjectEnumeratorSettings)` with `HiddenObjects` and
  `LockedObjects` set when looking for earlier bakes.
- Mirrored twins look identical up to a shift. Only follow a shift through real `Move` components, pairing item n with item n.
