# Tex🍅 (TexToMatO)
## TexToMatO - A powerful texture to material converter for Cinema 4D
![image](https://github.com/HerzogVonWiesel/TexToMatO/assets/58423784/7303c021-015a-4197-9c7d-96a89791ab4d)

Check it out on [Gumroad to support this project and me!](https://jeromestephan.gumroad.com/l/TexToMatO)

### Important Notes
* This script is intended to create & modify Redshift materials in Cinema 4D using the node system.
* It depends on the [Redshift Material API](https://github.com/HerzogVonWiesel/Custom_Redshift_API) to work.

### Installation
* Unzip TexToMatO into your plugins folder of Cinema 4D. (below are examples)
     - Windows: `C:\Users\USERNAME\AppData\Roaming\MAXON\CINEMA 4D VERSION\plugins\`
     - Mac: `/Users/USERNAME/Library/Preferences/MAXON/CINEMA 4D VERSION/plugins/`
* Make sure there is no TexToMatO folder inside of the plugins/TexToMatO folder
* You can then open TexToMatO by going to Extensions -> TexToMatO
    * You can add a shortcut to open TexToMatO in your layout for easier access!

### Features
TexToMatO has two modes: Either you can import all textures inside a folder to create new materials for each set from scratch, or you can import missing textures in selected materials (which often occur after importing .fbx files for example).

* `Import all textures from folder`
* `Import textures from base in material` : Searches for an already existing texture in the selected materials and finds the missing ones from the texture folder
  * `Derive texture folder from base` : If OFF, you can specify which folder to read the textures from instead of automatically deriving it from the base texture in the material
  * `Delete base texture in material`: Deletes the already existing texture in the material to not end up with duplicate texture nodes.
  * `Rename material based on texture`: Renames the material to the base texture's base name.
---
* `Normal options`
  * `Flip Y` : Toggles the option to flip the Y channel of the normal. This is useful when working with DirectX vs. OpenGL normal maps.
  * `Use Legacy Bump` : If you see any artifacting with the normal maps, toggle this option.
---
* `MultiTexture` : Textures from game files often pack multiple textures into a single one by using the RGB channels. With this option you can specify which texture is used to pack the textures, and what texture is in which channel. TexToMatO will connect it accordingly.
---
* `Miscellaneous`
  * `Use Sprite node for opacity` : You can decide whether the opacity texture gets plugged into the Standard Material's opacity channel or whether it should be used as a sprite node (more efficient, but only binary opacity).
  * `Use case-insensitive regex` (be careful not to match too much with that though)
---
* Regex options
  *Use custom regex: Manage your own custom, additional regex you can add for your version of the plugin: maybe you have some interesting channel names in your studio?
---
* Preferences
  * Automatically add Color Correct nodes to color textures (Albedo & Translucency)
  * Automatically add Triplanar nodes to all textures
  * Whether to connect AO to overall tint or multiplying it with Albedo in a color layer
---
* Additional Features
  * All texture nodes can be managed at once with SCALE, OFFSET and ROTATION nodes added to the graph
  * Submit Bugs and Feedback easily with a form
  * Once you import one or more textures, all settings are saved and are there for you when you need them (well, and restart C4D)
  * No worries, you can easily reset them to default in the preferences menu should you want to!
---
Have fun and keep on creating!

- Jérôme


https://github.com/HerzogVonWiesel/TexToMatO/assets/58423784/97296862-e080-4ad1-b7c0-f7dbe042e90b

