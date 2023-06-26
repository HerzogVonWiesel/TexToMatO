# Tex🍅 (TexToMatO)
## TexToMatO - A powerful texture to material converter for Cinema 4D

### Important Notes
* This script is intended to create & modify Redshift materials in Cinema 4D using the node system.
* It depends on the [Redshift Material API](https://github.com/HerzogVonWiesel/Custom_Redshift_API) to work.

### Installation
* Install the Redshift Material API if you haven't already.
    * Copy redshift_ID.py and redshift_node.py into the Cinema 4D python library folder.
        - Windows: `C:\Users\USERNAME\AppData\Roaming\MAXON\CINEMA 4D VERSION\python310\libs\`
        - Mac: `/Users/USERNAME/Library/Preferences/MAXON/CINEMA 4D VERSION/python310/libs/`
* Copy TexToMatO into the scripts folder of Cinema 4D.
    * Extensions -> User Scripts -> Open script folder
* You can then open TexToMatO by going to Extensions -> User Scripts -> User Scripts -> TexToMatO
    * You can add a shortcut to open TexToMatO in your layout for easier access.

### Features
TexToMatO has two modes: Either you can import all textures inside a folder to create new materials for each set from scratch, or you can import missing textures in selected materials (which often occur after importing .fbx files for example).

* `Import all textures from folder`
* `Import textures from base in material` : Searches for an already existing texture in the selected materials and finds the missing ones from the texture folder
  * `Derive texture folder from base` : If OFF, you can specify which folder to read the textures from instead of automatically deriving it from the base texture in the material
  * `Delete base texture in material`: Deletes the already existing texture in the material to not end up with duplicate texture nodes.
---
* `Normal options`
  * `Flip Y` : Toggles the option to flip the Y channel of the normal. This is useful when working with DirectX vs. OpenGL normal maps.
  * `Use Legacy Bump` : If you see any artifacting with the normal maps, toggle this option.
---
* `MultiTexture` : Textures from game files often pack multiple textures into a single one by using the RGB channels. With this option you can specify which texture is used to pack the textures, and what texture is in which channel. TexToMatO will connect it accordingly.
---
* `Miscellaneous`
  * `Use Sprite node for opacity` : You can decide whether the opacity texture gets plugged into the Standard Material's opacity channel or whether it should be used as a sprite node (more efficient, but only binary opacity).



https://github.com/HerzogVonWiesel/TexToMatO/assets/58423784/97296862-e080-4ad1-b7c0-f7dbe042e90b

