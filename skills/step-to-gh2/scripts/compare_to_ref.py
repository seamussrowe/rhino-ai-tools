# Paste into Rhino MCP run_python after g2_solve_canvas. Compares a GH2 output brep with the reference.
# Distances are in document units (the < 0.01 mm target is 0.0004 in an inch document).
GH_COMPONENT_ID = "00000000-0000-0000-0000-000000000000"  # e.g. the final Solid Difference
GH_OUTPUT_INDEX = 0
REF_ID = "00000000-0000-0000-0000-000000000000"           # reference brep in the Rhino doc

import System
import Rhino.Geometry as G
import Grasshopper2.UI as UI
out = []
try:
    gdoc = UI.Editor.Instance.Canvas.Document
    o = list(gdoc.Objects.Find(System.Guid(GH_COMPONENT_ID)).Parameters.Outputs)[GH_OUTPUT_INDEX]
    res = [p.Item for p in o.State.Data.Tree().AllPears]
    out.append("GH output items: %d" % len(res))
    gh = res[0]
    ref = __rhino_doc__.Objects.FindId(System.Guid(REF_ID)).Geometry
    naked = len([e for e in ref.Edges if e.Valence == G.EdgeAdjacency.Naked])
    out.append("GH  faces %d solid %s valid %s" % (gh.Faces.Count, gh.IsSolid, gh.IsValid))
    out.append("REF faces %d solid %s naked edges %d" % (ref.Faces.Count, ref.IsSolid, naked))
    a1 = G.AreaMassProperties.Compute(gh).Area; a2 = G.AreaMassProperties.Compute(ref).Area
    out.append("area GH %.4f REF %.4f diff %.4f%%" % (a1, a2, 100 * (a1 - a2) / a2))
    if gh.IsSolid: out.append("volume GH %.4f" % G.VolumeMassProperties.Compute(gh).Volume)
    mp = G.MeshingParameters.QualityRenderMesh
    def dev(src, tgt):
        mx = 0.0; tot = 0.0; n = 0; worst = None
        for m in G.Mesh.CreateFromBrep(src, mp):
            for v in m.Vertices:
                p = G.Point3d(v); d = p.DistanceTo(tgt.ClosestPoint(p)); n += 1; tot += d
                if d > mx: mx = d; worst = p
        return mx, tot / max(n, 1), n, worst
    out.append("GH->REF max %.5f mean %.6f n=%d worst %s" % dev(gh, ref))
    out.append("REF->GH max %.5f mean %.6f n=%d worst %s" % dev(ref, gh))
    # Mesh VERTICES of a hole through a thin plate sit only on its top/bottom rims, i.e. on the uncut plate faces of
    # the other brep, so a missing or misplaced through-feature can still read ~0. Also sample render-mesh FACE CENTRES,
    # projected back onto the true surface (removes chord sag), both ways.
    def dev_faces(src, tgt):
        mp2 = G.MeshingParameters.QualityRenderMesh; mp2.MaximumEdgeLength = 0.05 * max(1.0, src.GetBoundingBox(True).Diagonal.Length / 100.0)
        mx = 0.0; n = 0; worst = None
        for m in G.Mesh.CreateFromBrep(src, mp2):
            for i in range(m.Faces.Count):
                p = src.ClosestPoint(m.Faces.GetFaceCenter(i)); d = p.DistanceTo(tgt.ClosestPoint(p)); n += 1
                if d > mx: mx = d; worst = p
        return mx, n, worst
    out.append("GH->REF surface samples max %.5f n=%d worst %s" % dev_faces(gh, ref))
    out.append("REF->GH surface samples max %.5f n=%d worst %s" % dev_faces(ref, gh))
except Exception:
    import traceback; out.append(traceback.format_exc())
print("\n".join(out))
