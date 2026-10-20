# Paste into Rhino MCP run_python (Rhino 9, GH2 canvas open). Helpers for things the g2_* MCP tools
# cannot do: constant input values, input expressions, graft/flatten, slider values, reading outputs.
# Edit the ACTIONS block at the bottom, run, then call the g2_solve_canvas MCP tool.
import System
import Rhino.Geometry as G
import Grasshopper2.UI as UI

gdoc = UI.Editor.Instance.Canvas.Document
out = []

def obj(gid): return gdoc.Objects.Find(System.Guid(gid))
def inp(gid, i): return list(obj(gid).Parameters.Inputs)[i]

def set_numbers(gid, i, *vals): inp(gid, i).Set(System.Array[System.Double]([float(v) for v in vals]))
def set_ints(gid, i, *vals): inp(gid, i).Set(System.Array[System.Int32]([int(v) for v in vals]))
def set_texts(gid, i, *vals): inp(gid, i).Set(System.Array[System.String](list(vals)))
def set_planes(gid, i, *planes): inp(gid, i).Set(System.Array[G.Plane](list(planes)))
def plane_z(z): return G.Plane(G.Point3d(0, 0, z), G.Vector3d.XAxis, G.Vector3d.YAxis)

def set_vector_fields(gid, i, *vecs):
    """For inputs typed 'field' (e.g. Plane From Axes X-Axis/Y-Axis)."""
    p = inp(gid, i)
    F = [m for m in p.GetType().GetMethods() if m.Name == "Set"][0].GetParameters()[0].ParameterType.GetElementType()
    imp = [m for m in F.GetMethods() if m.Name == "op_Implicit" and m.GetParameters()[0].ParameterType.Name == "Vector3d"][0]
    arr = System.Array.CreateInstance(F, len(vecs))
    for k, v in enumerate(vecs):
        arr[k] = imp.Invoke(None, System.Array[System.Object]([G.Vector3d(*v)]))
    p.Set(arr)

def expr(gid, i, text): inp(gid, i).ExpressionText = text          # e.g. "x/2", "-(x+1)"
def flatten(gid, i): p = inp(gid, i); p.Modifiers = p.Modifiers.WithFlatten()
def graft(gid, i): p = inp(gid, i); p.Modifiers = p.Modifiers.WithGrafting()

def set_slider(gid, value):
    s = obj(gid); s.InternalSlider.Values.Assign(System.Decimal(value)); s.Expire()

def sliders():
    return dict((str(o.UserName), str(o.InternalSlider.Values.Average))
                for o in gdoc.Objects.ActiveObjects if o.GetType().Name == "NumberSliderObject")

def wait_idle(timeout=60.0):
    """Solution.StartWait() can return while another (auto-started) solution is still running; outputs read then are
    stale or half-built. Poll until idle, and call solve_all() (two passes) before reading results."""
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = gdoc.Solution.State
        if st.CurrentlyRunning is None and str(st.Phase) == "Completed": return True
        time.sleep(0.05)
    return False

def solve_all():
    gdoc.Objects.ExpireAll(); gdoc.Solution.StartWait(); wait_idle()
    gdoc.Solution.StartWait(); wait_idle()

def output_items(gid, i=0):
    o = list(obj(gid).Parameters.Outputs)[i]
    d = o.State.Data
    return [] if d is None else [p.Item for p in d.Tree().AllPears]

try:
    # ---- ACTIONS (edit) -------------------------------------------------
    # set_numbers("<IntervalFromMiddle id>", 0, 0.0); expr("<id>", 1, "x/2")
    # set_texts("<EvaluateExpression id>", 0, "x-2*y")
    # set_planes("<Rectangle id>", 0, plane_z(1.0))
    # set_vector_fields("<PlaneFromAxes id>", 1, (-1,0,0), (0,1,0), (1,0,0), (0,-1,0))
    # flatten("<SolidDifference id>", 1); graft("<Orient id>", 2)
    # set_slider("<slider id>", 0.2)
    out.append(str(sliders()))
    # ---------------------------------------------------------------------
    solve_all()
except Exception:
    import traceback; out.append(traceback.format_exc())
print("\n".join(out))
