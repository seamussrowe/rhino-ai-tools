# Paste into Rhino MCP run_python. Read-only analysis of a brep.
# Set the three values below. Units are reported in mm whatever the doc units are.
SRC_ID = "00000000-0000-0000-0000-000000000000"   # object guid
AXIS = "Z"            # main axis of the part: "X", "Y" or "Z"
SECTIONS = None       # list of positions (doc units) along AXIS, or None for 5 evenly spaced

import System, Rhino
import Rhino.Geometry as G
from collections import Counter
doc = __rhino_doc__
out = []
try:
    k = Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem, Rhino.UnitSystem.Millimeters)
    b = doc.Objects.FindId(System.Guid(SRC_ID)).Geometry
    if isinstance(b, G.Extrusion): b = b.ToBrep()
    bb = b.GetBoundingBox(True); d = bb.Diagonal
    out.append("doc %s units %s (x%.0f to mm)" % (doc.Path, doc.ModelUnitSystem, k))
    out.append("bbox mm min (%.3f, %.3f, %.3f) size %.3f x %.3f x %.3f" % (bb.Min.X*k, bb.Min.Y*k, bb.Min.Z*k, d.X*k, d.Y*k, d.Z*k))
    out.append("faces %d edges %d solid %s naked %d" % (b.Faces.Count, b.Edges.Count, b.IsSolid,
               len([e for e in b.Edges if e.Valence == G.EdgeAdjacency.Naked])))
    c = Counter()
    for f in b.Faces:
        if f.IsPlanar(1e-6):
            ok, p = f.TryGetPlane(1e-6); t = "plane n=(%.2f,%.2f,%.2f)" % (p.Normal.X, p.Normal.Y, p.Normal.Z)
        else:
            ok, cy = f.TryGetCylinder(1e-6)
            ok2, cn = f.TryGetCone(1e-6)
            if ok: t = "cyl r=%.3f ax=(%.0f,%.0f,%.0f)" % (cy.Radius*k, abs(cy.Axis.X), abs(cy.Axis.Y), abs(cy.Axis.Z))
            elif ok2: t = "cone %.1fdeg" % cn.AngleInDegrees()
            else: t = f.UnderlyingSurface().GetType().Name
        c[t] += 1
    for t, n in sorted(c.items()): out.append("  %3d x %s" % (n, t))
    ax = {"X": G.Vector3d.XAxis, "Y": G.Vector3d.YAxis, "Z": G.Vector3d.ZAxis}[AXIS]
    lo = {"X": bb.Min.X, "Y": bb.Min.Y, "Z": bb.Min.Z}[AXIS]; hi = {"X": bb.Max.X, "Y": bb.Max.Y, "Z": bb.Max.Z}[AXIS]
    secs = SECTIONS or [lo + (hi - lo) * t for t in (0.01, 0.25, 0.5, 0.75, 0.99)]
    for s in secs:
        o = G.Point3d(bb.Center);
        if AXIS == "X": o.X = s
        elif AXIS == "Y": o.Y = s
        else: o.Z = s
        ok, crvs, pts = G.Intersect.Intersection.BrepPlane(b, G.Plane(o, ax), doc.ModelAbsoluteTolerance * 0.1)
        loops = G.Curve.JoinCurves(crvs, doc.ModelAbsoluteTolerance) if crvs else []
        out.append("--- section %s=%.3f mm: %d loops" % (AXIS, s*k, len(loops)))
        for L in loops:
            lb = L.GetBoundingBox(True)
            segs = []
            for sg in L.DuplicateSegments():
                if sg.IsLinear(1e-6): segs.append("L%.3f" % (sg.GetLength()*k))
                else:
                    ok3, a = sg.TryGetArc(1e-6)
                    segs.append(("A r%.3f" % (a.Radius*k)) if ok3 else "C")
            out.append("  closed=%s len=%.3f bb (%.3f,%.3f,%.3f)-(%.3f,%.3f,%.3f): %s" % (
                L.IsClosed, L.GetLength()*k, lb.Min.X*k, lb.Min.Y*k, lb.Min.Z*k, lb.Max.X*k, lb.Max.Y*k, lb.Max.Z*k, " ".join(segs)))
except Exception:
    import traceback; out.append(traceback.format_exc())
print("\n".join(out))
