import json
import logging
import pathlib

import bpy
import bmesh

import importer

GLTF_FILE = 'examples/A320_NEO_LOD00.gltf'


def fill_mesh_data(buffer, gltf, gltf_mesh, uv, b_mesh, mat_mapping):
    idx_offset = 0
    primitives = gltf_mesh['primitives']
    idx, pos, tc = importer.read_primitive(gltf, buffer, primitives[0])

    for p in pos:
        # converting to blender z up world
        b_mesh.verts.new((p[0], -p[2], p[1]))
    b_mesh.verts.ensure_lookup_table()

    for prim_idx, primitive in enumerate(primitives[0:]):
        # TODO handle asobo primitives with different indices
        # see skipped exception on a320 model
        try:
            asobo_data = primitive['extras']['ASOBO_primitive']
        except KeyError:
            # TODO enhance error message
            logging.error("no ASOBO sub primitive")
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
                loop[uv].uv = tc[face_indices[i]]


def create_meshes(buffer, gltf, materials):
    meshes = []
    for gltf_mesh in gltf['meshes']:
        # FIXME remove this after testing
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

        bl_mesh.use_fake_user = True
        b_mesh = bmesh.new()
        uv = b_mesh.loops.layers.uv.new()

        try:
            fill_mesh_data(buffer, gltf, gltf_mesh, uv, b_mesh, mat_mapping)
        except Exception:
            mesh_name = gltf_mesh['name']
            logging.error(f'could not convert mesh "{mesh_name}"')
            continue

        b_mesh.to_mesh(bl_mesh)
        bl_mesh.update()
    return meshes


def create_objects(gltf, meshes):
    objects = []
    for node in gltf['nodes']:
        name = node['name']
        try:
            mesh = meshes[node['mesh']]
        except KeyError:
            mesh = bpy.data.meshes.new(name)

        obj = bpy.data.objects.new(name, mesh)
        trans = node['translation']
        # converting to blender z up world
        obj.location = (trans[0], -trans[2], trans[1])
        obj.scale = node['scale']
        obj.rotation_quaternion = node['rotation']
        obj.use_fake_user = True
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


def create_materials(gltf):
    materials = []
    for gltf_mat in gltf['materials']:
        name = gltf_mat['name']
        bl_mat = bpy.data.materials.new(name)
        materials.append(bl_mat)
    return materials


def import_asobo_gltf(gltf_file):
    gltf, buffer = load_gltf_file(gltf_file)

    materials = create_materials(gltf)
    meshes = create_meshes(buffer, gltf, materials)
    objects = create_objects(gltf, meshes)
    collection = bpy.data.scenes['Scene'].collection
    for obj in objects:
        collection.objects.link(obj)
    bpy.ops.wm.save_as_mainfile(filepath='imported.blend')


if __name__ == '__main__':
    import_asobo_gltf(GLTF_FILE)
