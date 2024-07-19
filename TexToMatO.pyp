PLUGIN_ID = 1061499

import typing
import c4d
from c4d import gui
import webbrowser
from typing import Optional
import os
import sys
import maxon
import glob
import errno
import re
import json
from ctypes import pythonapi, c_int, py_object

def decodeMessage(message): # As taken from https://developers.maxon.net/docs/Cinema4DPythonSDK/html/manuals/misc/python3_migration.html
    pythonapi.PyCapsule_GetPointer.restype = c_int
    pythonapi.PyCapsule_GetPointer.argtypes = [py_object]
    return pythonapi.PyCapsule_GetPointer(message.GetVoid(c4d.BFM_CORE_PAR1), None)

_path_ = os.path.dirname(__file__).replace("\\", "/")
if _path_ not in sys.path:
    sys.path.append( _path_ )

def ReadJSON(file_to_read, backup_file = None):
    try:
        with open(_path_ + file_to_read, "r") as read_file:
            return json.load(read_file)
    except FileNotFoundError:
        with open(_path_ + backup_file, "r") as backup_read_file:
            return json.load(backup_read_file)

import custom_redshift_api.redshift_node as rs
import custom_redshift_api.redshift_ID as rsID
_RS_NODE_PREFIX = rsID.RS_SHADER_PREFIX


doc: c4d.documents.BaseDocument  # The active document
op: Optional[c4d.BaseObject]  # The active object, None if unselected

doc = None

multitex_channels = [" ", "AO", "Glossiness", "Metalness", "Opacity", "Roughness", "Specular"]
multitex_dict = {"BASE": " ", "R": " ", "G": " ", "B": " "}

# TODO: Add undo --- Deferred until I find a way to manually set the position of nodes
# TODO: Add functionality to exclude specific channel names from the regex

# TODO HIGH: Add default toggle to delete and create a new material

##########################################################################
##                                                                      ##
##                               LOGIC                                  ##
##                                                                      ##
##########################################################################

def init_channels(custom_regex_dict, case_insensitive = False):
    global image_extensions
    global color_channel
    global normal_channel
    global ao_channel
    global metalness_channel
    global roughness_channel
    global specular_channel
    global glossiness_channel
    global opacity_channel
    global translucency_channel
    global displacement_channel
    global misc_channel
    global all_channels
    global channels_regex

    channels_dict = {
        "image_extensions":         ["png", "jpeg", "jpg", "dds", "tga", "tif", "tiff", "bmp", "exr"],
        "color_channel":            ["Base_Color", "BaseColor", "basecolor", "color", "COL", "Color", "Albedo", "albedo", "col", "Base", "diff", "_D-", "_D."],
        "normal_channel":           ["Normal_OpenGL", "normal", "NRM", "Normal", "nml", "nrml", "Norm", "_N.", "_N("],
        "ao_channel":               ["Mixed_AO", "ao", "AO"],
        "metalness_channel":        ["Metallic", "Meta", "_M.", "_metal."],
        "roughness_channel":        ["Roughness", "roughness", "Roug", "_R.", "_rough."],
        "specular_channel":         ["Specular", "specular", "_S."],
        "glossiness_channel":       ["GLOSS", "glossiness", "gloss"],
        "opacity_channel":          ["opacity", "alpha", "opac", "_O.", "Opacity"],
        "translucency_channel":     ["_L.", "_L_", "Translucency", "Transmission"],
        "displacement_channel":     ["height", "DISP", "Displacement", "depth"],
        "misc_channel":             ["soft-mask", "color-mask", "mix-mask", "tint-mask", "paint-mask", "mask", "_M(", "_MSK", "OVERLAY", "blend"]
    }
    
    if custom_regex_dict:
        for key, value in custom_regex_dict.items():
            channels_dict[key] += value
    
    if case_insensitive:
        channels_dict = {key: [element.lower() for element in value] for key, value in channels_dict.items()}

    image_extensions = channels_dict["image_extensions"]
    color_channel = channels_dict["color_channel"]
    normal_channel = channels_dict["normal_channel"]
    ao_channel = channels_dict["ao_channel"]
    metalness_channel = channels_dict["metalness_channel"]
    roughness_channel = channels_dict["roughness_channel"]
    specular_channel = channels_dict["specular_channel"]
    glossiness_channel = channels_dict["glossiness_channel"]
    opacity_channel = channels_dict["opacity_channel"]
    translucency_channel = channels_dict["translucency_channel"]
    displacement_channel = channels_dict["displacement_channel"]
    misc_channel = channels_dict["misc_channel"]

    all_channels = [channel for channels in channels_dict.values() for channel in channels]
    all_channels.sort(key=len, reverse=True)
    all_channels_reg = []
    for element in all_channels:
        all_channels_reg.append(re.escape(element))
    channels_regex = '|'.join(all_channels_reg)

# Set material to RedshiftNodeMaterial Class
def GetRSMaterial(material):
    return rs.RedshiftNodeMaterial(material)

def processTextureToMaterial(RSMaterial, texture_node, connect_node, channel_port, material_arguments, scale_node, trans_node, rot_node, channel_name=""):
    texture_id = "texturesampler"
    rotation_node = "rsmathabs"
    rotation_port = "rotate"
    if material_arguments["addTriplanar"]:
        triplanar_node = RSMaterial.AddShader("triplanar")
        RSMaterial.SetShaderName(triplanar_node, channel_name+ " TRIPL")
        RSMaterial.AddConnection(texture_node, rsID.StrPortID(texture_id, "outcolor"), triplanar_node, rsID.StrPortID("triplanar", "imagex"))
        texture_id = "triplanar"
        rotation_port = "rotation"
        rotation_node = "rsmathabsvector"
        texture_node = triplanar_node

    if material_arguments["addScaleRotOff"]:
        RSMaterial.AddConnection(scale_node, rsID.StrPortID("rsmathabsvector", "out"), texture_node, rsID.StrPortID(texture_id, "scale"))
        RSMaterial.AddConnection(trans_node, rsID.StrPortID("rsmathabsvector", "out"), texture_node, rsID.StrPortID(texture_id, "offset"))
        RSMaterial.AddConnection(rot_node, rsID.StrPortID(rotation_node, "out"), texture_node, rsID.StrPortID(texture_id, rotation_port))

    RSMaterial.AddConnection(texture_node, rsID.StrPortID(texture_id, "outcolor"), connect_node, channel_port)
    return texture_node

def importTexturesToMaterial(RSMaterial, tex_tuples, material_arguments):
    standard_surface = RSMaterial.GetRootBRDF()

    albedo_connectport = (standard_surface, rsID.PortStr.base_color)
    ao_connectport = (standard_surface, rsID.StrPortID("standardmaterial", "overall_color"))
    if not material_arguments["aoOverallTint"]:
        color_layer = RSMaterial.AddShader("rscolorlayer")
        RSMaterial.SetShaderValue(color_layer, _RS_NODE_PREFIX+"rscolorlayer.layer1_enable", False)
        RSMaterial.SetShaderValue(color_layer, _RS_NODE_PREFIX+"rscolorlayer.layer1_blend_mode", 4) # Multiply
        RSMaterial.AddConnection(color_layer, rsID.StrPortID("rscolorlayer", "outcolor"), *albedo_connectport)
        albedo_connectport = (color_layer, rsID.StrPortID("rscolorlayer", "base_color"))
        ao_connectport = (color_layer, rsID.StrPortID("rscolorlayer", "layer1_color"))

    
    scale = None
    translate = None
    rotate = None
    if material_arguments["addScaleRotOff"]:
        translate = RSMaterial.AddShader("rsmathabsvector")
        RSMaterial.SetShaderName(translate, "OFFSET")
        scale = RSMaterial.AddShader("rsmathabsvector")
        RSMaterial.SetShaderName(scale, "SCALE")
        RSMaterial.SetShaderValue(scale, _RS_NODE_PREFIX+"rsmathabsvector.input", maxon.Vector(1, 1, 1))
        if material_arguments["addTriplanar"]:
            RSMaterial.SetShaderValue(scale, _RS_NODE_PREFIX+"rsmathabsvector.input", maxon.Vector(.01, .01, .01))
            rotate = RSMaterial.AddShader("rsmathabsvector")
        else:
            rotate = RSMaterial.AddShader("rsmathabs")
        RSMaterial.SetShaderName(rotate, "ROTATE")
    # print(scale.GetInputs().FindChild(_RS_NODE_PREFIX+"rsmathabsvector.input").GetDefaultValue().GetType())

    mat_tex_dict = {
        "Roughness": None,
        "Roughness_Ramp": None,
        "Glossiness": None,
        "Specular": None,
        "AO": None,
        "Metalness": None,
        "Opacity": None,
    }

    for channel_name, filepath in tex_tuples:
        filename = os.path.basename(filepath)
        if material_arguments["caseInsensitive"]:
            channel_name = channel_name.lower()
        misc = ""
        processArgs = (material_arguments, scale, translate, rotate, channel_name)

        if channel_name in color_channel:
            tex_node_color = RSMaterial.AddTexture(filename, filepath, '') # Auto Colorspace
            if material_arguments["addCC"]:
                albedo_cc = RSMaterial.AddShader("rscolorcorrection")
                RSMaterial.SetShaderName(albedo_cc, "ALBEDO CC")
                RSMaterial.AddConnection(albedo_cc, rsID.StrPortID("rscolorcorrection", "outcolor"), *albedo_connectport)
                albedo_connectport = (albedo_cc, rsID.StrPortID("rscolorcorrection", "input"))
            processTextureToMaterial(RSMaterial, tex_node_color, *albedo_connectport, *processArgs)

        elif channel_name in roughness_channel or channel_name in glossiness_channel:
            tex_node_roughness = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            ramp_refl_roughness = RSMaterial.AddShader("rsscalarramp")
            RSMaterial.SetShaderName(ramp_refl_roughness, "ROUGHNESS RAMP")
            if channel_name in glossiness_channel:
                RSMaterial.SetShaderValue(ramp_refl_roughness, _RS_NODE_PREFIX+"rsscalarramp.inputinvert", True)
            RSMaterial.AddConnection(ramp_refl_roughness, rsID.StrPortID("rsscalarramp", "out"), standard_surface, rsID.PortStr.refl_roughness)
            mat_tex_dict["Roughness_Ramp"] = ramp_refl_roughness
            mat_tex_dict["Roughness"] = processTextureToMaterial(RSMaterial, tex_node_roughness, ramp_refl_roughness, rsID.StrPortID("rsscalarramp", "input"), *processArgs)
            mat_tex_dict["Glossiness"] = mat_tex_dict["Roughness"]

        elif channel_name in specular_channel:
            tex_node_specular = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            mat_tex_dict["Specular"] = processTextureToMaterial(RSMaterial, tex_node_specular, standard_surface, rsID.PortStr.refl_color, *processArgs)

        elif channel_name in normal_channel:
            tex_node_normal = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            bump_map = RSMaterial.AddShader("bumpmap")
            RSMaterial.AddConnection(bump_map, rsID.StrPortID("bumpmap", "out"), standard_surface, rsID.PortStr.bump_input)
            RSMaterial.SetShaderValue(bump_map, rsID.StrPortID("bumpmap", "inputtype"), 1)
            RSMaterial.SetShaderValue(bump_map, rsID.StrPortID("bumpmap", "flipy"), material_arguments["bumpFlipY"])
            RSMaterial.SetShaderValue(bump_map, rsID.StrPortID("bumpmap", "legacynormalmap"), material_arguments["bumpLegacy"])
            processTextureToMaterial(RSMaterial, tex_node_normal, bump_map, rsID.StrPortID("bumpmap", "input"), *processArgs)

        elif channel_name in metalness_channel:
            tex_node_metalness = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            mat_tex_dict["Metalness"] = processTextureToMaterial(RSMaterial, tex_node_metalness, standard_surface, rsID.PortStr.metalness, *processArgs)

        elif channel_name in opacity_channel:
            if material_arguments["spriteOpacity"]:
                sprite_opacity = RSMaterial.AddSprite(filepath, 'RS_INPUT_COLORSPACE_RAW')
                RSMaterial.AddtoOutput(sprite_opacity, rsID.StrPortID("sprite", "outcolor"))
                RSMaterial.AddConnection(standard_surface, rsID.PortStr.standard_outcolor, sprite_opacity, rsID.StrPortID("sprite", "input"))
            else:
                tex_node_opacity = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
                mat_tex_dict["Opacity"] = processTextureToMaterial(RSMaterial, tex_node_opacity, standard_surface, rsID.PortStr.opacity_color, *processArgs)

        elif channel_name in ao_channel:
            tex_node_ao = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            if not material_arguments["aoOverallTint"]:
                RSMaterial.SetShaderValue(color_layer, _RS_NODE_PREFIX+"rscolorlayer.layer1_enable", True)
            mat_tex_dict["AO"] = processTextureToMaterial(RSMaterial, tex_node_ao, *ao_connectport, *processArgs)

        elif channel_name in translucency_channel:
            tex_node_translucency = RSMaterial.AddTexture(filename, filepath, '')
            translucency_connectport = (standard_surface, rsID.PortStr.sss_color)
            if material_arguments["addCC"]:
                translucency_cc = RSMaterial.AddShader("rscolorcorrection")
                RSMaterial.SetShaderName(translucency_cc, "TRANSLUCENCC")
                RSMaterial.AddConnection(translucency_cc, rsID.StrPortID("rscolorcorrection", "outcolor"), *translucency_connectport)
                translucency_connectport = (translucency_cc, rsID.StrPortID("rscolorcorrection", "input"))
            RSMaterial.SetShaderValue(standard_surface, rsID.PortStr.sss_weight, 0.4)
            RSMaterial.SetShaderValue(standard_surface, _RS_NODE_PREFIX+"standardmaterial.refr_thin_walled", True)
            processTextureToMaterial(RSMaterial, tex_node_translucency, *translucency_connectport, *processArgs)

        elif channel_name in displacement_channel:
            tex_node_displacement = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            displacement = RSMaterial.AddShader("displacement")
            RSMaterial.AddtoDisplacement(displacement, rsID.StrPortID("displacement", "out"))
            processTextureToMaterial(RSMaterial, tex_node_displacement, displacement, rsID.StrPortID("displacement", "texmap"), *processArgs)

        elif channel_name in misc_channel:
            tex_node_misc = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            misc = " without connections"
        
        else:
            print("Texture " + filename + " could not be imported.")
            continue
        print("Texture " + filename + " exists and has been imported"+misc+".")

    if material_arguments["multiTex"]["BASE"] != " ":
        if not mat_tex_dict[material_arguments["multiTex"]["BASE"]]:
            print("Texture not found for provided multiTex base channel in material %s." % RSMaterial.GetMaterialName())

        else:
            color_split_multi = RSMaterial.AddShader("rscolorsplitter")
            RSMaterial.AddConnection(mat_tex_dict[material_arguments["multiTex"]["BASE"]], rsID.StrPortID("texturesampler", "outcolor"), color_split_multi, rsID.StrPortID("rscolorsplitter", "input"))

            for rgb_channel in ["R", "G", "B"]:
                multitex_channel = material_arguments["multiTex"][rgb_channel]
                if multitex_channel == " ":
                    pass
                elif multitex_channel == "Roughness" or multitex_channel == "Glossiness":
                    if not mat_tex_dict["Roughness_Ramp"]:
                        ramp_refl_roughness = RSMaterial.AddShader("rsscalarramp")
                        if multitex_channel == "Glossiness":
                            RSMaterial.SetShaderValue(ramp_refl_roughness, _RS_NODE_PREFIX+"rsscalarramp.inputinvert", True)
                    else:
                        ramp_refl_roughness = mat_tex_dict["Roughness_Ramp"]
                    RSMaterial.AddConnection(color_split_multi, rsID.StrPortID("rscolorsplitter", "out"+rgb_channel.lower()), ramp_refl_roughness, rsID.StrPortID("rsscalarramp", "input"))
                    RSMaterial.AddConnection(ramp_refl_roughness, rsID.StrPortID("rsscalarramp", "out"), standard_surface, rsID.PortStr.refl_roughness)
                elif multitex_channel == "Metalness":
                    RSMaterial.AddConnection(color_split_multi, rsID.StrPortID("rscolorsplitter", "out"+rgb_channel.lower()), standard_surface, rsID.PortStr.metalness)
                elif multitex_channel == "Specular":
                    RSMaterial.AddConnection(color_split_multi, rsID.StrPortID("rscolorsplitter", "out"+rgb_channel.lower()), standard_surface, rsID.PortStr.refl_color)
                elif multitex_channel == "AO":
                    RSMaterial.AddConnection(color_split_multi, rsID.StrPortID("rscolorsplitter", "out"+rgb_channel.lower()), *ao_connectport)
                    if not material_arguments["aoOverallTint"]:
                        RSMaterial.SetShaderValue(color_layer, _RS_NODE_PREFIX+"rscolorlayer.layer1_enable", True)
                elif multitex_channel == "Opacity":
                    RSMaterial.AddConnection(color_split_multi, rsID.StrPortID("rscolorsplitter", "out"+rgb_channel.lower()), standard_surface, rsID.PortStr.opacity_color)

    #RSMaterial.ArrangeNodes() #TODO: Doesn't work for import base texture...
    print("Importing textures finished for material " + RSMaterial.GetMaterialName() + ".")
    return RSMaterial


def importTexturesFromBase(derive_folder_from_base = False, delete_base_texture = False, rename_materials_from_base = False, material_arguments = None):
    doc =  c4d.documents.GetActiveDocument()

    custom_regex_dict = None
    if material_arguments["customRegex"]:
        custom_regex_dict = ReadJSON("/custom_regex.json", "/res/custom_regex.json")
    init_channels(custom_regex_dict, material_arguments["caseInsensitive"])
    base_texture_regex = r'^(.*?)(' + channels_regex + ')(.*?)(?:' + '|'.join(image_extensions) + ')\\b'

    doc.StartUndo()
    for RSMaterial in doc.GetActiveMaterials():
        RSMaterial = GetRSMaterial(RSMaterial)
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, RSMaterial.material)
        with rs.RSMaterialTransaction(RSMaterial) as transaction:
            standard_surface = RSMaterial.GetRootBRDF()

            #get texture shader
            base_color_tex = None
            shaders = RSMaterial.GetShaders()
            for shader in shaders:
                shaderId = RSMaterial.GetShaderId(shader)
                if shaderId == "texturesampler":
                    base_color_tex = shader
            if base_color_tex is None:
                c4d.gui.MessageDialog("No base texture found in Material %s" % RSMaterial.GetMaterialName(), c4d.GEMB_ICONEXCLAMATION)
                continue

            texture_path = base_color_tex.GetInputs().FindChild(_RS_NODE_PREFIX+"texturesampler.tex0").FindChild('path').GetDefaultValue()
            texture_path = str(texture_path)
            texture_name = os.path.basename(texture_path)
            texture_folder = material_arguments["texFolder"]

            if derive_folder_from_base:
                texture_folder = os.path.dirname(texture_path)
            elif texture_folder is None:
                c4d.gui.MessageDialog("No texture folder specified and deriving from base texture disabled.", c4d.GEMB_ICONEXCLAMATION)
                return

            #remove base channel from texture name
            match = re.search(base_texture_regex, texture_name)
            if match:
                texture_name_without_channel = match.group(1)
                channel_name = match.group(2)
                print(f"Prefix: {texture_name_without_channel} | Found in: {channel_name}")
            else:
                c4d.gui.MessageDialog("No regex match in base texture found in Material %s" % RSMaterial.GetMaterialName(), c4d.GEMB_ICONEXCLAMATION)
                continue

            if delete_base_texture:
                RSMaterial.RemoveShader(base_color_tex)

            texture_regex = r'^' + re.escape(texture_name_without_channel) + '(' + channels_regex + ')(.*?)(?:' + '|'.join(image_extensions) + ')\\b'
            flags = re.IGNORECASE if material_arguments["caseInsensitive"] else 0
            tex_tuples = []
            for filename in os.listdir(texture_folder):
                if filename.endswith(tuple(image_extensions)):
                    filepath = os.path.join(texture_folder, filename)
                match = re.search(texture_regex, filename, flags=flags)
                if match:
                    channel_name = match.group(1)
                    # print(f"Texture: {texture_name_without_channel} | Channel name: {channel_name}") # DEBUG
                    tex_tuples.append((channel_name, filepath))

            if RSMaterial.GetRootBRDF().ToString().split("@")[0] != "standardmaterial":
                oldmat = RSMaterial.GetRootBRDF()
                standard_surface = RSMaterial.AddShader("standardmaterial")
                RSMaterial.AddConnection(standard_surface,rsID.PortStr.standard_outcolor, RSMaterial.GetRSOutput(), rsID.PortStr.Output_Surface)
                RSMaterial.RemoveShader(oldmat)

            importTexturesToMaterial(RSMaterial, tex_tuples, material_arguments)
            if rename_materials_from_base:
                RSMaterial.SetMaterialName(texture_name_without_channel)

        # doc.SetActiveMaterial(RSMaterial.material)
        # doc.GetActiveMaterial()
        # c4d.CallCommand(465002362) # Send to node editor
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, RSMaterial.material)
        with rs.RSMaterialTransaction(RSMaterial) as transaction:
            RSMaterial.ArrangeNodes()

    doc.EndUndo()
    return
# Not every material has all of the mentioned textures, so we need to check if the texture exists before importing it.
# Example texture_path: C:/foo/bar/textures/basketball-hoop-set-a-color.dds
# Example imported textures: C:/foo/bar/textures_png/basketball-hoop-set-a-color.png, C:/foo/bar/textures_png/basketball-hoop-set-a-roughness.png, C:/foo/bar/textures_png/basketball-hoop-set-a-normal.png, C:/foo/bar/textures_png/basketball-hoop-set-a-opacity.png, C:/foo/bar/textures_png/basketball-hoop-set-a-ao.png
def importTexturesFromFolder(material_arguments):
    doc =  c4d.documents.GetActiveDocument()

    custom_regex_dict = None
    if material_arguments["customRegex"]:
        custom_regex_dict = ReadJSON("/custom_regex.json", "/res/custom_regex.json")
    init_channels(custom_regex_dict, material_arguments["caseInsensitive"])
    texture_regex = r'^(.*?)(' + channels_regex + ')(.*?)(?:' + '|'.join(image_extensions) + ')\\b'

    flags = re.IGNORECASE if material_arguments["caseInsensitive"] else 0
    # use image_extensions to find all files in the directory with the given extensions
    texture_folder = material_arguments["texFolder"]

    # Group the images by their common prefix
    image_groups = {}
    for filename in os.listdir(texture_folder):
        if filename.endswith(tuple(image_extensions)):
            filepath = os.path.join(texture_folder, filename)
            match = re.search(texture_regex, filename, flags=flags)
            if match:
                prefix = match.group(1)
                channel_name = match.group(2)
                print(f"Prefix: {prefix} | Channel Name: {channel_name}")
                if prefix not in image_groups:
                    image_groups[prefix] = []
                image_groups[prefix].append((channel_name, filepath))

    # Import each group of images separately and create a new material for each group
    doc.StartUndo()
    for prefix, tex_tuples in image_groups.items():
        RSMaterial = rs.CreateStandardSurface(prefix)
        doc.AddUndo(c4d.UNDOTYPE_NEW, RSMaterial.material)
        with rs.RSMaterialTransaction(RSMaterial) as transaction:
            importTexturesToMaterial(RSMaterial, tex_tuples, material_arguments)
            doc.InsertMaterial(RSMaterial.material)

    doc.EndUndo()
    return


##########################################################################
##                                                                      ##
##                                UI                                    ##
##                                                                      ##
##########################################################################

VERSION_NUMBER = "v4.2"
ABOUT_TEXT_COPYRIGHT = "©2024 by Jérôme Stephan. All rights reserved."
ABOUT_TEXT_GITHUB = "https://github.com/HerzogVonWiesel"
ABOUT_TEXT_WEBSITE = "https://jeromestephan.de"
ABOUT_LINK_README = "https://jeromestephan.gumroad.com/l/TexToMatO?layout=profile"
ABOUT_SUPPORT = "https://jeromestephan.gumroad.com/"

FORM_IMPROVEMENTS = "https://tally.so/r/w5jvov"

GROUP_BORDER_SPACE = 6
GROUP_BORDER_SPACE_SM = GROUP_BORDER_SPACE - 2

# region IDs
ID_SUBDIALOG = 10000
RADIO_GROUP = 10001
RADIO_IMPORT_FROM_FOLDER = 10002
RADIO_IMPORT_FROM_BASE = 10003

ID_LINK_ABOUT = 10010
ID_LINK_README = 10011
ID_AUTHOR_TEXT = 10012
ID_LINK_WEBSITE = 10013
ID_SUPPORT_ME = 10014
ID_FORM_IMPROVEMENTS = 10015
ID_LINK_GITHUB = 10016

ID_CREATE_AND_REPLACE = 10100
ID_DERIVE_FOLDER_FROM_BASE = 10101
ID_DELETE_BASE = 10102
ID_RENAME_MAT_FROM_BASE = 10103

ID_BUMP_FLIPY = 10200
ID_BUMP_LEGACY = 10201
ID_SPRITE_OPACITY = 10202
ID_REGEX_DANGER = 10203

ID_MULTITEX_BASE = 10300
ID_MULTITEX_GROUP_BASE = 10320
ID_MULTITEX_GROUP_R = 10321
ID_MULTITEX_GROUP_G = 10322
ID_MULTITEX_GROUP_B = 10323

ID_FOLDER_SELECT_TEXT = 10800
ID_FOLDER_SELECT_BUTTON = 10801
ID_FOLDER_SELECT_GROUP = 10802

ID_IMPORT_TEXTURES_BUTTON = 10900

ID_REGEX_GROUP = 12000
ID_REGEX_GROUP_INNER = 12001
ID_REGEX_EXTENSIONS = 12002
ID_REGEX_COLOR = 12003
ID_REGEX_NORMAL = 12004
ID_REGEX_AO = 12005
ID_REGEX_METALNESS = 12006
ID_REGEX_ROUGHNESS = 12007
ID_REGEX_SPECULAR = 12008
ID_REGEX_GLOSSINESS = 12009
ID_REGEX_OPACITY = 12010
ID_REGEX_TRANSLUCENCY = 12011
ID_REGEX_DISPLACEMENT = 12012
ID_REGEX_MISC = 12013
ID_REGEX_TOGGLE = 12100
ID_REGEX_MANAGE = 12101
ID_REGEX_UPDATE = 12102
ID_REGEX_NOTIF = 12103

ID_PREFS_GROUP = 13000
ID_PREFS_MANAGE = 13001
ID_PREFS_UPDATE = 13002
ID_PREFS_NOTIF = 13003
ID_PREFS_RESET_DEFAULTS = 13004
ID_PREFS_RESET_FINISHED = 13005
ID_PREFS_ADD_CC = 13006
ID_PREFS_ADD_SCALEROTOFF = 13007
ID_PREFS_ADD_TRIPLANAR = 13008
ID_PREFS_AO_OVERALL_TINT = 13009

ID_BLANK = 101010
#endregion IDs

class AboutDialog(c4d.gui.GeDialog):
    def CreateLayout(self):
        self.SetTitle("About")
        self.AddStaticText(ID_BLANK, c4d.BFH_CENTER, 0, 0, "TexToMatO")
        self.AddStaticText(ID_BLANK, c4d.BFH_CENTER, 0, 0, VERSION_NUMBER)
        self.AddStaticText(ID_BLANK, c4d.BFH_CENTER, 0, 0, "A powerful texture to material converter for Cinema 4D")
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddStaticText(ID_AUTHOR_TEXT, c4d.BFH_FIT, 0, 0, "Author:\t\tMarvin Jérôme Stephan")
        self.AddRadioText(ID_SUPPORT_ME, c4d.BFH_FIT, 0, 0, "Support me:\t" + ABOUT_SUPPORT)
        self.AddRadioText(ID_LINK_GITHUB, c4d.BFH_FIT, 0, 0, "GitHub:\t\t" + ABOUT_TEXT_GITHUB)
        self.AddRadioText(ID_LINK_WEBSITE, c4d.BFH_FIT, 0, 0, "Website:\t\t" + ABOUT_TEXT_WEBSITE)
        return True
    
    def Command(self, mid, msg):
        if mid == ID_SUPPORT_ME:
            webbrowser.open(ABOUT_SUPPORT)
        elif mid == ID_LINK_GITHUB:
            webbrowser.open(ABOUT_TEXT_GITHUB)
        elif mid == ID_LINK_WEBSITE:
            webbrowser.open(ABOUT_TEXT_WEBSITE)
        return True

class SettingsDialog(c4d.gui.SubDialog):
    settings_dict = {}
    def UpdateSettings(self):
        self.settings_dict["addCC"] = self.GetBool(ID_PREFS_ADD_CC)
        self.settings_dict["addTriplanar"] = self.GetBool(ID_PREFS_ADD_TRIPLANAR)
        self.settings_dict["addScaleRotOff"] = self.GetBool(ID_PREFS_ADD_SCALEROTOFF)
        self.settings_dict["aoOverallTint"] = self.GetBool(ID_PREFS_AO_OVERALL_TINT)
        # Creates the directory if it does not exist
        userDir = os.path.dirname(_path_ + "/user/settings.json")
        try:
            os.makedirs(userDir)
        except OSError as e:
            if e.errno == errno.EEXIST and os.path.isdir(userDir):
                pass
            else:
                print(e)
                raise
        try:
            with open(_path_ + "/user/settings.json", "w") as write_file:
                json.dump(self.settings_dict, write_file, indent=4)
            self.SetString(ID_PREFS_NOTIF, "Preferences updated!")
            return True
        except IOError as e:
            print(e)
            self.SetString(ID_PREFS_NOTIF, "Error updating preferences, check folder permissions! " + str(e))
            return False
        
    
    def ReadSettings(self):
        self.settings_dict = ReadJSON("/user/settings.json", "/res/settings.json")
    
    def CreateLayout(self):
        self.SetTitle("Manage your preferences")
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="OUTER GROUP", cols=1)
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="Material preferences", cols=1)
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.AddCheckbox(ID_PREFS_ADD_CC, c4d.BFH_SCALEFIT, 0, 0, "Add Color Correct node to color textures")
        self.AddCheckbox(ID_PREFS_ADD_SCALEROTOFF, c4d.BFH_SCALEFIT, 0, 0, "Add Scale, Rotation and Offset nodes to textures")
        self.AddCheckbox(ID_PREFS_ADD_TRIPLANAR, c4d.BFH_SCALEFIT, 0, 0, "Add Triplanar node to textures")
        self.AddCheckbox(ID_PREFS_AO_OVERALL_TINT, c4d.BFH_SCALEFIT, 0, 0, "Connect AO to overall tint instead of albedo")
        self.GroupEnd()
        
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddButton(ID_PREFS_UPDATE, c4d.BFH_SCALEFIT, 0, 30, "Update your preferences!")
        self.AddStaticText(ID_PREFS_NOTIF, c4d.BFH_CENTER, 0, 0, "                                                                                               ")
        self.AddSeparatorH(c4d.BFH_SCALEFIT | c4d.BFV_BOTTOM)
        self.AddButton(ID_PREFS_RESET_DEFAULTS, c4d.BFH_SCALEFIT | c4d.BFV_BOTTOM, 0, 0, "Reset all to defaults")
        self.GroupEnd()
        return True
    
    def InitValues(self):
        self.ReadSettings()
        self.SetBool(ID_PREFS_ADD_CC, self.settings_dict["addCC"])
        self.SetBool(ID_PREFS_ADD_TRIPLANAR, self.settings_dict["addTriplanar"])
        self.SetBool(ID_PREFS_ADD_SCALEROTOFF, self.settings_dict["addScaleRotOff"])
        self.SetBool(ID_PREFS_AO_OVERALL_TINT, self.settings_dict["aoOverallTint"])
        return True
    
    def Command(self, mid, msg):
        if mid == ID_PREFS_UPDATE:
            self.UpdateSettings()
        elif mid == ID_PREFS_RESET_DEFAULTS:
            c4d.SpecialEventAdd(PLUGIN_ID, ID_PREFS_RESET_DEFAULTS)
        return True
    def CoreMessage(self, id, msg):
        if id == PLUGIN_ID:
            message = decodeMessage(msg)
            if message == ID_PREFS_RESET_DEFAULTS:
                self.InitValues()
        return c4d.gui.GeDialog.CoreMessage(self, id, msg)

class RegexDialog(c4d.gui.GeDialog):
    regex_dict = {}
    def UpdateRegex(self):
        self.regex_dict["image_extensions"] = [value for value in self.GetString(ID_REGEX_EXTENSIONS).split(",") if value != ""]
        self.regex_dict["color_channel"] = [value for value in self.GetString(ID_REGEX_COLOR).split(",") if value != ""]
        self.regex_dict["normal_channel"] = [value for value in self.GetString(ID_REGEX_NORMAL).split(",") if value != ""]
        self.regex_dict["ao_channel"] = [value for value in self.GetString(ID_REGEX_AO).split(",") if value != ""]
        self.regex_dict["metalness_channel"] = [value for value in self.GetString(ID_REGEX_METALNESS).split(",") if value != ""]
        self.regex_dict["roughness_channel"] = [value for value in self.GetString(ID_REGEX_ROUGHNESS).split(",") if value != ""]
        self.regex_dict["specular_channel"] = [value for value in self.GetString(ID_REGEX_SPECULAR).split(",") if value != ""]
        self.regex_dict["glossiness_channel"] = [value for value in self.GetString(ID_REGEX_GLOSSINESS).split(",") if value != ""]
        self.regex_dict["opacity_channel"] = [value for value in self.GetString(ID_REGEX_OPACITY).split(",") if value != ""]
        self.regex_dict["translucency_channel"] = [value for value in self.GetString(ID_REGEX_TRANSLUCENCY).split(",") if value != ""]
        self.regex_dict["displacement_channel"] = [value for value in self.GetString(ID_REGEX_DISPLACEMENT).split(",") if value != ""]
        self.regex_dict["misc_channel"] = [value for value in self.GetString(ID_REGEX_MISC).split(",") if value != ""]
        # Creates the directory if it does not exist
        userDir = os.path.dirname(_path_ + "/user/custom_regex.json")
        try:
            os.makedirs(userDir)
        except OSError as e:
            if e.errno == errno.EEXIST and os.path.isdir(userDir):
                pass
            else:
                print(e)
                raise
        try:
            with open(_path_ + "/user/custom_regex.json", "w") as write_file:
                json.dump(self.regex_dict, write_file, indent=4)
            self.SetString(ID_REGEX_NOTIF, "Preferences updated!")
            return True
        except IOError as e:
            print(e)
            self.SetString(ID_REGEX_NOTIF, "Error updating Regex, check folder permissions! " + str(e))
            return False
    
    def CreateLayout(self):
        self.regex_dict = ReadJSON("/user/custom_regex.json", "/res/custom_regex.json")
        self.SetTitle("Manage your custom regex")
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="OUTER GROUP", cols=1)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Make sure to separate your regex with a comma, no space (except you want to match it!)")
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.GroupBegin(ID_REGEX_GROUP_INNER, c4d.BFH_SCALEFIT, title="REGEX SETTINGS", cols=2)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Image Extensions")
        self.AddEditText(ID_REGEX_EXTENSIONS, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Color")
        self.AddEditText(ID_REGEX_COLOR, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Normal")
        self.AddEditText(ID_REGEX_NORMAL, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "AO")
        self.AddEditText(ID_REGEX_AO, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Metalness")
        self.AddEditText(ID_REGEX_METALNESS, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Roughness")
        self.AddEditText(ID_REGEX_ROUGHNESS, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Specular")
        self.AddEditText(ID_REGEX_SPECULAR, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Glossiness")
        self.AddEditText(ID_REGEX_GLOSSINESS, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Opacity")
        self.AddEditText(ID_REGEX_OPACITY, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Translucency")
        self.AddEditText(ID_REGEX_TRANSLUCENCY, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Displacement")
        self.AddEditText(ID_REGEX_DISPLACEMENT, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Miscellaneous")
        self.AddEditText(ID_REGEX_MISC, c4d.BFH_SCALEFIT, 0, 0)
        self.GroupEnd()
        
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddButton(ID_REGEX_UPDATE, c4d.BFH_SCALEFIT, 0, 30, "Update custom regex!")
        self.AddStaticText(ID_REGEX_NOTIF, c4d.BFH_CENTER, 0, 0, "                           ")
        self.AddSeparatorH(c4d.BFH_SCALEFIT | c4d.BFV_BOTTOM)
        self.AddButton(ID_FORM_IMPROVEMENTS, c4d.BFH_SCALEFIT | c4d.BFV_BOTTOM, 0, 0, "Think it's useful for all? Submit missing regex here!")
        self.GroupEnd()
        return True
    
    def InitValues(self):
        self.SetString(ID_REGEX_EXTENSIONS, "png,jpg,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_COLOR, "Base_Color,BaseColor,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_NORMAL, "Normal_OpenGL,normal,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_AO, "Mixed_AO,ao,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_METALNESS, "Metallic,Meta,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_ROUGHNESS, "Roughness,roughness,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_SPECULAR, "Specular,specular,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_GLOSSINESS, "GLOSS,glossiness,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_OPACITY, "opacity,alpha,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_TRANSLUCENCY, "_L.,Translucency,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_DISPLACEMENT, "height,DISP,...", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_REGEX_MISC, "soft-mask,color-mask,...", flags=c4d.EDITTEXT_HELPTEXT)

        self.SetString(ID_REGEX_EXTENSIONS, ",".join(self.regex_dict["image_extensions"]))
        self.SetString(ID_REGEX_COLOR, ",".join(self.regex_dict["color_channel"]))
        self.SetString(ID_REGEX_NORMAL, ",".join(self.regex_dict["normal_channel"]))
        self.SetString(ID_REGEX_AO, ",".join(self.regex_dict["ao_channel"]))
        self.SetString(ID_REGEX_METALNESS, ",".join(self.regex_dict["metalness_channel"]))
        self.SetString(ID_REGEX_ROUGHNESS, ",".join(self.regex_dict["roughness_channel"]))
        self.SetString(ID_REGEX_SPECULAR, ",".join(self.regex_dict["specular_channel"]))
        self.SetString(ID_REGEX_GLOSSINESS, ",".join(self.regex_dict["glossiness_channel"]))
        self.SetString(ID_REGEX_OPACITY, ",".join(self.regex_dict["opacity_channel"]))
        self.SetString(ID_REGEX_TRANSLUCENCY, ",".join(self.regex_dict["translucency_channel"]))
        self.SetString(ID_REGEX_DISPLACEMENT, ",".join(self.regex_dict["displacement_channel"]))
        self.SetString(ID_REGEX_MISC, ",".join(self.regex_dict["misc_channel"]))
        return True
    
    def Command(self, mid, msg):
        self.SetString(ID_REGEX_NOTIF, " ")
        if mid == ID_REGEX_UPDATE:
            self.UpdateRegex()
        elif mid == ID_FORM_IMPROVEMENTS:
            webbrowser.open(FORM_IMPROVEMENTS)
        return True

class MainDialog(c4d.gui.GeDialog):
    settings_dict = {}
    def ReadSettings(self):
        self.settings_dict = ReadJSON("/settings.json", "/res/settings.json")
    def UpdateSettings(self, texArguments, importFromBase_args):
        for key, value in texArguments.items():
            self.settings_dict[key] = value
        for key, value in importFromBase_args.items():
            self.settings_dict[key] = value
        with open(_path_ + "/settings.json", "w") as write_file:
            json.dump(self.settings_dict, write_file, indent=4)
        return True
    def ResetSettings(self):
        with open(_path_ + "/settings.json", "w") as write_file:
            json.dump(ReadJSON("/res/settings.json"), write_file, indent=4)
        return True

    def CreateLayout(self):
        """
        """
        self.SetTitle("TexToMatO: über texture importer")

        self.MenuSubBegin("Preferences")
        self.MenuAddString(ID_PREFS_MANAGE, "Manage preferences")
        self.MenuSubEnd()

        self.MenuSubBegin("About")
        self.MenuAddString(ID_LINK_ABOUT, "About")
        self.MenuAddString(ID_LINK_README, "Readme")
        self.MenuSubEnd()
        
        self.MenuSubBegin("Feedback")
        self.MenuAddString(ID_FORM_IMPROVEMENTS, "Submit Feature Requests & Bug Reports")
        self.MenuSubEnd()
        
        self.MenuSubBegin("Support this project & me!")
        self.MenuAddString(ID_SUPPORT_ME, "Support this & other projects (& me) on Gumroad!")
        self.MenuSubEnd()
        self.MenuFinished()

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="Test")
        self.GroupBorderNoTitle(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.TabGroupBegin(RADIO_GROUP, c4d.BFH_SCALEFIT, c4d.TAB_RADIO)

        self.GroupBegin(RADIO_IMPORT_FROM_FOLDER, c4d.BFH_SCALEFIT, title="Import all textures from folder        ", cols=1)
        self.AddSeparatorH(c4d.BFH_SCALE)
        self.GroupEnd() # Import_from_folder

        self.GroupBegin(RADIO_IMPORT_FROM_BASE, c4d.BFH_SCALEFIT, title="Import textures from base in material  ", cols=2)
        self.AddSeparatorH(c4d.BFH_SCALE)
        self.AddSeparatorH(c4d.BFH_SCALE)
        # self.AddCheckbox(ID_CREATE_AND_REPLACE, c4d.BFH_SCALEFIT, 0, 0, "Create and replace material")
        self.AddCheckbox(ID_DERIVE_FOLDER_FROM_BASE, c4d.BFH_SCALEFIT, 0, 0, "Derive texture folder from base")
        self.AddCheckbox(ID_DELETE_BASE, c4d.BFH_SCALEFIT, 0, 0, "Delete base texture in material")
        self.AddCheckbox(ID_RENAME_MAT_FROM_BASE, c4d.BFH_SCALEFIT, 0, 0, "Rename material based on texture")

        self.GroupEnd() # Import_from_base
        self.GroupEnd() # TabGroup
        self.GroupEnd() # BorderGroup
        self.AddSeparatorH(c4d.BFH_SCALE)

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="Normal options")
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.AddCheckbox(ID_BUMP_FLIPY, c4d.BFH_SCALEFIT, 0, 0, "Flip Y (DirectX)")
        self.AddCheckbox(ID_BUMP_LEGACY, c4d.BFH_SCALEFIT, 0, 0, "Use legacy bump")
        self.GroupEnd()

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="MultiTexture", cols=3)
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="MultiTexture_Base", cols=2)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "Base")
        self.AddComboBox(ID_MULTITEX_GROUP_BASE, c4d.BFH_SCALEFIT, 0, 0)
        for i in range(len(multitex_channels)):
            self.AddChild(ID_MULTITEX_GROUP_BASE, ID_MULTITEX_BASE + i, multitex_channels[i])
        self.GroupEnd()
        self.AddSeparatorV(c4d.BFH_SCALE)
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="MultiTexture_RGB", cols=2)
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "R")
        self.AddComboBox(ID_MULTITEX_GROUP_R, c4d.BFH_SCALEFIT, 0, 0)
        for i in range(len(multitex_channels)):
            self.AddChild(ID_MULTITEX_GROUP_R, ID_MULTITEX_BASE + i, multitex_channels[i])
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "G")
        self.AddComboBox(ID_MULTITEX_GROUP_G, c4d.BFH_SCALEFIT, 0, 0)
        for i in range(len(multitex_channels)):
            self.AddChild(ID_MULTITEX_GROUP_G, ID_MULTITEX_BASE + i, multitex_channels[i])
        self.AddStaticText(ID_BLANK, c4d.BFH_FIT, 0, 0, "B")
        self.AddComboBox(ID_MULTITEX_GROUP_B, c4d.BFH_SCALEFIT, 0, 0)
        for i in range(len(multitex_channels)):
            self.AddChild(ID_MULTITEX_GROUP_B, ID_MULTITEX_BASE + i, multitex_channels[i])
        self.GroupEnd()
        self.GroupEnd()

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="Miscellaneous")
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.AddCheckbox(ID_SPRITE_OPACITY, c4d.BFH_SCALEFIT, 0, 0, "Use sprite node for opacity")
        self.AddCheckbox(ID_REGEX_DANGER, c4d.BFH_SCALEFIT, 0, 0, "Use case-insensitive RegEx (dangerous!)")
        self.GroupEnd()

        self.GroupBegin(ID_REGEX_GROUP, c4d.BFH_SCALEFIT, title="Custom regex", cols=2)
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.AddCheckbox(ID_REGEX_TOGGLE, c4d.BFH_SCALEFIT, 0, 0, "Use custom regex")
        self.AddButton(ID_REGEX_MANAGE, c4d.BFH_SCALEFIT, 0, 0, "Manage custom regex")
        self.GroupEnd()

        self.GroupBegin(ID_FOLDER_SELECT_GROUP, c4d.BFH_SCALEFIT, 2, 0)
        self.AddEditText(ID_FOLDER_SELECT_TEXT, c4d.BFH_SCALEFIT, 0, 0)
        self.AddButton(ID_FOLDER_SELECT_BUTTON, c4d.BFH_FIT, 0, 0, "Select folder...")
        self.GroupEnd()

        self.AddButton(ID_IMPORT_TEXTURES_BUTTON, c4d.BFH_SCALEFIT, 0, 30, "Import Textures!")
        self.AddSeparatorH(c4d.BFH_SCALE)

        self.AddSubDialog(ID_SUBDIALOG, c4d.BFV_SCALEFIT, 0, 0)
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="About")
        self.AddStaticText(ID_AUTHOR_TEXT, c4d.BFH_FIT, 0, 0, ABOUT_TEXT_COPYRIGHT)
        self.AddSubDialog(ID_BLANK, c4d.BFH_SCALEFIT, 0, 0)
        self.AddRadioText(ID_LINK_WEBSITE, c4d.BFH_FIT, 0, 0, ABOUT_TEXT_WEBSITE)
        self.GroupEnd()
        return True

    def InitValues(self):
        self.ReadSettings()
        self.SetBool(ID_DERIVE_FOLDER_FROM_BASE, self.settings_dict["derive_folder_from_base"])
        self.SetBool(ID_DELETE_BASE, self.settings_dict["delete_base_texture"])
        self.SetBool(ID_SPRITE_OPACITY, self.settings_dict["spriteOpacity"])
        self.SetString(ID_FOLDER_SELECT_TEXT, "Folder to read textures from", flags=c4d.EDITTEXT_HELPTEXT)
        self.SetString(ID_FOLDER_SELECT_TEXT, self.settings_dict["texFolder"])
        self.SetBool(ID_REGEX_TOGGLE, self.settings_dict["customRegex"])
        self.SetBool(ID_REGEX_DANGER, self.settings_dict["caseInsensitive"])
        self.SetBool(ID_BUMP_FLIPY, self.settings_dict["bumpFlipY"])
        self.SetBool(ID_BUMP_LEGACY, self.settings_dict["bumpLegacy"])
        self.SetBool(ID_SPRITE_OPACITY, self.settings_dict["spriteOpacity"])

        return True
    
    def CoreMessage(self, id, msg):
        if id == PLUGIN_ID:
            message = decodeMessage(msg)
            if message == ID_PREFS_RESET_DEFAULTS:
                self.ResetSettings()
                self.InitValues()
                c4d.SpecialEventAdd(PLUGIN_ID, ID_PREFS_RESET_FINISHED)
        return c4d.gui.GeDialog.CoreMessage(self, id, msg)

    def Command(self, mid, msg):

        if mid == ID_IMPORT_TEXTURES_BUTTON:
            self.ReadSettings()
            texArguments = {
                "bumpFlipY":        self.GetBool(ID_BUMP_FLIPY),
                "bumpLegacy":       self.GetBool(ID_BUMP_LEGACY),
                "spriteOpacity":    self.GetBool(ID_SPRITE_OPACITY),
                "caseInsensitive":  self.GetBool(ID_REGEX_DANGER),
                "customRegex":      self.GetBool(ID_REGEX_TOGGLE),
                "texFolder":        self.GetFilename(ID_FOLDER_SELECT_TEXT),
                "multiTex":         multitex_dict,

                "addCC":            self.settings_dict["addCC"],
                "addTriplanar":     self.settings_dict["addTriplanar"],
                "addScaleRotOff":     self.settings_dict["addScaleRotOff"],
                "aoOverallTint":    self.settings_dict["aoOverallTint"],
            }
            importFromBase_args = {
                "derive_folder_from_base":      self.GetBool(ID_DERIVE_FOLDER_FROM_BASE),
                "delete_base_texture":          self.GetBool(ID_DELETE_BASE),
                "rename_materials_from_base":   self.GetBool(ID_RENAME_MAT_FROM_BASE),
            }

            if self.GetInt32(ID_MULTITEX_GROUP_BASE):
                texArguments["multiTex"]["BASE"] = multitex_channels[self.GetInt32(ID_MULTITEX_GROUP_BASE) - ID_MULTITEX_BASE]
            if self.GetInt32(ID_MULTITEX_GROUP_R):
                texArguments["multiTex"]["R"] = multitex_channels[self.GetInt32(ID_MULTITEX_GROUP_R) - ID_MULTITEX_BASE]
            if self.GetInt32(ID_MULTITEX_GROUP_G):
                texArguments["multiTex"]["G"] = multitex_channels[self.GetInt32(ID_MULTITEX_GROUP_G) - ID_MULTITEX_BASE]
            if self.GetInt32(ID_MULTITEX_GROUP_B):
                texArguments["multiTex"]["B"] = multitex_channels[self.GetInt32(ID_MULTITEX_GROUP_B) - ID_MULTITEX_BASE]

            if self.GetBool(RADIO_IMPORT_FROM_FOLDER):
                importTexturesFromFolder(material_arguments = texArguments)
            elif self.GetBool(RADIO_IMPORT_FROM_BASE):
                importTexturesFromBase(material_arguments = texArguments, **importFromBase_args)
            self.UpdateSettings(texArguments, importFromBase_args)

        elif mid == ID_PREFS_MANAGE:
            settings_dlg = SettingsDialog()
            self.AddSubDialog(ID_PREFS_GROUP, c4d.BFV_SCALEFIT, 0, 0)
            settings_dlg.Open(c4d.DLG_TYPE_MODAL_RESIZEABLE, xpos=-2, ypos=-2)
        elif mid == ID_LINK_ABOUT:
            about_dlg = AboutDialog()
            about_dlg.Open(c4d.DLG_TYPE_MODAL, xpos=-2, ypos=-2)
        elif mid == ID_LINK_README:
            webbrowser.open(ABOUT_LINK_README)
        elif mid == ID_LINK_WEBSITE:
            webbrowser.open(ABOUT_TEXT_WEBSITE)
        elif mid == ID_SUPPORT_ME:
            webbrowser.open(ABOUT_SUPPORT)
        elif mid == ID_FORM_IMPROVEMENTS:
            webbrowser.open(FORM_IMPROVEMENTS)

        elif mid == ID_DERIVE_FOLDER_FROM_BASE or mid == RADIO_GROUP:
            if self.GetBool(ID_DERIVE_FOLDER_FROM_BASE) and self.GetBool(RADIO_IMPORT_FROM_BASE):
                self.Enable(ID_FOLDER_SELECT_TEXT, False)
                self.Enable(ID_FOLDER_SELECT_BUTTON, False)
            else:
                self.Enable(ID_FOLDER_SELECT_TEXT, True)
                self.Enable(ID_FOLDER_SELECT_BUTTON, True)

        # elif mid == ID_PREFS_ADD_SCALEROTOFF:
        #     if self.GetBool(ID_PREFS_ADD_SCALEROTOFF):
        #         self.Enable(ID_PREFS_ADD_TRIPLANAR, True)
        #     else:
        #         self.Enable(ID_PREFS_ADD_TRIPLANAR, False)

        elif mid == ID_REGEX_MANAGE:
            regex_dlg = RegexDialog()
            regex_dlg.Open(c4d.DLG_TYPE_MODAL_RESIZEABLE, defaultw=400, xpos=-2, ypos=-2)

        elif mid == ID_FOLDER_SELECT_BUTTON:
            path = c4d.storage.LoadDialog(c4d.FILESELECTTYPE_ANYTHING, "Select texture folder", c4d.FILESELECT_DIRECTORY, "Select")
            if path:
                self.SetFilename(ID_FOLDER_SELECT_TEXT, path)
        return True
    
class MainDialogCommand(c4d.plugins.CommandData):
    dlg = None
    def Execute(self, doc):
        if self.dlg is None:
            self.dlg = MainDialog()
        return self.dlg.Open(c4d.DLG_TYPE_ASYNC, pluginid=PLUGIN_ID, defaultw=0, defaulth=0, xpos=-2, ypos=-2)
    
    def RestoreLayout(self, sec_ref):
        if self.dlg is None:
            self.dlg = MainDialog()
        return self.dlg.Restore(pluginid=PLUGIN_ID, secret=sec_ref)

if __name__=='__main__':
    directory, _ = os.path.split(__file__)
    icon = os.path.join(directory, "res", "TexToMatO.tif")
    bmp = c4d.bitmaps.BaseBitmap()
    if bmp.InitWith(icon)[0] != c4d.IMAGERESULT_OK:
        raise MemoryError("Failed to initialize the BaseBitmap.")
    c4d.plugins.RegisterCommandPlugin(id=PLUGIN_ID, 
                                      str="TexToMatO", 
                                      info=0, 
                                      help="A powerful texture to material converter for Cinema 4D", 
                                      dat=MainDialogCommand(), 
                                      icon=bmp)