#! python3
# Rhino command FeatureContext: pick faces/edges (or whole objects) on GH2-baked parts and type what you want changed.
# Writes a packet (<time>.json + latest.json + a highlighted screenshot) to "FeatureContext packets" next to the open
# .3dm (see fc_core.packets_dir) and copies a text summary to the clipboard. Paste it into your AI chat (Rhino AI panel,
# Claude, ...) so it knows exactly which Grasshopper 2 component and sliders made that face.
# Faces are traced back through the open GH2 canvas to the component that created them (see fc_core.trace_face).
import os, sys
import Rhino
import Rhino.Geometry as G
from Rhino.DocObjects import ObjectType


def _tool_folder():
    try:
        return os.path.dirname(os.path.abspath(__file__))       # the folder this script was run from
    except NameError:
        return os.environ.get("FEATURECONTEXT_DIR", os.getcwd())


FOLDER = _tool_folder()
if FOLDER not in sys.path: sys.path.insert(0, FOLDER)
import importlib, fc_core
importlib.reload(fc_core)


def main():
    doc = Rhino.RhinoDoc.ActiveDoc
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("Pick faces / edges of a baked part (Ctrl+Shift+click), Enter when done")
    go.GeometryFilter = ObjectType.Surface | ObjectType.EdgeFilter | ObjectType.Brep | ObjectType.Extrusion
    go.SubObjectSelect = True
    go.EnablePreSelect(True, True)
    go.GetMultiple(1, 0)
    if go.CommandResult() != Rhino.Commands.Result.Success:
        return go.CommandResult()
    picks = []
    for i in range(go.ObjectCount):
        r = go.Object(i)
        ci = r.GeometryComponentIndex
        picks.append((r.Object(), ci if ci.ComponentIndexType != G.ComponentIndexType.InvalidType else None))

    gs = Rhino.Input.Custom.GetString()
    gs.SetCommandPrompt("What should change here? (Enter = no note)")
    gs.AcceptNothing(True)
    gs.GetLiteralString()
    note = gs.StringResult() if gs.CommandResult() == Rhino.Commands.Result.Success else ""

    # keep the picked faces/edges highlighted for the screenshot
    doc.Objects.UnselectAll()
    for obj, ci in picks:
        if ci is not None: obj.SelectSubObject(ci, True, True, True)
        else: obj.Select(True)
    doc.Views.Redraw()
    pk, txt = fc_core.build_packet(doc, picks, note, capture_view=doc.Views.ActiveView)

    ok = fc_core.to_clipboard(txt)
    print(txt)
    print("Packet: %s%s" % (pk["packet_path"], "  (summary copied to clipboard)" if ok else ""))
    return Rhino.Commands.Result.Success


if __name__ == "__main__":
    main()
