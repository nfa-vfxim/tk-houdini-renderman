import json
import os

import hou


def render(on_farm=False):
    import sgtk

    eng = sgtk.platform.current_engine()
    app = eng.apps["tk-houdini-renderman"]
    current_node = hou.pwd()

    if not setupAOVs(False):
        return

    if on_farm:
        app.submit_to_farm(current_node, "rop")
    else:
        app.execute_render(current_node, "rop")


def copy_to_clipboard():
    import sgtk

    eng = sgtk.platform.current_engine()
    app = eng.apps["tk-houdini-renderman"]
    current_node = hou.pwd()
    app.copy_to_clipboard(current_node.node("render"), "rop")

    hou.ui.displayMessage("Copied path to clipboard.")


def setupAOVs(show_notif=True):
    import sgtk

    eng = sgtk.platform.current_engine()
    app = eng.apps["tk-houdini-renderman"]

    hda = hou.pwd()
    rman = hda.node("render")

    if not app.validate_node(hda, "rop"):
        return False

    denoise = hda.node("denoise")
    use_denoise = hda.evalParm("denoise")

    beauty = hda.evalParm("aovBeauty")
    deep = hda.evalParm("aovDeep")

    aovs = hda.parmsInFolder(("AOVs",))

    crypto = list(
        filter(lambda parm: "Crypto" in parm.name() and parm.eval() == 1, aovs)
    )

    def make_lightgroups(use_node):
        light_group = hda.parm(use_node.name().replace("Use", ""))
        return light_group.parmTemplate().label(), light_group.eval()

    lightgroups = list(
        map(
            make_lightgroups,
            list(
                filter(lambda parm: "LGUse" in parm.name() and parm.eval() == 1, aovs)
            ),
        )
    )

    tee_count = hda.evalParm("tees")

    shading = hda.parmsInFolder(("AOVs", "Shading"))
    shading = list(
        filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, shading)
    )

    lighting = hda.parmsInFolder(("AOVs", "Lighting"))
    lighting = list(
        filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, lighting)
    )

    utility = hda.parmsInFolder(("AOVs", "Utility"))
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
    autocrop = hda.evalParm("autocrop")
    if autocrop:
        for i in range(file_count):
            rman.parm("ri_autocrop_" + str(i)).set("true")

    # Denoise
    denoise.parm("output").set(os.path.dirname(app.get_output_path(hda, "denoise")))

    # Statistics
    rman.parm("ri_statistics_xmlfilename").set(
        app.get_output_path(hda, "stats")[:-3] + "xml"
    )

    # TODO add custom aovs
    # 0: Beauty 16 bit DWAa
    # 1: Shading 16 bit DWAa
    # 2: Lighting 16 bit DWAa
    # 3: Utility 32 bit ZIP
    # 4: Deep
    i = 0
    if beauty:
        rman.parm("ri_display_" + str(i)).set(app.get_output_path(hda, "beauty"))

        rman.parm("ri_asrgba_" + str(i)).set(not use_denoise)
        rman.parm("ri_exrcompression_" + str(i)).set("dwaa")
        rman.parm("ri_denoiseon_" + str(i)).set(use_denoise)

        i += 1
    if len(shading):
        shading = list(map(lambda p: p.name().replace("aov", ""), shading))

        rman.parm("ri_display_" + str(i)).set(app.get_output_path(hda, "beauty"))
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
        rman.parm("ri_quickaov_indirectSpecular_" + str(i)).set("Specular" in shading)
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

        rman.parm("ri_display_" + str(i)).set(app.get_output_path(hda, "lighting"))
        rman.parm("ri_asrgba_" + str(i)).set(0)
        rman.parm("ri_exrcompression_" + str(i)).set("dwaa")
        rman.parm("ri_denoiseon_" + str(i)).set(use_denoise)

        rman.parm("ri_quickaov_Ci_" + str(i)).set(0)
        rman.parm("ri_quickaov_a_" + str(i)).set(0)

        rman.parm("ri_quickaov_occluded_" + str(i)).set("ShadowOccluded" in lighting)
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

        rman.parm("ri_display_" + str(i)).set(app.get_output_path(hda, "utility"))
        rman.parm("ri_asrgba_" + str(i)).set(0)
        rman.parm("ri_exrpixeltype_" + str(i)).set("float")

        rman.parm("ri_quickaov_Ci_" + str(i)).set(0)
        rman.parm("ri_quickaov_a_" + str(i)).set(0)

        rman.parm("ri_quickaov_curvature_" + str(i)).set("Pworld" in utility)
        rman.parm("ri_quickaov_dPdtime_" + str(i)).set("DTime" in utility)
        rman.parm("ri_quickaov_dPcameradtime_" + str(i)).set("CameraDTime" in utility)

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
                hda.parm("teeType_" + str(j + 1)).evalAsString()
            )
            rman.parm("ri_aovvariable_" + str(i) + "_" + str(j)).set(
                hda.evalParm("teeName_" + str(j + 1))
            )

        i += 1
    if deep:
        rman.parm("ri_display_" + str(i)).set(app.get_output_path(hda, "deep"))
        rman.parm("ri_device_" + str(i)).set("deepexr")

    # CRYPTOMATTE
    rman.parm("ri_samplefilters").set(len(crypto))
    for i, c in enumerate(crypto):
        name = c.name()[3:]
        cPath = "../aovs/" + name
        rman.parm("ri_samplefilter" + str(i)).set(cPath)
        hda.parm("./aovs/" + name + "/filename").set(app.get_output_path(hda, name))

    # METADATA
    md_config = app.get_metadata_config()

    md_config_groups = {}
    for md in md_config:
        group = md.get("group")
        if md_config_groups.get(group):
            md_config_groups.get(group).append(md.get("key"))
        else:
            md_config_groups[group] = [md.get("key")]
    md_config_groups = json.dumps(md_config_groups)

    md_count_node = hda.evalParm("ri_exr_metadata") + (len(lightgroups) > 0)
    md_count_external = len(md_config)
    md_lg = {}
    md_lg.update(lg for lg in lightgroups)
    md_lg = json.dumps(md_lg)
    md_parms = list(
        filter(
            lambda parm: "exr_metadata" in parm.name()
            and parm.name() != "ri_exr_metadata",
            hda.parms(),
        )
    )

    for f in range(file_count):
        rman.parm("ri_exr_metadata_{}".format(f)).set(
            md_count_node + md_count_external + (len(md_config) > 0)
        )

        rman.parm("ri_image_Artist_{}".format(f)).set(str(app.context.user["id"]))
        for parm in md_parms:
            name = parm.name().split("_")
            index = -1
            if name[-1] == "":
                index = -2
            name.insert(index, str(f))
            name = "_".join(name)
            __set_expression(rman, parm.name(), name)

        if len(lightgroups):
            rman.parm("ri_exr_metadata_key_{}_{}".format(f, md_count_node - 1)).set(
                "rmd_RenderLightGroups"
            )
            rman.parm("ri_exr_metadata_type_{}_{}".format(f, md_count_node - 1)).set(
                "string"
            )
            rman.parm("ri_exr_metadata_string_{}_{}_".format(f, md_count_node - 1)).set(
                md_lg
            )

        for i in range(md_count_external):
            item = md_config[i]
            rman.parm("ri_exr_metadata_key_{}_{}".format(f, md_count_node + i)).set(
                "rmd_{}".format(item.get("key"))
            )
            rman.parm("ri_exr_metadata_type_{}_{}".format(f, md_count_node + i)).set(
                item.get("type")
            )
            rman.parm(
                "ri_exr_metadata_{}_{}_{}_".format(
                    item.get("type"), f, md_count_node + i
                )
            ).setExpression(item.get("expression"))

        rman.parm(
            "ri_exr_metadata_key_{}_{}".format(f, md_count_node + md_count_external)
        ).set("rmd_PostRenderGroups")
        rman.parm(
            "ri_exr_metadata_type_{}_{}".format(f, md_count_node + md_count_external)
        ).set("string")
        rman.parm(
            "ri_exr_metadata_string_{}_{}_".format(f, md_count_node + md_count_external)
        ).set(md_config_groups)

    msg = "Setup AOVs complete with " + str(file_count + len(crypto)) + " files."
    if show_notif:
        hou.ui.displayMessage(msg)
    print("[RenderMan Renderer] " + msg)

    return True


def get_render_paths():
    import sgtk

    eng = sgtk.platform.current_engine()
    app = eng.apps["tk-houdini-renderman"]

    paths = []

    hda = hou.pwd()

    aovs = hda.parmsInFolder(("AOVs",))

    crypto = list(
        filter(lambda parm: "Crypto" in parm.name() and parm.eval() == 1, aovs)
    )

    lightgroups = list(
        filter(lambda parm: "LGUse" in parm.name() and parm.eval() == 1, aovs)
    )

    shading = hda.parmsInFolder(("AOVs", "Shading"))
    shading = list(
        filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, shading)
    )

    lighting = hda.parmsInFolder(("AOVs", "Lighting"))
    lighting = list(
        filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, lighting)
    )

    utility = hda.parmsInFolder(("AOVs", "Utility"))
    utility = list(
        filter(lambda parm: "aov" in parm.name() and parm.eval() == 1, utility)
    )

    if hda.evalParm("aovBeauty"):
        paths.append(app.get_output_path(hda, "beauty"))
    if len(shading):
        paths.append(app.get_output_path(hda, "beauty"))
    if len(lighting) or len(lightgroups):
        paths.append(app.get_output_path(hda, "lighting"))
    if len(utility) or hda.evalParm("tees"):
        paths.append(app.get_output_path(hda, "utility"))
    if hda.evalParm("aovDeep"):
        paths.append(app.get_output_path(hda, "deep"))

    # Cryptomatte
    for i, c in enumerate(crypto):
        name = c.name()[3:]
        paths.append(app.get_output_path(hda, name))

    # Denoise
    if hda.evalParm("denoise"):
        paths.append(os.path.dirname(app.get_output_path(hda, "denoise")))

    # Statistiscs
    paths.append(app.get_output_path(hda, "stats")[:-3] + "xml")

    return paths


def __set_expression(node, source_parm, dist_parm):
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


def open_stats():
    rman = hou.pwd().node("render")
    file_path = rman.evalParm("ri_statistics_xmlfilename")

    if os.path.exists(file_path):
        for pane in hou.ui.curDesktop().panes():
            if not pane.isSplitMinimized():
                pane = pane.createTab(hou.paneTabType.HelpBrowser)
                pane.setUrl(file_path)
                return
    else:
        raise Exception("Statistics file doesn't exist (yet)!")
