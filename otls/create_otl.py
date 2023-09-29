import os
import re
import xml.etree.ElementTree as ET

import hou


# Run from Houdini python shell to build HDAs:
# exec(open(r"D:\Developer\Pipeline\tk-houdini-renderman\otls\create_otl.py").read())


#
# Functions
#
def convert_naming_scheme(naming_scheme):
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


def link_parm(origin, parm_name, level=1, prepend="", append=""):
    org_parm = origin.parmTemplateGroup().find(parm_name)
    if not org_parm:
        print("parm not found: ", parm_name)
        return

    parm_type = "ch"
    if org_parm.dataType() == hou.parmData.String:
        parm_type = "chsop"

    if org_parm.numComponents() == 1:
        origin.parm(parm_name).setExpression(
            '{}("{}{}")'.format(parm_type, "../" * level, prepend + parm_name + append)
        )
    else:
        scheme = convert_naming_scheme(org_parm.namingScheme())
        for i in range(org_parm.numComponents()):
            origin.parm(parm_name + scheme[i]).setExpression(
                '{}("{}{}")'.format(
                    parm_type, "../" * level, prepend + parm_name + append + scheme[i]
                )
            )


def link_deep_parms(origin, parms, prepend="", append=""):
    for parm in parms:
        if parm.type() == hou.parmTemplateType.Folder:
            link_deep_parms(origin, parm.parmTemplates(), prepend, append)
        else:
            link_parm(origin, parm.name(), 2, prepend, append)


def reference_parm(origin, dist, parm, conditional=None):
    org_parms = origin.parmTemplateGroup()
    org_parm = org_parms.find(parm)
    if not org_parm:
        print("parm not found: ", parm)
        return

    if conditional:
        org_parm.setConditional(conditional[0], conditional[1])

    if hasattr(dist, "append"):
        dist.append(org_parm)
    elif hasattr(dist, "addParmTemplate"):
        dist.addParmTemplate(org_parm)
    else:
        print("undefined method")
        return

    link_parm(origin, parm)


def rename_deep_parms(parms, prepend="", append=""):
    for parm in parms:
        parm.setName(prepend + parm.name() + append)
        if parm.type() == hou.parmTemplateType.Folder:
            renamed = rename_deep_parms(parm.parmTemplates(), prepend, append)
            parm.setParmTemplates(renamed)
    return parms


def space_camel_case(text):
    return re.sub(r"((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))", r" \1", text)


def build_aovs(folder, aovs, parm_type="toggle"):
    for aov in aovs:
        if type(aov) is tuple:
            name = aov[0]
            label = aov[1]
        else:
            name = label = aov

        if parm_type == "toggle":
            folder.addParmTemplate(hou.ToggleParmTemplate("aov{}".format(name), label))
        elif parm_type == "string":
            folder.addParmTemplate(
                hou.StringParmTemplate("aov{}".format(name), label, 1)
            )


def setup_custom_aovs(dist, name):
    disable = "{{aov{}CustomDisable_# == 1}}".format(name)
    folder = hou.FolderParmTemplate(
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

    folder.addParmTemplate(custom)
    dist.addParmTemplate(folder)


hda = hou.node("/out/SGTK_RenderMan")
if hda:
    hda.destroy()

hda = hou.node("/out/").createNode("subnet", "SGTK_RenderMan")

#
# Create nodes
#
rman = hda.createNode("ris", "render")
denoise = hda.createNode("denoise", "denoise")

integrators = hda.createNode("matnet", "integrators")
integrator_list = list()

# Find available integrators and add them
for key, value in hou.vopNodeTypeCategory().nodeTypes().items():
    name = value.nameComponents()[2]
    if "pxr" in name and value.hasSectionData("Tools.shelf"):
        if "Integrator" in ET.fromstring(value.sectionData("Tools.shelf")).find(
            "tool"
        ).findtext("toolSubmenu"):
            inte = integrators.createNode(name, name)
            integrator_list.append(
                (name, space_camel_case(value.description().replace("Pxr", "")))
            )

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

hda.layoutChildren((rman, denoise, aovs, integrators))
hda.setSelected(True)


#
# Setup RIS node
#

# Enable statistics
rman.parm("ri_statistics_level").set(True)
rman.parm("ri_statistics_texturestatslevel").set(True)

#
# Create HDA
#
hda = hou.Node.createDigitalAsset(
    hda,
    "sgtk_ris",
    r"D:\Developer\Pipeline\tk-houdini-renderman\otls\sgtk_ris.otl",
    version="25.2",
    ignore_external_references=True,
)
hda.type().setDefaultColor(hou.Color(0, 0.2, 0.3))

hda_def = hda.type().definition()
hda_options = hda_def.options()

python_module = open(
    r"D:\Developer\Pipeline\tk-houdini-renderman\otls\PythonModule.py", "r"
)
hda_def.addSection("PythonModule", python_module.read())
hda_def.setExtraFileOption("PythonModule/IsPython", True)
hda_def.addSection("OnCreated", 'kwargs["node"].setColor(hou.Color(0, 0.2, 0.3))')
hda_def.setExtraFileOption("OnCreated/IsPython", True)

hda_def.addSection("EditableNodes", "render denoise aovs")

# HDA Icon
image_file = r"D:\Developer\Pipeline\tk-houdini-renderman\images\rman_logo.svg"
suffix = os.path.splitext(image_file)[1]
icon_section_name = "IconSVG"

with open(image_file, "rb") as open_file:
    icon_data = open_file.read()

hda_def.addSection(icon_section_name, icon_data)
hda_def.setIcon("opdef:{}?{}".format(hda.type().nameWithCategory(), icon_section_name))

#
# Populate nodes
#

# HDA
hda_parms = hda_def.parmTemplateGroup()
rman_parms = rman.parmTemplateGroup()

hda_parms.hide(hda_parms.find("execute"), True)
hda_parms.hide(hda_parms.find("renderdialog"), True)

hda_parms.append(
    hou.ButtonParmTemplate(
        "executeFarm",
        "Submit to Farm",
        join_with_next=True,
        script_callback="hou.phm().render(True)",
        script_callback_language=hou.scriptLanguage.Python,
    )
)
hda_parms.append(
    hou.ButtonParmTemplate(
        "executeLocal",
        "Render to Disk",
        join_with_next=True,
        script_callback="hou.phm().render(False)",
        script_callback_language=hou.scriptLanguage.Python,
    )
)
hda_parms.append(
    hou.ButtonParmTemplate(
        "copyPathToClipboard",
        "Copy path to clipboard",
        join_with_next=True,
        script_callback="hou.phm().copy_to_clipboard()",
        script_callback_language=hou.scriptLanguage.Python,
    )
)
hda_parms.append(
    hou.ButtonParmTemplate(
        "openStats",
        "Open render statistics",
        script_callback="hou.phm().open_stats()",
        script_callback_language=hou.scriptLanguage.Python,
    )
)

hda_parms.append(hou.StringParmTemplate("name", "Name", 1, default_value=("main",)))

hda_parms.append(hou.SeparatorParmTemplate("sep1"))

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
    reference_parm(rman, hda_parms, p, conditional)

# Rendering
rendering = hou.FolderParmTemplate("rendering", "Rendering")

for p in ("renderer_variant",):
    reference_parm(rman, rendering, p)

rendering.addParmTemplate(hou.SeparatorParmTemplate("sep2"))

it_names = list()
it_labels = list()
for it in integrator_list:
    it_names.append(it[0])
    it_labels.append(it[1])

rendering.addParmTemplate(
    hou.MenuParmTemplate(
        "integrator",
        "Integrator",
        tuple(it_names),
        tuple(it_labels),
        default_value=it_names.index("pxrpathtracer"),
    )
)
rman.parm("shop_integratorpath").setExpression(
    '"../{}/" + chs("../integrator")'.format(integrators.name())
)

for p in (
    "ri_hider_type",
    "ri_dof",
    "allowmotionblur",
    "ri_hider_samplemotion",
    "xform_motionsamples",
    "geo_motionsamples",
    "shutteroffset",
):
    reference_parm(rman, rendering, p)
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
    "raydepth2", "Default Ray Depth", folder_type=hou.folderType.Collapsible
)

for p in ("maxdiffusedepth", "maxspeculardepth"):
    reference_parm(rman, raydepth, p)

rendering.addParmTemplate(raydepth)

for parm in rman_parms.findFolder("Rendering").parmTemplates():
    if parm.label() == "Sampling" or parm.label() == "Baking":
        rendering.addParmTemplate(parm)
        for p in parm.parmTemplates():
            link_parm(rman, p.name())
    elif parm.label() == "Render":
        for p in parm.parmTemplates():
            if p.label() == "Limits":
                p.setLabel("Render Limits")
                p.setFolderType(hou.folderType.Tabs)
                rendering.addParmTemplate(p)
                for pa in p.parmTemplates():
                    link_parm(rman, pa.name())

# Add integrators
for name, label in integrator_list:
    intf = hou.FolderParmTemplate(name, label)
    node = integrators.node(name)
    temp = node.parmTemplateGroup().parmTemplates()

    link_deep_parms(node, temp, name + "_")
    rename_deep_parms(temp, name + "_")

    intf.setParmTemplates(temp)
    intf.setTabConditional(
        hou.parmCondType.HideWhen, "{{ integrator != {} }}".format(name)
    )
    rendering.addParmTemplate(intf)

hda_parms.append(rendering)
# End Rendering

# AOVs
aovs_folder = hou.FolderParmTemplate("aovs", "AOVs")

aovs_folder.addParmTemplate(
    hou.ButtonParmTemplate(
        "setupAOVs",
        "Setup AOV's",
        script_callback="hou.phm().setupAOVs()",
        script_callback_language=hou.scriptLanguage.Python,
    )
)
aovs_folder.addParmTemplate(hou.ToggleParmTemplate("autocrop", "Autocrop"))
aovs_folder.addParmTemplate(hou.ToggleParmTemplate("denoise", "Denoise"))
reference_parm(
    denoise, aovs_folder, "mode", (hou.parmCondType.HideWhen, "{ denoise == 0 }")
)
aovs_folder.addParmTemplate(hou.SeparatorParmTemplate("sep3"))
beauty = hou.ToggleParmTemplate("aovBeauty", "Beauty + Alpha")
beauty.setDefaultValue(True)
aovs_folder.addParmTemplate(beauty)
aovs_folder.addParmTemplate(hou.ToggleParmTemplate("aovDeep", "Deep"))

aovs_shading = hou.FolderParmTemplate("shading", "Shading")
shading_aovs = (
    "Albedo",
    "Emissive",
    ("Diffuse", "(In)direct Diffuse"),
    ("DiffuseU", "(In)direct Diffuse Unoccluded"),
    ("Specular", "(In)direct Specular"),
    ("SpecularU", "(In)direct Specular Unoccluded"),
    "Subsurface",
)
build_aovs(aovs_shading, shading_aovs)
aovs_shading_lobes = hou.FolderParmTemplate(
    "shadingLobes", "Lobes", folder_type=hou.folderType.Simple
)
shading_lobes_aovs = (
    ("LobeDiffuse", "(In)direct Diffuse"),
    ("LobeSpecularPrimary", "(In)direct Specular Primary"),
    ("LobeSpecularRough", "(In)direct Specular Rough"),
    ("LobeSpecularClearcoat", "(In)direct Specular Clearcoat"),
    ("LobeSpecularIridescence", "(In)direct Specular Iridescence"),
    ("LobeSpecularFuzz", "(In)direct Specular Fuzz"),
    ("LobeSpecularGlass", "(In)direct Specular Glass"),
    ("LobeSubsurface", "Subsurface"),
    ("LobeTransmissiveSingleScatter", "Transmissive Single Scatter"),
    ("LobeTransmissiveGlass", "Transmissive Glass"),
)
build_aovs(aovs_shading_lobes, shading_lobes_aovs)
aovs_shading.addParmTemplate(aovs_shading_lobes)

setup_custom_aovs(aovs_shading, "Shading")
aovs_folder.addParmTemplate(aovs_shading)

# Lighting
aovs_lighting = hou.FolderParmTemplate("lighting", "Lighting")

aovs_lighting_shadow = hou.FolderParmTemplate(
    "lightingShadow", "Shadow", folder_type=hou.folderType.Simple
)
shadow_msg = hou.LabelParmTemplate(
    "shadowInfo",
    "Info",
    column_labels=(
        "Enable the Holdout tag for an object to show " "up in the shadow aovs",
    ),
)
shadow_msg.setLabelParmType(hou.labelParmType.Message)
aovs_lighting_shadow.addParmTemplate(shadow_msg)
shadow_aovs = (
    ("ShadowOccluded", "Occluded"),
    ("ShadowUnoccluded", "Unoccluded"),
    ("Shadow", "Shadow"),
)
build_aovs(aovs_lighting_shadow, shadow_aovs)
aovs_lighting.addParmTemplate(aovs_lighting_shadow)

aovs_lighting_groups = hou.FolderParmTemplate(
    "lightingGroups", "Light Groups", folder_type=hou.folderType.Simple
)
lg_aovs = list(map(lambda x: "Cat" + chr(x), range(65, 75)))
lg_aovs.insert(0, "EyeReflection")
for lg in lg_aovs:
    aovs_lighting_groups.addParmTemplate(
        hou.ToggleParmTemplate(
            "aovLGUse{}".format(lg), "", is_label_hidden=True, join_with_next=True
        )
    )
    aovs_lighting_groups.addParmTemplate(
        hou.StringParmTemplate(
            "aovLG{}".format(lg),
            lg,
            1,
            default_value=(lg,),
            disable_when="{{aovLGUse{} == 0}}".format(lg),
        )
    )

aovs_lighting.addParmTemplate(aovs_lighting_groups)

setup_custom_aovs(aovs_lighting, "Lighting")
aovs_folder.addParmTemplate(aovs_lighting)
# End Lighting

aovs_utility = hou.FolderParmTemplate("utility", "Utility")
utility_aovs1 = (
    "Curvature",
    ("DTime", "Motion Vector"),
    ("CameraDTime", "Motion Vector Camera"),
)
build_aovs(aovs_utility, utility_aovs1)
aovs_utility.addParmTemplate(hou.SeparatorParmTemplate("sep4"))
utility_aovs2 = (
    ("Pworld", "P World"),
    ("Nworld", "N World"),
    ("Depth", "Depth (Anti-Aliased)"),
    ("z", "Depth (Aliased)"),
    ("ST", "ST (UV)"),
    ("Pref", "P Ref"),
    ("Nref", "N Ref"),
    ("WPref", "P Ref World"),
    ("WNref", "N Ref World"),
)
build_aovs(aovs_utility, utility_aovs2)

aovs_utility.addParmTemplate(hou.SeparatorParmTemplate("sep5"))
aovs_tee = hou.FolderParmTemplate(
    "tees", "Shading AOVs (Tee)", folder_type=hou.folderType.MultiparmBlock
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
aovs_tee.addParmTemplate(hou.StringParmTemplate("teeName_#", "    Name", 1))
aovs_utility.addParmTemplate(aovs_tee)
tee_msg = hou.LabelParmTemplate(
    "teeInfo",
    "Info",
    column_labels=(
        "Use a PxrTee node in your shader to export a "
        "specific shading step.\
If you want to export something that isn't directly put into the shader, input the tee node into the userColor input.\
Use the PxrArithmetic node to combine multiple Tee nodes for export.",
    ),
)
tee_msg.setLabelParmType(hou.labelParmType.Message)
aovs_utility.addParmTemplate(tee_msg)

setup_custom_aovs(aovs_utility, "Utility")

aovs_folder.addParmTemplate(aovs_utility)

aovs_crypto = hou.FolderParmTemplate("crypto", "Cryptomatte")
crypto_aovs = (
    ("CryptoMaterial", "Material"),
    ("CryptoName", "Name"),
    ("CryptoPath", "Path"),
)
build_aovs(aovs_crypto, crypto_aovs)
aovs_folder.addParmTemplate(aovs_crypto)

aovs_metadata = hou.FolderParmTemplate("metadata", "Metadata")
for parm in rman_parms.findFolder("Images").parmTemplates():
    if parm.label() == "Displays":
        for p in parm.parmTemplates():
            if p.label() == "Meta Data":
                for p2 in p.parmTemplates():
                    if p2.label() == "Metadata":
                        p2.setConditional(hou.parmCondType.HideWhen, "")
                        p2.setName(p2.name()[:-2])
                        temp = p2.parmTemplates()
                        for p3 in temp:
                            p3.setName(p3.name().replace("_#_#", "_#"))
                            cond = p3.conditionals().get(hou.parmCondType.HideWhen)
                            if cond:
                                p3.setConditional(
                                    hou.parmCondType.HideWhen,
                                    cond.replace("_#_#", "_#"),
                                )
                        p2.setParmTemplates(temp)
                        aovs_metadata.addParmTemplate(p2)
aovs_folder.addParmTemplate(aovs_metadata)

hda_parms.append(aovs_folder)
# End AOVs

# Objects
hda_parms.addParmTemplate(rman_parms.findFolder("Objects"))
for parm in rman_parms.findFolder("Objects").parmTemplates():
    link_parm(rman, parm.name())

hda_def.setParmTemplateGroup(hda_parms)


hda_def.save(hda_def.libraryFilePath(), hda, hda_options)
