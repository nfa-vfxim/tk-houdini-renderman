from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union

import hou


# 0: Beauty 16 bit DWAa
# 1: Shading 16 bit DWAa
# 2: Lighting 16 bit DWAa
# 3: Utility 32 bit ZIP
# 4: Deep
# X: Denoise
# X: Cryptomatte
class OutputIdentifier(str, Enum):
    """Identifier for an OutputFile"""

    BEAUTY = "Beauty"
    SHADING = "Shading"
    LIGHTING = "Lighting"
    UTILITY = "Utility"
    DEEP = "Deep"
    CRYPTOMATTE = "Cryptomatte"


class Bitdepth(str, Enum):
    """Bitdepth of OutputFile"""

    HALF = "half"
    FULL = "float"


class Compression(str, Enum):
    """Compression of OutputFile"""

    ZIPS = "zips"
    DWAA = "dwaa"


@dataclass
class AOVOption:
    key: str
    name: str
    aovs: Optional[list[str]] = field(default_factory=list)
    default_value: Optional[bool] = False
    group: Optional[str] = None

    def __repr__(self):
        return f"<AOVOption {self.key}>"

    def get_parm_name(self) -> str:
        """
        Get the parm name of this AOVOption

        Returns:
            str: Parm name
        """
        if self.group:
            return f"{self.group}_{self.key}"
        return self.key

    def is_active(self, node: hou.Node) -> bool:
        return node.parm(self.get_parm_name()).eval() == 1


@dataclass
class AOVSeparator:
    key: str


@dataclass
class CustomAOV:
    name: str
    type: str
    lpe: str

    def get_format(self):
        if self.type == "color":
            return "color3f"
        if self.type == "float":
            return "float"
        if self.type == "integer":
            return "int"
        if self.type == "vector" or self.type == "normal" or self.type == "point":
            return "color3f"


@dataclass
class OutputFile:
    identifier: OutputIdentifier
    as_rgba: bool
    bitdepth: Bitdepth
    compression: Compression
    options: Optional[list[Union[AOVOption, AOVSeparator]]]
    notes: Optional[dict] = field(default_factory=dict)
    has_custom: Optional[bool] = False
    can_denoise: Optional[bool] = True

    def __repr__(self):
        return f"<OutputFile {self.identifier} ({self.bitdepth}, {self.compression}): {self.options}>"

    def has_active_aovs(self, node: hou.Node) -> bool:
        for option in self.options:
            if type(option) is not AOVSeparator:
                if option.is_active(node):
                    return True

        return False

    def has_active_custom_aovs(self, node: hou.Node) -> bool:
        if self.has_custom:
            name = self.identifier
            count = node.parm(f"{name.lower()}CustomAOVs").eval()
            for i in range(1, count + 1):
                if not node.parm(f"aov{name}CustomDisable_{i}").evalAsInt():
                    return True

        return False

    def get_active_custom_aovs(self, node: hou.Node) -> list[CustomAOV]:
        aovs = []
        if self.has_custom:
            name = self.identifier
            count = node.parm(f"{name.lower()}CustomAOVs").eval()
            for i in range(1, count + 1):
                if not node.parm(f"aov{name}CustomDisable_{i}").evalAsInt():
                    aov_name = node.parm(f"aov{name}CustomName_{i}").evalAsString()
                    aov_type = node.parm(f"aov{name}CustomSource_{i}").evalAsString()
                    aov_value = node.parm(f"aov{name}CustomLPE_{i}").evalAsString()

                    if " " in aov_name:
                        raise Exception(
                            f'A custom aov under {name} has an invalid name: "{aov_name}"'
                        )

                    aovs.append(CustomAOV(aov_name, aov_type, aov_value))

        is_lop = isinstance(node, hou.LopNode)

        # Add light groups to custom AOVs if Lighting file
        if self.identifier == OutputIdentifier.LIGHTING:
            light_group_count = node.parm("light_groups_select").eval()

            for j in range(1, light_group_count + 1):
                light_group_name = node.parm(f"light_group_name_{j}").eval()

                prefix = "" if is_lop else "color lpe:"

                aovs.append(
                    CustomAOV(
                        f"LG_{light_group_name}",
                        "color",
                        f"{prefix}C.*<L.'LG_{light_group_name}'>",
                    )
                )

        # Add tees to custom AOVs if Utility file
        if self.identifier == OutputIdentifier.UTILITY:
            tee_count = node.parm("tees").eval()

            for j in range(1, tee_count + 1):
                tee_name = node.parm(f"teeName_{j}").eval()
                aovs.append(
                    CustomAOV(
                        tee_name,
                        node.parm(f"teeType_{j}").evalAsString(),
                        tee_name if is_lop else "",
                    )
                )

        return aovs

    def get_aovs(self):
        aovs = []
        for option in self.options:
            if type(option) is not AOVSeparator:
                aovs += option.aovs

        return aovs

    def get_active_aovs(self, node: hou.Node) -> list[str]:
        active_aovs = []
        for option in self.options:
            if type(option) is not AOVSeparator:
                if option.is_active(node):
                    active_aovs += option.aovs

        return active_aovs

    def get_inactive_aovs(self, node: hou.Node) -> list[str]:
        inactive_aovs = []
        for option in self.options:
            if type(option) is not AOVSeparator:
                if not option.is_active(node):
                    inactive_aovs += option.aovs

        return inactive_aovs


output_files = [
    OutputFile(
        OutputIdentifier.BEAUTY,
        True,
        Bitdepth.HALF,
        Compression.DWAA,
        [AOVOption("beauty", "Beauty + Alpha", ["Ci", "a"], True)],
    ),
    OutputFile(
        OutputIdentifier.SHADING,
        False,
        Bitdepth.HALF,
        Compression.DWAA,
        [
            AOVOption("albedo", "Albedo", ["albedo"]),
            AOVOption("emissive", "Emissive", ["emissive"]),
            AOVOption(
                "diffuse", "(In)direct Diffuse", ["directDiffuse", "indirectDiffuse"]
            ),
            AOVOption(
                "diffuseU",
                "(In)direct Diffuse Unoccluded",
                ["directDiffuseUnoccluded", "indirectDiffuseUnoccluded"],
            ),
            AOVOption(
                "specular",
                "(In)direct Specular",
                ["directSpecular", "indirectSpecular"],
            ),
            AOVOption(
                "specularU",
                "(In)direct Specular Unoccluded",
                ["directSpecularUnoccluded", "indirectSpecularUnoccluded"],
            ),
            AOVOption("subsurface", "Subsurface", ["albedo"]),
            AOVOption(
                "diffuse",
                "(In)direct Diffuse",
                ["directDiffuseLobe", "indirectDiffuseLobe"],
                group="lobes",
            ),
            AOVOption(
                "specularPrimary",
                "(In)direct Specular Primary",
                ["directSpecularPrimaryLobe", "indirectSpecularPrimaryLobe"],
                group="lobes",
            ),
            AOVOption(
                "specularRough",
                "(In)direct Specular Rough",
                ["directSpecularRoughLobe", "indirectSpecularRoughLobe"],
                group="lobes",
            ),
            AOVOption(
                "specularClearcoat",
                "(In)direct Specular Clearcoat",
                [
                    "directSpecularClearcoatLobe",
                    "indirectSpecularClearcoatLobe",
                ],
                group="lobes",
            ),
            AOVOption(
                "specularIridescence",
                "(In)direct Specular Iridescence",
                [
                    "directSpecularIridescenceLobe",
                    "indirectSpecularIridescenceLobe",
                ],
                group="lobes",
            ),
            AOVOption(
                "specularFuzz",
                "(In)direct Specular Fuzz",
                ["directSpecularFuzzLobe", "indirectSpecularFuzzLobe"],
                group="lobes",
            ),
            AOVOption(
                "specularGlass",
                "(In)direct Specular Glass",
                ["directSpecularGlassLobe", "indirectSpecularGlassLobe"],
                group="lobes",
            ),
            AOVOption("subsurface", "Subsurface", ["subsurfaceLobe"], group="lobes"),
            AOVOption(
                "transmissiveSingleScatter",
                "Transmissive Single Scatter",
                ["transmissiveSingleScatterLobe"],
                group="lobes",
            ),
            AOVOption(
                "transmissiveGlass",
                "Transmissive Glass",
                ["transmissiveGlassLobe"],
                group="lobes",
            ),
        ],
        has_custom=True,
    ),
    OutputFile(
        OutputIdentifier.LIGHTING,
        False,
        Bitdepth.HALF,
        Compression.DWAA,
        [
            AOVOption("shadowOccluded", "Occluded", ["occluded"], group="shadow"),
            AOVOption("shadowUnoccluded", "Unoccluded", ["unoccluded"], group="shadow"),
            AOVOption("shadow", "Shadow", ["shadow"], group="shadow"),
        ],
        notes={
            "shadow": "Enable the Holdout tag for an object to show up in the shadow AOVs",
        },
        has_custom=True,
    ),
    OutputFile(
        OutputIdentifier.UTILITY,
        False,
        Bitdepth.FULL,
        Compression.ZIPS,
        [
            AOVOption("curvature", "Curvature", ["curvature"]),
            AOVOption("motionVector", "Motion Vector World Space", ["dPdtime"]),
            AOVOption(
                "motionVectorCamera",
                "Motion Vector Camera Space",
                ["dPcameradtime"],
            ),
            AOVSeparator("sep1"),
            AOVOption("pWorld", "Position (world-space)", ["__Pworld"]),
            AOVOption("nWorld", "Normal (world-space)", ["__Nworld"]),
            AOVOption(
                "depthAA",
                "Depth (Anti-Aliased) + Facing Ratio",
                ["__depth"],
            ),
            AOVOption("depth", "Depth (Aliased)", ["z"]),
            AOVOption("st", "Texture Coordinates (UV maps)", ["__st"]),
            AOVOption("pRef", "Reference Position", ["__Pref"]),
            AOVOption("nRef", "Reference Normal", ["__Nref"]),
            AOVOption("pRefWorld", "Reference World Position", ["__WPref"]),
            AOVOption("nRefWorld", "Reference World Normal", ["__WNref"]),
        ],
        has_custom=True,
        can_denoise=False,
    ),
    OutputFile(
        OutputIdentifier.DEEP,
        True,
        Bitdepth.HALF,
        Compression.DWAA,
        [
            AOVOption(
                "deep",
                "Deep",
                ["Ci", "a"],
            ),
        ],
        can_denoise=False,
    ),
    OutputFile(
        OutputIdentifier.CRYPTOMATTE,
        False,
        Bitdepth.HALF,
        Compression.ZIPS,
        [
            AOVOption("cryptoMaterial", "Material", ["user:__materialid"]),
            AOVOption("cryptoName", "Name", ["identifier:object"]),
            AOVOption("cryptoPath", "Path", ["identifier:name"]),
        ],
    ),
]
