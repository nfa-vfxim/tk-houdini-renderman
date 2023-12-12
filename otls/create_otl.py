import logging
import re
import string
import xml.etree.ElementTree as ET
from enum import Enum
from typing import Callable

import hou


# Run from Houdini python shell to build HDAs:
# exec(open(r"D:\Developer\Pipeline\tk-houdini-renderman\otls\create_otl.py").read())


class OTLTypes(Enum):
    DRIVER = "driver"
    LOP = "lop"
    DRIVER_SG = "driver_sg"
    LOP_SG = "lop_sg"


# 0: Beauty 16 bit DWAa
# 1: Shading 16 bit DWAa
# 2: Lighting 16 bit DWAa
# 3: Utility 32 bit ZIP
# 4: Deep
# X: Denoise
# X: Cryptomatte
class OutputIdentifier(Enum):
    BEAUTY = "Beauty"
    SHADING = "Shading"
    LIGHTING = "Lighting"
    UTILITY = "Utility"
    CRYPTOMATTE = "Cryptomatte"
    DEEP = "Deep"


OUTPUT_FILES = {
    OutputIdentifier.BEAUTY: {
        "asRGBA": True,
        "bitdepth": "half",
        "compression": "dwaa",
        "options": {
            "beauty": {"name": "Beauty + Alpha", "aovs": ["Ci", "a"], "default": True},
        },
    },
    OutputIdentifier.SHADING: {
        "asRGBA": False,
        "bitdepth": "half",
        "compression": "dwaa",
        "options": {
            "albedo": {"name": "Albedo", "aovs": ["albedo"]},
            "emissive": {
                "name": "Emissive",
                "aovs": ["emissive"],
            },
            "diffuse": {
                "name": "(In)direct Diffuse",
                "aovs": ["directDiffuse", "indirectDiffuse"],
            },
            "diffuseU": {
                "name": "(In)direct Diffuse Unoccluded",
                "aovs": ["directDiffuseUnoccluded", "indirectDiffuseUnoccluded"],
            },
            "specular": {
                "name": "(In)direct Specular",
                "aovs": ["directSpecular", "indirectSpecular"],
            },
            "specularU": {
                "name": "(In)direct Specular Unoccluded",
                "aovs": ["directSpecularUnoccluded", "indirectSpecularUnoccluded"],
            },
            "subsurface": {"name": "Subsurface", "aovs": ["albedo"]},
            "lobes_diffuse": {
                "name": "(In)direct Diffuse",
                "aovs": ["directDiffuseLobe", "indirectDiffuseLobe"],
            },
            "lobes_specularPrimary": {
                "name": "(In)direct Specular Primary",
                "aovs": ["directSpecularPrimaryLobe", "indirectSpecularPrimaryLobe"],
            },
            "lobes_specularRough": {
                "name": "(In)direct Specular Rough",
                "aovs": ["directSpecularRoughLobe", "indirectSpecularRoughLobe"],
            },
            "lobes_specularClearcoat": {
                "name": "(In)direct Specular Clearcoat",
                "aovs": [
                    "directSpecularClearcoatLobe",
                    "indirectSpecularClearcoatLobe",
                ],
            },
            "lobes_specularIridescence": {
                "name": "(In)direct Specular Iridescence",
                "aovs": [
                    "directSpecularIridescenceLobe",
                    "indirectSpecularIridescenceLobe",
                ],
            },
            "lobes_specularFuzz": {
                "name": "(In)direct Specular Fuzz",
                "aovs": ["directSpecularFuzzLobe", "indirectSpecularFuzzLobe"],
            },
            "lobes_specularGlass": {
                "name": "(In)direct Specular Glass",
                "aovs": ["directSpecularGlassLobe", "indirectSpecularGlassLobe"],
            },
            "lobes_subsurface": {
                "name": "Subsurface",
                "aovs": ["subsurfaceLobe"],
            },
            "lobes_transmissiveSingleScatter": {
                "name": "Transmissive Single Scatter",
                "aovs": ["transmissiveSingleScatterLobe"],
            },
            "lobes_transmissiveGlass": {
                "name": "Transmissive Glass",
                "aovs": ["transmissiveGlassLobe"],
            },
        },
    },
    OutputIdentifier.LIGHTING: {
        "asRGBA": False,
        "bitdepth": "half",
        "compression": "dwaa",
        "notes": {
            "shadow": "Enable the Holdout tag for an object to show up in the shadow AOVs",
        },
        "options": {
            "shadow_shadowOccluded": {"name": "Occluded", "aovs": ["occluded"]},
            "shadow_shadowUnoccluded": {"name": "Unoccluded", "aovs": ["unoccluded"]},
            "shadow_shadow": {"name": "Shadow", "aovs": ["shadow"]},
        },
    },
    OutputIdentifier.UTILITY: {
        "asRGBA": False,
        "bitdepth": "full",
        "compression": "zips",
        "options": {
            "curvature": {"name": "Curvature", "aovs": ["curvature"]},
            "motionVector": {"name": "Motion Vector World Space", "aovs": ["shadow"]},
            "motionVectorCamera": {
                "name": "Motion Vector Camera Space",
                "aovs": ["shadow"],
            },
            "sep1": "-",
            "pWorld": {"name": "Position (world-space)", "aovs": ["__Pworld"]},
            "nWorld": {"name": "Normal (world-space)", "aovs": ["__Nworld"]},
            "depthAA": {
                "name": "Depth (Anti-Aliased) + Facing Ratio",
                "aovs": ["__depth"],
            },
            "depth": {"name": "Depth (Aliased)", "aovs": ["z"]},
            "st": {"name": "Texture Coordinates (UV maps)", "aovs": ["__st"]},
            "pRef": {"name": "Reference Position", "aovs": ["__Pref"]},
            "nRef": {"name": "Reference Normal", "aovs": ["__Nref"]},
            "pRefWorld": {"name": "Reference World Position", "aovs": ["__WPref"]},
            "nRefWorld": {"name": "Reference World Normal", "aovs": ["__WNref"]},
        },
    },
    OutputIdentifier.CRYPTOMATTE: {
        "asRGBA": False,
        "bitdepth": "half",
        "compression": "zips",
        "options": {
            "cryptoMaterial": {
                "name": "Material",
                "aovs": [],
            },
            "cryptoName": {
                "name": "Name",
                "aovs": [],
            },
            "cryptoPath": {
                "name": "Path",
                "aovs": [],
            },
        },
    },
    OutputIdentifier.DEEP: {
        "asRGBA": False,
        "bitdepth": "half",
        "compression": "dwaa",
        "options": {
            "deep": {
                "name": "Deep",
                "aovs": ["Ci", "a"],
            },
        },
    },
}

PARM_MAPPING = {
    "ri_statistics_level": "xn__ristatisticslevel_n3ak",
    "ri_statistics_xmlfilename": "xn__ristatisticsxmlfilename_febk",
    "ri_hider_samplemotion": "xn__rihidersamplemotion_w6af",
    "integrator": "xn__riintegratorname_01ak",
    # Cryptomatte
    "ri:samplefilter0:name": "xn__risamplefilter0name_w6an",
    "ri:samplefilter0:PxrCryptomatte:filename": "xn__risamplefilter0PxrCryptomattefilename_70bno",
    "ri:samplefilter0:PxrCryptomatte:layer": "xn__risamplefilter0PxrCryptomattelayer_cwbno",
}


class CreateOtl:
    def __init__(self, otl_type: OTLTypes):
        self._otl_type = otl_type

        self._is_shotgrid = otl_type.value.endswith("sg")
        self._is_lop = otl_type.value.startswith("lop")
        self._context_type = "lop" if self._is_lop else "driver"
        self._context_name = "stage" if self._is_lop else "out"

        self._node_name = "sgtk_ris" if self._is_shotgrid else "RenderMan_Renderer"
        self._otl_name = "SGTK_RenderMan" if self._is_shotgrid else "RenderMan_Renderer"

    def _parm_name(self, sop_name: str) -> str:
        """Get the parameter name for the current context

        Args:
            sop_name (str): Source name
        Returns:
            str: Corrected name
        """
        if self._is_lop:
            if sop_name in PARM_MAPPING.keys():
                return PARM_MAPPING[sop_name]
        return sop_name

    def _link_parm(
        self,
        node: hou.Node,
        parm_name: str,
        level: int = 1,
        prepend: str = "",
        append: str = "",
    ):
        """
        Link a parameter from the source node to a destination node

        Args:
            node (hou.None): Node to add the expression to
            parm_name (str): Parameter key on the source node
            level (int): Levels between source and destination node
            prepend (str): String to prepend to source parameter key
            append (str): String to append to source parameter key
        """
        dist_name = self._parm_name(parm_name)
        org_parm = node.parmTemplateGroup().find(dist_name)
        if not org_parm:
            logging.error("parm not found: ", parm_name)
            return

        if self._is_lop and level != 1:
            level -= 1

        parm_type = "ch"
        if org_parm.dataType() == hou.parmData.String:
            parm_type = "chsop"

        if org_parm.numComponents() == 1:
            node.parm(dist_name).setExpression(
                '{}("{}{}")'.format(
                    parm_type, "../" * level, prepend + parm_name + append
                )
            )
        else:
            scheme = self._convert_naming_scheme(org_parm.namingScheme())
            for i in range(org_parm.numComponents()):
                node.parm(dist_name + scheme[i]).setExpression(
                    '{}("{}{}")'.format(
                        parm_type,
                        "../" * level,
                        prepend + parm_name + append + scheme[i],
                    )
                )

    def _link_deep_parms(
        self, node: hou.Node, parms: list[str], prepend: str = "", append: str = ""
    ):
        """
        Link a list of parameters from the source node to a destination node, including items in folders

        Args:
            node (hou.None): Node to add the expression to
            parms (list[str]): A list of parameter keys on the source node
            prepend (str): String to prepend to source parameter key
            append (str): String to append to source parameter key
        """
        for parm in parms:
            if parm.type() == hou.parmTemplateType.Folder:
                self._link_deep_parms(node, parm.parmTemplates(), prepend, append)
            else:
                self._link_parm(node, parm.name(), 2, prepend, append)

    def _set_deep_conditional(
        self,
        parms: tuple[hou.ParmTemplate, ...],
        cond_type: hou.parmCondType,
        modifier: Callable[[str], str],
    ):
        """
        Modify the conditionals of a list of parm templates

        Args:
            parms (tuple[hou.ParmTemplate, ...]): List of ParmTemplates to modify
            cond_type (hou.parmCondType): The type of conditional to modify
            modifier (Callable[[str], str]): The function which is called on the source conditional
        """
        for parm in parms:
            if parm.type() == hou.parmTemplateType.Folder:
                new_parms = self._set_deep_conditional(
                    parm.parmTemplates(), cond_type, modifier
                )
                parm.setParmTemplates(new_parms)
            elif cond_type in parm.conditionals():
                parm.setConditional(cond_type, modifier(parm.conditionals()[cond_type]))
        return parms

    def _reference_parm(
        self,
        node: hou.Node,
        dest: hou.ParmTemplateGroup,
        parm: str,
        conditional: list[hou.parmCondType, str] = None,
    ):
        """
        Create a reference of a parameter to a template group

        Args:
            node (hou.Node): The node to get the parameter from
            dest (hou.ParmTemplateGroup): The ParmTemplateGroup to add the reference to
            parm (str): The parameter key
            conditional (list[hou.parmCondType, str]): An optional conditional
        """
        org_parms = node.parmTemplateGroup()
        org_parm = org_parms.find(parm)
        if not org_parm:
            logging.error("Parm not found: ", parm)
            return

        if conditional:
            org_parm.setConditional(conditional[0], conditional[1])

        if hasattr(dest, "append"):
            dest.append(org_parm)
        elif hasattr(dest, "addParmTemplate"):
            dest.addParmTemplate(org_parm)
        else:
            logging.error("Undefined method")
            return

        self._link_parm(node, parm)

    def _rename_deep_parms(
        self, parms: list[hou.ParmTemplate], prepend: str = "", append: str = ""
    ) -> list[hou.ParmTemplate]:
        """
        Prepend and/or append a string to a list of parameter templates

        Args:
            parms (list[hou.ParmTemplate]): List of ParmTemplates to modify
            prepend (str): String to prepend to the name
            append (str): String to append to the name

        Returns:
            list[hou.ParmTemplate]: Modified list of ParmTemplates
        """
        for parm in parms:
            parm.setName(prepend + parm.name() + append)
            if parm.type() == hou.parmTemplateType.Folder:
                renamed = self._rename_deep_parms(parm.parmTemplates(), prepend, append)
                parm.setParmTemplates(renamed)
        return parms

    def _set_parm(self, node: hou.Node, parm_name: str, value: any):
        """
        Set the value of a parameter, with the context corrected name

        Args:
            node (hou.Node): Node containing parameter to modify
            parm_name (str): Name of the parameter
            value (any): Value to set parameter to
        """
        node.parm(self._parm_name(parm_name)).set(value)

    def _set_parm_expression(self, node: hou.Node, parm_name: str, value: str):
        """
        Set the value of a parameter, with the context corrected name, to an expression

        Args:
            node (hou.Node): Node containing parameter to modify
            parm_name (str): Name of the parameter
            value (str): Expression to set parameter to
        """
        node.parm(self._parm_name(parm_name)).setExpression(value)

    @staticmethod
    def _setup_custom_aovs(folder: hou.FolderParmTemplate):
        """
        Add custom AOV collapsible block

        Args:
            folder (hou.FolderParmTemplate): Folder to add the custom AOV block to
        """
        name = folder.label().replace(" ", "")

        disable = "{{aov{}CustomDisable_# == 1}}".format(name)
        custom_folder = hou.FolderParmTemplate(
            "{}Custom".format(name.lower()),
            "Custom AOVs",
            folder_type=hou.folderType.Collapsible,
        )
        custom = hou.FolderParmTemplate(
            "{}CustomAOVs".format(name.lower()),
            "Extra Image Planes",
            folder_type=hou.folderType.MultiparmBlock,
        )
        custom.addParmTemplate(
            hou.ToggleParmTemplate("aov{}CustomDisable_#".format(name), "Disable AOV")
        )
        custom.addParmTemplate(
            hou.StringParmTemplate(
                "aov{}CustomName_#".format(name), "Name", 1, disable_when=disable
            )
        )
        custom.addParmTemplate(
            hou.MenuParmTemplate(
                "aov{}CustomSource_#".format(name),
                "Source",
                ("color", "float", "integer", "vector", "normal", "point"),
                ("Color", "Float", "Integer", "Vector", "Normal", "Point"),
                join_with_next=True,
                disable_when=disable,
            )
        )
        custom.addParmTemplate(
            hou.StringParmTemplate(
                "aov{}CustomLPE_#".format(name),
                "LPE",
                1,
                is_label_hidden=True,
                disable_when=disable,
            )
        )

        custom_folder.addParmTemplate(custom)
        folder.addParmTemplate(custom_folder)

    @staticmethod
    def _get_metadata_block():
        """
        Get a MultiparmBlock to set up metadata with

        Returns:
            hou.FolderParmTemplate: MultiparmBlock with metadata entries
        """
        metadata_entries = hou.FolderParmTemplate(
            "metadata_entries", "Entries", folder_type=hou.folderType.MultiparmBlock
        )
        metadata_entries.addParmTemplate(
            hou.StringParmTemplate("metadata_#_key", "Key", 1, join_with_next=True)
        )

        metadata_types = [
            {"key": "float", "name": "Float", "type": "float", "components": 1},
            {"key": "int", "name": "Integer", "type": "int", "components": 1},
            {"key": "string", "name": "String", "type": "string", "components": 1},
            {"key": "v2f", "name": "Vector 2 Float", "type": "float", "components": 2},
            {"key": "v2i", "name": "Vector 2 Int", "type": "int", "components": 2},
            {"key": "v3f", "name": "Vector 3 Float", "type": "float", "components": 3},
            {"key": "v3i", "name": "Vector 3 Int", "type": "int", "components": 3},
            {"key": "box2f", "name": "Box 2 Float", "type": "float", "components": 4},
            {"key": "box2i", "name": "Box 2 Int", "type": "int", "components": 4},
            {"key": "m33f", "name": "Matrix 3x3", "type": "float", "components": 9},
            {"key": "m44f", "name": "Matrix 4x4", "type": "float", "components": 16},
        ]
        metadata_names = [md_type["key"] for md_type in metadata_types]
        metadata_labels = [md_type["name"] for md_type in metadata_types]

        metadata_entries.addParmTemplate(
            hou.MenuParmTemplate(
                "metadata_#_type", "   Type", metadata_names, metadata_labels
            )
        )

        for md_type in metadata_types:
            if md_type["type"] == "float":
                parm = hou.FloatParmTemplate(
                    f"metadata_#_{md_type['key']}", "Value", md_type["components"]
                )
            elif md_type["type"] == "int":
                parm = hou.IntParmTemplate(
                    f"metadata_#_{md_type['key']}", "Value", md_type["components"]
                )
            elif md_type["type"] == "string":
                parm = hou.StringParmTemplate(
                    f"metadata_#_{md_type['key']}", "Value", md_type["components"]
                )
            parm.setConditional(
                hou.parmCondType.HideWhen, f"{{ metadata_#_type != {md_type['key']} }}"
            )
            metadata_entries.addParmTemplate(parm)

        return metadata_entries

    def _add_output_file(
        self, output_id: OutputIdentifier, folder: hou.FolderParmTemplate
    ):
        """
        Add aov toggles for a specific output file

        Args:
            output_id (OutputIdentifier): Output identifier
            folder (hou.FolderParmTemplate): Folder to add the toggles to
        """
        output_file = OUTPUT_FILES[output_id]
        subfolders = {}

        for key, value in output_file["options"].items():
            add_folder = folder
            if "_" in key:
                subfolder_id = key.split("_")[0]
                if subfolder_id not in subfolders:
                    subfolder_name = string.capwords(
                        self._space_camel_case(subfolder_id)
                    )
                    add_folder = hou.FolderParmTemplate(
                        subfolder_id,
                        subfolder_name,
                        folder_type=hou.folderType.Simple,
                    )

                    # Add folder note
                    if "notes" in output_file and subfolder_id in output_file["notes"]:
                        note = hou.LabelParmTemplate(
                            f"{subfolder_id}Note",
                            "Note",
                            column_labels=(output_file["notes"][subfolder_id],),
                        )
                        note.setLabelParmType(hou.labelParmType.Message)
                        add_folder.addParmTemplate(note)

                    subfolders[subfolder_id] = add_folder
                else:
                    add_folder = subfolders[subfolder_id]

            if type(value) is str:
                add_folder.addParmTemplate(hou.SeparatorParmTemplate(f"aov{key}"))
            else:
                toggle = hou.ToggleParmTemplate(key, value["name"])
                if "default" in value:
                    toggle.setDefaultValue(value["default"])
                add_folder.addParmTemplate(toggle)

        for subfolder in subfolders.values():
            folder.addParmTemplate(subfolder)

    @staticmethod
    def _convert_naming_scheme(naming_scheme: hou.parmNamingScheme) -> tuple[str, ...]:
        """
        Convert Houdini naming scheme to name suffixes

        Args:
            naming_scheme (hou.parmNamingScheme): The naming scheme

        Returns:
           tuple[str, ...]: Suffixes for the components
        """
        if naming_scheme == hou.parmNamingScheme.Base1:
            return "1", "2", "3", "4"
        elif naming_scheme == hou.parmNamingScheme.XYZW:
            return "x", "y", "z", "w"
        elif naming_scheme == hou.parmNamingScheme.XYWH:
            return "x", "y", "w", "h"
        elif naming_scheme == hou.parmNamingScheme.UVW:
            return "u", "v", "w"
        elif naming_scheme == hou.parmNamingScheme.RGBA:
            return "r", "g", "b", "a"
        elif naming_scheme == hou.parmNamingScheme.MinMax:
            return "min", "max"
        elif naming_scheme == hou.parmNamingScheme.MaxMin:
            return "max", "min"
        elif naming_scheme == hou.parmNamingScheme.StartEnd:
            return "start", "end"
        elif naming_scheme == hou.parmNamingScheme.BeginEnd:
            return "begin", "end"

    @staticmethod
    def _space_camel_case(text: str) -> str:
        """
        Convert camel case to spaced string

        Args:
            text (str): Camel cased string

        Returns:
            str: Spaced string
        """
        return re.sub(r"((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))", r" \1", text)

    def build(self):
        """
        Build the HDA
        """
        logging.debug("Creating nodes")
        hda = hou.node(f"/{self._context_name}/{self._otl_name}")
        if hda:
            hda.destroy()

        hda = hou.node(f"/{self._context_name}/").createNode("subnet", self._otl_name)

        integrator_list = list()

        # Find available integrators and add them
        for key, value in hou.vopNodeTypeCategory().nodeTypes().items():
            name = value.nameComponents()[2]
            if "pxr" in name and value.hasSectionData("Tools.shelf"):
                if "Integrator" in ET.fromstring(value.sectionData("Tools.shelf")).find(
                    "tool"
                ).findtext("toolSubmenu"):
                    if not (self._is_lop and value.description() == "PxrValidateBxdf"):
                        integrator_list.append(
                            (
                                value.description(),
                                self._space_camel_case(
                                    value.description().replace("Pxr", "")
                                ),
                            )
                        )

        #
        # Create nodes
        #
        if self._is_lop:
            node_aovs = hda.createNode("hdprmanstandardrendervars", "aovs")
            node_custom_aovs = hda.createNode("additionalrendervars", "custom_aovs")
            node_output_files = hda.createNode(
                "rendermanrenderproducts", "output_files"
            )
            rman = hda.createNode("hdprmanrenderproperties", "render_settings")
            node_user_metadata = hda.createNode("attribwrangle", "user_metadata")
            node_sg_metadata = hda.createNode("attribwrangle", "sg_metadata")
            node_set_cam_resolution = hda.createNode(
                "renderproduct", "set_cam_resolution"
            )
            node_render = hda.createNode("usdrender_rop", "render")

            # Link nodes
            node_aovs.setInput(0, hda.indirectInputs()[0])
            node_custom_aovs.setInput(0, node_aovs)
            node_output_files.setInput(0, node_custom_aovs)
            rman.setInput(0, hda.indirectInputs()[0])
            rman.setInput(1, node_output_files)
            node_user_metadata.setInput(0, rman)
            node_sg_metadata.setInput(0, node_user_metadata)
            node_set_cam_resolution.setInput(0, node_sg_metadata)
            node_render.setInput(0, node_set_cam_resolution)
            hda.subnetOutputs()[0].setInput(0, node_set_cam_resolution)

            # Output Files config
            node_output_files.parm("camera").setExpression(
                'chs("../render_settings/camera")'
            )
            node_output_files.parm("resolution1").setExpression(
                'ch("../render_settings/resolutionx")'
            )
            node_output_files.parm("resolution2").setExpression(
                'ch("../render_settings/resolutiony")'
            )
            node_output_files.parm("instantaneousShutter").setExpression(
                'ch("../render_settings/instantaneousShutter")'
            )
            node_output_files.parm("aspectRatioConformPolicy").setExpression(
                'chs("../render_settings/aspectRatioConformPolicy")'
            )
            for i in range(1, 4):
                node_output_files.parm(f"dataWindowNDC{i}").setExpression(
                    f'ch("../render_settings/dataWindowNDC{i}")'
                )
            node_output_files.parm("pixelAspectRatio").setExpression(
                'ch("../render_settings/pixelAspectRatio")'
            )
            node_output_files.parm("products").set(0)

            # Render Settings config
            rman.parm("importsecondaryinputvars").set(True)
            rman.parm("importsecondaryproducts").set(True)

            # Metadata Wrangles
            for i, node in enumerate([node_user_metadata, node_sg_metadata]):
                node.parm("primpattern").set("/Render/** & %type:RenderProduct")

                if i == 0:
                    level = "../"
                else:
                    level = ""
                    metadata_params = node_sg_metadata.parmTemplateGroup()
                    metadata_params.addParmTemplate(self._get_metadata_block())
                    metadata_params.addParmTemplate(
                        hou.StringParmTemplate("artist", "Artist", 1)
                    )
                    node_sg_metadata.setParmTemplateGroup(metadata_params)

                node.parm("snippet").set(
                    f'for (int i = 1; i <= chi("{level}metadata_entries"); i++) {{ \n\
    string type = chs(sprintf("{level}metadata_%g_type", i)); \n\
    string name = "driver:parameters:OpenEXR:" + chs(sprintf("{level}metadata_%g_key", i)); \n\
    string value_name = sprintf("{level}metadata_%g_%s", i, type); \n\
            \n\
    if (type == "float") \n\
        usd_setattrib(0, @primpath, name, chf(value_name)); \n\
    else if (type == "int") \n\
        usd_setattrib(0, @primpath, name, chi(value_name)); \n\
    else if (type == "string") \n\
        usd_setattrib(0, @primpath, name, chs(value_name)); \n\
    else if (startswith(type, "v")) \n\
        usd_setattrib(0, @primpath, name, chv(value_name)); \n\
    else if (startswith(type, "bix")) \n\
        usd_setattrib(0, @primpath, name, chp(value_name)); \n\
    else if (type == "m33f") \n\
        usd_setattrib(0, @primpath, name, ch3(value_name)); \n\
    else if (type == "m44f") \n\
        usd_setattrib(0, @primpath, name, ch4(value_name)); \n\
}} \n\n\
usd_setattrib(0, @primpath, "driver:parameters:artist", chs("artist"));'
                )

            # Set Cam Resolution
            node_set_cam_resolution.parm("primpattern").set(
                "/Render/** & %type:RenderProduct"
            )
            node_set_cam_resolution.parm("createprims").set("off")
            node_set_cam_resolution.parm("orderedVars_control").set("none")
            node_set_cam_resolution.parm("productName_control").set("none")
            node_set_cam_resolution.parm("productType_control").set("none")
            node_set_cam_resolution.parm("camera_control").set("set")
            node_set_cam_resolution.parm("camera").setExpression(
                'chs("../render_settings/camera")'
            )

            # Render
            node_render.parm("rendersettings").set("/Render/rendersettings")

            # Set editable nodes
            editable_nodes = [
                node_aovs,
                node_custom_aovs,
                node_output_files,
                rman,
                node_sg_metadata,
            ]

            hda.layoutChildren()
        else:
            rman = hda.createNode("ris", "render")
            denoise = hda.createNode("denoise", "denoise")

            integrators = hda.createNode("matnet", "integrators")

            for integrator in integrator_list:
                integrators.createNode(integrator[0].lower(), integrator[0])

            integrators.layoutChildren()

            # AOV filters
            aovs = hda.createNode("matnet", "aovs")

            cmat = aovs.createNode("pxrcryptomatte", "CryptoMaterial")
            cmat.parm("layer").set("user:__materialid")
            cname = aovs.createNode("pxrcryptomatte", "CryptoName")
            cname.parm("layer").set("identifier:object")
            cpath = aovs.createNode("pxrcryptomatte", "CryptoPath")
            cpath.parm("layer").set("identifier:name")

            aovs.layoutChildren()

            # Style nodes
            integrators.setColor(hou.Color(0, 0, 0))
            aovs.setColor(hou.Color(0.1, 0.8, 0.1))

            # Link nodes
            denoise.setInput(0, rman)

            editable_nodes = [rman, denoise, aovs]

            hda.layoutChildren((rman, denoise, aovs, integrators))

        hda.setSelected(True)

        #
        # Setup RIS node
        #

        # Enable statistics
        self._set_parm(rman, "ri_statistics_level", True)
        if not self._is_lop:
            rman.parm("ri_statistics_texturestatslevel").set(True)

        #
        # Create HDA
        #
        logging.debug("Creating HDA")
        hda = hou.Node.createDigitalAsset(
            hda,
            self._node_name,
            rf"D:\Developer\Pipeline\tk-houdini-renderman\otls\{self._context_type}_{self._node_name}.otl",
            version="25.2",
            ignore_external_references=True,
            create_backup=False,
            min_num_inputs=self._is_lop,
            max_num_inputs=self._is_lop,
        )
        hda.type().setDefaultColor(hou.Color(0, 0.2, 0.3))
        if self._is_lop:
            hda.type().setDefaultShape("clipped_right")

        hda_def = hda.type().definition()
        hda_options = hda_def.options()

        # TODO add non-ShotGrid version of PythonModule
        python_module = open(
            r"D:\Developer\Pipeline\tk-houdini-renderman\otls\PythonModule.py", "r"
        )
        hda_def.addSection("PythonModule", python_module.read())
        hda_def.setExtraFileOption("PythonModule/IsPython", True)

        on_created = 'kwargs["node"].setColor(hou.Color(0, 0.2, 0.3))'
        if self._is_lop:
            on_created += '\nkwargs["node"].setUserData("nodeshape", "clipped_right")'

        hda_def.addSection("OnCreated", on_created)
        hda_def.setExtraFileOption("OnCreated/IsPython", True)

        editable_nodes = " ".join([node.name() for node in editable_nodes])
        hda_def.addSection("EditableNodes", editable_nodes)

        # HDA Icon
        image_file = r"D:\Developer\Pipeline\tk-houdini-renderman\images\rman_logo.svg"
        icon_section_name = "IconSVG"

        with open(image_file, "rb") as open_file:
            icon_data = open_file.read()

        hda_def.addSection(icon_section_name, icon_data)
        hda_def.setIcon(
            "opdef:{}?{}".format(hda.type().nameWithCategory(), icon_section_name)
        )

        #
        # Populate nodes
        #
        logging.debug("Adding render params")

        # HDA
        hda_parms = hda_def.parmTemplateGroup()
        rman_parms = rman.parmTemplateGroup()

        if not self._is_lop:
            hda_parms.hide(hda_parms.find("execute"), True)
            hda_parms.hide(hda_parms.find("renderdialog"), True)

        hda_parms.append(
            hou.ButtonParmTemplate(
                "executeFarm",
                "Submit to Farm",
                join_with_next=True,
                script_callback="hou.phm().render(kwargs['node'], True)",
                script_callback_language=hou.scriptLanguage.Python,
            )
        )
        hda_parms.append(
            hou.ButtonParmTemplate(
                "executeLocal",
                "Render to Disk",
                join_with_next=True,
                script_callback="hou.phm().render(kwargs['node'], False)",
                script_callback_language=hou.scriptLanguage.Python,
            )
        )
        hda_parms.append(
            hou.ButtonParmTemplate(
                "copyPathToClipboard",
                "Copy path to clipboard",
                join_with_next=True,
                script_callback="hou.phm().copy_to_clipboard(kwargs['node'])",
                script_callback_language=hou.scriptLanguage.Python,
            )
        )
        hda_parms.append(
            hou.ButtonParmTemplate(
                "openStats",
                "Open render statistics",
                script_callback="hou.phm().open_stats(kwargs['node'])",
                script_callback_language=hou.scriptLanguage.Python,
            )
        )

        hda_parms.append(
            hou.StringParmTemplate("name", "Name", 1, default_value=("main",))
        )

        if not self._is_shotgrid:
            hda_parms.append(
                hou.StringParmTemplate(
                    "basePath",
                    "Base Path",
                    1,
                    default_value=("$HIP/render/",),
                    string_type=hou.stringParmType.FileReference,
                    file_type=hou.fileType.Directory,
                )
            )
            hda_parms.append(
                hou.IntParmTemplate("version", "Version", 1, default_value=(1,), max=25)
            )

        hda_parms.append(hou.SeparatorParmTemplate("sep1"))

        if self._is_lop:
            for p in (
                "trange",
                "f",
                "foffset",
            ):
                conditional = None
                if p == "f":
                    conditional = (hou.parmCondType.DisableWhen, '{ trange == "off" }')
                if p == "foffset":
                    conditional = (
                        hou.parmCondType.DisableWhen,
                        '{ trange != "stage" }',
                    )
                self._reference_parm(node_render, hda_parms, p, conditional)

            for p in ("camera", "resolution", "resolutionMenu", "instantaneousShutter"):
                self._reference_parm(rman, hda_parms, p)

            # Aspect Ratio Folder
            aspect_ratio = hou.FolderParmTemplate(
                "aspect_ratio", "Aspect Ratio", folder_type=hou.folderType.Collapsible
            )
            for p in (
                "aspectRatioConformPolicy",
                "dataWindowNDC",
                "pixelAspectRatio",
            ):
                self._reference_parm(rman, aspect_ratio, p)
            hda_parms.append(aspect_ratio)
        else:
            for p in (
                "trange",
                "f",
                "camera",
                "override_camerares",
                "res_fraction",
                "res_override",
                "res_overrideMenu",
                "aspect_override",
            ):
                conditional = None
                if p == "f":
                    conditional = (hou.parmCondType.DisableWhen, '{ trange == "off" }')
                self._reference_parm(rman, hda_parms, p, conditional)

        # Rendering
        logging.debug("Adding rendering settings")
        rendering = hou.FolderParmTemplate("rendering", "Rendering")

        if self._is_lop:
            renderer_names = (
                "HdPrmanLoaderRendererPlugin",
                "HdPrmanXpuLoaderRendererPlugin",
                "HdPrmanXpuCpuLoaderRendererPlugin",
                "HdPrmanXpuGpuLoaderRendererPlugin",
            )
            renderer_labels = ("RIS", "XPU", "XPU - CPU", "XPU - GPU")
            rendering.addParmTemplate(
                hou.MenuParmTemplate(
                    "renderer_variant",
                    "Renderer",
                    renderer_names,
                    renderer_labels,
                    default_value=0,
                )
            )
            node_render.parm("renderer").setExpression('chs("../renderer_variant")')
        else:
            self._reference_parm(rman, rendering, "renderer_variant")

        rendering.addParmTemplate(hou.SeparatorParmTemplate("sep2"))

        if self._is_lop:
            rendering.addParmTemplate(
                hou.MenuParmTemplate(
                    "ri_hider_samplemotion",
                    "Motion Blur Type",
                    ("0", "1"),
                    ("2D Motion Blur (Motion Vectors)", "3D Motion Blur (Render)"),
                    default_value=0,
                )
            )
            self._set_parm_expression(
                rman, "ri_hider_samplemotion", 'ch("../ri_hider_samplemotion")'
            )
        else:
            for p in (
                "ri_dof",
                "allowmotionblur",
                "ri_hider_samplemotion",
                "xform_motionsamples",
                "geo_motionsamples",
                "shutteroffset",
            ):
                self._reference_parm(rman, rendering, p)
                if p == "ri_hider_samplemotion":
                    tmp = rendering.parmTemplates()
                    tmp[-1].setMenuLabels(
                        ("2D Motion Blur (Motion Vectors)", "3D Motion Blur (Render)")
                    )
                    rendering.setParmTemplates(tmp)
                if p == "geo_motionsamples":
                    tmp = rendering.parmTemplates()
                    tmp[-1].setDefaultValue((2,))
                    rendering.setParmTemplates(tmp)

            raydepth = hou.FolderParmTemplate(
                "raydepth2",
                "Default Ray Depth",
                folder_type=hou.folderType.Collapsible,
            )

            for p in ("maxdiffusedepth", "maxspeculardepth"):
                self._reference_parm(rman, raydepth, p)

            rendering.addParmTemplate(raydepth)

        for parm in rman_parms.findFolder("Rendering").parmTemplates():
            if parm.label() == "Sampling":
                tab = hou.FolderParmTemplate(
                    parm.name(),
                    parm.label(),
                )
                for p in parm.parmTemplates():
                    if p.label() not in ["Sample Motion", "Frame Number"]:
                        p.setConditional(hou.parmCondType.HideWhen, "")
                        tab.addParmTemplate(p)
                        self._link_parm(rman, p.name())

                rendering.addParmTemplate(tab)

            elif parm.label() == "Render":
                for p in parm.parmTemplates():
                    if p.label() == "Limits":
                        p.setLabel("Render Limits")
                        p.setFolderType(hou.folderType.Tabs)
                        rendering.addParmTemplate(p)
                        for pa in p.parmTemplates():
                            self._link_parm(rman, pa.name())

            elif self._is_lop and parm.label() == "Integrator":
                integrator_params: tuple[hou.ParmTemplate, ...] = parm.parmTemplates()

        # Add integrators
        logging.debug("Adding integrator settings")
        integrator_folder = hou.FolderParmTemplate("integrator_folder", "Integrator")

        it_names = [md_type[0] for md_type in integrator_list]
        it_labels = [md_type[1] for md_type in integrator_list]

        integrator_folder.addParmTemplate(
            hou.MenuParmTemplate(
                "integrator",
                "Integrator",
                tuple(it_names),
                tuple(it_labels),
                default_value=it_names.index("PxrPathTracer"),
            )
        )
        if self._is_lop:
            self._link_parm(rman, "integrator", 2)

            if integrator_params:
                parameters = []
                for parm in integrator_params:
                    if parm.name() == PARM_MAPPING["integrator"]:
                        continue
                    parameters.append(parm)

                self._link_deep_parms(rman, parameters)
                self._set_deep_conditional(
                    parameters,
                    hou.parmCondType.HideWhen,
                    lambda conditional: conditional.replace(
                        PARM_MAPPING["integrator"], "integrator"
                    ),
                )

                for parm in parameters:
                    if hou.parmCondType.HideWhen in parm.conditionals():
                        hide_when = parm.conditionals()[
                            hou.parmCondType.HideWhen
                        ].replace(PARM_MAPPING["integrator"], "integrator")
                        parm.setConditional(hou.parmCondType.HideWhen, hide_when)
                    integrator_folder.addParmTemplate(parm)
            else:
                logging.debug("Integrator parameters couldn't be found!")
                return
        else:
            rman.parm("shop_integratorpath").setExpression(
                '"../{}/" + chs("../integrator")'.format(integrators.name())
            )

            for name, label in integrator_list:
                node = integrators.node(name)
                temp = node.parmTemplateGroup().parmTemplates()
                prefix = f"{name}_"

                self._link_deep_parms(node, temp, prefix)
                self._rename_deep_parms(temp, prefix)

                for parm in temp:
                    parm.setConditional(
                        hou.parmCondType.HideWhen, "{{ integrator != {} }}".format(name)
                    )
                    integrator_folder.addParmTemplate(parm)

        rendering.addParmTemplate(integrator_folder)

        hda_parms.append(rendering)
        # End Rendering

        # AOVs
        logging.debug("Adding AOV settings")
        aovs_folder = hou.FolderParmTemplate("aovs", "AOVs")

        aovs_folder.addParmTemplate(
            hou.ButtonParmTemplate(
                "setupAOVs",
                "Setup AOV's",
                script_callback="hou.phm().setup_aovs(kwargs['node'])",
                script_callback_language=hou.scriptLanguage.Python,
            )
        )
        aovs_folder.addParmTemplate(hou.ToggleParmTemplate("autocrop", "Autocrop"))
        aovs_folder.addParmTemplate(hou.ToggleParmTemplate("denoise", "Denoise"))
        if self._is_lop:
            rman.parm("enableDenoise").setExpression('ch("../denoise")')
        else:
            self._reference_parm(
                denoise,
                aovs_folder,
                "mode",
                (hou.parmCondType.HideWhen, "{ denoise == 0 }"),
            )
        aovs_folder.addParmTemplate(hou.SeparatorParmTemplate("sep3"))
        self._add_output_file(OutputIdentifier.BEAUTY, aovs_folder)
        self._add_output_file(OutputIdentifier.DEEP, aovs_folder)

        for file in (
            OutputIdentifier.SHADING,
            OutputIdentifier.LIGHTING,
            OutputIdentifier.UTILITY,
            OutputIdentifier.CRYPTOMATTE,
        ):
            folder = hou.FolderParmTemplate(file.name, file.value)

            self._add_output_file(file, folder)

            if file == OutputIdentifier.LIGHTING:
                light_groups = hou.FolderParmTemplate(
                    "light_groups",
                    "Light Groups",
                    folder_type=hou.folderType.Simple,
                )

                light_groups.addParmTemplate(
                    hou.ButtonParmTemplate(
                        "setup_light_groups",
                        "Update light groups",
                        script_callback="hou.phm().setup_light_groups(kwargs['node'])",
                        script_callback_language=hou.scriptLanguage.Python,
                    )
                )

                light_group_item = hou.FolderParmTemplate(
                    "light_groups_select",
                    "Light Groups",
                    folder_type=hou.folderType.MultiparmBlock,
                )
                light_group_name = hou.StringParmTemplate(
                    "light_group_name_#",
                    "Name",
                    1,
                    string_type=hou.stringParmType.Regular,
                    naming_scheme=hou.parmNamingScheme.Base1,
                )

                light_operator_list = hou.StringParmTemplate(
                    "select_light_ops_#",
                    f"Select Light {'L' if self._is_lop else ''}OPs",
                    1,
                    string_type=hou.stringParmType.NodeReferenceList,
                    naming_scheme=hou.parmNamingScheme.Base1,
                    tags={
                        "opfilter": f"!!{'LOP' if self._is_lop else 'OBJ/LIGHT'}!!",
                        "oprelative": ".",
                    },
                )

                light_group_item.addParmTemplate(light_group_name)
                light_group_item.addParmTemplate(light_operator_list)
                light_group_item.addParmTemplate(hou.SeparatorParmTemplate("lgSep#"))

                light_groups.addParmTemplate(light_group_item)
                folder.addParmTemplate(light_groups)

            if file == OutputIdentifier.UTILITY:
                folder.addParmTemplate(hou.SeparatorParmTemplate("sep5"))
                aovs_tee = hou.FolderParmTemplate(
                    "tees",
                    "Shading AOVs (Tee)",
                    folder_type=hou.folderType.MultiparmBlock,
                )
                aovs_tee.addParmTemplate(
                    hou.MenuParmTemplate(
                        "teeType_#",
                        "",
                        ("color", "float", "integer", "vector", "normal", "point"),
                        ("Color", "Float", "Integer", "Vector", "Normal", "Point"),
                        join_with_next=True,
                        is_label_hidden=True,
                    )
                )
                aovs_tee.addParmTemplate(
                    hou.StringParmTemplate("teeName_#", "    Name", 1)
                )
                folder.addParmTemplate(aovs_tee)
                tee_msg = hou.LabelParmTemplate(
                    "teeInfo",
                    "Info",
                    column_labels=(
                        "Use a PxrTee node in your shader to export a specific shading step.\n"
                        "If you want to export something that isn't directly put into the shader, input the tee node "
                        "into the userColor input.\n"
                        "Use the PxrArithmetic node to combine multiple Tee nodes for export.",
                    ),
                )
                tee_msg.setLabelParmType(hou.labelParmType.Message)
                folder.addParmTemplate(tee_msg)

            # Add custom aovs block
            if file != OutputIdentifier.CRYPTOMATTE:
                self._setup_custom_aovs(folder)

            aovs_folder.addParmTemplate(folder)

        # Metadata
        logging.debug("Adding metadata settings")

        metadata_folder = hou.FolderParmTemplate("metadata", "Metadata")
        metadata_folder.addParmTemplate(self._get_metadata_block())

        aovs_folder.addParmTemplate(metadata_folder)

        hda_parms.append(aovs_folder)
        # End AOVs

        # Objects
        if not self._is_lop:
            logging.debug("Adding object settings")

            hda_parms.addParmTemplate(rman_parms.findFolder("Objects"))
            for parm in rman_parms.findFolder("Objects").parmTemplates():
                self._link_parm(rman, parm.name())

        hda_def.setParmTemplateGroup(hda_parms)

        hda_def.save(hda_def.libraryFilePath(), hda, hda_options)

        logging.debug("Saved hda")


if __name__ == "__main__":
    CreateOtl(OTLTypes.DRIVER).build()
    CreateOtl(OTLTypes.DRIVER_SG).build()
    CreateOtl(OTLTypes.LOP).build()
    CreateOtl(OTLTypes.LOP_SG).build()
