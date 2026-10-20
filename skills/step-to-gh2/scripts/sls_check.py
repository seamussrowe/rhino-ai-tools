# SLS / MJF printability check for a closed brep (exec in Rhino MCP run_python).
# Local wall thickness = distance along the inward normal from a surface sample to where the line LEAVES the solid
# (exact brep crossings, not mesh rays: mesh rays graze adjacent walls at concave corners and report false thin spots).
# Set before exec:  BREP (Rhino.Geometry.Brep); optional LIMITS, EDGE (mesh edge for sampling), ZONES [(name, BoundingBox)].
# Each thin cluster is classified: "supported" if material continues past >= 2 of its 4 in-plane sides,
# otherwise "UNSUPPORTED fin / free edge". Feather edges (thickness tapering to ~0) show up as tiny min values.
# Typical PA12 SLS limits (vendors differ, check yours): hard min ~0.6 (thinner may not form / over-thickens < 0.5),
# 0.8 recommended for supported walls & pins, ~1.0 for free-standing fins. Holes < 1.0-1.5 may close.
import Rhino, System, math
import Rhino.Geometry as G
LIMITS = globals().get("LIMITS", {"hard_min": 0.6, "supported": 0.8, "unsupported": 1.0})
EDGE = globals().get("EDGE", 0.3)
ZONES = globals().get("ZONES", [])
b = BREP
mp = G.MeshingParameters.QualityRenderMesh; mp.MaximumEdgeLength = EDGE; mp.MinimumEdgeLength = 0.01; mp.GridAmplification = 2
m = G.Mesh()
for x in G.Mesh.CreateFromBrep(b, mp): m.Append(x)
m.Weld(math.radians(22)); m.FaceNormals.ComputeFaceNormals(); m.Compact()

def thickness_at(c, n):
    """n = outward normal at surface point c. Returns distance to the exit crossing along -n."""
    start = c + n * 0.01
    L = G.LineCurve(start, c - n * 8.0)
    ok, cs, pts = G.Intersect.Intersection.CurveBrep(L, b, 0.0001)
    ts = sorted((start - q).Length for q in pts) if ok else []
    ts = [t for t in ts if t > 0.015]          # drop the entry crossing at c itself
    return (ts[0] - 0.01) if ts else 99.0

th = []
for i in range(m.Faces.Count):
    c = m.Faces.GetFaceCenter(i); n = G.Vector3d(m.FaceNormals[i]); n.Unitize()
    if b.IsPointInside(c + n * 0.02, 0.001, False): n.Reverse()
    th.append(thickness_at(c, n))

thin = set(i for i, t in enumerate(th) if t < LIMITS["unsupported"])
adj = {}
for e in range(m.TopologyEdges.Count):
    fs = list(m.TopologyEdges.GetConnectedFaces(e))
    for a in fs:
        for c2 in fs:
            if a != c2: adj.setdefault(a, set()).add(c2)
seen = set(); clusters = []
for f in thin:
    if f in seen: continue
    stack = [f]; cl = []
    while stack:
        k = stack.pop()
        if k in seen or k not in thin: continue
        seen.add(k); cl.append(k)
        stack.extend(j for j in adj.get(k, ()) if abs(th[j] - th[k]) < 0.08)
    clusters.append(cl)

def zone(p):
    for nm, bb in ZONES:
        if bb.Contains(p): return nm
    return "?"

rows = []
for cl in clusters:
    if len(cl) < 3: continue
    ts = sorted(th[i] for i in cl)
    bb = G.BoundingBox.Empty
    for i in cl: bb.Union(m.Faces.GetFaceCenter(i))
    tmin = ts[0]; t10 = ts[max(0, len(ts) // 10)]; tmed = ts[len(ts) // 2]
    ext = [bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y, bb.Max.Z - bb.Min.Z]
    axes = sorted(range(3), key=lambda k: -ext[k])[:2]
    attached = 0; ctr = bb.Center
    for ax in axes:
        for s in (-1, 1):
            p = G.Point3d(ctr); d = 0.4
            if ax == 0: p.X = (bb.Max.X + d) if s > 0 else (bb.Min.X - d)
            if ax == 1: p.Y = (bb.Max.Y + d) if s > 0 else (bb.Min.Y - d)
            if ax == 2: p.Z = (bb.Max.Z + d) if s > 0 else (bb.Min.Z - d)
            if any(b.IsPointInside(p + v, 0.001, False) for v in (G.Vector3d(0, 0, 0), G.Vector3d(0.3, 0, 0), G.Vector3d(-0.3, 0, 0),
                                                                 G.Vector3d(0, 0.3, 0), G.Vector3d(0, -0.3, 0), G.Vector3d(0, 0, 0.3), G.Vector3d(0, 0, -0.3))):
                attached += 1
    sup = attached >= 2
    lim = LIMITS["supported"] if sup else LIMITS["unsupported"]
    verdict = ("FAIL (< %.2f)" % LIMITS["hard_min"]) if tmed < LIMITS["hard_min"] - 1e-3 else \
              ("FEATHER EDGE (min %.2f)" % tmin if tmin < LIMITS["hard_min"] - 1e-3 else
               ("WARN (< %.2f)" % lim if tmed < lim - 1e-3 else "ok"))
    rows.append((tmed, tmin, len(cl), zone(ctr), "supported %d/4" % attached if sup else "UNSUPPORTED %d/4" % attached, verdict, bb))
rows.sort(key=lambda r: r[0])
out = ["SLS check: %d samples, limits %s" % (m.Faces.Count, LIMITS),
       "| zone | median t | min t | samples | support | verdict | bbox |", "|---|---|---|---|---|---|---|"]
for r in rows:
    bb = r[6]
    out.append("| %s | %.2f | %.2f | %d | %s | %s | (%.1f,%.1f,%.1f)-(%.1f,%.1f,%.1f) |" % (r[3], r[0], r[1], r[2], r[4], r[5],
               bb.Min.X, bb.Min.Y, bb.Min.Z, bb.Max.X, bb.Max.Y, bb.Max.Z))
SLS_MESH, SLS_THICK, SLS_ROWS = m, th, rows
print("\n".join(out))
