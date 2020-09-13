# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####
import math
import subprocess
from typing import Optional, Callable

bl_info = {
    "name": "MSFS glTF importer",
    "author": "bestdani",
    "version": (0, 2),
    "blender": (2, 80, 0),
    "location": "File > Import > MSFS glTF",
    "description": "Imports a glTF file with Asobo extensions from the "
                   "Microsoft Flight Simulator (2020) for texture painting",
    "warning": "",
    "doc_url": "",
    "category": "Import-Export",
}

import json
import pathlib
import struct

import bpy
import bmesh

import numpy as np
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator, AddonPreferences

STRUCT_INDEX = struct.Struct('H')
STRUCT_VEC2 = struct.Struct('ee')
STRUCT_VEC3 = struct.Struct('fff')

converted_normal_images = set()


def sub_buffer_from_view(buffer, buffer_view) -> list:
    start = buffer_view['byteOffset']
    end = start + buffer_view['byteLength']
    return buffer[start:end]


def get_start_indices(accessor, stride) -> list:
    try:
        start = accessor['byteOffset']
    except KeyError:
        start = 0
    count = accessor['count']
    end = start + count * stride
    return [i for i in range(start, end, stride)]


def get_indices(accessor_indices, buffer_indices) -> list:
    try:
        start = accessor_indices['byteOffset']
    except KeyError:
        start = 0
    end = start + accessor_indices['count'] * STRUCT_INDEX.size
    return [
        STRUCT_INDEX.unpack(buffer_indices[i:i + STRUCT_INDEX.size])[0]
        for i in range(start, end, STRUCT_INDEX.size)
    ]


def read_primitive(gltf, buffer, selected):
    attributes = selected['attributes']

    accessor_pos = gltf['accessors'][attributes['POSITION']]
    accessor_texcoord_0 = gltf['accessors'][attributes['TEXCOORD_0']]
    accessor_texcoord_1 = gltf['accessors'][attributes['TEXCOORD_1']]
    accessor_indices = gltf['accessors'][selected['indices']]
    buffer_view_indices = gltf['bufferViews'][accessor_indices['bufferView']]
    # TODO separate buffer views and buffers per accessor since they can
    #  potentially be different
    buffer_view_data = gltf['bufferViews'][accessor_pos['bufferView']]
    buffer_indices = sub_buffer_from_view(buffer, buffer_view_indices)
    buffer_data = sub_buffer_from_view(buffer, buffer_view_data)

    indices = get_indices(accessor_indices, buffer_indices)

    pos_starts = get_start_indices(
        accessor_pos, buffer_view_data['byteStride'])
    texcoord_0_starts = get_start_indices(
        accessor_texcoord_0, buffer_view_data['byteStride'])
    texcoord_1_starts = get_start_indices(
        accessor_texcoord_1, buffer_view_data['byteStride'])

    pos_values = [
        STRUCT_VEC3.unpack(buffer_data[i:i + STRUCT_VEC3.size])
        for i in pos_starts]
    texcoord_0_values = [
        STRUCT_VEC2.unpack(buffer_data[i:i + STRUCT_VEC2.size])
        for i in texcoord_0_starts]
    texcoord_1_values = [
        STRUCT_VEC2.unpack(buffer_data[i:i + STRUCT_VEC2.size])
        for i in texcoord_1_starts]

    return indices, pos_values, texcoord_0_values, texcoord_1_values


def as_tris(indices, pos_values, texcoord_values):
    triangles_indices = [
        (indices[i], indices[i + 1], indices[i + 2])
        for i in range(0, len(indices), 3)
    ]
    pos_tris = []
    texcoord_tris = []
    for tri_idx in triangles_indices:
        i1, i2, i3 = tri_idx
        pos_tris.append((pos_values[i1], pos_values[i2], pos_values[i3]))
        texcoord_tris.append(
            (texcoord_values[i1], texcoord_values[i2], texcoord_values[i3]))
    return pos_tris, texcoord_tris


def fill_mesh_data(buffer, gltf, gltf_mesh, uv0, uv1, b_mesh, mat_mapping, report):
    idx_offset = 0
    primitives = gltf_mesh['primitives']
    idx, pos, tc0, tc1 = read_primitive(gltf, buffer, primitives[0])

    for p in pos:
        # converting to blender z up world
        b_mesh.verts.new((p[0], -p[2], p[1]))
    b_mesh.verts.ensure_lookup_table()

    for prim_idx, primitive in enumerate(primitives[0:]):
        # TODO handle Asobo primitives with different indices
        # see skipped exceptions on a320 model for example
        try:
            asobo_data = primitive['extras']['ASOBO_primitive']
        except KeyError:
            # TODO enhance error message
            report({'ERROR'}, "No Asobo sub primitive")
            continue

        try:
            mat_index = mat_mapping[primitive['material']]
        except KeyError:
            mat_index = -1

        try:
            start_index = asobo_data['StartIndex']
        except KeyError:
            start_index = 0

        try:
            start_vertex = asobo_data['BaseVertexIndex']
        except KeyError:
            start_vertex = 0

        tri_count = asobo_data['PrimitiveCount']
        for tri_i in range(tri_count):
            i = start_index + tri_i * 3
            face_indices = (
                idx_offset + start_vertex + idx[i + 2],
                idx_offset + start_vertex + idx[i + 1],
                idx_offset + start_vertex + idx[i + 0],
            )
            face = b_mesh.faces.new((
                b_mesh.verts[face_indices[0]],
                b_mesh.verts[face_indices[1]],
                b_mesh.verts[face_indices[2]],
            ))
            face.material_index = mat_index
            for i, loop in enumerate(face.loops):
                u, v = tc0[face_indices[i]]
                loop[uv0].uv = (u, 1 - v)
                u, v = tc1[face_indices[i]]
                loop[uv1].uv = (u, 1 - v)


def create_meshes(buffer, gltf, materials, report):
    meshes = []
    for gltf_mesh in gltf['meshes']:
        bl_mesh = bpy.data.meshes.new(gltf_mesh['name'])
        meshes.append(bl_mesh)

        mat_mapping = {}
        material_count = 0
        for primitive in gltf_mesh['primitives']:
            gltf_mat_index = primitive['material']
            material = materials[gltf_mat_index]
            mesh_mat_index = bl_mesh.materials.find(material.name)
            if mesh_mat_index > -1:
                mat_mapping[gltf_mat_index] = mesh_mat_index
            else:
                mat_mapping[gltf_mat_index] = material_count
                bl_mesh.materials.append(material)
                material_count += 1

        b_mesh = bmesh.new()
        uv0 = b_mesh.loops.layers.uv.new()
        uv1 = b_mesh.loops.layers.uv.new()

        try:
            fill_mesh_data(buffer, gltf, gltf_mesh, uv0, uv1, b_mesh, mat_mapping,
                           report)
        except Exception:
            mesh_name = gltf_mesh['name']
            report({'ERROR'}, f'could not handle mesh "{mesh_name}"')
            continue

        b_mesh.to_mesh(bl_mesh)
        bl_mesh.update()
    return meshes


def create_objects(nodes, meshes):
    objects = []
    for node in nodes:
        name = node['name']
        try:
            mesh = meshes[node['mesh']]
        except KeyError:
            mesh = bpy.data.meshes.new(name)

        obj = bpy.data.objects.new(name, mesh)

        trans = node['translation']
        # converting to blender z up world
        obj.location = trans[0], -trans[2], trans[1]

        scale = node['scale']
        # converting to blender z up world
        obj.scale = scale[0], scale[2], scale[1]

        obj.rotation_mode = 'QUATERNION'
        rot = node['rotation']
        # converting to blender z up world
        obj.rotation_quaternion = rot[3], rot[0], -rot[2], rot[1]

        objects.append(obj)
    return objects


def load_gltf_file(gltf_file_name):
    gltf_file_path = pathlib.Path(gltf_file_name)
    bin_file_name = gltf_file_path.with_suffix('.bin')

    with open(gltf_file_path, 'r') as handle:
        gltf = json.load(handle)

    with open(bin_file_name, 'rb') as handle:
        buffer = handle.read()

    return gltf, buffer


def convert_normal_image(normal_image, report):
    pixels = np.array(normal_image.pixels[:]).reshape((-1, 4))
    rgb_pixels = pixels[:, 0:3]
    rgb_pixels[:, 1] = 1.0 - rgb_pixels[:, 1]
    rgb_pixels[:, 2] = np.sqrt(
        1 - (rgb_pixels[:, 0] - 0.5) ** 2 - (rgb_pixels[:, 1] - 0.5) ** 2
    )
    pixel_data = pixels.reshape((-1, 1)).transpose()[0]
    normal_image.pixels = pixel_data
    try:
        normal_image.save()
    except RuntimeError:
        report(
            {'ERROR'},
            f"could not save converted image {normal_image.name}")


def setup_mat_nodes(bl_mat, gltf_mat, textures, images, report):
    try:
        base_texture = textures[
            gltf_mat['pbrMetallicRoughness']['baseColorTexture']['index']]
        base_image = images[
            base_texture['extensions']['MSFT_texture_dds']['source']]
    except (KeyError, IndexError):
        base_image = None

    try:
        metallic_roughness_texture = textures[
            gltf_mat['pbrMetallicRoughness']['metallicRoughnessTexture'][
                'index']]
        met_rough_image = images[
            metallic_roughness_texture['extensions']['MSFT_texture_dds'][
                'source']]
    except (KeyError, IndexError):
        met_rough_image = None

    try:
        normal_texture = textures[gltf_mat['normalTexture']['index']]
        normal_image = images[
            normal_texture['extensions']['MSFT_texture_dds']['source']]
    except (KeyError, IndexError):
        normal_image = None

    bl_mat.use_nodes = True
    tree = bl_mat.node_tree
    p_bsdf_node = tree.nodes['Principled BSDF']

    if base_image:
        base_image_node = tree.nodes.new('ShaderNodeTexImage')
        base_image_node.location = (-500, 400)
        base_image_node.image = base_image
        tree.links.new(p_bsdf_node.inputs['Base Color'],
                       base_image_node.outputs['Color'])
        tree.links.new(p_bsdf_node.inputs['Alpha'],
                       base_image_node.outputs['Alpha'])

    if met_rough_image:
        met_rough_image_node = tree.nodes.new('ShaderNodeTexImage')
        met_rough_image_node.location = (-500, 0)
        met_rough_image_node.image = met_rough_image
        met_rough_image_node.image.colorspace_settings.name = 'Non-Color'

        separate_node = tree.nodes.new('ShaderNodeSeparateRGB')
        separate_node.location = (-200, 0)

        tree.links.new(separate_node.inputs['Image'],
                       met_rough_image_node.outputs['Color'])
        tree.links.new(p_bsdf_node.inputs['Metallic'],
                       separate_node.outputs['B'])
        tree.links.new(p_bsdf_node.inputs['Roughness'],
                       separate_node.outputs['G'])

    if normal_image:
        if normal_image not in converted_normal_images:
            report({'INFO'}, f"converting_normal_image {normal_image}")
            convert_normal_image(normal_image, report)
            converted_normal_images.add(normal_image)
        normal_image_node = tree.nodes.new('ShaderNodeTexImage')
        normal_image_node.location = (-500, -400)
        normal_image_node.image = normal_image
        normal_image_node.image.colorspace_settings.name = 'Non-Color'

        normal_map_node = tree.nodes.new('ShaderNodeNormalMap')
        normal_map_node.location = (-200, -400)

        tree.links.new(normal_map_node.inputs['Color'],
                       normal_image_node.outputs['Color'])
        tree.links.new(p_bsdf_node.inputs['Normal'],
                       normal_map_node.outputs['Normal'])


def create_materials(gltf, images, report):
    report({'INFO'}, 'creating materials')
    materials = []
    textures = gltf['textures']
    for gltf_mat in gltf['materials']:
        try:
            blend_method = gltf_mat['alphaMode']
        except KeyError:
            blend_method = 'OPAQUE'

        name = gltf_mat['name']
        bl_mat = bpy.data.materials.new(name)
        bl_mat.blend_method = blend_method
        setup_mat_nodes(bl_mat, gltf_mat, textures, images, report)
        materials.append(bl_mat)
    return materials


def setup_object_hierarchy(bl_objects, gltf, collection):
    scene_description = gltf['scenes'][0]
    gltf_nodes = gltf['nodes']
    for i in scene_description['nodes']:
        gltf_node = gltf_nodes[i]
        bl_object = bl_objects[i]
        collection.objects.link(bl_object)
        try:
            gltf_children = gltf_node['children']
        except KeyError:
            # no children to add
            pass
        else:
            for j in gltf_children:
                bl_subobject = bl_objects[j]
                bl_subobject.parent = bl_object
                collection.objects.link(bl_subobject)


def convert_images(gltf, texture_in_dir, texconv_path, texture_out_dir,
                   report) -> list:
    to_convert_images = []
    converted_images = []
    final_image_paths = []
    for i, image in enumerate(gltf['images']):
        try:
            dds_file = texture_in_dir / image['uri']
        except KeyError:
            report({'ERROR'}, f"invalid image at {i}")
            final_image_paths.append(None)
            continue

        if not dds_file.exists():
            report({'ERROR'},
                   f"invalid image file location at {i}: {dds_file}")
            final_image_paths.append(None)
            continue

        final_image_paths.append('')
        to_convert_images.append(str(dds_file))

    output_dir_param = str(texture_out_dir)
    texture_out_dir.mkdir(parents=True, exist_ok=True)
    report({'INFO'}, "converting images with texconv")
    try:
        output_lines = subprocess.run(
            [
                str(texconv_path),
                '-y',
                '-o', output_dir_param,
                '-f', 'rgba',
                '-ft', 'png',
                *to_convert_images
            ],
            check=True,
            capture_output=True
        ).stdout.decode('cp1252').split('\r\n')
    except subprocess.CalledProcessError as e:
        report({'ERROR'}, f"could not convert image textures {e}")
        return final_image_paths
    else:
        for line in output_lines:
            line: str
            if line.startswith('writing'):
                png_file = line[len('writing '):]
                path = pathlib.Path(png_file)
                if path.exists():
                    converted_images.append(path)
                else:
                    converted_images.append(None)

        conv_i = 0
        for i, image in enumerate(final_image_paths):
            if image is None:
                continue
            try:
                final_image_paths[i] = converted_images[conv_i]
            except IndexError:
                final_image_paths[i] = None
            else:
                conv_i += 1
        return final_image_paths


def load_images(images, report) -> list:
    bl_images = []
    for image in images:
        if image:
            bl_image = bpy.data.images.load(filepath=str(image))
            bl_image.use_fake_user = True
        else:
            bl_image = None
        bl_images.append(bl_image)
    return bl_images


def import_msfs_gltf(context, gltf_file: str, report: Callable,
                     textures_allowed: bool,
                     texconv_path: Optional[pathlib.Path],
                     texture_out_dir: Optional[pathlib.Path],
                     texture_in_dir: Optional[pathlib.Path]):
    gltf, buffer = load_gltf_file(gltf_file)

    if textures_allowed:
        gltf_name = pathlib.Path(gltf_file).name
        texture_name = pathlib.Path(texture_in_dir).name
        full_texture_out_dir = texture_out_dir / gltf_name / texture_name
        images = convert_images(
            gltf, texture_in_dir, texconv_path, full_texture_out_dir, report)
    else:
        images = []

    bl_images = load_images(images, report)
    materials = create_materials(gltf, bl_images, report)
    meshes = create_meshes(buffer, gltf, materials, report)
    objects = create_objects(gltf['nodes'], meshes)
    setup_object_hierarchy(objects, gltf, context.collection)

    return {'FINISHED'}


def path_good(path: pathlib.Path) -> bool:
    return path.name == 'texconv.exe' and path.exists()


class MsfsGltfImporter(Operator, ImportHelper):
    bl_idname = "msfs_gltf.importer"
    bl_label = "Import MSFS glTF file"

    filename_ext = ".gltf"

    texture_folder_name: StringProperty(
        name="Texture name",
        description="texture folder name",
        default="TEXTURE",
    )

    filter_glob: StringProperty(
        default="*.gltf",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        preferences = context.preferences
        addon_prefs = preferences.addons[__name__].preferences
        file_path = pathlib.Path(self.filepath)
        textures_allowed = addon_prefs.textures_allowed

        textures_path = file_path.parent.parent / self.texture_folder_name
        textures_allowed = textures_allowed and textures_path.exists() and \
                           textures_path.is_dir()

        if textures_allowed:
            texconv_path = pathlib.Path(addon_prefs.texconv_file)
            texture_target_dir = pathlib.Path(addon_prefs.texture_target_dir)
        else:
            texconv_path = None
            texture_target_dir = None

        return import_msfs_gltf(
            context, self.filepath, self.report,
            textures_allowed, texconv_path, texture_target_dir, textures_path)


class MsfsGltfImporterPreferences(AddonPreferences):
    bl_idname = __name__

    texconv_file: StringProperty(
        name="Folder path",
        description="absolute path to Microsoft texconv tool",
        default="",
        subtype="FILE_PATH"
    )

    texture_target_dir: StringProperty(
        name="Folder path",
        description="location where converted textures get saved in their "
                    "subfolders",
        default="",
        subtype="DIR_PATH"
    )

    textures_allowed: BoolProperty(options={'HIDDEN'})

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        row = box.row()
        row.label(text="Microsoft Texconv Tool")
        row = box.row()
        row.label(text="Required to enable importing textures.")
        row = box.row()
        row.label(
            text="This tool automatically converts DDS images for usage "
                 "inside of blender")
        row = box.row()
        row.operator("wm.url_open", text="Download texconv.exe").url = \
            "https://github.com/microsoft/DirectXTex/releases"
        row = box.row()
        row.prop(self, "texconv_file", text="Path to downloaded texconv.exe")
        texconv_path = pathlib.Path(self.texconv_file)

        self.textures_allowed = True
        if not path_good(texconv_path):
            self.textures_allowed = False
            row = box.row()
            row.label(
                text="No texconv.exe file has been selected. Texture import "
                     "is disabled.",
                icon='ERROR')
        row = box.row()
        row.prop(self, "texture_target_dir",
                 text="Base path for converted textures")
        target_path = pathlib.Path(self.texture_target_dir)
        if self.texture_target_dir == "" or not target_path.exists() or not \
                target_path.is_dir():
            self.textures_allowed = False
            row = box.row()
            row.label(
                text="No valid conversion path path entered. Texture import "
                     "is disabled.",
                icon='ERROR')


def menu_func_import(self, context):
    self.layout.operator(MsfsGltfImporter.bl_idname, text="MSFS glTF (.gltf)")


def register():
    bpy.utils.register_class(MsfsGltfImporter)
    bpy.utils.register_class(MsfsGltfImporterPreferences)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(MsfsGltfImporter)
    bpy.utils.unregister_class(MsfsGltfImporterPreferences)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
    register()
