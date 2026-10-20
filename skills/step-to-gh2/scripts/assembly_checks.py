# exec in run_python (Rhino 9, GH2 canvas open). Assembly verification helpers:
#   gh_out(guid) -> breps from a GH2 output; rd(doc_guid) -> doc geometry; ov(a,b) overlap volume;
#   min_gap(mesh, brep_or_mesh, maxd, filt) -> (d, p, q); fine_mesh(brep, edge);
#   sweep(movers, fixed, direction, smax, step) -> clashes while sliding parts in along an insertion direction;
#   sl(slider_guid, v) / val(guid) for slider sweeps; desc_b(name, brep) one-line summary.
# NOTE: Brep.CreateBooleanIntersection of two IDENTICAL solids returns empty - compare bbox + volume instead.
import clr; clr.AddReference("Grasshopper2")
import System, Rhino
import Rhino.Geometry as G
import Grasshopper2.UI as UI
gdoc = UI.Editor.Instance.Canvas.Document
rdoc = __rhino_doc__
def gh_out(gid, i=0):
    o = list(gdoc.Objects.Find(System.Guid(gid)).Parameters.Outputs)[i]
    d = o.State.Data
    res = []
    if d is None: return res
    for p in d.Tree().AllPears:
        it = p.Item
        if isinstance(it, G.Brep): res.append(it)
        else:
            try: res.append(it.ToBrep())
            except Exception:
                try: res.append(G.Brep.TryConvertBrep(it))
                except Exception: res.append(it)
    return res
def rd(gid): return rdoc.Objects.FindId(System.Guid(gid)).Geometry
def fine_mesh(b, edge=0.4):
    mp = G.MeshingParameters.QualityRenderMesh
    mp.MaximumEdgeLength = edge; mp.MinimumEdgeLength = 0.01; mp.GridAmplification = 2
    m = G.Mesh()
    for x in G.Mesh.CreateFromBrep(b, mp): m.Append(x)
    return m
def min_gap(src_mesh, dst_brep_or_mesh, maxd=6.0, filt=None):
    """Smallest vertex -> closest-point distance. filt(Point3d) -> bool limits the source vertices."""
    dm = dst_brep_or_mesh if isinstance(dst_brep_or_mesh, G.Mesh) else fine_mesh(dst_brep_or_mesh, 0.5)
    best = (1e9, None, None)
    for v in src_mesh.Vertices:
        p = G.Point3d(v)
        if filt and not filt(p): continue
        mp = dm.ClosestMeshPoint(p, maxd)
        if mp is None: continue
        d = p.DistanceTo(mp.Point)
        if d < best[0]: best = (d, p, mp.Point)
    return best
def sl(gid, v):
    s = gdoc.Objects.Find(System.Guid(gid)); s.InternalSlider.Values.Assign(System.Decimal(v)); s.Expire()
def val(gid, i=0):
    d = list(gdoc.Objects.Find(System.Guid(gid)).Parameters.Outputs)[i].State.Data
    return [str(p.Item)[:40] for p in d.Tree().AllPears] if d else None
def ov(a, b):
    ix = G.Brep.CreateBooleanIntersection(a, b, 0.001)
    return sum(abs(i.GetVolume()) for i in ix) if ix else 0.0
def desc_b(nm, b):
    bb = b.GetBoundingBox(True)
    return "%s solid=%s faces=%d vol=%.1f bbox (%.2f,%.2f,%.2f)-(%.2f,%.2f,%.2f)" % (nm, b.IsSolid, b.Faces.Count, b.GetVolume() if b.IsSolid else -1, bb.Min.X, bb.Min.Y, bb.Min.Z, bb.Max.X, bb.Max.Y, bb.Max.Z)
def sweep(movers, fixed, out=G.Vector3d(0, -1, 0), smax=30.0, step=0.5):
    """movers = [(name, brep)] in their FINAL position. Steps them back along `out` (the way they came in)
    and reports (distance, name, overlap volume) wherever they clash with `fixed` on the insertion path."""
    d = G.Vector3d(out); d.Unitize()
    bad = []
    s = step
    while s <= smax + 1e-9:
        t = G.Transform.Translation(d * s)
        for nm, part in movers:
            c = part.DuplicateBrep(); c.Transform(t)
            v = ov(c, fixed)
            if v > 1e-3: bad.append((s, nm, round(v, 3)))
        s += step
    return bad
