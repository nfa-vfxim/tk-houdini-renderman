import json
import os

import hou


def render(node: hou.Node, on_farm: bool = False):
    import sgtk

    eng = sgtk.platform.current_engine()
    app = eng.apps["tk-houdini-renderman"]

    if not setup_aovs(node, False):
        return

    if on_farm:
        app.submit_to_farm(node, "rop")
    else:
        app.execute_render(node, "rop")


def copy_to_clipboard(node: hou.Node):
    import sgtk

    eng = sgtk.platform.current_engine()
    app = eng.apps["tk-houdini-renderman"]
    app.copy_to_clipboard(node.node("render"), "rop")

    hou.ui.displayMessage("Copied path to clipboard.")


def setup_aovs(node: hou.Node, show_notif: bool = True) -> bool:
    import sgtk

    eng = sgtk.platform.current_engine()
    app = eng.apps["tk-houdini-renderman"]
    return app.setup_aovs(node, show_notif)


def get_output_paths(node: hou.Node):
    import sgtk

    eng = sgtk.platform.current_engine()
    app = eng.apps["tk-houdini-renderman"]
    return app.get_output_paths(node)


def open_stats():
    rman = hou.pwd().node("render")
    file_path = rman.evalParm("ri_statistics_xmlfilename")

    if os.path.exists(file_path):
        for pane in hou.ui.curDesktop().panes():
            if not pane.isSplitMinimized():
                pane = pane.createTab(hou.paneTabType.HelpBrowser)
                pane.setUrl(file_path)
                return
    else:
        raise Exception("Statistics file doesn't exist (yet)!")
