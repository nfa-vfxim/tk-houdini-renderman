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

import hou
import sgtk
from hou import Node


class TkHoudiniRenderMan(sgtk.platform.Application):
    def init_app(self):
        """Initialize the app."""
        tk_houdini_usdrop = self.import_module("tk_houdini_renderman")
        self.handler = tk_houdini_usdrop.TkRenderManNodeHandler(self)

        types = ("string", "int", "float")
        failed = False
        for metadata in self.get_metadata_config():
            if metadata.get("key").lower() == "renderlightgroups":
                self.logger.error('Reserved metadata key "RenderLightGroups" was used.')
                failed = True
            if metadata.get("key").lower() == "postrendergroups":
                self.logger.error('Reserved metadata key "PostRenderGroups" was used.')
                failed = True
            if metadata.get("type") not in types:
                msg = f"Invalid metadata type for key '{metadata.get('key')}': '{metadata.get('type')}'"
                self.logger.error(msg)
                failed = True
        if failed:
            raise ValueError(
                "One or more errors occurred while validating the metadata config. Please check the config "
                "and try again."
            )

    def execute_render(self, node: hou.Node, network: str):
        """Start farm render

        Args:
            node (hou.Node): RenderMan node
            network (str): Network type
        """
        self.handler.execute_render(node, network)

    def submit_to_farm(self, node: hou.Node, network: str):
        """Start local render

        Args:
            node (hou.Node): RenderMan node
            network (str): Network type
        """
        self.handler.submit_to_farm(node, network)

    def copy_to_clipboard(self, node, network=None):
        """Copy render path to clipboard

        Args:
            node (hou.Node): RenderMan node
            network (str): Network type
        """
        self.handler.copy_to_clipboard(node, network)

    @staticmethod
    def get_all_renderman_nodes() -> tuple[Node]:
        """Get all nodes from node type sgtk_hdprman"""
        lop_nodes = hou.lopNodeTypeCategory().nodeType("sgtk_hdprman").instances()
        rop_nodes = hou.ropNodeTypeCategory().nodeType("sgtk_ris").instances()
        nodes = lop_nodes + rop_nodes
        return nodes

    def get_output_path(
        self, node: hou.Node, aov_name: str, network: str = "rop"
    ) -> str:
        """Calculate render path for an aov

        Args:
            node (hou.Node): RenderMan node
            aov_name (str): AOV name
            network (str): Network type
        """
        return self.handler.get_output_path(node, aov_name, network)

    def get_metadata_config(self):
        """Get Metadata config from ShotGrid"""
        return self.get_setting("render_metadata")

    def validate_node(self, node: hou.Node, network: str) -> str:
        """This function will make sure all the parameters
        are filled in and setup correctly.

        Args:
            node (hou.Node): RenderMan node
            network (str): Network type
        """
        return self.handler.validate_node(node, network)

    def get_work_template(self) -> str:
        """Get work file template from ShotGrid"""
        work_template = self.get_template("work_file_template")
        return work_template

    def get_publish_template(self) -> str:
        """Get render file template from ShotGrid"""
        publish_template = self.get_template("output_render_template")
        return publish_template

    @staticmethod
    def get_render_name(node) -> str:
        """Get render name from node

        Args:
            node (hou.Node): RenderMan node
        """
        name = node.parm("name").eval()
        return name
