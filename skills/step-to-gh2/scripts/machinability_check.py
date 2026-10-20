# Machinability check for Rhino breps / GH2 outputs (paste or exec in Rhino MCP run_python).
# Not CAM: it flags what drives tool count and cost. Small corner radii, long reach, undercuts,
# sharp internal vertical corners, 3D surfacing, and the minimum tool set.
#
# Edit TARGETS / LIBRARY / LIMITS below. A target's geometry comes from a GH2 component output (gh_id)
# or a Rhino object (doc_id).
#   kind "bar"       -> every face is machined
#   kind "extrusion" -> faces parallel to `axis` that run >= 95% of the part length are AS EXTRUDED (die-formed)
#                       and are not machined, so e.g. the profile's R0.3 corners are excluded.
# setups: tool approach directions (the direction the tool moves INTO the part), e.g. (0,0,-1) = from above.

TARGETS = [   # one entry per part; gh_id = GH2 component whose output 0 is the part (or doc_id = Rhino object id)
    {"name": "My part", "gh_id": "00000000-0000-0000-0000-000000000000", "kind": "bar",
     "setups": {"A top (from +Z)": (0, 0, -1), "B underside (from -Z)": (0, 0, 1)}},
]
LIBRARY = {   # stock tools (mm)
    "flat":  [1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12],
    "ball":  [1, 2, 3, 4, 6, 8, 10],
    "drill": [x / 2.0 for x in range(2, 41)],          # 1.0 .. 20.0 in 0.5 steps
    "chamfer": ["90deg chamfer mill"],
}
LIMITS = {"small_bit": 3.0, "reach_warn": 3.0, "reach_bad": 5.0}
MARK_LAYER = "Machinability check"     # TextDots at flagged features; None to skip
OUT_MD = None                          # e.g. r"C:\...\Machinability report.md" (set by caller via globals)

import System, math, Rhino
OUT_MD = globals().get('OUT_MD_OVERRIDE', OUT_MD)
import Rhino.Geometry as G
doc = __rhino_doc__
out = []

# Tool library and limits are in mm. Geometry is scaled to mm here, so inch documents work too;
# the report is always in mm, and TextDots are scaled back to document units.
TO_MM = Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem, Rhino.UnitSystem.Millimeters)

def get_brep(t):
    if t.get("gh_id"):
        import Grasshopper2.UI as UI
        g = UI.Editor.Instance.Canvas.Document
        o = list(g.Objects.Find(System.Guid(t["gh_id"])).Parameters.Outputs)[t.get("out", 0)]
        b = [p.Item for p in o.State.Data.Tree().AllPears][0].DuplicateBrep()
    else:
        b = doc.Objects.FindId(System.Guid(t["doc_id"])).Geometry.DuplicateBrep()
    if abs(TO_MM - 1.0) > 1e-9:
        b.Transform(G.Transform.Scale(G.Point3d.Origin, TO_MM))
    return b

def V(v): return G.Vector3d(*v)
def samples(f, n=24):
    """Points inside the TRIMMED face (render-mesh face centres, away from edges), with outward normals."""
    pts = []
    try:
        ms = G.Mesh.CreateFromBrep(f.DuplicateFace(False), G.MeshingParameters.FastRenderMesh)
        verts = [m.Faces.GetFaceCenter(i) for m in ms for i in range(m.Faces.Count)]
    except Exception:
        verts = []
    if verts:
        step = max(1, len(verts) // n)
        for q in verts[::step]:
            ok, u, v = f.ClosestPoint(q)
            if ok: pts.append((u, v, f.PointAt(u, v), onorm(f, u, v)))
    if not pts:
        u = f.Domain(0).Mid; v = f.Domain(1).Mid; pts.append((u, v, f.PointAt(u, v), onorm(f, u, v)))
    return pts

_CUR = {"brep": None}
def onorm(f, u, v):
    # outward normal of the solid, checked empirically (API orientation conventions vary)
    n = f.NormalAt(u, v); p = f.PointAt(u, v)
    b = _CUR["brep"]
    if b is not None:
        eps = 0.01
        out_ok = not b.IsPointInside(p + n * eps, 0.0005, False)
        in_ok = b.IsPointInside(p - n * eps, 0.0005, False)
        if not out_ok and not in_ok:
            n = -n
        elif not out_ok and in_ok is False:
            n = -n
    return n

def concavity(f, u, v, p, n):
    """+1 concave (internal), -1 convex, 0 flat; radius from principal curvature."""
    sc = f.CurvatureAt(u, v)
    kmax = max(abs(sc.Kappa(0)), abs(sc.Kappa(1))) if sc else 0
    if kmax < 1e-6: return 0, None
    du = f.Domain(0).Length * 0.01; dv = f.Domain(1).Length * 0.01
    s = 0
    for a, b in [(du, 0), (-du, 0), (0, dv), (0, -dv)]:
        q = f.PointAt(u + a, v + b); s += (q - p) * n
    return (1 if s > 0 else -1), 1.0 / kmax

def visible(brep, p, n, a, bb):
    start = p + n * 0.02
    end = start - a * (bb.Diagonal.Length * 2)
    ok, crvs, pts = G.Intersect.Intersection.CurveBrep(G.LineCurve(start, end), brep, 0.001)
    return not ((pts and len(pts) > 0) or (crvs and len(crvs) > 0))

def pick(kind, maxd):
    c = [d for d in LIBRARY[kind] if d <= maxd + 1e-9]
    return max(c) if c else None

report = []
dots = []
for t in TARGETS:
    b = get_brep(t)
    if b.SolidOrientation == G.BrepSolidOrientation.Inward: b.Flip()
    _CUR["brep"] = b
    bb = b.GetBoundingBox(True)
    ax = V(t["axis"]) if t.get("axis") else None
    length = None
    if ax:
        ax.Unitize(); length = abs((bb.Max - bb.Min) * ax)
    setups = dict((k, V(v)) for k, v in t["setups"].items())
    for k in setups: setups[k].Unitize()
    tops = {}
    for k, a in setups.items():
        tops[k] = max((-a) * G.Vector3d(c) for c in bb.GetCorners())
    feats = []
    for f in b.Faces:
        pts = samples(f)
        fb = f.GetBoundingBox(True)
        # --- as-extruded exclusion
        if ax:
            span = abs((fb.Max - fb.Min) * ax)
            par = all(abs(n * ax) < 1e-3 for (_, _, _, n) in pts)
            if par and span >= 0.95 * length:
                feats.append({"face": f.FaceIndex, "what": "as extruded", "skip": True}); continue
        # --- geometry class
        ok_c, cyl = f.TryGetCylinder(1e-4)
        ok_k, cone = f.TryGetCone(1e-4)
        planar = f.IsPlanar(1e-4)
        u, v, p, n = pts[len(pts) // 2]
        cv, r = (0, None) if planar else concavity(f, u, v, p, n)
        # --- best setup: visible at all samples, then shallowest
        cands = []
        for k, a in setups.items():
            if all(n_ * (-a) > -1e-3 for (_, _, _, n_) in pts) and all(visible(b, p_, n_, a, bb) for (_, _, p_, n_) in pts):
                depth = tops[k] - min((-a) * G.Vector3d(p_) for (_, _, p_, _) in pts)
                cands.append((k, depth, a))
        if ok_c:   # vertical radii are contoured from the setup whose axis they follow
            par = [c for c in cands if abs(cyl.Axis * c[2]) > 0.98]
            if par: cands = par
        best = min(cands, key=lambda c: c[1]) if cands else None
        reach_all = [c[0] for c in cands]
        feat = {"face": f.FaceIndex, "center": fb.Center, "setup": best[0] if best else None, "reach": reach_all,
                "depth": best[1] if best else None, "flags": [], "tool": None}
        a = best[2] if best else None
        is45 = a is not None and all(abs(abs(n_ * a) - math.sqrt(0.5)) < 0.03 for (_, _, _, n_) in pts)
        if is45:
            feat["what"] = "45deg chamfer" + (" plane" if planar else " corner blend"); feat["tool"] = ("chamfer", LIBRARY["chamfer"][0])
        elif planar:
            feat["what"] = "plane"
        elif ok_c:
            r = cyl.Radius
            axis_par = a is not None and abs(cyl.Axis * a) > 0.98
            closed = f.IsClosed(0) or f.IsClosed(1)
            if cv > 0:
                if axis_par and closed:
                    feat["what"] = "hole R%.2f (D%.2f)" % (r, 2 * r); feat["tool"] = ("drill", 2 * r)
                elif axis_par:
                    feat["what"] = "internal corner R%.2f" % r; feat["tool"] = ("flat", pick("flat", 2 * r))
                else:
                    feat["what"] = "internal fillet R%.2f (not on tool axis)" % r; feat["tool"] = ("ball", pick("ball", 2 * r))
            else:
                feat["what"] = "external radius R%.2f" % r
                if a is not None and not axis_par:
                    feat["what"] += " (edge round across tool axis)"; feat["tool"] = ("ball", None)
        elif ok_k:
            ang = cone.AngleInDegrees()
            if abs(ang - 45) < 1: feat["what"] = "45deg chamfer (cone)"; feat["tool"] = ("chamfer", LIBRARY["chamfer"][0])
            elif cv > 0: feat["what"] = "drill point %.0fdeg (from drill)" % (2 * ang); feat["tool"] = ("drill-point", None)
            else: feat["what"] = "external cone %.0fdeg" % ang; feat["tool"] = ("ball", None)
        else:
            wall_axes = [k for k, a_ in setups.items() if all(abs(n_ * a_) < 0.05 for (_, _, _, n_) in pts)]
            if wall_axes:
                # 2.5D profile wall: per concave sample, the radius and the shallowest setup that reaches it
                worst = None
                for (u_, v_, p_, n_) in samples(f, 400):
                    c_, r_ = concavity(f, u_, v_, p_, n_)
                    if c_ <= 0 or r_ is None: continue
                    reach = [(tops[k] - (-setups[k]) * G.Vector3d(p_), k) for k in wall_axes if visible(b, p_, n_, setups[k], bb)]
                    if not reach: continue
                    d_, k_ = min(reach)
                    key = (round(r_, 2), d_, k_)
                    if worst is None or r_ < worst[0] - 1e-6 or (abs(r_ - worst[0]) < 1e-6 and d_ > worst[1]): worst = key
                if worst:
                    feat["what"] = "2.5D profile wall, min internal R%.2f" % worst[0]
                    feat["tool"] = ("flat", pick("flat", 2 * worst[0])); feat["setup"] = worst[2]; feat["depth"] = worst[1]
                else:
                    feat["what"] = "2.5D profile wall (convex only)"
            elif cv > 0:
                feat["what"] = "3D concave surface, min R%.2f" % r; feat["tool"] = ("ball", pick("ball", 2 * r))
            else:
                feat["what"] = "3D convex surface (surfacing)"; feat["tool"] = ("ball", None)
        # --- flags
        if best is None: feat["flags"].append("UNDERCUT: not reachable from any setup")
        kd = feat["tool"]
        if kd and kd[0] in ("flat", "ball") and kd[1] is None and "internal" in feat["what"]:
            feat["flags"].append("NO STOCK TOOL small enough")
        if kd and kd[0] in ("flat", "ball", "drill") and isinstance(kd[1], (int, float)):
            if kd[0] in ("flat", "ball") and kd[1] < LIMITS["small_bit"]: feat["flags"].append("small bit D%.1f" % kd[1])
            if feat["depth"] is not None and kd[1] > 0:
                ratio = feat["depth"] / kd[1]
                feat["reach_ratio"] = ratio
                if ratio > LIMITS["reach_bad"]: feat["flags"].append("reach %.1fxD (bad)" % ratio)
                elif ratio > LIMITS["reach_warn"]: feat["flags"].append("reach %.1fxD" % ratio)
        feats.append(feat)
    # sharp concave edges parallel to a setup axis = square internal corner: needs EDM/broach
    for e in b.Edges:
        if e.Valence != G.EdgeAdjacency.Interior: continue
        tmid = e.Domain.Mid
        try: conc = e.ConcavityAt(tmid, 0.01)
        except: continue
        if conc == G.Concavity.Concave and e.IsLinear(0.01):
            d = e.PointAtEnd - e.PointAtStart; d.Unitize()
            if ax and abs(d * ax) > 0.99 and abs((e.PointAtEnd - e.PointAtStart) * ax) >= 0.95 * length: continue
            fs = [ff for ff in feats if ff.get("face") in (e.AdjacentFaces()[0], e.AdjacentFaces()[1])]
            if len(fs) < 2: continue
            common = set(fs[0].get("reach") or []) & set(fs[1].get("reach") or [])
            if not common: common = set(ff["setup"] for ff in fs if ff.get("setup"))
            # only a problem if EVERY setup that reaches both faces has the edge along its tool axis
            if common and all(abs(d * setups[k]) > 0.98 for k in common):
                feats.append({"face": "edge %d" % e.EdgeIndex, "center": e.PointAt(tmid), "what": "SHARP internal corner along tool axis",
                              "flags": ["needs EDM / broach (no rotating tool)"], "tool": None, "setup": None, "depth": None})
    # --- consolidate
    tools = {}
    for ft in feats:
        if ft.get("skip") or not ft.get("tool"): continue
        k, d = ft["tool"]
        if k in ("flat", "ball"):
            tools.setdefault(k, []).append(d if d is not None else 99)
        elif k == "drill": tools.setdefault("drill", set()).add(round(d, 2))
        elif k == "chamfer": tools["chamfer"] = {d}
        elif k == "drill-point": pass
    tset = []
    for k in ("flat", "ball"):
        if k in tools:
            dmin = min(tools[k]); dsel = pick(k, dmin) if dmin < 99 else (6 if k == "ball" else 6)
            tset.append("%s end mill D%s (covers %d features)" % (k, dsel, len(tools[k])))
    if "flat" not in tools:
        tset.append("flat end mill (general facing/contour, any size e.g. D6)")
    if "drill" in tools: tset += ["drill D%g" % d for d in sorted(tools["drill"])]
    n_under = len([f for f in feats if any("UNDERCUT" in x for x in f.get("flags", []))])
    if n_under: tset.append("+ T-slot/lollipop cutter or extra side setups for %d undercut faces" % n_under)
    if "chamfer" in tools: tset.append(list(tools["chamfer"])[0])
    report.append((t["name"], feats, tset))
    for ft in feats:
        if ft.get("flags") and ft.get("center") is not None:
            dots.append((t["name"], ft["center"], "; ".join(ft["flags"]) + " | " + ft["what"]))

# --- print
md = []
for name, feats, tset in report:
    md.append("## %s" % name)
    skipped = len([f for f in feats if f.get("skip")])
    if skipped: md.append("- %d faces as extruded (not machined)" % skipped)
    groups = {}
    for f in feats:
        if f.get("skip"): continue
        key = (f["what"], f.get("setup"), tuple(f.get("flags", [])), str(f.get("tool")))
        g_ = groups.setdefault(key, {"n": 0, "depth": 0})
        g_["n"] += 1; g_["depth"] = max(g_["depth"], f.get("depth") or 0)
    md.append("| feature | n | setup | max depth | tool | flags |")
    md.append("|---|---|---|---|---|---|")
    for (what, setup, flags, tool), g_ in sorted(groups.items(), key=lambda kv: (len(kv[0][2]) == 0, kv[0][0])):
        md.append("| %s | %d | %s | %.2f | %s | %s |" % (what, g_["n"], setup or "-", g_["depth"], tool, ", ".join(flags) or "ok"))
    md.append("**Minimum tool set:** " + "; ".join(tset))
    md.append("")
text = "\n".join(md)
print(text)
if OUT_MD:
    open(OUT_MD, "w").write(text)
if MARK_LAYER:
    li = doc.Layers.FindByFullPath(MARK_LAYER, -1)
    if li < 0 and dots:
        L = Rhino.DocObjects.Layer(); L.Name = MARK_LAYER; L.Color = System.Drawing.Color.Red; li = doc.Layers.Add(L)
    if li >= 0:
        for o in list(doc.Objects.FindByLayer(doc.Layers[li]) or []): doc.Objects.Delete(o.Id, True)
    for name, c, s in dots:
        a = Rhino.DocObjects.ObjectAttributes(); a.LayerIndex = li; a.Name = name
        doc.Objects.AddTextDot(G.TextDot(s[:120], G.Point3d(c.X / TO_MM, c.Y / TO_MM, c.Z / TO_MM)), a)
    doc.Views.Redraw()
