# exec in run_python (GH2 canvas open). desc(guid) prints a component's inputs (sources, constants, expressions)
# and outputs (targets); byname(UserName) -> guids. Param names: p.Nomen.Name; wires: doc.Objects.AllWires (param ids).
import clr; clr.AddReference("Grasshopper2")
import System
import Grasshopper2.UI as UI
g = UI.Editor.Instance.Canvas.Document
objs = {}
pown = {}
for o in g.Objects.ActiveObjects:
    objs[str(o.InstanceId)] = o
    try:
        for p in list(o.Parameters.Inputs) + list(o.Parameters.Outputs):
            pown[str(p.InstanceId)] = (o, p)
    except Exception:
        pown[str(o.InstanceId)] = (o, None)
srcs = {}; tgts = {}
for w in g.Objects.AllWires:
    s, t = str(w.Source), str(w.Target)
    srcs.setdefault(t, []).append(s); tgts.setdefault(s, []).append(t)
def pname(p):
    try: return str(p.Nomen.Name)
    except Exception: return '?'
def label(pid):
    o, p = pown.get(pid, (None, None))
    if o is None: return pid
    n = o.UserName or o.GetType().Name
    if p is None or p is o: return n
    return "%s.%s" % (n, pname(p))
def pdata(p):
    try:
        d = p.PersistentDataWeak
        if d is None: return ""
        items = [str(x.Item) for x in d.AllPears] if hasattr(d,'AllPears') else [str(d)]
        return "const=" + ";".join(items[:6])
    except Exception as e: return ""
def desc(oid):
    o = objs[oid]; L = ["## %s  <%s> %s" % (o.UserName, o.GetType().Name, oid)]
    try:
        for i, p in enumerate(o.Parameters.Inputs):
            s = [label(x) for x in srcs.get(str(p.InstanceId), [])]
            mods = ''
            try: mods = str(p.Modifiers)
            except Exception: pass
            ex = None
            try: ex = p.ExpressionText
            except Exception: pass
            L.append("  in%d %s <- %s %s %s %s" % (i, pname(p), s, ("expr=" + ex) if ex else "", pdata(p) if not s else "", mods if mods and mods!='None' else ''))
        for i, p in enumerate(o.Parameters.Outputs):
            L.append("  out%d %s -> %s" % (i, pname(p), [label(x) for x in tgts.get(str(p.InstanceId), [])]))
    except Exception as e:
        L.append("  (%r) -> %s" % (e, [label(x) for x in tgts.get(oid, [])]))
    return "\n".join(L)
def byname(n):
    return [k for k, o in objs.items() if o.UserName == n]
