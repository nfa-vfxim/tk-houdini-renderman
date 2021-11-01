# MIT License

# Copyright (c) 2021 Netherlands Film Academy

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sgtk
import hou


class TkHoudiniRenderMan(sgtk.platform.Application):
    def init_app(self):
        """Initialize the app."""
        tk_houdini_usdrop = self.import_module("tk_houdini_renderman")
        self.handler = tk_houdini_usdrop.TkRenderManNodeHandler(self)

    def execute_render(self, node):
        self.handler.execute_render(node)

    def submit_to_farm(self, node):
        self.handler.submit_to_farm(node)

    def copy_to_clipboard(self, node):
        self.handler.copy_to_clipboard(node)

    @staticmethod
    def get_all_renderman_nodes():
        # Get all nodes from node type sgtk_hdprman
        nodes = hou.lopNodeTypeCategory().nodeType("sgtk_hdprman").instances()
        return nodes

    @staticmethod
    def get_output_path(node):
        output_path = node.parm("picture").eval()
        return output_path

    def get_work_template(self):
        work_template = self.get_template("work_file_template")
        return work_template

    def get_publish_template(self):
        publish_template = self.get_template("output_render_template")
        return publish_template

    @staticmethod
    def get_render_name(node):
        name = node.parm('name').eval()
        return name