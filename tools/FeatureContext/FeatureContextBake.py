#! python3
# Rhino command FeatureContextBake: GH2-native bake of chosen parts from the open Grasshopper 2 canvas onto
# "GH Bake::<part>", with provenance (source component id + metadata) so FeatureContext can trace picked faces back.
# Offered parts: named components with solid output that feed nothing downstream (or have ALL-CAPS names).
# Parts that were baked before are only replaced after you confirm.
import os, sys
import Rhino


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
    g = fc_core.gh2_doc()
    if g is None:
        print("FeatureContextBake: open the Grasshopper 2 definition first."); return
    names = fc_core.part_candidates(g)
    if not names:
        print("FeatureContextBake: no named components with solid output found. Give your final component a name "
              "(right-click > rename) and run again."); return
    chosen = Rhino.UI.Dialogs.ShowMultiListBox("FeatureContext bake", "Parts to bake onto '%s::<part>'" % fc_core.BAKE_ROOT, names)
    if not chosen: return
    gr = fc_core.Graph(g)
    again = [n for n in chosen if any(fc_core.baked_ids(doc, c.InstanceId) for c in gr.by_name(n))]
    replace = False
    if again:
        r = Rhino.UI.Dialogs.ShowMessage("Already baked:\n  " + "\n  ".join(again) + "\n\nReplace those bakes?",
                                         "FeatureContext bake", Rhino.UI.ShowMessageButton.YesNo, Rhino.UI.ShowMessageIcon.Question)
        replace = (r == Rhino.UI.ShowMessageResult.Yes)
    for line in fc_core.bake_parts(doc, list(chosen), replace=replace):
        print(line)


if __name__ == "__main__":
    main()
