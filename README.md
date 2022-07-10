# Microsoft Flight Simulator (FS2020) Model Importer for Blender
![github_teaser](https://user-images.githubusercontent.com/11302762/178145547-89f1a095-cfd9-4ee8-909f-531fa320f084.jpg)

## Latest Release Download
See Releases page or click here: [Latest Release](https://github.com/bestdani/msfs2blend/releases/download/v0.1.1/io_msfs_gltf.py)

## How To Install and Use
**Enter required paths in the addon preferences:**

![0_addon_options](https://user-images.githubusercontent.com/11302762/178145514-b3ae9929-b926-410d-8916-255825e26813.png)

The texconv.exe will be used to convert MSFS dds files to png files for blender and further usage.
Ensure to also point to the MSFS installation directory (will be required to find textures and config files).

**Use the import menu to import the MSFS glTF file:**

![1_import_menu](https://user-images.githubusercontent.com/11302762/178145522-8a274104-f918-4108-983a-8fdc15b40cf8.png)

**Ensure *Convert Original Textures* is selected and open the desired model file**

![2_select_texture_conversion](https://user-images.githubusercontent.com/11302762/178145523-67c1d7ed-5512-4913-b9aa-92df9f053ea9.png)

**Selected the texture.cfg file from which you want to import the textures (using the default texture directory is recommended)**

![3_select_texture_cfg_file](https://user-images.githubusercontent.com/11302762/178145524-64d0ae72-26eb-400d-9e7f-ecb28959059c.png)

**Select the texture conversion working directory**

![4_select_textures_output](https://user-images.githubusercontent.com/11302762/178145525-77e1ed00-4ad7-4fa5-b310-634c71faa33f.png)

**Select the texture *output* directory to which the converted textures will be *written* first and then imported and assigned to the materials by blender**

![5_final_import](https://user-images.githubusercontent.com/11302762/178145526-b07d26a6-c2a3-4528-8e52-190057f5a019.png)

You can then either start 3d painting in blender or export the result to external 3d painting tools. When exporting glTF all textures can be exported applied if the target tool supports glTF import, other compatible formats might give the same seamless experience.

## Quickstart Video Introduction
[Add-on installation and blender 3d texturing basics](https://youtu.be/SZCe_x-V9co) (outdated, texture import capability is not shown there)

## About this Importer
This is a **quick and dirty** importer for [Blender 3.0+](https://blender.org) **intended to be used for painting liveries** using the existing model files in 3d texture painting tools like blender itself.

This means at the current stage the importer is able to import **most meshes** with a UV map and nothing more!

It's by no means able to fully reconstruct the original model files and not intended to be used like this.

Note that you probably want to move some objects to be able to use these files for 3D texture painting.

##  Known Limitations and Issues
* Some object rotations seem to be wrong probably because they are animated with bones which is not supported by this importer for now.
* Some special objects (sound positions) causes errors which can just be ignored for texture painting purposes.

## Community:
Flight Sim Forums discussion: https://forums.flightsimulator.com/t/3d-livery-painting-on-the-msfs-models/257637
