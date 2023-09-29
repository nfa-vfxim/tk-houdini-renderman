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

import os

import hou
import sgtk


class TkHoudiniRenderMan(sgtk.platform.Application):
    def init_app(self):
        """Initialize the app."""
        tk_houdini_usdrop = self.import_module("tk_houdini_renderman")
        self.handler = tk_houdini_usdrop.TkRenderManNodeHandler(self)

        types = ("string", "int", "float")
        failed = False
        for md in self.get_metadata_config():
            if md.get("key") == "groups":
                self.logger.error('Reserved metadata key "groups" was used.')
                failed = True
            if md.get("type") not in types:
                self.logger.error(
                    "Invalid metadata type for key {}: {}".format(
                        md.get("key"), md.get("type")
                    )
                )
                failed = True
        if failed:
            raise Exception(
                "One or more errors occurred while validating the metadata config. Please check the config "
                "and try again."
            )

    def execute_render(self, node, network):
        self.handler.execute_render(node, network)

    def submit_to_farm(self, node, network):
        self.handler.submit_to_farm(node, network)

    def copy_to_clipboard(self, node, network=None):
        self.handler.copy_to_clipboard(node, network)

    @staticmethod
    def get_all_renderman_nodes():
        # Get all nodes from node type sgtk_hdprman
        lop_nodes = hou.lopNodeTypeCategory().nodeType("sgtk_hdprman").instances()
        rop_nodes = hou.ropNodeTypeCategory().nodeType("sgtk_ris").instances()
        nodes = lop_nodes + rop_nodes
        return nodes

    def get_output_path(self, node, aov_name, network="rop"):
        current_filepath = hou.hipFile.path()

        work_template = self.get_template("work_file_template")
        render_template = self.get_template("output_render_template")

        resolution_x_field = "resolutionx"
        resolution_y_field = "resolutiony"

        resolution_x = 0
        resolution_y = 0

        evaluate_parm = True

        # Because RenderMan in the rop network uses different
        # parameter names, we need to change some bits
        if network == "rop":
            camera = node.parm("camera").eval()

            evaluate_parm = False
            resolution_x = hou.node(camera).parm("resx").eval()
            resolution_y = hou.node(camera).parm("resy").eval()

            if node.parm("override_camerares").eval():
                res_fraction = node.parm("res_fraction").eval()

                if res_fraction == "specific":
                    evaluate_parm = True
                    resolution_x_field = "res_overridex"
                    resolution_y_field = "res_overridey"

                else:
                    resolution_x = resolution_x * res_fraction
                    resolution_y = resolution_y * res_fraction

        # Set fields
        fields = work_template.get_fields(current_filepath)
        fields["SEQ"] = "FORMAT: $F"
        fields["output"] = node.parm("name").eval()
        fields["aov_name"] = aov_name
        if evaluate_parm is True:
            fields["width"] = node.parm(resolution_x_field).eval()
            fields["height"] = node.parm(resolution_y_field).eval()

        else:
            fields["width"] = resolution_x
            fields["height"] = resolution_y

        return render_template.apply_fields(fields).replace(os.sep, "/")

    def get_metadata_config(self):
        return self.get_setting("render_metadata")

    def validate_node(self, node, network):
        return self.handler.validate_node(node, network)

    def get_work_template(self):
        work_template = self.get_template("work_file_template")
        return work_template

    def get_publish_template(self):
        publish_template = self.get_template("output_render_template")
        return publish_template

    @staticmethod
    def get_render_name(node):
        name = node.parm("name").eval()
        return name
