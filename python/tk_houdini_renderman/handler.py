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
import platform
import re

import hou
import sgtk

from .farm_dialog import FarmSubmission


class TkRenderManNodeHandler(object):
    def __init__(self, app):
        """Set global variables"""
        self.app = app
        self.sg = self.app.shotgun

    def submit_to_farm(self, node: hou.Node, network: str):
        """Start farm render

        Args:
            node (hou.Node): RenderMan node
            network (str): Network type
        """
        render_name = node.parm("name").eval()

        # Create directories
        render_paths = node.type().hdaModule().get_render_paths()
        for path in render_paths:
            self.__create_directory(path)

        # Determine basic variables for submission
        file_name = hou.hipFile.name()
        file_name = os.path.basename(file_name).split(".")[0] + " (%s)" % render_name

        # Determine framerange
        framerange_type = node.parm("trange").eval()
        if framerange_type > 0:
            start_frame = int(node.parm("f1").eval())
            end_frame = int(node.parm("f2").eval())
            framerange = str(start_frame) + "-" + str(end_frame)
        else:
            current_frame = int(hou.frame())
            framerange = str(current_frame) + "-" + str(current_frame)
        # TODO add increment parameter

        # Open node so it will work on the farm
        # even if the node is not installed
        node.allowEditingOfContents()

        global submission
        # Start submission panel
        submission = FarmSubmission(
            self.app, node, file_name, 50, framerange, render_paths, network=network
        )
        submission.show()

    def execute_render(self, node: hou.Node, network: str):
        """Start local render

        Args:
            node (hou.Node): RenderMan node
            network (str): Network type
        """
        # Create directories
        render_paths = node.type().hdaModule().get_render_paths()
        for path in render_paths:
            self.__create_directory(path)

        # Execute rendering
        if network == "lop":
            node.node("rop_usdrender").parm("execute").pressButton()
        else:
            node.node("denoise" if node.evalParm("denoise") else "render").parm(
                "execute"
            ).pressButton()

    def copy_to_clipboard(self, node: hou.Node, network: str = None):
        """Function to copy the path directly to the clipboard,
        currently only Windows is supported

        Args:
            node (hou.Node): RenderMan node to get path from
            network (str): Network type
        """

        # Function to copy the path directly to the clipboard,
        # currently only Windows is supported
        if platform.system() == "Windows":
            if network == "rop":
                parameter = "ri_display_0"
            else:
                parameter = "picture"

            render_path = node.parm(parameter).eval()
            render_path = os.path.dirname(render_path).replace("/", os.sep)
            copy_to_clipboard = 'echo|set /p="' + render_path.strip() + '"| clip'
            os.system(copy_to_clipboard)
        else:
            self.app.logger.debug(
                "Currently copying to clipboard is only supported on Windows."
            )

    @staticmethod
    def validate_node(node: hou.Node, network: str) -> bool:
        """This function will make sure all the parameters
        are filled in and setup correctly.

        Args:
            node (hou.Node): RenderMan node
            network (str): Network type
        """
        # First we'll check if there is a name
        render_name = node.parm("name").eval()
        if render_name == "":
            hou.ui.displayMessage(
                "Name is not defined, please set the name parameter before submitting.",
                severity=hou.severityType.Error,
            )
            return False
        elif not render_name.isalnum():
            hou.ui.displayMessage(
                "Name is not alphanumeric, please only use alphabet letters (a-z) and numbers (0-9).",
                severity=hou.severityType.Error,
            )
            return False

        # Check if camera exists
        elif not hou.node(node.evalParm("camera")):
            hou.ui.displayMessage(
                "Invalid camera path.", severity=hou.severityType.Error
            )
            return False

        else:
            # Make sure the node has an input to render
            if network == "lop":
                inputs = node.inputs()
                if len(inputs) <= 0:
                    hou.ui.displayMessage(
                        "Node doesn't have input, please connect this "
                        "ShotGrid RenderMan render node to "
                        "the stage to render.",
                        severity=hou.severityType.Error,
                    )
                    return False
                else:
                    return True
            else:
                return True

    def get_output_path(self, node: hou.Node, aov_name: str, network="rop") -> str:
        """Calculate render path for an aov

        Args:
            node (hou.Node): RenderMan node
            aov_name (str): AOV name
            network (str): Network type
        """
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

    def __create_directory(self, render_path: str):
        """Create directory to render to

        Args:
            render_path (str): Render path to create directory for
        """
        directory = os.path.dirname(render_path)

        # If directory doesn't exist, create it
        if not os.path.isdir(directory):
            os.makedirs(directory)
            self.app.logger.debug("Created directory %s." % directory)

    @staticmethod
    def __check_rop_filters(node: hou.Node):
        # Create list to appends filters to
        filters = []

        # We have two types of filters
        filter_types = ["displayfilter", "samplefilter"]

        # Iterate trough filters
        for filter_type in filter_types:
            # Get amount of filters for filter type
            filter_amount = node.parm("ri_%ss" % filter_type).eval()

            # Iterate trough amount of existing filters
            for filter_number in range(0, filter_amount):
                # Create parameter name to search for values
                parm_name = "ri_%s%s" % (filter_type, str(filter_number))

                # Get value of parameter
                filter_parameter = node.parm(parm_name).eval()

                # Add to list
                filters.append(filter_parameter)

        return filters

    @staticmethod
    def __check_lop_filters(node: hou.Node):
        # Amount of groups in the filter tab in the node
        tabs = range(0, 5)

        # Process display filters
        filters = []

        # Go trough every tab and check if the
        # parameters match the requirements
        for number in tabs:
            # We have two types, the display filters and sample filters.
            # Basically the same in terms of the way they
            # are created, so its just doing the same operation for both
            filter_types = ["displayfilter", "samplefilter"]

            for filter in filter_types:
                # Get the correct group name
                filter_type = filter + str(number)
                filter_name = hou.encode("ri:%s:name" % filter_type)

                # Get the ordered dropdown parameter value
                filter_name = node.parm(filter_name).eval()

                # Only add to the filters list if the ordered dropdown
                # parameters is anything else than "None"
                if filter_name != "None":
                    filter_type = {"group": filter_type, "value": filter_name}
                    filters.append(filter_type)

        # Return
        return filters

    def get_filters_output(self, node: hou.Node):
        if node.type().nameComponents()[2] == "sgtk_ris":
            filter_passes = self.__get_filters_rop_output(node)

        else:
            filter_passes = self.__get_filters_lop_output(node)

        return filter_passes

    def __get_filters_rop_output(self, node: hou.Node):
        filters = self.__check_rop_filters(node)
        filter_passes = []
        for node in filters:
            # Get node shader network
            node = hou.node(node)

            # Get node type
            node_type = node.nameComponents()[2]

            parameter = node.parm("filename")

            if parameter is None:
                continue

            # Build a dictionary per item, containing the name of the
            # filter and the path where the file is rendered to
            rendered_filter = {"name": node_type, "path": parameter.eval()}

            filter_passes.append(rendered_filter)

        return filters

    def __get_filters_lop_output(self, node: hou.Node):
        # This function will check every item in the filters group,
        # and return the file paths that are in there
        filters = self.__check_lop_filters(node)
        filter_passes = []
        for item in filters:
            # Look at our dictionary and get the keys/values supplied
            group = item.get("group")
            value = item.get("value")

            # Build the paramater name
            parameter_name = hou.encode("ri:" + group + ":" + value + ":filename")
            parameter = node.parm(parameter_name)

            # If there is no "filename" parameter, skip this one
            if parameter is None:
                continue

            # Build a dictionary per item, containing the name of the
            # filter and the path where the file is rendered to
            rendered_filter = {"name": value, "path": parameter.eval()}

            # Add the dictionary to the main filter_passes list
            filter_passes.append(rendered_filter)

        # Return the list containing every filter
        return filter_passes

    def get_published_status(self, node: hou.Node):
        """This function will check on ShotGrid if there is a publish
        with exactly the same name on the project. If
        there is a publish existing it will return a "True" value,
        otherwise a "False" value

        Args:
            node (hou.Node): RenderMan node
        """
        sg = self.sg

        # Define the regex to detect the Houdini "$F4" expressions
        # (or other numbers to define the padding)
        regex = r"[$][fF]\d"

        # Get the raw string from the picture parameter

        if node.type().nameComponents()[2] == "sgtk_ris":
            parameter = "ri_display_0"
        else:
            parameter = "picture"

        file_path = node.parm(parameter).rawValue()

        # Detect "$F4" in the file path, and return it
        frame_match = re.search(regex, file_path)
        frame_match = frame_match.group(0)

        # Detect the padding number specified
        padding_length = re.search("[0-9]", frame_match)
        padding_length = padding_length.group(0)

        # Replace $F4 with %04d format
        file_name = file_path.replace(frame_match, "%0" + str(padding_length) + "d")
        file_name = os.path.basename(file_name)

        # Get current project ID
        current_engine = sgtk.platform.current_engine()
        current_context = current_engine.context
        project_id = current_context.project["id"]

        # Create the filter to search on ShotGrid for publishes with the same file name
        filters = [
            ["project", "is", {"type": "Project", "id": project_id}],
            ["code", "is", file_name],
        ]

        # Search on ShotGrid
        published_file = sg.find_one("PublishedFile", filters)

        # If there is no publish, it will return a None value.
        # So set the variable is_published to "False"
        if published_file is None:
            is_published = False
        # If the value is not None, there is a publish with the
        # same name. So set the variable is_published to "True
        else:
            is_published = True

        return is_published
