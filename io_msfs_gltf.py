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
import configparser
import itertools
import subprocess
from typing import Callable, List, Optional, Set

NORMAL_IMAGES_LIST_JSON = 'bl_importer_converted_normal_images.json'

bl_info = {
    "name": "MSFS glTF importer",
    "author": "bestdani",
    "version": (0, 3),
    "blender": (2, 80, 0),
    "location": "File > Import > MSFS glTF",
    "description": "Imports a glTF file with Asobo extensions from the "
                   "Microsoft Flight Simulator (2020) for texture painting",
    "warning": "",
    "doc_url": "https://github.com/bestdani/msfs2blend",
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


def fill_mesh_data(buffer, gltf, gltf_mesh, uv0, uv1, b_mesh, mat_mapping,
                   report):
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
            fill_mesh_data(buffer, gltf, gltf_mesh, uv0, uv1, b_mesh,
                           mat_mapping,
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


def setup_mat_nodes(bl_mat, gltf_mat, textures, images,
                    converted_normal_images: set, report):
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
        normal_image_name = pathlib.Path(normal_image.filepath).name
        if normal_image_name not in converted_normal_images:
            report({'INFO'}, f"converting_normal_image {normal_image}")
            convert_normal_image(normal_image, report)
            converted_normal_images.add(normal_image_name)
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


def create_materials(gltf, images, report, converted_normal_images: set):
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
        setup_mat_nodes(bl_mat, gltf_mat, textures, images,
                        converted_normal_images, report)
        materials.append(bl_mat)
    return materials


def setup_object_hierarchy(bl_objects, gltf, collection):
    scene_description = gltf['scenes'][0]
    gltf_nodes = gltf['nodes']

    def add_children(bl_parent_object, gltf_parent_node):
        try:
            gltf_children = gltf_parent_node['children']
        except KeyError:
            return

        for j in gltf_children:
            gltf_child_node = gltf_nodes[j]
            bl_child_object = bl_objects[j]
            bl_child_object.parent = bl_parent_object
            collection.objects.link(bl_child_object)
            add_children(bl_child_object, gltf_child_node)

    for i in scene_description['nodes']:
        gltf_node = gltf_nodes[i]
        bl_object = bl_objects[i]
        collection.objects.link(bl_object)
        add_children(bl_object, gltf_node)


def import_images(gltf, converted_textures_dir: pathlib.Path, report) -> list:
    image_list = []
    for i, image in enumerate(gltf['images']):
        dds_file = converted_textures_dir / image['uri']
        png_file = dds_file.with_suffix('.PNG')
        if png_file.exists():
            image_list.append(png_file)
        else:
            report({'ERROR'}, f"Cannot import image {png_file}")
    return image_list


def convert_images(gltf, original_textures_dir, texconv_path: pathlib.Path,
                   fs_base_path: Optional[pathlib.Path],
                   converted_textures_dir: pathlib.Path, report) -> list:
    to_convert_images = []
    converted_images = []
    final_image_paths = []
    for i, image in enumerate(gltf['images']):
        try:
            dds_file = original_textures_dir / image['uri']
        except KeyError:
            report({'ERROR'}, f"invalid image at {i}")
            final_image_paths.append(None)
            continue

        if not dds_file.exists():
            texture_fallbacks = collect_fallbacks_of(original_textures_dir,
                                                     fs_base_path, report)
            for fallback_dir in texture_fallbacks:
                dds_file = fallback_dir / image['uri']
                if dds_file.exists():
                    break
            else:
                report({'ERROR'},
                       f"invalid image file location at {i}: {dds_file}")
                final_image_paths.append(None)
                continue

        final_image_paths.append('')
        to_convert_images.append(str(dds_file))

    converted_textures_dir.mkdir(parents=True, exist_ok=True)
    output_dir_param = str(converted_textures_dir)
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


def collect_fallbacks_of(
        texture_path: pathlib.Path, fs_base_path: Optional[pathlib.Path],
        report: Callable
) -> Set[pathlib.Path]:
    def _collect_recursive(current_path: pathlib.Path):
        texture_cfg_path = current_path / 'texture.cfg'
        config = configparser.ConfigParser()
        config.read(texture_cfg_path.absolute())

        if not texture_cfg_path.exists():
            report({'INFO'}, f"non existing texture.cfg {texture_cfg_path}")

        try:
            fltsim = config['fltsim']
            for i in itertools.count(start=1):
                fallback_path = pathlib.Path(fltsim[f'fallback.{i}'])
                absolute_path = (texture_path / fallback_path).resolve()
                if absolute_path.exists():
                    final_path = absolute_path
                elif fs_base_path is not None:
                    for i, dir in enumerate(fallback_path.parts):
                        if dir != '..':
                            non_backwards_path = '/'.join(
                                fallback_path.parts[i:])
                            base_relative_path = fs_base_path / \
                                                 non_backwards_path
                            break
                    else:
                        report({'INFO'},
                               f"could not find fallback {fallback_path}")
                        continue

                    if base_relative_path.exists():
                        final_path = base_relative_path
                    else:
                        report({'INFO'},
                               f"could not find fallback {fallback_path}")
                        continue
                else:
                    report({'INFO'},
                           f"could not find fallback {fallback_path}")
                    continue

                if final_path not in fallbacks:
                    fallbacks.add(final_path)
                    _collect_recursive(final_path)

        except KeyError:
            pass

    fallbacks = set()
    _collect_recursive(texture_path)
    return fallbacks


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


def save_converted_normal_list(normal_images: list, json_file: pathlib.Path):
    with open(str(json_file), 'w') as handle:
        json.dump(normal_images, handle)


# FIXME refactor parameters
def load_converted_normal_list(json_file: pathlib.Path) -> list:
    with open(str(json_file), 'r') as handle:
        normal_images = json.load(handle)
    return normal_images


def import_msfs_gltf(context, gltf_file: pathlib.Path, report: Callable,
                     convert_textures: bool, import_textures: bool,
                     texconv_path: Optional[pathlib.Path],
                     fs_base_path: Optional[pathlib.Path],
                     converted_textures_dir: Optional[pathlib.Path],
                     original_textures_dirs: List[pathlib.Path]):
    gltf, buffer = load_gltf_file(gltf_file)

    if convert_textures:
        # TODO refactor multiple dir usage
        images = convert_images(gltf, original_textures_dirs[0], texconv_path,
                                fs_base_path, converted_textures_dir, report)
        converted_normal_images = set()

    elif import_textures:
        images = import_images(
            gltf, converted_textures_dir, report)
        try:
            converted_normal_images = set(load_converted_normal_list(
                converted_textures_dir / NORMAL_IMAGES_LIST_JSON
            ))
        except FileNotFoundError:
            converted_normal_images = set()

    else:
        images = []
        converted_normal_images = set()

    bl_images = load_images(images, report)
    materials = create_materials(gltf, bl_images, report,
                                 converted_normal_images)

    if convert_textures:
        save_converted_normal_list(
            list(converted_normal_images),
            converted_textures_dir / NORMAL_IMAGES_LIST_JSON
        )

    meshes = create_meshes(buffer, gltf, materials, report)
    objects = create_objects(gltf['nodes'], meshes)
    setup_object_hierarchy(objects, gltf, context.collection)


def path_good(path: pathlib.Path) -> bool:
    return path.name == 'texconv.exe' and path.exists()


class ImportProperties:
    texconv_path: Optional[pathlib.Path]
    fs_base_path: Optional[pathlib.Path]
    gltf_file: Optional[pathlib.Path]
    convert_textures: bool
    import_textures: bool
    convert_textures_dirs: List[pathlib.Path]
    import_textures_dir: Optional[pathlib.Path]

    @classmethod
    def reset(cls):
        cls.texconv_path = None
        cls.fs_base_path = None
        cls.gltf_file = None
        cls.convert_textures = False
        cls.import_textures = False
        cls.convert_textures_dirs = []
        cls.import_textures_dir = None


class MsfsTexturesImporter(Operator, ImportHelper):
    bl_idname = "msfs_gltf.textures_importer"
    bl_label = "Import Textures"

    filter_glob: StringProperty(
        default="*.png",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        ImportProperties.import_textures = True
        textures_dir = pathlib.Path(self.filepath)
        if not textures_dir.is_dir():
            textures_dir = textures_dir.parent
        ImportProperties.import_textures_dir = textures_dir
        import_msfs_gltf(context, ImportProperties.gltf_file, self.report,
                         ImportProperties.convert_textures,
                         ImportProperties.import_textures,
                         ImportProperties.texconv_path,
                         ImportProperties.fs_base_path,
                         ImportProperties.import_textures_dir,
                         ImportProperties.convert_textures_dirs)

        return {'FINISHED'}


class MsfsTexturesConverter(Operator, ImportHelper):
    bl_idname = "msfs_gltf.textures_converter"
    bl_label = "texture.cfg"

    filter_glob: StringProperty(
        default="*.cfg",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        ImportProperties.convert_textures = True
        textures_dir = pathlib.Path(self.filepath)
        if not textures_dir.is_dir():
            textures_dir = textures_dir.parent
        ImportProperties.convert_textures_dirs = [textures_dir.absolute()]
        bpy.ops.msfs_gltf.textures_importer('INVOKE_DEFAULT')

        return {'FINISHED'}


class MsfsGltfImporter(Operator, ImportHelper):
    bl_idname = "msfs_gltf.model_importer"
    bl_label = "Import MSFS glTF file"

    filename_ext = ".gltf"

    filter_glob: StringProperty(
        default="*.gltf",
        options={'HIDDEN'},
        maxlen=255,
    )

    import_textures: EnumProperty(
        name="Import Textures",
        description="Choose between two items",
        items=(
            ('NO_IMPORT', "No Texture Import", "Do not import any texture"),
            ('LOAD_CONVERTED', "Load Converted Textures",
             "Load already converted textures"),
            ('CONVERT', "Convert Original Textures",
             "Convert MSFS textures, save at a specified directory and load "
             "these textures."),
        ),
        default='NO_IMPORT',
    )

    def execute(self, context):
        preferences = context.preferences
        addon_prefs = preferences.addons[__name__].preferences

        ImportProperties.reset()
        ImportProperties.gltf_file = self.filepath
        if self.import_textures == 'LOAD_CONVERTED':
            ImportProperties.fs_base_path = pathlib.Path(
                addon_prefs.fs_base_dir)
            bpy.ops.msfs_gltf.textures_importer('INVOKE_DEFAULT')
        elif self.import_textures == 'CONVERT':
            ImportProperties.texconv_path = pathlib.Path(
                addon_prefs.texconv_file)
            ImportProperties.fs_base_path = pathlib.Path(
                addon_prefs.fs_base_dir)
            if addon_prefs.conversion_allowed:
                bpy.ops.msfs_gltf.textures_converter('INVOKE_DEFAULT')
            else:
                self.report(
                    {'ERROR'},
                    "Texture conversion is disabled because of non "
                    "proper texconv.exe configuration in the Add-on settings")
        else:
            import_msfs_gltf(context, ImportProperties.gltf_file, self.report,
                             ImportProperties.convert_textures,
                             ImportProperties.import_textures,
                             ImportProperties.texconv_path,
                             ImportProperties.fs_base_path,
                             ImportProperties.import_textures_dir,
                             ImportProperties.convert_textures_dirs)

        return {'FINISHED'}


class MsfsGltfImporterPreferences(AddonPreferences):
    bl_idname = __name__

    texconv_file: StringProperty(
        name="Folder path",
        description="absolute path to Microsoft texconv tool",
        default="",
        subtype="FILE_PATH"
    )

    fs_base_dir: StringProperty(
        name="Folder path",
        description="location where converted textures get saved in their "
                    "subfolders",
        default="",
        subtype="DIR_PATH"
    )

    conversion_allowed: BoolProperty(options={'HIDDEN'})
    texconv_path: Optional[pathlib.Path]
    fs_base_path: Optional[pathlib.Path]

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        row = box.row()
        row.label(text="Microsoft Texconv Tool")
        row = box.row()
        row.label(text="Required to enable texture conversion.")
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
        if path_good(texconv_path):
            self.conversion_allowed = True
            self.texconv_path = texconv_path
        else:
            self.conversion_allowed = False
            row = box.row()
            row.label(
                text="No texconv.exe file has been selected. Texture import "
                     "is disabled.",
                icon='ERROR')

        box = layout.box()
        row = box.row()
        row.label(text="Flight Simulator Installation")
        row = box.row()
        row.label(text="Required to find all textures")
        row = box.row()
        row.prop(self, "fs_base_dir",
                 text="Flight Simulator fs-base path")
        fs_base_path = pathlib.Path(self.fs_base_dir)
        if fs_base_path.exists() and fs_base_path.is_dir():
            self.fs_base_path = fs_base_path
        else:
            row = box.row()
            row.label(
                text="No fs base path has been specified. Some textures "
                     "might not get imported!",
                icon='ERROR')


def menu_func_import(self, context):
    self.layout.operator(MsfsGltfImporter.bl_idname, text="MSFS glTF (.gltf)")


def register():
    bpy.utils.register_class(MsfsGltfImporterPreferences)
    bpy.utils.register_class(MsfsGltfImporter)
    bpy.utils.register_class(MsfsTexturesConverter)
    bpy.utils.register_class(MsfsTexturesImporter)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(MsfsGltfImporterPreferences)
    bpy.utils.unregister_class(MsfsGltfImporter)
    bpy.utils.unregister_class(MsfsTexturesConverter)
    bpy.utils.unregister_class(MsfsTexturesImporter)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
    register()
