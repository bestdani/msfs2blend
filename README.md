# MSFS (FS2020) Model Importer for Blender

## Latest Release Download
See Releases page or click here: [TODO link]

## How To Install
In a nutshell:
* Menu Bar: **Edit > Preferences...**
* Preferences Popup: Select **Add-ons** on the left side.
* Addon Settings: Press **Install** Button.
* File Browser: Locate the downloaded **io_msfs_gltf.py** file and press **Install Add-on**.
* Addon Settings: Tick the Checkbox next to the Add-on entry.

For details refer to the [blender manual](https://docs.blender.org/manual/en/latest/editors/preferences/addons.html#rd-party-add-ons).

## About this Importer
This is a **quick and dirty** importer for [Blender 2.8+](https://blender.org) **intended to be used for painting liveries** using the existing model files in 3d texture painting tools like blender itslef.

This means at the current stage the importer is able to import **most meshes** with a UVMap and nothing more!

It's by no means able to fully reconstruct the original model files and not intended to be used like this.

Note that you probably want to move some objects to be able to use these files for 3D texture painting.

##  Known Limitations and Issues
Many of these could be potentially solved with future updates.
* Some meshes cannot be imported.
* No support for UV channel 2 for now.
* No import textures or material properties.
* Some object translations seem not to be at the actual positions. 
