# Paste into Rhino MCP run_python (or Rhino's ScriptEditor) once per Rhino session, with the GH2 definition open.
# Every GH2 component's preview is Hidden; a component's preview turns on only while it is SELECTED on the canvas.
# The Hidden state is saved in the .ghz; this listener lives only in the current session, so re-run it after restarting.
# GH2 does not preview a Hidden component when it is selected (unlike GH1), hence the listener.
import System, sys, types
import Grasshopper2.UI as UI

g = UI.Editor.Instance.Canvas.Document
asm = [x for x in System.AppDomain.CurrentDomain.GetAssemblies() if x.GetName().Name == "Grasshopper2"][0]
OD = asm.GetType("Grasshopper2.Doc.ObjectDisplay")
VIS = System.Enum.Parse(OD, "Visible"); HID = System.Enum.Parse(OD, "Hidden")

old = sys.modules.get("__gh2_preview_on_select__")
if old is not None:
    try: old.doc.Objects.ObjectSelectionChanged -= old.handler
    except Exception: pass

def sync(sender, args):
    for o in g.Objects.ActiveObjects:
        try:
            want = VIS if str(o.Selection) == "Selected" else HID
            if str(o.Display) != str(want): o.Display = want
        except Exception:
            pass

g.Objects.ObjectSelectionChanged += sync
h = types.ModuleType("__gh2_preview_on_select__"); h.doc = g; h.handler = sync
sys.modules["__gh2_preview_on_select__"] = h
sync(None, None)
print("GH2 preview-on-select active for: %s" % g)
