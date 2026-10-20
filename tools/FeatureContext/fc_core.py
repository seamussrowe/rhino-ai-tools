# FeatureContext core (Rhino 9 / RhinoCode Python 3, GH2). Used by FeatureContext.py, FeatureContextBake.py
# and by Claude Code over the Rhino MCP (exec this file, then call the functions).
#   bake_parts(doc, names)        GH2-native bake + provenance metadata, onto "GH Bake::<name>"
#   build_packet(doc, picks, note) picked faces/edges -> JSON packet + clipboard summary (+ highlighted PNG)
#   trace_face(brep_face, key)     walks the GH2 brep chain back to the component that CREATED the face
# GH2 bake stores in attr.UserDictionary: G2ProcName / G2ProcGuid (source component), G2Item, and our
# metadata embedded as "GH2:fc.*". We also write fc.* Attribute User Text so it shows in Rhino's Properties.
import os, json, datetime
import System
import Rhino
import Rhino.Geometry as G

try:
    ROOT = os.path.dirname(os.path.abspath(__file__))          # this tool's folder, wherever it was copied to
except NameError:
    ROOT = os.getcwd()
BAKE_ROOT = "GH Bake"


def _config():
    """Optional fc_config.json next to this file, e.g. {"packets": "<folder>\\\\my packets"}."""
    try:
        with open(os.path.join(ROOT, "fc_config.json")) as fh: return json.load(fh)
    except Exception:
        return {}


def packets_dir(doc=None):
    """Where packets go: fc_config.json "packets", else "FeatureContext packets" next to the open .3dm,
    else "packets" in the tool folder (unsaved document)."""
    p = _config().get("packets")
    if not p and doc is not None and doc.Path:
        p = os.path.join(os.path.dirname(doc.Path), "FeatureContext packets")
    if not p:
        p = os.path.join(ROOT, "packets")
    if not os.path.isdir(p): os.makedirs(p)
    return p
TOL = 0.01          # mm, face coincidence
NTOL = 0.995        # |cos| for normal agreement
MAX_DEPTH = 80
RIGID = ("Move",)   # component types whose output is a translated copy of the input


# ---------------------------------------------------------------- GH2 canvas
def gh2_doc():
    try:
        import Grasshopper2.UI as UI
        return UI.Editor.Instance.Canvas.Document
    except Exception:
        return None


def gh2_path(g):
    try:
        return str(g.File.Path) if g.File.HasPath else ""
    except Exception:
        return ""


def _brep(x):
    if isinstance(x, G.Brep): return x
    if isinstance(x, G.Extrusion): return x.ToBrep()
    return None


def param_pears(p):
    try:
        d = p.State.Data
        return [] if d is None else list(d.Tree().AllPears)
    except Exception:
        return []


def param_breps(p):
    return [b for b in (_brep(x.Item) for x in param_pears(p)) if b is not None]


class Graph(object):
    """Wire/owner maps of the active GH2 document (same approach as step-to-gh2/scripts/gh2_describe.py)."""
    def __init__(self, g):
        self.g = g
        self.objs, self.pown, self.srcs = {}, {}, {}
        for o in g.Objects.ActiveObjects:
            self.objs[str(o.InstanceId)] = o
            try:
                for p in list(o.Parameters.Inputs) + list(o.Parameters.Outputs):
                    self.pown[str(p.InstanceId)] = (o, p)
            except Exception:
                self.pown[str(o.InstanceId)] = (o, None)
        for w in g.Objects.AllWires:
            self.srcs.setdefault(str(w.Target), []).append(str(w.Source))

    def find(self, gid):
        return self.objs.get(str(gid))

    def by_name(self, name):
        return [o for o in self.objs.values() if str(o.UserName or "") == name]

    def inputs(self, o):
        try: return list(o.Parameters.Inputs)
        except Exception: return []

    def outputs(self, o):
        try: return list(o.Parameters.Outputs)
        except Exception: return []

    def sources(self, p):
        """[(owner, param-or-None)] wired into input param p."""
        return [self.pown[s] for s in self.srcs.get(str(p.InstanceId), []) if s in self.pown]


def cname(o):
    return str(o.UserName or "") or o.GetType().Name


def pname(p):
    try: return str(p.Nomen.Name)
    except Exception: return "?"


def _pdata(p):
    try:
        d = p.PersistentDataWeak
        if d is None: return None
        return ";".join(str(x.Item) for x in list(d.AllPears)[:6])
    except Exception:
        return None


def source_value(o, p):
    """Readable value of a source object (slider, toggle, panel...)."""
    try:
        return float(str(o.InternalSlider.Values.Average))
    except Exception:
        pass
    items = param_pears(p) if p is not None else []
    if not items:
        try: items = list(o.State.Data.Tree().AllPears)
        except Exception: items = []
    return ";".join(str(x.Item) for x in items[:6]) or None


def is_source(gr, o):
    return o.GetType().Name == "NumberSliderObject" or not gr.inputs(o)


# ---------------------------------------------------------------- face tracing
def face_samples(face):
    """Interior points + outward normals of a (trimmed) brep face. The grid is refined until it lands
    inside the trims (thin rings on a large untrimmed plane need ~60x60)."""
    du, dv = face.Domain(0), face.Domain(1)
    for n in (7, 19, 61, 151):
        pts = []
        for i in range(n):
            for j in range(n):
                u = du.ParameterAt((i + 0.5) / n); v = dv.ParameterAt((j + 0.5) / n)
                if face.IsPointOnFace(u, v) == G.PointFaceRelation.Interior:
                    pts.append((face.PointAt(u, v), face.NormalAt(u, v)))
        if len(pts) >= 4: break
    if len(pts) > 9:
        step = len(pts) / 9.0
        pts = [pts[int(k * step)] for k in range(9)]
    return pts


def match_face(brep, samples, xf=None):
    """Index of the face of `brep` that contains every sample (normals parallel), or None.
    Returns (face_index, reversed)."""
    bb = brep.GetBoundingBox(False); bb.Inflate(TOL * 10)
    hits = {}
    for p, n in samples:
        q = G.Point3d(p); m = G.Vector3d(n)
        if xf is not None: q.Transform(xf); m.Transform(xf)
        if not bb.Contains(q): return None
        r = brep.ClosestPoint(q, TOL * 2)
        if not r[0]: return None
        ci, s, t = r[2], r[3], r[4]
        if ci.ComponentIndexType != Rhino.Geometry.ComponentIndexType.BrepFace: return None
        f = brep.Faces[ci.Index]
        d = f.NormalAt(s, t) * m
        if abs(d) < NTOL: return None
        key = (ci.Index, d < 0)
        hits[key] = hits.get(key, 0) + 1
    if not hits: return None
    return max(hits, key=hits.get)


def _move_xfs(out_b, in_b):
    """Candidate transforms output->input for rigid components (Move etc.): identity, then bbox-centre shift."""
    xfs = [None]
    if out_b is not None and in_b is not None and out_b.Faces.Count == in_b.Faces.Count:
        c0 = out_b.GetBoundingBox(True).Center; c1 = in_b.GetBoundingBox(True).Center
        if c0.DistanceTo(c1) > TOL:
            xfs.append(G.Transform.Translation(c1 - c0))
    return xfs


def trace_face(gr, comp, item, samples):
    """Walk upstream from `comp` output item `item` until no input brep contains the face.
    Returns list of steps; the last one is the component that created the face."""
    steps = []
    cur_comp, cur_item, cur_samples = comp, item, samples
    seen = set()
    for _ in range(MAX_DEPTH):
        outs = gr.outputs(cur_comp)
        cur_brep = None
        if outs:
            bs = param_breps(outs[0])
            cur_brep = bs[cur_item] if 0 <= cur_item < len(bs) else None
        nxt = None
        # pass 1: exact position in any input. pass 2 (Move-type components only): bbox-centre shift.
        # Never shift elsewhere - mirrored twins (Keeper notch +X / -X) would match each other.
        rigid = cur_comp.GetType().Name in RIGID
        for shifted in ((False, True) if rigid else (False,)):
            for p in gr.inputs(cur_comp):
                flat = 0        # item index across all sources wired into p (Move pairs input n -> output n)
                for so, sp in gr.sources(p):
                    bs = param_breps(sp) if sp is not None else []
                    base, flat = flat, flat + len(bs)
                    if sp is None or str(sp.InstanceId) in seen: continue
                    for j, b in enumerate(bs):
                        if shifted and base + j != cur_item: continue
                        xfs = _move_xfs(cur_brep, b)[1:] if shifted else [None]
                        for xf in xfs:
                            mf = match_face(b, cur_samples, xf)
                            if mf is not None:
                                nxt = (so, sp, j, xf, mf, pname(p)); break
                        if nxt: break
                    if nxt: break
                if nxt: break
            if nxt: break
        if nxt is None:
            break
        so, sp, j, xf, mf, via = nxt
        seen.add(str(sp.InstanceId))
        if xf is not None:
            new = []
            for pt, n in cur_samples:
                q = G.Point3d(pt); m = G.Vector3d(n); q.Transform(xf); m.Transform(xf); new.append((q, m))
            cur_samples = new
        steps.append({"component": cname(so), "type": so.GetType().Name, "id": str(so.InstanceId),
                      "item": j, "face_index": mf[0], "reversed": bool(mf[1]),
                      "into": "%s.%s" % (cname(cur_comp), via)})
        cur_comp, cur_item = so, j
    return steps


def drivers(gr, comp, max_depth=12, nest=1):
    """Per input of `comp`: constant, or the sliders/values feeding it (not crossing into other breps).
    For geometry inputs, `nest` levels of the feeding component's own sliders are listed too."""
    res = []
    for p in gr.inputs(comp):
        e = {"input": pname(p)}
        try:
            ex = p.ExpressionText
            if ex: e["expression"] = str(ex)
        except Exception:
            pass
        srcs = gr.sources(p)
        if not srcs:
            c = _pdata(p)
            if c is not None: e["constant"] = c
            res.append(e); continue
        sl, via, geo, seen = [], [], [], set()
        stack = [(o, sp, 0) for o, sp in srcs]
        while stack:
            o, sp, dep = stack.pop()
            k = str(o.InstanceId)
            if k in seen: continue
            seen.add(k)
            if is_source(gr, o):
                sl.append({"name": cname(o), "value": source_value(o, sp), "id": k}); continue
            if sp is not None and param_breps(sp):   # geometry from another feature: don't walk through it
                gi = {"component": cname(o), "type": o.GetType().Name}
                if nest > 0:
                    ss = list(dict((s["id"], s) for dd in drivers(gr, o, max_depth, nest - 1)
                                   for s in dd.get("sources", [])).values())
                    if ss: gi["sliders"] = ss
                geo.append(gi); continue
            via.append(cname(o))
            if dep < max_depth:
                for ip in gr.inputs(o):
                    for so, ssp in gr.sources(ip):
                        stack.append((so, ssp, dep + 1))
        if sl: e["sources"] = sl
        if geo: e["geometry_from"] = geo
        if via: e["via"] = via[:8]
        res.append(e)
    return res


# ---------------------------------------------------------------- bake
def _layer(doc, path):
    idx = doc.Layers.FindByFullPath(path, -1)
    if idx >= 0: return idx
    parent = System.Guid.Empty
    for k, part in enumerate(path.split("::")):
        full = "::".join(path.split("::")[:k + 1])
        i = doc.Layers.FindByFullPath(full, -1)
        if i < 0:
            L = Rhino.DocObjects.Layer(); L.Name = part; L.ParentLayerId = parent
            i = doc.Layers.Add(L)
        parent = doc.Layers[i].Id
    return i


def baked_ids(doc, comp_id):
    res = []
    es = Rhino.DocObjects.ObjectEnumeratorSettings()   # doc.Objects alone skips hidden/locked layers
    es.HiddenObjects = True; es.LockedObjects = True; es.IncludeLights = False
    for o in doc.Objects.GetObjectList(es):
        ud = o.Attributes.UserDictionary      # GH2 stores G2ProcGuid as a Guid, not a string
        if ud.ContainsKey("G2ProcGuid") and str(ud["G2ProcGuid"]) == str(comp_id):
            res.append(o.Id)
    return res


def bake_parts(doc, names, replace=False, layer_root=BAKE_ROOT, layer_path=None, obj_name=None, replace_ids=(),
               extra_copy=False, tags=None):
    """GH2-native bake of output 0 of each named component. Returns report lines.
    replace=False skips parts that already have baked objects from that component.
    layer_path / obj_name override the "GH Bake::<part>" layer and the object name (e.g. to bake in place of an
    older, untagged bake); replace_ids are deleted after a successful bake.
    extra_copy=True bakes another copy (e.g. an A/B test variant on its own layer) without checking or touching
    earlier bakes of the same component. tags: extra fc.* user text, e.g. {"fc.variant": "A trim lip"}."""
    from Grasshopper2.Bake import BakeContext, MetaPattern, UserPattern
    from Grasshopper2.Data import Pear
    from Grasshopper2.Data.Meta import MetaName, MetaData
    from System.Runtime.CompilerServices import RuntimeHelpers
    g = gh2_doc(); gr = Graph(g); ghz = gh2_path(g)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    rep = []
    for name in names:
        comps = gr.by_name(name)
        if len(comps) != 1:
            rep.append("SKIP %s: %d components with that name" % (name, len(comps))); continue
        c = comps[0]
        old = [] if extra_copy else baked_ids(doc, c.InstanceId)
        if old and not replace:
            rep.append("SKIP %s: already baked (%d objects); pass replace=True" % (name, len(old))); continue
        for oid in old: doc.Objects.Delete(oid, True)
        att = doc.CreateDefaultAttributes()
        att.LayerIndex = _layer(doc, layer_path or "%s::%s" % (layer_root, name))
        ctx = BakeContext(name, c.InstanceId, doc, att, RuntimeHelpers.GetUninitializedObject(UserPattern),
                          MetaPattern(True, True))
        # .ghz FILE NAME only: full paths would leak user names into shared .3dm files
        fc = {"fc.feature": name, "fc.component": str(c.InstanceId), "fc.ghz": os.path.basename(ghz), "fc.baked_at": stamp}
        fc.update(tags or {})
        n = 0
        for i, pr in enumerate(param_pears(gr.outputs(c)[0])):
            meta = MetaData.Empty
            for k, v in list(fc.items()) + [("fc.item", str(i))]:
                meta = meta.Add(MetaName.Parse(k), v)
            for sid in ctx.BakeObject(Pear.WithMeta(pr, meta)):
                o = doc.Objects.FindId(System.Guid(sid))
                a = o.Attributes.Duplicate()
                base = obj_name or name
                a.Name = base if i == 0 else "%s [%d]" % (base, i)
                for k, v in list(fc.items()) + [("fc.item", str(i))]:
                    a.SetUserString(k, v)
                doc.Objects.ModifyAttributes(o, a, True)
                n += 1
        if n:
            for oid in replace_ids: doc.Objects.Delete(System.Guid(str(oid)), True)
        rep.append("BAKED %s: %d object(s) -> %s" % (name, n, doc.Layers[att.LayerIndex].FullPath))
    doc.Views.Redraw()
    return rep


def part_candidates(g=None):
    """Bakeable parts: named components with solid (brep) output that either feed nothing downstream (end results)
    or have ALL-CAPS names (a convention for marking finished parts mid-graph)."""
    gr = Graph(g or gh2_doc()); res = []
    used = set()
    for w in gr.g.Objects.AllWires: used.add(str(w.Source))
    for o in gr.objs.values():
        n = str(o.UserName or "")
        if not n: continue
        outs = gr.outputs(o)
        if not outs or not param_breps(outs[0]): continue
        terminal = str(outs[0].InstanceId) not in used
        caps = n.split(" (")[0].upper() == n.split(" (")[0] and any(c.isalpha() for c in n)
        if terminal or caps: res.append(n)
    return sorted(set(res))


# ---------------------------------------------------------------- pick -> packet
def _v(p): return [round(p.X, 3), round(p.Y, 3), round(p.Z, 3)]


def _bake_info(obj):
    a = obj.Attributes; ud = a.UserDictionary
    info = {}
    for k in ud.Keys:
        if k.startswith("G2") or k.startswith("GH2:"):
            info[k] = str(ud[k])
    for k in a.GetUserStrings().AllKeys:
        info[k] = a.GetUserString(k)
    return info


def _surface(face):
    d = {"area": None}
    try: d["area"] = round(G.AreaMassProperties.Compute(face.DuplicateFace(False)).Area, 3)
    except Exception: pass
    s = face.UnderlyingSurface()
    ok, pl = face.TryGetPlane(0.001)
    if ok: d["type"] = "plane"; return d
    ok, cy = face.TryGetCylinder(0.001)
    if ok: d.update(type="cylinder", radius=round(cy.Radius, 3), axis=_v(cy.Axis)); return d
    ok, co = face.TryGetCone(0.001)
    if ok: d.update(type="cone", half_angle_deg=round(Rhino.RhinoMath.ToDegrees(co.AngleInRadians()), 3)); return d
    ok, sp = face.TryGetSphere(0.001)
    if ok: d.update(type="sphere", radius=round(sp.Radius, 3)); return d
    ok, to = face.TryGetTorus(0.001)
    if ok: d.update(type="torus", major=round(to.MajorRadius, 3), minor=round(to.MinorRadius, 3)); return d
    d["type"] = s.GetType().Name
    return d


def _face_record(brep, fi):
    f = brep.Faces[fi]
    smp = face_samples(f)
    if smp:
        ok, u, v = f.ClosestPoint(smp[len(smp) // 2][0])
    else:
        u, v = f.Domain(0).Mid, f.Domain(1).Mid
    rec = {"face_index": fi, "point_on_face": _v(f.PointAt(u, v)), "normal": _v(f.NormalAt(u, v))}
    rec.update(_surface(f))
    bb = f.DuplicateFace(False).GetBoundingBox(True)
    rec["bbox"] = [_v(bb.Min), _v(bb.Max)]
    return rec, smp


def _trace(gr, info, smp):
    gid = info.get("G2ProcGuid") or info.get("fc.component")
    if gr is None or not gid: return {"status": "no GH2 provenance on this object"}
    comp = gr.find(gid)
    if comp is None: return {"status": "source component %s not on the open GH2 canvas" % gid}
    item = int(info.get("fc.item", info.get("G2Item", "0")) or 0)
    off = info.get("fc.offset")             # "dx,dy,dz": baked copy moved for display (e.g. side-by-side A/B)
    if off:
        v = G.Vector3d(*[float(x) for x in off.split(",")])
        smp = [(p - v, n) for p, n in smp]
    outs = gr.outputs(comp); bs = param_breps(outs[0]) if outs else []
    if not (0 <= item < len(bs)) or match_face(bs[item], smp) is None:
        hint = (" This is a '%s' bake: set the variant slider to it first." % info["fc.variant"]) if info.get("fc.variant") else ""
        return {"status": "STALE: the baked face is not in the component's current output (canvas changed "
                          "since bake?). Re-bake with FeatureContextBake." + hint, "part": cname(comp)}
    steps = trace_face(gr, comp, item, smp)
    origin = gr.find(steps[-1]["id"]) if steps else comp
    named = [gr.find(s["id"]) for s in reversed(steps) if gr.find(s["id"]).UserName] or [comp]
    feat = named[0]
    t = {"status": "ok", "part": cname(comp),
         "chain": [cname(comp)] + [s["component"] for s in steps],
         "steps": steps,
         "created_by": {"component": cname(origin), "type": origin.GetType().Name, "id": str(origin.InstanceId)},
         "drivers": drivers(gr, origin)}
    if feat is not origin:      # origin is unnamed: also give the nearest named feature downstream of it
        t["feature"] = {"component": cname(feat), "type": feat.GetType().Name, "id": str(feat.InstanceId),
                        "drivers": drivers(gr, feat)}
    # The creator is often a shared extrusion of many 2D profiles: follow the extruded item back to the component
    # that drew its profile (through item-for-item steps like Move / Simplify Curve).
    item_o = steps[-1]["item"] if steps else item
    src = profile_source(gr, origin, item_o)
    if src is not None and src is not origin:
        t["profile_from"] = {"component": cname(src), "type": src.GetType().Name, "id": str(src.InstanceId),
                             "drivers": drivers(gr, src)}
    grp = group_of(gr, src if src is not None else origin)   # canvas groups are usually the most readable feature names
    if grp: t["group"] = grp
    return t


PASS_ITEMWISE = ("Move", "Orient", "SimplifyCurve", "FilletEntireCurve", "Rotate", "Mirror")


def _xy_key(x):
    """Plan-view (XY) bounding box of a curve/circle/region/brep item, rounded, or None."""
    try:
        if hasattr(x, "ToCurve") and not isinstance(x, G.GeometryBase):
            x = x.ToCurve(0)                               # GH2 Region
        if isinstance(x, G.Circle): x = x.ToNurbsCurve()
        b = _brep(x)
        bb = (b if b is not None else x).GetBoundingBox(True)
        return (round(bb.Min.X, 4), round(bb.Min.Y, 4), round(bb.Max.X, 4), round(bb.Max.Y, 4))
    except Exception:
        return None


def profile_source(gr, comp, item, max_hops=8):
    """For a component fed by 2D profiles (e.g. one Extrude of many deck cut-outs), find the upstream component that
    drew the profile of output item `item`. Items are matched by plan-view bounding box, NOT by position: GH2 does not
    keep wire order when it merges several wires into one input."""
    try: key = _xy_key(param_pears(gr.outputs(comp)[0])[item].Item)
    except Exception: return None
    if key is None: return None
    cur = comp
    for _ in range(max_hops):
        nxt = None
        for p in gr.inputs(cur):
            for so, sp in gr.sources(p):
                if sp is None: continue
                prs = param_pears(sp)
                if not prs or isinstance(prs[0].Item, (int, float, str, bool)): continue
                for pr in prs:
                    k2 = _xy_key(pr.Item)
                    if k2 is not None and all(abs(a - b) < 1e-3 for a, b in zip(k2, key)):
                        nxt = so; break
                if nxt: break
            if nxt: break
        if nxt is None: return cur if cur is not comp else None
        cur = nxt
        if cur.GetType().Name not in PASS_ITEMWISE:
            return cur
    return cur


def group_of(gr, o):
    """UserName of the GH2 canvas group containing object o (first match), or None."""
    try:
        oid = str(o.InstanceId)
        for g in gr.g.Objects.Groups:
            if any(str(x) == oid for x in g.ContentIds):
                return str(g.UserName or "") or None
    except Exception:
        pass
    return None


def build_packet(doc, picks, note, capture_view=None):
    """picks: list of (RhinoObject, ComponentIndex or None). Writes <packets>/<stamp>.json + latest.json (+ PNG),
    see packets_dir(). Returns (packet dict, summary text)."""
    g = gh2_doc(); gr = Graph(g) if g is not None else None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    PACKETS = packets_dir(doc)
    pk = {"created": stamp, "note": note, "rhino_doc": doc.Path, "units": str(doc.ModelUnitSystem),
          "gh2_file": gh2_path(g) if g is not None else None, "picks": []}
    for obj, ci in picks:
        info = _bake_info(obj)
        rec = {"object_id": str(obj.Id), "object_name": obj.Attributes.Name,
               "layer": doc.Layers[obj.Attributes.LayerIndex].FullPath, "provenance": info}
        if info.get("fc.ghz") and pk["gh2_file"] and                 os.path.basename(info["fc.ghz"]).lower() != os.path.basename(pk["gh2_file"]).lower():
            rec["warning"] = "baked from a different .ghz than the one open"
        brep = _brep(obj.Geometry)
        typ = ci.ComponentIndexType if ci is not None else None
        if brep is not None and typ == G.ComponentIndexType.BrepFace:
            fr, smp = _face_record(brep, ci.Index)
            rec["kind"] = "face"; rec.update(fr); rec["trace"] = _trace(gr, info, smp)
        elif brep is not None and typ == G.ComponentIndexType.BrepEdge:
            e = brep.Edges[ci.Index]
            rec.update(kind="edge", edge_index=ci.Index, length=round(e.GetLength(), 3),
                       start=_v(e.PointAtStart), end=_v(e.PointAtEnd))
            ok, arc = e.TryGetArc(0.001)
            if ok: rec.update(arc_radius=round(arc.Radius, 3), arc_angle_deg=round(arc.AngleDegrees, 2))
            rec["adjacent_faces"] = []
            for fi in e.AdjacentFaces():
                fr, smp = _face_record(brep, fi)
                fr["trace"] = _trace(gr, info, smp)
                rec["adjacent_faces"].append(fr)
        else:
            bb = obj.Geometry.GetBoundingBox(True)
            rec.update(kind="object", bbox=[_v(bb.Min), _v(bb.Max)])
            gid = info.get("G2ProcGuid")
            comp = gr.find(gid) if (gr and gid) else None
            if comp is not None:
                rec["part"] = cname(comp)
        pk["picks"].append(rec)
    if capture_view is not None:
        try:
            bmp = capture_view.CaptureToBitmap(System.Drawing.Size(1200, 800))
            img = os.path.join(PACKETS, stamp + ".png")
            bmp.Save(img, System.Drawing.Imaging.ImageFormat.Png)
            pk["image"] = img
        except Exception as ex:
            pk["image_error"] = repr(ex)
    txt = summary(pk)
    pk["summary"] = txt
    s = json.dumps(pk, indent=2)
    for fn in (stamp + ".json", "latest.json"):
        with open(os.path.join(PACKETS, fn), "w") as fh: fh.write(s)
    pk["packet_path"] = os.path.join(PACKETS, stamp + ".json")
    return pk, txt


def _trace_lines(t, ind="  "):
    L = []
    if t.get("status") != "ok":
        L.append(ind + "Trace: " + t.get("status", "?")); return L
    cb = t["created_by"]
    if t.get("group"):
        L.append(ind + 'Feature group: "%s"' % t["group"])
    L.append(ind + 'Created by GH2 component "%s" (%s)' % (cb["component"], cb["type"]))
    if "profile_from" in t:
        L.append(ind + 'Profile drawn by "%s" (%s)' % (t["profile_from"]["component"], t["profile_from"]["type"]))
    # The nearest named feature only helps when it isn't just the finished part itself
    feat = t.get("feature") if t.get("feature", {}).get("component") != t.get("part") else None
    if feat:
        L.append(ind + 'Nearest named feature: "%s" (%s)' % (feat["component"], feat["type"]))
    L.append(ind + "Chain: " + " <- ".join(t["chain"]))
    if "profile_from" not in t:
        L += _driver_lines(cb["component"], t["drivers"], ind)
    else:                                # shared extrusion: its profile input lists every profile, so only show the rest
        rest = [d for d in t["drivers"] if d["input"].lower() not in ("profile", "curve", "shape")]
        if rest: L += _driver_lines(cb["component"] + " (depth / span of the cut)", rest, ind)
    if feat:
        L += _driver_lines(feat["component"], feat["drivers"], ind)
    if "profile_from" in t:
        L += _driver_lines(t["profile_from"]["component"], t["profile_from"]["drivers"], ind)
    return L


def _driver_lines(name, drv, ind):
    L = [ind + "Inputs of %s:" % name]
    for d in drv:
        bits = []
        if "constant" in d: bits.append("= %s" % d["constant"])
        if "expression" in d: bits.append("expr %s" % d["expression"])
        for s in d.get("sources", []): bits.append('%s = %s' % (s["name"], s["value"]))
        for gfrom in d.get("geometry_from", []):
            sl = ", ".join("%s = %s" % (s["name"], s["value"]) for s in gfrom.get("sliders", []))
            bits.append('geometry from "%s" (%s)%s' % (gfrom["component"], gfrom["type"], (" driven by " + sl) if sl else ""))
        L.append(ind + "  %s: %s" % (d["input"], "; ".join(bits) or "(wired)"))
    return L


def summary(pk):
    u = {"Millimeters": "mm", "Inches": "in", "Centimeters": "cm", "Meters": "m"}.get(pk.get("units", ""), pk.get("units", ""))
    L = ["[Feature context]"]
    if pk.get("gh2_file"): L.append("GH2 file: " + os.path.basename(pk["gh2_file"]) + ("   (units: %s)" % u if u else ""))
    for i, r in enumerate(pk["picks"]):
        part = r.get("provenance", {}).get("fc.feature") or r.get("provenance", {}).get("G2ProcName") or r["object_name"]
        if r["kind"] == "face":
            L.append("Pick %d: face %d of part \"%s\" - %s, area %s %s2, at %s, normal %s%s" % (
                i + 1, r["face_index"], part, r.get("type"), r.get("area"), u, r["point_on_face"], r["normal"],
                (", radius %s" % r["radius"]) if "radius" in r else ""))
            L += _trace_lines(r["trace"])
        elif r["kind"] == "edge":
            L.append("Pick %d: edge %d of part \"%s\" - length %s%s" % (
                i + 1, r["edge_index"], part, r["length"], (", arc R%s" % r["arc_radius"]) if "arc_radius" in r else ""))
            for f in r["adjacent_faces"]:
                L.append("  adjacent face %d (%s):" % (f["face_index"], f.get("type")))
                L += _trace_lines(f["trace"], "    ")
        else:
            L.append("Pick %d: whole object \"%s\" (layer %s)" % (i + 1, part, r["layer"]))
        if r.get("warning"): L.append("  WARNING: " + r["warning"])
    L.append("Request: " + (pk.get("note") or "(none)"))
    if pk.get("image"): L.append("Screenshot: " + pk["image"])
    return "\n".join(L)


def to_clipboard(text):
    try:
        import Eto.Forms as ef
        ef.Clipboard().Text = text; return True
    except Exception:
        try:
            import clr; clr.AddReference("System.Windows.Forms")
            import System.Windows.Forms as wf
            wf.Clipboard.SetText(text); return True
        except Exception:
            return False
