"""
PBR Node Wiring

Constructs Principled BSDF node trees with PBR map textures.
Handles Normal, Roughness, Metallic, ORM, AO, and Emission maps.
"""

import bpy

from .scanner import TextureGroup
from ..core.logging import debug_log


def wire_pbr_maps(mat, texture_group):
    """Wire PBR texture maps into an existing material's node tree.

    The material should already have a Principled BSDF with a base color
    texture connected (created by the standard create_material_with_image).

    Args:
        mat: Blender material with use_nodes=True
        texture_group: TextureGroup with detected PBR maps
    """
    if not mat or not mat.use_nodes or not mat.node_tree:
        return

    nt = mat.node_tree
    bsdf = _get_principled_bsdf(nt)
    if not bsdf:
        return

    x_offset = -700  # PBR textures placed left of the base color texture

    _wiring_steps = []

    if 'normal' in texture_group.maps:
        _wiring_steps.append(
            ('normal', _wire_normal_map, (nt, bsdf, texture_group.maps['normal'], x_offset)))

    if 'orm' in texture_group.maps:
        _wiring_steps.append(
            ('orm', _wire_orm_map, (nt, bsdf, texture_group.maps['orm'], x_offset)))
    else:
        if 'roughness' in texture_group.maps:
            _wiring_steps.append(
                ('roughness', _wire_single_channel,
                 (nt, bsdf, texture_group.maps['roughness'], 'Roughness', x_offset, -200)))
        if 'metallic' in texture_group.maps:
            _wiring_steps.append(
                ('metallic', _wire_single_channel,
                 (nt, bsdf, texture_group.maps['metallic'], 'Metallic', x_offset, -400)))
        if 'ao' in texture_group.maps:
            _wiring_steps.append(
                ('ao', _wire_ao_map, (nt, texture_group.maps['ao'], x_offset)))

    if 'emission' in texture_group.maps:
        _wiring_steps.append(
            ('emission', _wire_emission_map, (nt, bsdf, texture_group.maps['emission'], x_offset)))

    for map_type, func, args in _wiring_steps:
        try:
            func(*args)
            debug_log(f"[PBR] Wired {map_type}: {texture_group.maps[map_type]}")
        except Exception as e:
            print(f"Anvil Level Design: Failed to wire PBR map '{map_type}': {e}", flush=True)


def _get_principled_bsdf(node_tree):
    """Find the Principled BSDF node in the node tree."""
    for node in node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            return node
    return None


def _load_image(filepath, color_space='Non-Color'):
    """Load an image and set its color space."""
    img = bpy.data.images.load(filepath, check_existing=True)
    img.colorspace_settings.name = color_space
    return img


def _add_image_texture(node_tree, filepath, color_space, location):
    """Add an Image Texture node with the given image."""
    tex = node_tree.nodes.new('ShaderNodeTexImage')
    tex.image = _load_image(filepath, color_space)
    tex.location = location
    return tex


def _wire_normal_map(node_tree, bsdf, filepath, x_offset):
    """Wire: Image Texture → Normal Map → BSDF Normal."""
    tex = _add_image_texture(
        node_tree, filepath, 'Non-Color', (x_offset - 300, -500)
    )

    normal_map = node_tree.nodes.new('ShaderNodeNormalMap')
    normal_map.space = 'TANGENT'
    normal_map.location = (x_offset, -500)

    node_tree.links.new(tex.outputs['Color'], normal_map.inputs['Color'])
    node_tree.links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])


def _wire_single_channel(node_tree, bsdf, filepath, input_name, x_offset, y_offset):
    """Wire: Image Texture → BSDF input directly."""
    tex = _add_image_texture(
        node_tree, filepath, 'Non-Color', (x_offset, y_offset)
    )
    node_tree.links.new(tex.outputs['Color'], bsdf.inputs[input_name])


def _wire_orm_map(node_tree, bsdf, filepath, x_offset):
    """Wire ORM map: Image → Separate RGB → R=AO, G=Roughness, B=Metallic."""
    tex = _add_image_texture(
        node_tree, filepath, 'Non-Color', (x_offset - 300, -200)
    )

    separate = node_tree.nodes.new('ShaderNodeSeparateColor')
    separate.location = (x_offset, -200)

    node_tree.links.new(tex.outputs['Color'], separate.inputs['Color'])
    node_tree.links.new(separate.outputs['Green'], bsdf.inputs['Roughness'])
    node_tree.links.new(separate.outputs['Blue'], bsdf.inputs['Metallic'])

    # AO via glTF Material Output if available
    _wire_ao_from_channel(node_tree, separate.outputs['Red'], x_offset)


def _wire_ao_map(node_tree, filepath, x_offset):
    """Wire standalone AO map via glTF Material Output node."""
    tex = _add_image_texture(
        node_tree, filepath, 'Non-Color', (x_offset - 300, -600)
    )
    _wire_ao_from_channel(node_tree, tex.outputs['Color'], x_offset)


def _wire_ao_from_channel(node_tree, source_output, x_offset):
    """Connect an AO channel to glTF Material Output.

    Creates the glTF Material Output node group if needed.
    """
    # Find or create glTF Material Output
    gltf_output = None
    for node in node_tree.nodes:
        if node.type == 'GROUP' and node.node_tree and node.node_tree.name == 'glTF Material Output':
            gltf_output = node
            break

    if gltf_output is None:
        # Try to create the node group
        try:
            # The glTF Material Output is a built-in node group
            group_name = 'glTF Material Output'
            if group_name not in bpy.data.node_groups:
                # Create a minimal glTF Material Output node group
                ng = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
                ng.interface.new_socket(
                    name='Occlusion', in_out='INPUT', socket_type='NodeSocketFloat'
                )

            gltf_output = node_tree.nodes.new('ShaderNodeGroup')
            gltf_output.node_tree = bpy.data.node_groups[group_name]
            gltf_output.location = (x_offset + 200, -600)
        except Exception:
            return

    if 'Occlusion' in gltf_output.inputs:
        node_tree.links.new(source_output, gltf_output.inputs['Occlusion'])


def _wire_emission_map(node_tree, bsdf, filepath, x_offset):
    """Wire emission map to BSDF Emission Color and set strength."""
    tex = _add_image_texture(
        node_tree, filepath, 'sRGB', (x_offset, -800)
    )
    node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Emission Color'])
    # Set emission strength if it's at default 0
    if bsdf.inputs['Emission Strength'].default_value < 0.01:
        bsdf.inputs['Emission Strength'].default_value = 1.0
