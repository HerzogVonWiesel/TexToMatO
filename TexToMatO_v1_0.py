import typing
import c4d
from c4d import gui
import webbrowser
from typing import Optional
import os
import sys
import maxon
import glob
import re
import redshift_node as rs
import redshift_ID as rsID
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

image_extensions = ["png", "jpeg", "jpg", "dds", "tga", "tif", "tiff", "bmp", "exr"]

color_channel = ["Base_Color", "BaseColor", "color", "COL", "Color", "Albedo", "col", "Base", "diff", "_D-", "_D."]
normal_channel = ["Normal_OpenGL", "normal", "NRM", "Normal", "nml", "nrml", "Norm", "_N.", "_N("]
ao_channel = ["Mixed_AO", "ao", "AO"]
metalness_channel = ["Metallic", "Meta", "_M."]
roughness_channel = ["Roughness", "roughness", "Roug", "_R."]
specular_channel = ["Specular", "specular", "_S."]
glossiness_channel = ["GLOSS", "glossiness"]
opacity_channel = ["opacity", "alpha", "opac", "_O."]
translucency_channel = ["_L.", "_L_", "Translucency", "Transmission"]
displacement_channel = ["height", "DISP", "Displacement", "depth"]
misc_channel = ["soft-mask", "color-mask", "mix-mask", "tint-mask", "paint-mask", "mask", "_M(", "_MSK", "OVERLAY", "blend"]

all_channels = color_channel + normal_channel + ao_channel + metalness_channel + roughness_channel + specular_channel + glossiness_channel + opacity_channel + translucency_channel + displacement_channel + misc_channel

all_channels.sort(key=len, reverse=True)
all_channels_reg = []
for element in all_channels:
    all_channels_reg.append(re.escape(element))
channels_regex = '|'.join(all_channels_reg)

# Set material to RedshiftNodeMaterial Class
def GetRSMaterial(material):
    return rs.RedshiftNodeMaterial(material)

def importTexturesToMaterial(RSMaterial, tex_tuples, material_arguments):
    #get standard surface
    standard_surface = RSMaterial.GetRootBRDF()

    color_layer = RSMaterial.AddShader("rscolorlayer")
    #print(color_layer.GetInputs().GetChildren())
    RSMaterial.SetShaderValue(color_layer, _RS_NODE_PREFIX+"rscolorlayer.layer1_enable", False)
    RSMaterial.SetShaderValue(color_layer, _RS_NODE_PREFIX+"rscolorlayer.layer1_blend_mode", 4) # Multiply
    RSMaterial.AddConnection(color_layer, rsID.StrPortID("rscolorlayer", "outcolor"), standard_surface, rsID.PortStr.base_color)

    bump_map = RSMaterial.AddShader("bumpmap")
    RSMaterial.SetShaderValue(bump_map, rsID.StrPortID("bumpmap", "inuse"), False)
    RSMaterial.AddConnection(bump_map, rsID.StrPortID("bumpmap", "out"), standard_surface, rsID.PortStr.bump_input)

    mat_tex_dict = {
        "Roughness": None,
        "Roughness_Ramp": None,
        "Glossiness": None,
        "Specular": None,
        "AO": None,
        "Base_Color_Layer": color_layer,
        "Metalness": None,
        "Opacity": None,
    }
    
    for channel_name, filepath in tex_tuples:
        filename = os.path.basename(filepath)

        if channel_name in color_channel:
            tex_node_color = RSMaterial.AddTexture(filename, filepath, '') # Auto Colorspace
            RSMaterial.AddConnection(tex_node_color, rsID.StrPortID("texturesampler", "outcolor"), color_layer, _RS_NODE_PREFIX+"rscolorlayer.base_color")
            print("Texture " + filename + " exists and has been imported.")

        elif channel_name in roughness_channel or channel_name in glossiness_channel:
            tex_node_roughness = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            ramp_refl_roughness = RSMaterial.AddShader("rsscalarramp")
            if channel_name in glossiness_channel:
                RSMaterial.SetShaderValue(ramp_refl_roughness, _RS_NODE_PREFIX+"rsscalarramp.inputinvert", True)
            RSMaterial.AddConnection(tex_node_roughness, rsID.StrPortID("texturesampler", "outcolor"), ramp_refl_roughness, rsID.StrPortID("rsscalarramp", "input"))
            RSMaterial.AddConnection(ramp_refl_roughness, rsID.StrPortID("rsscalarramp", "out"), standard_surface, rsID.PortStr.refl_roughness)
            print("Texture " + filename + " exists and has been imported.")
            mat_tex_dict["Roughness_Ramp"] = ramp_refl_roughness
            mat_tex_dict["Roughness"] = tex_node_roughness
            mat_tex_dict["Glossiness"] = tex_node_roughness

        elif channel_name in specular_channel:
            tex_node_specular = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            RSMaterial.AddConnection(tex_node_specular, rsID.StrPortID("texturesampler", "outcolor"), standard_surface, rsID.PortStr.refl_color)
            print("Texture " + filename + " exists and has been imported.")
            mat_tex_dict["Specular"] = tex_node_specular

        elif channel_name in normal_channel:
            tex_node_normal = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            RSMaterial.AddConnection(tex_node_normal, rsID.StrPortID("texturesampler", "outcolor"), bump_map, rsID.StrPortID("bumpmap", "input"))
            RSMaterial.SetShaderValue(bump_map, rsID.StrPortID("bumpmap", "inuse"), True)
            RSMaterial.SetShaderValue(bump_map, rsID.StrPortID("bumpmap", "inputtype"), 1)
            RSMaterial.SetShaderValue(bump_map, rsID.StrPortID("bumpmap", "flipy"), material_arguments["bumpFlipY"])
            RSMaterial.SetShaderValue(bump_map, rsID.StrPortID("bumpmap", "legacynormalmap"), material_arguments["bumpLegacy"])
            print("Texture " + filename + " exists and has been imported.")

        elif channel_name in metalness_channel:
            tex_node_metalness = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            RSMaterial.AddConnection(tex_node_metalness, rsID.StrPortID("texturesampler", "outcolor"), standard_surface, rsID.PortStr.metalness)
            print("Texture " + filename + " exists and has been imported.")
            mat_tex_dict["Metalness"] = tex_node_metalness

        elif channel_name in opacity_channel:
            if material_arguments["spriteOpacity"]:
                sprite_opacity = RSMaterial.AddSprite(filepath, 'RS_INPUT_COLORSPACE_RAW')
                RSMaterial.AddtoOutput(sprite_opacity, rsID.StrPortID("sprite", "outcolor"))
                RSMaterial.AddConnection(standard_surface, rsID.PortStr.standard_outcolor, sprite_opacity, rsID.StrPortID("sprite", "input"))
            else:
                tex_node_opacity = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
                RSMaterial.AddConnection(tex_node_opacity, rsID.StrPortID("texturesampler", "outcolor"), standard_surface, rsID.PortStr.opacity_color)
                mat_tex_dict["Opacity"] = tex_node_opacity
            print("Texture " + filename + " exists and has been imported.")

        elif channel_name in ao_channel:
            tex_node_ao = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            RSMaterial.AddConnection(tex_node_ao, rsID.StrPortID("texturesampler", "outcolor"), color_layer, rsID.StrPortID("rscolorlayer", "layer1_color"))
            RSMaterial.SetShaderValue(color_layer, _RS_NODE_PREFIX+"rscolorlayer.layer1_enable", True)
            print("Texture " + filename + " exists and has been imported.")
            mat_tex_dict["AO"] = tex_node_ao

        elif channel_name in translucency_channel:
            tex_node_translucency = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            RSMaterial.AddConnection(tex_node_translucency, rsID.StrPortID("texturesampler", "outcolor"), standard_surface, rsID.PortStr.sss_color)
            RSMaterial.SetShaderValue(standard_surface, rsID.PortStr.sss_weight, 1.0)
            RSMaterial.SetShaderValue(standard_surface, _RS_NODE_PREFIX+"standardmaterial.refr_thin_walled", True)
            print("Texture " + filename + " exists and has been imported.")

        elif channel_name in displacement_channel:
            tex_node_displacement = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            displacement = RSMaterial.AddShader("displacement")
            RSMaterial.AddConnection(tex_node_displacement, rsID.StrPortID("texturesampler", "outcolor"), displacement, rsID.StrPortID("displacement", "texmap"))
            RSMaterial.AddtoDisplacement(displacement, rsID.StrPortID("displacement", "out"))
            print("Texture " + filename + " exists and has been imported.")

        elif channel_name in misc_channel:
            tex_node_misc = RSMaterial.AddTexture(filename, filepath, 'RS_INPUT_COLORSPACE_RAW')
            print("Texture " + filename + " exists and has been imported without connections.")

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
                    RSMaterial.AddConnection(color_split_multi, rsID.StrPortID("rscolorsplitter", "out"+rgb_channel.lower()), color_layer, rsID.StrPortID("rscolorlayer", "layer1_color"))
                    RSMaterial.SetShaderValue(color_layer, _RS_NODE_PREFIX+"rscolorlayer.layer1_enable", True)
                elif multitex_channel == "Opacity":
                    RSMaterial.AddConnection(color_split_multi, rsID.StrPortID("rscolorsplitter", "out"+rgb_channel.lower()), standard_surface, rsID.PortStr.opacity_color)


    #RSMaterial.ArrangeNodes() #TODO: Doesn't work for import base texture...
    print("Importing textures finished for material " + RSMaterial.GetMaterialName() + ".")
    return RSMaterial


def importTexturesFromBase(derive_folder_from_base = False, delete_base_texture = False, material_arguments = None):
    doc =  c4d.documents.GetActiveDocument()

    base_texture_regex = r'^(.*?)(' + channels_regex + ')(.*?)(?:' + '|'.join(image_extensions) + ')\\b'

    doc.StartUndo()
    for RSMaterial in doc.GetActiveMaterials():
        RSMaterial = GetRSMaterial(RSMaterial)
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, RSMaterial.material)
        with rs.RSMaterialTransaction(RSMaterial) as transaction:
            #get standard surface
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
                return

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
                return
            
            if delete_base_texture:
                RSMaterial.RemoveShader(base_color_tex)
            
            texture_regex = r'^' + re.escape(texture_name_without_channel) + '(' + channels_regex + ')(.*?)(?:' + '|'.join(image_extensions) + ')\\b'

            tex_tuples = []
            for filename in os.listdir(texture_folder):
                if filename.endswith(tuple(image_extensions)):
                    filepath = os.path.join(texture_folder, filename)
                match = re.search(texture_regex, filename)
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

    texture_regex = r'^(.*?)(' + channels_regex + ')(.*?)(?:' + '|'.join(image_extensions) + ')\\b'

    # use image_extensions to find all files in the directory with the given extensions
    texture_folder = material_arguments["texFolder"]

    # Group the images by their common prefix
    image_groups = {}
    for filename in os.listdir(texture_folder):
        if filename.endswith(tuple(image_extensions)):
            filepath = os.path.join(texture_folder, filename)
            match = re.search(texture_regex, filename)
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

VERSION_NUMBER = "v1.0"
ABOUT_TEXT_COPYRIGHT = "©2023 by Jérôme Stephan. All rights reserved."
ABOUT_TEXT_GITHUB = "https://github.com/HerzogVonWiesel"
ABOUT_TEXT_WEBSITE = "https://jeromestephan.de"
ABOUT_LINK_README = "https://github.com/HerzogVonWiesel/CG_Scripts"

GROUP_BORDER_SPACE = 6
GROUP_BORDER_SPACE_SM = GROUP_BORDER_SPACE - 2

ID_SUBDIALOG = 10000
RADIO_GROUP = 10001
RADIO_IMPORT_FROM_FOLDER = 10002
RADIO_IMPORT_FROM_BASE = 10003

ID_LINK_ABOUT = 10010
ID_LINK_README = 10011
ID_AUTHOR_TEXT = 10012

ID_CREATE_AND_REPLACE = 10100
ID_DERIVE_FOLDER_FROM_BASE = 10101
ID_DELETE_BASE = 10102

ID_BUMP_FLIPY = 10200
ID_BUMP_LEGACY = 10201
ID_SPRITE_OPACITY = 10202

ID_MULTITEX_BASE = 10300
ID_MULTITEX_GROUP_BASE = 10320
ID_MULTITEX_GROUP_R = 10321
ID_MULTITEX_GROUP_G = 10322
ID_MULTITEX_GROUP_B = 10323

ID_FOLDER_SELECT_TEXT = 10800
ID_FOLDER_SELECT_BUTTON = 10801
ID_FOLDER_SELECT_GROUP = 10802

ID_IMPORT_TEXTURES_BUTTON = 10900

ID_BLANK = 101010

class TexArguments:
    pass

class AboutDialog(c4d.gui.GeDialog):
    def CreateLayout(self):
        self.SetTitle("About")
        self.AddStaticText(ID_BLANK, c4d.BFH_CENTER, 0, 0, "TexToMatO")
        self.AddStaticText(ID_BLANK, c4d.BFH_CENTER, 0, 0, VERSION_NUMBER)
        self.AddStaticText(ID_BLANK, c4d.BFH_CENTER, 0, 0, "A powerful texture to material converter for Cinema 4D")
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddStaticText(ID_AUTHOR_TEXT, c4d.BFH_FIT, 0, 0, "Author:\tMarvin Jérôme Stephan")
        self.AddStaticText(ID_AUTHOR_TEXT, c4d.BFH_FIT, 0, 0, "GitHub:\t" + ABOUT_TEXT_GITHUB)
        self.AddStaticText(ID_AUTHOR_TEXT, c4d.BFH_FIT, 0, 0, "Website:\t" + ABOUT_TEXT_WEBSITE)
        return True


class MainDialog(c4d.gui.GeDialog):

    def CreateLayout(self):
        """
        """
        self.SetTitle("TexToMatO: über texture importer")

        self.MenuSubBegin("About & Help")
        self.MenuAddString(ID_LINK_ABOUT, "About")
        self.MenuAddString(ID_LINK_README, "Readme")
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
        self.AddStaticText(ID_AUTHOR_TEXT, c4d.BFH_FIT, 0, 0, ABOUT_TEXT_WEBSITE)
        self.GroupEnd()
        return True

    def InitValues(self):
        # self.SetBool(ID_CREATE_AND_REPLACE, True)
        self.SetBool(ID_DERIVE_FOLDER_FROM_BASE, True)
        self.SetBool(ID_DELETE_BASE, True)
        self.SetBool(ID_SPRITE_OPACITY, True)
        self.SetString(ID_FOLDER_SELECT_TEXT, "Folder to read textures from", flags=c4d.EDITTEXT_HELPTEXT)

        return True

    def Command(self, mid, msg):
        # print(mid)

        if mid == ID_IMPORT_TEXTURES_BUTTON:

            texArguments = {
                "bumpFlipY":        self.GetBool(ID_BUMP_FLIPY),
                "bumpLegacy":       self.GetBool(ID_BUMP_LEGACY),
                "spriteOpacity":    self.GetBool(ID_SPRITE_OPACITY),
                "texFolder":        self.GetFilename(ID_FOLDER_SELECT_TEXT),
                "multiTex":         multitex_dict
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
                    importTexturesFromBase(derive_folder_from_base = self.GetBool(ID_DERIVE_FOLDER_FROM_BASE), 
                                           delete_base_texture = self.GetBool(ID_DELETE_BASE),
                                           material_arguments = texArguments)

        elif mid == ID_LINK_ABOUT:
            about_dlg = AboutDialog()
            about_dlg.Open(c4d.DLG_TYPE_MODAL, xpos=-2, ypos=-2)

        elif mid == ID_LINK_README:
            webbrowser.open(ABOUT_LINK_README)

        elif mid == ID_DERIVE_FOLDER_FROM_BASE or mid == RADIO_GROUP:
            if self.GetBool(ID_DERIVE_FOLDER_FROM_BASE) and self.GetBool(RADIO_IMPORT_FROM_BASE):
                self.Enable(ID_FOLDER_SELECT_TEXT, False)
                self.Enable(ID_FOLDER_SELECT_BUTTON, False)
            else:
                self.Enable(ID_FOLDER_SELECT_TEXT, True)
                self.Enable(ID_FOLDER_SELECT_BUTTON, True)

        elif mid == ID_FOLDER_SELECT_BUTTON:
            path = c4d.storage.LoadDialog(c4d.FILESELECTTYPE_ANYTHING, "Select texture folder", c4d.FILESELECT_DIRECTORY, "Select")
            if path:
                self.SetFilename(ID_FOLDER_SELECT_TEXT, path)
        return True

if __name__=='__main__':
    dlg = MainDialog()
    dlg.Open(c4d.DLG_TYPE_ASYNC, defaultw=0, xpos=-2, ypos=-2)
