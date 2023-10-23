# MIT License
import json

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
        render_paths = self.get_output_paths(node)
        for path in render_paths:
            self.__create_directory(path)

        # Determine basic variables for submission
        file_name = hou.hipFile.name()
        file_name = os.path.basename(file_name).split(".")[0] + " (%s)" % render_name

        # Determine framerange
        framerange = self.get_output_range(node)
        framerange = f"{framerange[0]}-{framerange[1]}"

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
        render_paths = self.get_output_paths(node)
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

    def setup_aovs(self, node: hou.Node, show_notif: bool = True) -> bool:
        rman = node.node("render")

        if not self.validate_node(node, "rop"):
            return False

        denoise = node.node("denoise")
        use_denoise = node.evalParm("denoise")

        beauty = node.evalParm("aovBeauty")
        deep = node.evalParm("aovDeep")

        aovs = node.parmsInFolder(("AOVs",))

        crypto = list(
            filter(lambda parm: "Crypto" in parm.name() and parm.eval() == 1, aovs)
        )

        def make_lightgroups(use_node):
            light_group = node.parm(use_node.name().replace("Use", ""))
            return light_group.parmTemplate().label(), light_group.eval()

        lightgroups = list(
            map(
                make_lightgroups,
                list(
                    filter(
                        lambda parm: "LGUse" in parm.name() and parm.eval() == 1, aovs
                    )
                ),
            )
        )

        tee_count = node.evalParm("tees")

        shading = node.parmsInFolder(("AOVs", "Shading"))
        shading = list(
            filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, shading)
        )

        lighting = node.parmsInFolder(("AOVs", "Lighting"))
        lighting = list(
            filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, lighting)
        )

        utility = node.parmsInFolder(("AOVs", "Utility"))
        utility = list(
            filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, utility)
        )

        # SET FILE COUNT
        file_count = beauty + deep
        if len(shading):
            file_count += 1
        if len(lighting) or len(lightgroups):
            file_count += 1
        if len(utility) or tee_count:
            file_count += 1

        rman.parm("ri_displays").set(0)
        rman.parm("ri_displays").set(file_count)

        # SETUP FILES

        # Autocrop
        autocrop = node.evalParm("autocrop")
        if autocrop:
            for i in range(file_count):
                rman.parm("ri_autocrop_" + str(i)).set("true")

        # Denoise
        denoise.parm("output").set(
            os.path.dirname(self.get_output_path(node, "denoise"))
        )

        # Statistics
        rman.parm("ri_statistics_xmlfilename").set(
            self.get_output_path(node, "stats")[:-3] + "xml"
        )

        # TODO add custom aovs
        # 0: Beauty 16 bit DWAa
        # 1: Shading 16 bit DWAa
        # 2: Lighting 16 bit DWAa
        # 3: Utility 32 bit ZIP
        # 4: Deep
        i = 0
        if beauty:
            rman.parm("ri_display_" + str(i)).set(self.get_output_path(node, "beauty"))

            rman.parm("ri_asrgba_" + str(i)).set(not use_denoise)
            rman.parm("ri_exrcompression_" + str(i)).set("dwaa")
            rman.parm("ri_denoiseon_" + str(i)).set(use_denoise)

            i += 1
        if len(shading):
            shading = list(map(lambda p: p.name().replace("aov", ""), shading))

            rman.parm("ri_display_" + str(i)).set(self.get_output_path(node, "beauty"))
            rman.parm("ri_asrgba_" + str(i)).set(0)
            rman.parm("ri_exrcompression_" + str(i)).set("dwaa")
            rman.parm("ri_denoiseon_" + str(i)).set(use_denoise)

            rman.parm("ri_quickaov_Ci_" + str(i)).set(0)
            rman.parm("ri_quickaov_a_" + str(i)).set(0)

            rman.parm("ri_quickaov_albedo_" + str(i)).set("Albedo" in shading)
            rman.parm("ri_quickaov_emissive_" + str(i)).set("Emissive" in shading)
            rman.parm("ri_quickaov_directDiffuse_" + str(i)).set("Diffuse" in shading)
            rman.parm("ri_quickaov_indirectDiffuse_" + str(i)).set("Diffuse" in shading)
            rman.parm("ri_quickaov_directDiffuseUnoccluded_" + str(i)).set(
                "DiffuseU" in shading
            )
            rman.parm("ri_quickaov_indirectDiffuseUnoccluded_" + str(i)).set(
                "DiffuseU" in shading
            )
            rman.parm("ri_quickaov_directSpecular_" + str(i)).set("Specular" in shading)
            rman.parm("ri_quickaov_indirectSpecular_" + str(i)).set(
                "Specular" in shading
            )
            rman.parm("ri_quickaov_directSpecularUnoccluded_" + str(i)).set(
                "SpecularU" in shading
            )
            rman.parm("ri_quickaov_indirectSpecularUnoccluded_" + str(i)).set(
                "SpecularU" in shading
            )
            rman.parm("ri_quickaov_subsurface_" + str(i)).set("Subsurface" in shading)

            rman.parm("ri_quickaov_directDiffuseLobe_" + str(i)).set(
                "LobeDiffuse" in shading
            )
            rman.parm("ri_quickaov_indirectDiffuseLobe_" + str(i)).set(
                "LobeDiffuse" in shading
            )
            rman.parm("ri_quickaov_directSpecularPrimaryLobe_" + str(i)).set(
                "LobeSpecularPrimary" in shading
            )
            rman.parm("ri_quickaov_indirectSpecularPrimaryLobe_" + str(i)).set(
                "LobeSpecularPrimary" in shading
            )
            rman.parm("ri_quickaov_directSpecularRoughLobe_" + str(i)).set(
                "LobeSpecularRough" in shading
            )
            rman.parm("ri_quickaov_indirectSpecularRoughLobe_" + str(i)).set(
                "LobeSpecularRough" in shading
            )
            rman.parm("ri_quickaov_directSpecularClearcoatLobe_" + str(i)).set(
                "LobeSpecularClearcoat" in shading
            )
            rman.parm("ri_quickaov_indirectSpecularClearcoatLobe_" + str(i)).set(
                "LobeSpecularClearcoat" in shading
            )
            rman.parm("ri_quickaov_directSpecularIridescenceLobe_" + str(i)).set(
                "LobeSpecularIridescence" in shading
            )
            rman.parm("ri_quickaov_indirectSpecularIridescenceLobe_" + str(i)).set(
                "LobeSpecularIridescence" in shading
            )
            rman.parm("ri_quickaov_directSpecularFuzzLobe_" + str(i)).set(
                "LobeSpecularFuzz" in shading
            )
            rman.parm("ri_quickaov_indirectSpecularFuzzLobe_" + str(i)).set(
                "LobeSpecularFuzz" in shading
            )
            rman.parm("ri_quickaov_directSpecularGlassLobe_" + str(i)).set(
                "LobeSpecularGlass" in shading
            )
            rman.parm("ri_quickaov_indirectSpecularGlassLobe_" + str(i)).set(
                "LobeSpecularGlass" in shading
            )
            rman.parm("ri_quickaov_subsurfaceLobe_" + str(i)).set(
                "LobeSubsurface" in shading
            )
            rman.parm("ri_quickaov_transmissiveSingleScatterLobe_" + str(i)).set(
                "LobeTransmissiveSingleScatter" in shading
            )
            rman.parm("ri_quickaov_transmissiveGlassLobe_" + str(i)).set(
                "LobeTransmissiveGlass" in shading
            )

            i += 1
        if len(lighting) or len(lightgroups):
            lighting = list(map(lambda p: p.name().replace("aov", ""), lighting))

            rman.parm("ri_display_" + str(i)).set(
                self.get_output_path(node, "lighting")
            )
            rman.parm("ri_asrgba_" + str(i)).set(0)
            rman.parm("ri_exrcompression_" + str(i)).set("dwaa")
            rman.parm("ri_denoiseon_" + str(i)).set(use_denoise)

            rman.parm("ri_quickaov_Ci_" + str(i)).set(0)
            rman.parm("ri_quickaov_a_" + str(i)).set(0)

            rman.parm("ri_quickaov_occluded_" + str(i)).set(
                "ShadowOccluded" in lighting
            )
            rman.parm("ri_quickaov_unoccluded_" + str(i)).set(
                "ShadowUnoccluded" in lighting
            )
            rman.parm("ri_quickaov_shadow_" + str(i)).set("Shadow" in lighting)

            # Lightgroups
            rman.parm("ri_numcustomaovs_" + str(i)).set(len(lightgroups))

            for j, group in enumerate(lightgroups):
                rman.parm("ri_aovvariable_" + str(i) + "_" + str(j)).set(group[0])
                rman.parm("ri_aovsource_" + str(i) + "_" + str(j)).set(
                    f"color lpe:C.*<L.'{group[1]}'>"
                )

            i += 1
        if len(utility) or tee_count:
            utility = list(map(lambda p: p.name().replace("aov", ""), utility))

            rman.parm("ri_display_" + str(i)).set(self.get_output_path(node, "utility"))
            rman.parm("ri_asrgba_" + str(i)).set(0)
            rman.parm("ri_exrpixeltype_" + str(i)).set("float")

            rman.parm("ri_quickaov_Ci_" + str(i)).set(0)
            rman.parm("ri_quickaov_a_" + str(i)).set(0)

            rman.parm("ri_quickaov_curvature_" + str(i)).set("Pworld" in utility)
            rman.parm("ri_quickaov_dPdtime_" + str(i)).set("DTime" in utility)
            rman.parm("ri_quickaov_dPcameradtime_" + str(i)).set(
                "CameraDTime" in utility
            )

            rman.parm("ri_quickaov___Pworld_" + str(i)).set("Pworld" in utility)
            rman.parm("ri_quickaov___Nworld_" + str(i)).set("Nworld" in utility)
            rman.parm("ri_quickaov___depth_" + str(i)).set("Depth" in utility)
            rman.parm("ri_quickaov___st_" + str(i)).set("ST" in utility)
            rman.parm("ri_quickaov___Pref_" + str(i)).set("Pref" in utility)
            rman.parm("ri_quickaov___Nref_" + str(i)).set("Nref" in utility)
            rman.parm("ri_quickaov___WPref_" + str(i)).set("WPref" in utility)
            rman.parm("ri_quickaov___WNref_" + str(i)).set("WNref" in utility)

            # Tees
            rman.parm("ri_numcustomaovs_" + str(i)).set(tee_count)

            for j in range(tee_count):
                rman.parm("ri_aovtype_" + str(i) + "_" + str(j)).set(
                    node.parm("teeType_" + str(j + 1)).evalAsString()
                )
                rman.parm("ri_aovvariable_" + str(i) + "_" + str(j)).set(
                    node.evalParm("teeName_" + str(j + 1))
                )

            i += 1
        if deep:
            rman.parm("ri_display_" + str(i)).set(self.get_output_path(node, "deep"))
            rman.parm("ri_device_" + str(i)).set("deepexr")

        # CRYPTOMATTE
        rman.parm("ri_samplefilters").set(len(crypto))
        for i, c in enumerate(crypto):
            name = c.name()[3:]
            cPath = "../aovs/" + name
            rman.parm("ri_samplefilter" + str(i)).set(cPath)
            node.parm("./aovs/" + name + "/filename").set(
                self.get_output_path(node, name)
            )

        # METADATA
        md_config = self.app.get_setting("render_metadata")

        md_config_groups = {}
        for md in md_config:
            group = md.get("group")
            if md_config_groups.get(group):
                md_config_groups.get(group).append(md.get("key"))
            else:
                md_config_groups[group] = [md.get("key")]
        md_config_groups = json.dumps(md_config_groups)

        md_count_node = node.evalParm("ri_exr_metadata") + (len(lightgroups) > 0)
        md_count_external = len(md_config)
        md_lg = {}
        md_lg.update(lg for lg in lightgroups)
        md_lg = json.dumps(md_lg)
        md_parms = list(
            filter(
                lambda parm: "exr_metadata" in parm.name()
                and parm.name() != "ri_exr_metadata",
                node.parms(),
            )
        )

        for f in range(file_count):
            rman.parm("ri_exr_metadata_{}".format(f)).set(
                md_count_node + md_count_external + (len(md_config) > 0)
            )

            rman.parm("ri_image_Artist_{}".format(f)).set(
                str(self.app.context.user["id"])
            )
            for parm in md_parms:
                name = parm.name().split("_")
                index = -1
                if name[-1] == "":
                    index = -2
                name.insert(index, str(f))
                name = "_".join(name)
                self.__set_expression(rman, parm.name(), name)

            if len(lightgroups):
                rman.parm("ri_exr_metadata_key_{}_{}".format(f, md_count_node - 1)).set(
                    "rmd_RenderLightGroups"
                )
                rman.parm(
                    "ri_exr_metadata_type_{}_{}".format(f, md_count_node - 1)
                ).set("string")
                rman.parm(
                    "ri_exr_metadata_string_{}_{}_".format(f, md_count_node - 1)
                ).set(md_lg)

            for i in range(md_count_external):
                item = md_config[i]
                rman.parm("ri_exr_metadata_key_{}_{}".format(f, md_count_node + i)).set(
                    "rmd_{}".format(item.get("key"))
                )
                rman.parm(
                    "ri_exr_metadata_type_{}_{}".format(f, md_count_node + i)
                ).set(item.get("type"))
                rman.parm(
                    "ri_exr_metadata_{}_{}_{}_".format(
                        item.get("type"), f, md_count_node + i
                    )
                ).setExpression(item.get("expression"))

            rman.parm(
                "ri_exr_metadata_key_{}_{}".format(f, md_count_node + md_count_external)
            ).set("rmd_PostRenderGroups")
            rman.parm(
                "ri_exr_metadata_type_{}_{}".format(
                    f, md_count_node + md_count_external
                )
            ).set("string")
            rman.parm(
                "ri_exr_metadata_string_{}_{}_".format(
                    f, md_count_node + md_count_external
                )
            ).set(md_config_groups)

        msg = "Setup AOVs complete with " + str(file_count + len(crypto)) + " files."
        if show_notif:
            hou.ui.displayMessage(msg)
        print("[RenderMan Renderer] " + msg)

        return True

    @staticmethod
    def __set_expression(node: hou.Node, source_parm: str, dist_parm: str):
        org_parm = node.parm(dist_parm).parmTemplate()
        if not org_parm:
            print("parm not found: ", dist_parm)
            return

        parm_type = "ch"
        if org_parm.dataType() == hou.parmData.String:
            parm_type = "chsop"

        node.parm(dist_parm).setExpression(
            '{}("{}{}")'.format(parm_type, "../", source_parm)
        )

    def get_output_path(self, node: hou.Node, aov_name: str, network="rop") -> str:
        """Calculate render path for an aov

        Args:
            node (hou.Node): RenderMan node
            aov_name (str): AOV name
            network (str): Network type
        """
        aov_name = aov_name[0].lower() + aov_name[1:]

        current_filepath = hou.hipFile.path()

        work_template = self.app.get_template("work_file_template")
        render_template = self.app.get_template("output_render_template")

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

    def get_output_paths(self, node: hou.Node) -> list[str]:
        paths = []

        aovs = node.parmsInFolder(("AOVs",))

        crypto = list(
            filter(lambda parm: "Crypto" in parm.name() and parm.eval() == 1, aovs)
        )

        lightgroups = list(
            filter(lambda parm: "LGUse" in parm.name() and parm.eval() == 1, aovs)
        )

        shading = node.parmsInFolder(("AOVs", "Shading"))
        shading = list(
            filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, shading)
        )

        lighting = node.parmsInFolder(("AOVs", "Lighting"))
        lighting = list(
            filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, lighting)
        )

        utility = node.parmsInFolder(("AOVs", "Utility"))
        utility = list(
            filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, utility)
        )

        if node.evalParm("aovBeauty"):
            paths.append(self.get_output_path(node, "beauty"))
        if len(shading):
            paths.append(self.get_output_path(node, "shading"))
        if len(lighting) or len(lightgroups):
            paths.append(self.get_output_path(node, "lighting"))
        if len(utility) or node.evalParm("tees"):
            paths.append(self.get_output_path(node, "utility"))
        if node.evalParm("aovDeep"):
            paths.append(self.get_output_path(node, "deep"))

        # Cryptomatte
        for i, c in enumerate(crypto):
            name = c.name()[3:]
            paths.append(self.get_output_path(node, name))

        # Denoise
        if node.evalParm("denoise"):
            paths.append(os.path.dirname(self.get_output_path(node, "denoise")))

        # Statistiscs
        paths.append(self.get_output_path(node, "stats")[:-3] + "xml")

        return paths

    def get_output_range(self, node: hou.Node) -> list[int]:
        framerange_type = node.parm("trange").eval()
        if framerange_type > 0:
            start_frame = int(node.parm("f1").eval())
            end_frame = int(node.parm("f2").eval())
            framerange = [start_frame, end_frame]
        else:
            current_frame = int(hou.frame())
            framerange = [current_frame, current_frame]
        # TODO add increment parameter

        return framerange

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

    def get_published_status(self, node: hou.Node) -> bool:
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

        file_path = node.node("render").parm(parameter).rawValue()

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
