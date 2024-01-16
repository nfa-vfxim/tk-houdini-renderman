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

import json
import os
import platform
import re

import hou
import sgtk
from PySide2.QtWidgets import QMessageBox

from .farm_dialog import FarmSubmission
from ..datamodel import aov_file
from ..datamodel.lpe import LPEControl
from ..datamodel.metadata import MetaData
from ..datamodel.render_engine import RenderEngine


class TkRenderManNodeHandler(object):
    def __init__(self, app):
        """Set global variables"""
        self.app = app
        self.sg = self.app.shotgun

    @staticmethod
    def _error(comment: str, error: Exception):
        QMessageBox.critical(
            hou.qt.mainWindow(),
            "Error",
            f"{comment}:\n{error}",
        )

    def submit_to_farm(self, node: hou.Node):
        """Start farm render

        Args:
            node (hou.Node): RenderMan node
        """
        if not self.setup_light_groups(node, RenderEngine.RENDERMAN, False):
            return
        if not self.setup_aovs(node, False):
            return

        is_lop = isinstance(node, hou.LopNode)
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
            self.app,
            node,
            file_name,
            50,
            framerange,
            render_paths,
            network="lop" if is_lop else "rop",
        )
        submission.show()

    def execute_render(self, node: hou.Node):
        """Start local render

        Args:
            node (hou.Node): RenderMan node
        """
        if not self.setup_light_groups(node, RenderEngine.RENDERMAN, False):
            return
        if not self.setup_aovs(node, False):
            return

        is_lop = isinstance(node, hou.LopNode)

        # Create directories
        render_paths = self.get_output_paths(node)
        for path in render_paths:
            self.__create_directory(path)

        # Execute rendering
        if is_lop:
            node.node("render").parm("execute").pressButton()
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

    def setup_light_groups(
        self,
        node: hou.Node,
        render_engine: RenderEngine = RenderEngine.RENDERMAN,
        show_notification: bool = True,
    ) -> bool:
        """This function clears all automated LPE tags from lights,
        then it sets their tags according to user input,
        after which it will set the proper render variables."""
        is_lop = isinstance(node, hou.LopNode)

        self.app.logger.debug("Setting up light groups")

        lpe_tags = [
            LPEControl(
                RenderEngine.KARMA,
                lop_control="xn__karmalightlpetag_control_4fbf",
                lop_light_group="xn__karmalightlpetag_31af",
                sop_light_group="vm_lpetag",
            ),
            LPEControl(
                RenderEngine.RENDERMAN,
                lop_control="xn__inputsrilightlightGroup_control_krbcf",
                lop_light_group="xn__inputsrilightlightGroup_jebcf",
                sop_light_group="lightGroup",
            ),
        ]

        lpe_tag = next(
            lpe_tag for lpe_tag in lpe_tags if lpe_tag.renderer == render_engine
        )

        # First we clear all our LPE tags, so we can add them again later
        stage = hou.node("/stage")

        all_nodes = stage.allSubChildren()

        for light_node in all_nodes:
            if light_node.type().name().startswith("light"):
                lpe_parm = light_node.parm(lpe_tag.get_light_group(is_lop))
                if lpe_parm:
                    expressions_to_keep = ""
                    for expression in lpe_parm.eval().split():
                        # We only remove our own LPE tags so the custom ones remain.
                        if not expression.startswith("LG_"):
                            expressions_to_keep += expression

                    lpe_parm.set(expressions_to_keep)

        # Now we add our LPE tags to the lights
        light_group_count = node.parm("light_groups_select").eval()
        light_groups_info = {}

        for i in range(1, light_group_count + 1):
            # Collecting light group information from the node
            light_group_name_parm = f"light_group_name_{i}"
            selected_light_lops_parm = f"select_light_ops_{i}"

            light_group_name = node.parm(light_group_name_parm).eval()
            selected_light_lops = node.parm(selected_light_lops_parm).eval()

            light_groups_info[light_group_name] = selected_light_lops.split()

        lights_list = []
        for light_group in light_groups_info:
            if not re.match(r"^[A-Za-z0-9_]+$", light_group):
                hou.ui.displayMessage(
                    f"Error: Invalid light group name: '{light_group}'. You can only use letters, numbers and "
                    f"underscores.",
                    severity=hou.severityType.Error,
                )
                return False

            # Using the collected information to set LPE tags
            for light in light_groups_info[light_group]:
                try:
                    if light not in lights_list:
                        lights_list.append(light)
                        light_node = hou.node(light)

                        if is_lop:
                            lpe_control_parm = light_node.parm(lpe_tag.get_control())
                            lpe_control_parm.set("set")
                            lpe_control_parm.pressButton()

                        lpe_param = light_node.parm(lpe_tag.get_light_group(is_lop))
                        lpe_param.set(f"LG_{light_group}")
                        lpe_param.pressButton()

                    else:
                        hou.ui.displayMessage(
                            f"Error: Node {light} is in several light groups. A light can only be in one group.",
                            severity=hou.severityType.Error,
                        )
                        return False
                except AttributeError as e:
                    hou.ui.displayMessage(
                        f"Error: Can't set LPE tags for node {light} in light group list {light_group}. \n{e}",
                        severity=hou.severityType.Error,
                    )
                    return False

        if render_engine == RenderEngine.KARMA:
            # Now we add the render vars to the Karma render settings node
            karma_render_settings = node.node("karmarendersettings")
            extra_render_variables = karma_render_settings.parm("extrarendervars")

            indices_to_remove = []
            # Collect our automated render variables, so we can remove only those
            for i in range(1, extra_render_variables.eval() + 1):
                if karma_render_settings.parm(
                    f"name{i}"
                ) and karma_render_settings.parm(f"name{i}").eval().startswith("LG_"):
                    indices_to_remove.append(i)

            # Remove instances from the last to the first to avoid re-indexing issues
            for i in reversed(indices_to_remove):
                # Instance indices are 1-based, but removal is 0-based
                karma_render_settings.parm("extrarendervars").removeMultiParmInstance(
                    i - 1
                )

            # Add our automated light groups back in
            for light_group in light_groups_info:
                render_variable_index = extra_render_variables.eval() + 1
                extra_render_variables.set(render_variable_index)
                karma_render_settings.parm(f"name{render_variable_index}").set(
                    f"LG_{light_group}"
                )
                karma_render_settings.parm(f"format{render_variable_index}").set(
                    "color3f"
                )
                karma_render_settings.parm(f"sourceName{render_variable_index}").set(
                    f"C.*<L.'LG_{light_group}'>"
                )
                karma_render_settings.parm(f"sourceType{render_variable_index}").set(
                    "lpe"
                )

        if show_notification:
            hou.ui.displayMessage(
                f"Finished light group setup for {light_group_count} groups",
            )

        return True

    @staticmethod
    def validate_node(node: hou.Node, network: str) -> bool:
        """
        This function will make sure all the parameters are filled in and setup correctly.

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
        if not render_name.isalnum():
            hou.ui.displayMessage(
                "Name is not alphanumeric, please only use alphabet letters (a-z) and numbers (0-9).",
                severity=hou.severityType.Error,
            )
            return False

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

        # Check if camera exists
        if network == "lop":
            stage = node.inputs()[0].stage()
            if not stage.GetPrimAtPath(node.evalParm("camera")):
                hou.ui.displayMessage(
                    "Invalid camera path.", severity=hou.severityType.Error
                )
                return False
        else:
            if not hou.node(node.evalParm("camera")):
                hou.ui.displayMessage(
                    "Invalid camera path.", severity=hou.severityType.Error
                )
                return False

        return True

    @staticmethod
    def _lop_setup_custom_aovs(node: hou.Node, custom_aovs: list[aov_file.CustomAOV]):
        for i, aov in enumerate(custom_aovs):
            aov: aov_file.CustomAOV
            node.parm(f"name{i + 1}").set(aov.name)
            node.parm(f"format{i + 1}").set(aov.get_format())
            node.parm(f"dataType{i + 1}").set("")
            node.parm(f"sourceName{i + 1}").set(aov.lpe)
            node.parm(f"sourceType{i + 1}").set("lpe")

    @staticmethod
    def get_active_files(node: hou.Node):
        output_files = 0
        active_files = []

        for file in aov_file.output_files:
            if file.has_active_aovs(node) or file.has_active_custom_aovs(node):
                active_files.append(file)
                if file.identifier != aov_file.OutputIdentifier.CRYPTOMATTE:
                    output_files += 1
                continue

            # If file is Lighting and there are light groups
            if (
                file.identifier == aov_file.OutputIdentifier.LIGHTING
                and node.parm("light_groups_select").eval() > 0
            ):
                active_files.append(file)
                output_files += 1
                continue

            # If file is Utility and there are tees
            if (
                file.identifier == aov_file.OutputIdentifier.UTILITY
                and node.parm("tees").eval() > 0
            ):
                active_files.append(file)
                output_files += 1
                continue
        return [output_files, active_files]

    def setup_aovs(self, node: hou.Node, show_notification: bool = True) -> bool:
        is_lop = isinstance(node, hou.LopNode)

        # Validate node
        if not self.validate_node(node, "lop" if is_lop else "driver"):
            return False

        use_denoise = node.parm("denoise").eval()
        use_autocrop = node.parm("autocrop").eval()

        # Get active files
        output_files, active_files = self.get_active_files(node)

        # Metadata
        md_config = self.app.get_setting("render_metadata")

        md_items = [
            MetaData("colorspace", "string", "ACES - ACEScg"),
        ]
        md_config_groups = {}
        for md in md_config:
            key = f'rmd_{md.get("key")}'
            md_items.append(
                MetaData(
                    key,
                    md.get("type"),
                    f'`{md.get("expression")}`'
                    if md.get("expression")
                    else md.get("value"),
                )
            )
            group = md.get("group")
            # TODO should use prefixed version in group mapping?
            if md_config_groups.get(group):
                md_config_groups.get(group).append(key)
            else:
                md_config_groups[group] = [key]
        md_items.append(
            MetaData("rmd_PostRenderGroups", "string", json.dumps(md_config_groups))
        )

        md_artist = str(self.app.context.user["id"])

        # Metadata get used publish versions
        current_engine = sgtk.platform.current_engine()
        breakdown_app = current_engine.apps["tk-multi-breakdown"]

        if breakdown_app:
            self.app.logger.debug(
                "Getting used publish versions with tk-multi-breakdown."
            )

            used_versions = []

            # Get list of breakdown items
            published_items = breakdown_app.analyze_scene()

            # Now loop over all items
            for published_item in published_items:
                fields = published_item["fields"]

                # Get the latest version on disk
                latest_version = breakdown_app.compute_highest_version(
                    published_item["template"], fields
                )

                version = {
                    "version": fields["version"],
                    "latest_version": latest_version,
                    "published": False,
                }

                if "Shot" in fields:
                    version["type"] = "Shot"
                    version[
                        "name"
                    ] = f"{fields['Sequence']} {fields['Shot']} {fields['Step']} {fields['name']}"
                elif "Asset" in fields:
                    version["type"] = "Asset"
                    version[
                        "name"
                    ] = f"{fields['Asset']} {fields['Step']} {fields['name']}"

                if published_item["sg_data"]:
                    version["published"] = True

                used_versions.append(version)

            md_items.append(
                MetaData("rmd_UsedPublishVersions", "string", json.dumps(used_versions))
            )

        else:
            self.app.logger.debug(
                "The app tk-multi-breakdown is not installed, skipping used publish version metadata."
            )

        self.app.logger.debug(
            f"Setting up aovs for files: {', '.join([file.identifier.value for file in active_files])}"
        )

        if is_lop:
            node_rman = node.node("render_settings")
            node_aovs = node.node("aovs")
            node_products = node.node("output_files")

            if output_files > 1:
                node_products.parm("products").set(output_files - 1)

            # Disable all
            for group in node_aovs.parmTemplateGroup().parmTemplates():
                parms: list[hou.ParmTemplate, ...] = [
                    parm
                    for parm in group.parmTemplates()
                    if "precision" not in parm.name()
                ]
                for parm in parms:
                    node_rman.parm(parm.name()).set(False)
                    node_aovs.parm(parm.name()).set(False)

            custom_aovs: list[aov_file.CustomAOV] = []

            # Enable active AOVs
            for i, file in enumerate(active_files):
                file: aov_file.OutputFile

                # Crypto
                if file.identifier == aov_file.OutputIdentifier.CRYPTOMATTE:
                    cryptomattes = [
                        crypto
                        for crypto in file.options
                        if node.parm(crypto.key).eval()
                    ]
                    for j in range(0, len(file.options)):
                        if j < len(cryptomattes):
                            crypto = cryptomattes[j]
                            node_rman.parm(f"xn__risamplefilter{j}name_w6an").set(
                                "PxrCryptomatte"
                            )
                            node_rman.parm(
                                f"xn__risamplefilter{j}PxrCryptomattefilename_70bno"
                            ).set(self.get_output_path(node, crypto.key))
                            node_rman.parm(
                                f"xn__risamplefilter{j}PxrCryptomattelayer_cwbno"
                            ).set(crypto.aovs[0])
                        else:
                            node_rman.parm(f"xn__risamplefilter{j}name_w6an").set(
                                "None"
                            )
                    continue

                # Add custom AOVs
                try:
                    local_custom_aovs = file.get_active_custom_aovs(node)
                except Exception as e:
                    self._error(f"Something is wrong with one or more of the AOVs", e)
                    return False

                # For first aov
                if i == 0:
                    # Set file output path
                    node_rman.parm("picture").set(
                        self.get_output_path(node, file.identifier.lower())
                    )

                    # Set as RGBA
                    node_rman.parm(f"xn__driverparametersopenexrasrgba_bobkh").set(
                        file.as_rgba and not (file.can_denoise and use_denoise)
                    )

                    # Set output type
                    if file.identifier == aov_file.OutputIdentifier.DEEP:
                        node_rman.parm("productType").set("deepexr")
                    # Set use autocrop
                    node_rman.parm("xn__driverparametersopenexrautocrop_krbkh").set(
                        "on" if use_autocrop else "off"
                    )
                    # Set bitdepth level
                    node_rman.parm("xn__driverparametersopenexrexrpixeltype_2xbkh").set(
                        file.bitdepth
                    )
                    # Set compression type
                    node_rman.parm(
                        "xn__driverparametersopenexrexrcompression_c1bkh"
                    ).set(file.compression)

                    # Add custom AOVs
                    node_rman.parm("extrarendervars").set(0)
                    node_rman.parm("extrarendervars").set(len(local_custom_aovs))
                    self._lop_setup_custom_aovs(node_rman, local_custom_aovs)
                # And the others
                else:
                    custom_aovs += local_custom_aovs

                    # Set file settings
                    node_products.parm(f"primname_{i - 1}").set(
                        file.identifier.value.lower()
                    )
                    # Set file output path
                    node_products.parm(f"productName_{i - 1}").set(
                        self.get_output_path(node, file.identifier.lower())
                    )
                    if file.identifier == aov_file.OutputIdentifier.DEEP:
                        node_products.parm(f"productType_{i - 1}").set("deepexr")
                    node_products.parm(f"doorderedVars_{i - 1}").set(True)
                    node_products.parm(f"orderedVars_{i - 1}").set(
                        " ".join(
                            [
                                f"/Render/Products/Vars/{aov}"
                                for aov in file.get_active_aovs(node)
                            ]
                            + [
                                f"/Render/Products/Vars/{aov.name}"
                                for aov in local_custom_aovs
                            ]
                        )
                    )
                    node_products.parm(f"autocrop_{i - 1}").set(use_autocrop)
                    node_products.parm(f"openexr_bitdepth_{i - 1}").set(file.bitdepth)
                    node_products.parm(f"openexr_compression_{i - 1}").set(
                        file.compression
                    )

                # Enable active AOVs
                active_node = node_rman if i == 0 else node_aovs
                for active_aov in file.get_active_aovs(node):
                    active_node.parm(active_aov).set(True)

            node_custom_aovs = node.node("custom_aovs")
            node_custom_aovs.parm("rendervars").set(0)
            node_custom_aovs.parm("rendervars").set(len(custom_aovs))
            self._lop_setup_custom_aovs(node_custom_aovs, custom_aovs)

            # Statistics
            node_rman.parm("xn__ristatisticsxmlfilename_febk").set(
                self.get_output_path(node, "stats")[:-3] + "xml"
            )

            # Metadata
            # Check if custom metadata has valid keys
            for j in range(1, node.evalParm("metadata_entries") + 1):
                md_key = node.parm(f"metadata_{j}_key").eval()
                if not re.match(r"^[A-Za-z0-9_]+$", md_key):
                    hou.ui.displayMessage(
                        f'The metadata key "{md_key}" is invalid. You can only use letters, numbers, and '
                        f"underscores.",
                        severity=hou.severityType.Error,
                    )
                    return False

            node_md = node.node("sg_metadata")

            node_md.parm("artist").set(md_artist)

            node_md.parm("metadata_entries").set(0)
            node_md.parm("metadata_entries").set(len(md_items))

            for i, item in enumerate(md_items):
                item: MetaData

                node_md.parm(f"metadata_{i + 1}_key").set(item.key)
                node_md.parm(f"metadata_{i + 1}_type").set(item.type)
                if "`" in item.value:
                    expression = item.value[1:-1]
                    expression = re.sub(
                        r"(ch[a-z]*)(\()([\"'])", r"\1(\3../", expression
                    )

                    node_md.parm(f"metadata_{i + 1}_{item.type}").setExpression(
                        expression
                    )
                else:
                    node_md.parm(f"metadata_{i + 1}_{item.type}").set(item.value)
        else:
            rman = node.node("render")
            rman.parm("ri_displays").set(0)
            rman.parm("ri_displays").set(output_files)

            # Denoise
            node.node("denoise").parm("output").set(
                os.path.dirname(self.get_output_path(node, "denoise"))
            )

            # Statistics
            rman.parm("ri_statistics_xmlfilename").set(
                self.get_output_path(node, "stats")[:-3] + "xml"
            )

            for i, file in enumerate(active_files):
                file: aov_file.OutputFile

                # Crypto
                if file.identifier == aov_file.OutputIdentifier.CRYPTOMATTE:
                    cryptomattes = [
                        crypto
                        for crypto in file.options
                        if node.parm(crypto.key).eval()
                    ]

                    rman.parm("ri_samplefilters").set(0)
                    rman.parm("ri_samplefilters").set(len(cryptomattes))
                    for j, c in enumerate(cryptomattes):
                        name = f"Crypto{c.name}"
                        rman.parm(f"ri_samplefilter{j}").set(f"../aovs/{name}")
                        node.parm("./aovs/" + name + "/filename").set(
                            self.get_output_path(node, name)
                        )
                    continue

                rman.parm(f"ri_display_{i}").set(
                    self.get_output_path(node, file.identifier.lower())
                )

                if file.identifier == aov_file.OutputIdentifier.DEEP:
                    rman.parm(f"ri_device_{i}").set("deepexr")

                rman.parm(f"ri_autocrop_{i}").set("on" if use_autocrop else "off")
                rman.parm(f"ri_exrpixeltype_{i}").set(file.bitdepth)
                rman.parm(f"ri_exrcompression_{i}").set(file.compression)

                denoise_on = file.can_denoise and use_denoise
                rman.parm(f"ri_denoiseon_{i}").set(denoise_on)

                rman.parm(f"ri_asrgba_{i}").set(file.as_rgba and not denoise_on)

                # Disable defaults
                rman.parm(f"ri_quickaov_Ci_{i}").set(False)
                rman.parm(f"ri_quickaov_a_{i}").set(False)

                # Enable active AOVs
                for aov in file.get_active_aovs(node):
                    rman.parm(f"ri_quickaov_{aov}_{i}").set(True)

                # Add custom AOVs
                custom_aovs = file.get_active_custom_aovs(node)

                rman.parm(f"ri_numcustomaovs_{i}").set(0)
                rman.parm(f"ri_numcustomaovs_{i}").set(len(custom_aovs))
                for j, aov in enumerate(custom_aovs):
                    aov: aov_file.CustomAOV
                    rman.parm(f"ri_aovvariable_{i}_{j}").set(aov.name)
                    rman.parm(f"ri_aovtype_{i}_{j}").set(aov.type)
                    rman.parm(f"ri_aovsource_{i}_{j}").set(aov.lpe)

                node_md = node.node("render")
                for j in range(1, node.evalParm("metadata_entries") + 1):
                    md_key = node.parm(f"metadata_{j}_key").eval()
                    md_type = node.parm(f"metadata_{j}_type").evalAsString()
                    md_value_parm = node.parm(f"metadata_{j}_{md_type}")
                    try:
                        md_value = f"`{md_value_parm.expression()}`"
                    except:
                        md_value = md_value_parm.rawValue()

                    md_items.append(MetaData(md_key, md_type, md_value))

                node_md.parm(f"ri_exr_metadata_{i}").set(0)
                node_md.parm(f"ri_exr_metadata_{i}").set(len(md_items))

                node_md.parm(f"ri_image_Artist_{i}").set(md_artist)

                for j, item in enumerate(md_items):
                    item: MetaData

                    node_md.parm(f"ri_exr_metadata_key_{i}_{j}").set(item.key)
                    node_md.parm(f"ri_exr_metadata_type_{i}_{j}").set(item.type)
                    if "`" in item.value:
                        expression = item.value[1:-1]
                        expression = re.sub(
                            r"(ch[a-z]*)(\()([\"'])", r"\1(\3../", expression
                        )

                        node_md.parm(
                            f"ri_exr_metadata_{item.type}_{i}_{j}_"
                        ).setExpression(expression)
                    else:
                        node_md.parm(f"ri_exr_metadata_{item.type}_{i}_{j}_").set(
                            item.value
                        )

        msg = f"Setup AOVs complete with {len(active_files)} files."
        if show_notification:
            hou.ui.displayMessage(msg)
        self.app.logger.debug(msg)

        return True

    @staticmethod
    def _set_expression(node: hou.Node, source_parm: str, dist_parm: str):
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

    def get_output_path(self, node: hou.Node, aov_name: str) -> str:
        """Calculate render path for an aov

        Args:
            node (hou.Node): RenderMan node
            aov_name (str): AOV name
        """
        is_lop = isinstance(node, hou.LopNode)

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
        if not is_lop:
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

        try:
            output_files, active_files = self.get_active_files(node)
            for file in active_files:
                file: aov_file.OutputFile
                if file.identifier == aov_file.OutputIdentifier.CRYPTOMATTE:
                    for crypto in file.options:
                        if node.parm(crypto.key).eval():
                            paths.append(self.get_output_path(node, crypto.key))
                else:
                    paths.append(self.get_output_path(node, file.identifier.lower()))
        except Exception as e:
            self._error(
                f'Something is wrong with one or more of the AOVs on node "{node.name()}"',
                e,
            )
            return []

        # Denoise
        if node.evalParm("denoise"):
            paths.append(self.get_output_path(node, "denoise"))

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
