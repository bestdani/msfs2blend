import struct

STRUCT_INDEX = struct.Struct('H')
STRUCT_VEC2 = struct.Struct('ee')
STRUCT_VEC3 = struct.Struct('fff')


def sub_buffer_from_view(buffer, buffer_view) -> list:
    start = buffer_view['byteOffset']
    end = start + buffer_view['byteLength']
    return buffer[start:end]


def get_start_indices(accessor, stride) -> list:
    start = accessor['byteOffset']
    count = accessor['count']
    end = start + count * stride
    return [i for i in range(start, end, stride)]


def get_indices(accessor_indices, buffer_indices) -> list:
    start = accessor_indices['byteOffset']
    end = start + accessor_indices['count'] * STRUCT_INDEX.size
    return [
        STRUCT_INDEX.unpack(buffer_indices[i:i + STRUCT_INDEX.size])
        for i in range(start, end, STRUCT_INDEX.size)
    ]


def read_primitive(gltf, buffer, selected):
    accessor_pos = gltf['accessors'][91]
    accessor_texcoord = gltf['accessors'][94]
    accessor_indices = gltf['accessors'][97]
    buffer_view_indices = gltf['bufferViews'][4]
    buffer_view_data = gltf['bufferViews'][3]
    buffer_indices = sub_buffer_from_view(buffer, buffer_view_indices)
    buffer_data = sub_buffer_from_view(buffer, buffer_view_data)

    indices = get_indices(accessor_indices, buffer_indices)
    # TODO use actual indices although they appear to be ordered for now
    triangles_indices = [
        (indices[i], indices[i + 1], indices[i + 2])
        for i in range(0, len(indices), 3)
    ]

    pos_starts = get_start_indices(
        accessor_pos, buffer_view_data['byteStride'])
    texcoord_starts = get_start_indices(
        accessor_texcoord, buffer_view_data['byteStride'])

    pos_values = [
        STRUCT_VEC3.unpack(buffer_data[i:i + STRUCT_VEC3.size])
        for i in pos_starts]
    texcoord_values = [
        STRUCT_VEC2.unpack(buffer_data[i:i + STRUCT_VEC2.size])
        for i in texcoord_starts]

    pos_tris = [
        (pos_values[i], pos_values[i + 1], pos_values[i + 2])
        for i in range(0, len(pos_values), 3)]
    texcoord_tris = [
        (texcoord_values[i], texcoord_values[i + 1], texcoord_values[i + 2])
        for i in range(0, len(texcoord_values), 3)]

    return pos_tris, texcoord_tris
