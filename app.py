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
        for metadata in self.get_setting("render_metadata"):
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

    def execute_render(self, node: hou.Node):
        """Start farm render

        Args:
            node (hou.Node): RenderMan node
        """
        self.handler.execute_render(node)

    def submit_to_farm(self, node: hou.Node):
        """Start local render

        Args:
            node (hou.Node): RenderMan node
        """
        self.handler.submit_to_farm(node)

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
        rop_nodes = hou.ropNodeTypeCategory().nodeType("sgtk_ris").instances()
        lop_nodes = hou.lopNodeTypeCategory().nodeType("sgtk_ris").instances()
        return rop_nodes + lop_nodes

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

    def validate_node(self, node: hou.Node, network: str) -> str:
        """This function will make sure all the parameters
        are filled in and setup correctly.

        Args:
            node (hou.Node): RenderMan node
            network (str): Network type
        """
        return self.handler.validate_node(node, network)

    def setup_light_groups(self, node: hou.Node) -> bool:
        """Setup light groups on the light nodes

        Args:
            node (hou.Node): RenderMan node
        """
        return self.handler.setup_light_groups(node)

    def setup_aovs(self, node: hou.Node, show_notification: bool = True) -> bool:
        """Setup outputs on the RenderMan node with correct aovs

        Args:
            node (hou.Node): RenderMan node
            show_notification (bool): Show notification when successfully set up AOVs
        """
        return self.handler.setup_aovs(node, show_notification)

    def get_output_paths(self, node: hou.Node) -> list[str]:
        """Get output paths for the RenderMan node

        Args:
            node (hou.Node): RenderMan node
        """
        return self.handler.get_output_paths(node)

    def get_output_range(self, node: hou.Node) -> list[int]:
        """Get output frame range for the RenderMan node

        Args:
            node (hou.Node): RenderMan node
        """
        return self.handler.get_output_range(node)

    def get_work_template(self) -> str:
        """Get work file template from ShotGrid"""
        return self.get_template("work_file_template")

    def get_render_template(self) -> str:
        """Get render file template from ShotGrid"""
        return self.get_template("output_render_template")

    @staticmethod
    def get_render_name(node) -> str:
        """Get render name from node

        Args:
            node (hou.Node): RenderMan node
        """
        name = node.parm("name").eval()
        return name

    def get_published_status(self, node: hou.Node) -> bool:
        """This function will check on ShotGrid if there is a publish
        with exactly the same name on the project. If
        there is a publish existing it will return a "True" value,
        otherwise a "False" value

        Args:
            node (hou.Node): RenderMan node
        """
        return self.handler.get_published_status(node)
