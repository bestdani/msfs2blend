# Microsoft Flight Simulator (FS2020) Model Importer for Blender
![](https://i.imgur.com/zxj4pZC.jpg)

## Latest Release Download
See Releases page or click here: [Latest Release](https://github.com/bestdani/msfs2blend/releases/download/v0.1.1/io_msfs_gltf.py)

## Quickstart Video Introduction
[Add-on installation and blender 3d texturing basics](https://youtu.be/SZCe_x-V9co)

## How To Install
In a nutshell:
* Menu Bar: **Edit > Preferences...**
* Preferences Popup: Select **Add-ons** on the left side.
* Addon Settings: Press **Install** Button.
* File Browser: Locate the downloaded **io_msfs_gltf.py** file and press **Install Add-on**.
* Addon Settings: Tick the Checkbox next to the Add-on entry.
* Follow the instructions in the addon to download and setup [texconv.exe](https://github.com/microsoft/DirectXTex/releases) to enable texture import after conversion.

For details refer to the [blender manual](https://docs.blender.org/manual/en/latest/editors/preferences/addons.html#rd-party-add-ons).

## How To Use
* TODO Add short picture description especially explain texture import options

## About this Importer
This is a **quick and dirty** importer for [Blender 2.8+](https://blender.org) **intended to be used for painting liveries** using the existing model files in 3d texture painting tools like blender itself.

This means at the current stage the importer is able to import **most meshes** with a UV map and nothing more!

It's by no means able to fully reconstruct the original model files and not intended to be used like this.

Note that you probably want to move some objects to be able to use these files for 3D texture painting.

##  Known Limitations and Issues
Many of these can potentially be solved with future updates.
* Some meshes cannot be imported (see TODO items in the source code).
* Some object rotations seem to be wrong probably because they are animated with bones which is not supported by this importer for now.

## Community:
Flight Sim Forums discussion: https://forums.flightsimulator.com/t/3d-livery-painting-on-the-msfs-models/257637
