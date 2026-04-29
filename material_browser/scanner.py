"""
PBR Texture Scanner

Given a selected texture file, finds associated PBR maps by checking:
1. Same directory — sibling files with PBR suffixes sharing the same base name
2. "pbr" subfolder — files in a "pbr" subdirectory with matching PBR suffixes
"""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


# Supported image extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tga', '.bmp', '.exr', '.tiff', '.tif', '.webp'}

# PBR suffix patterns → map type (order matters: longer/more specific first)
_PBR_SUFFIX_MAP = [
    # ORM packed
    (re.compile(r'_orm$', re.IGNORECASE), 'orm'),
    # Ambient occlusion
    (re.compile(r'_ambient_occlusion$', re.IGNORECASE), 'ao'),
    (re.compile(r'_occlusion$', re.IGNORECASE), 'ao'),
    (re.compile(r'_ao$', re.IGNORECASE), 'ao'),
    # Normal
    (re.compile(r'_normal$', re.IGNORECASE), 'normal'),
    (re.compile(r'_nor$', re.IGNORECASE), 'normal'),
    (re.compile(r'_nrm$', re.IGNORECASE), 'normal'),
    # Roughness
    (re.compile(r'_roughness$', re.IGNORECASE), 'roughness'),
    (re.compile(r'_rough$', re.IGNORECASE), 'roughness'),
    (re.compile(r'_smoothness$', re.IGNORECASE), 'roughness'),
    # Metallic
    (re.compile(r'_metallic$', re.IGNORECASE), 'metallic'),
    (re.compile(r'_metal$', re.IGNORECASE), 'metallic'),
    (re.compile(r'_met$', re.IGNORECASE), 'metallic'),
    # Emission
    (re.compile(r'_emissive$', re.IGNORECASE), 'emission'),
    (re.compile(r'_emission$', re.IGNORECASE), 'emission'),
    (re.compile(r'_emit$', re.IGNORECASE), 'emission'),
    # Base color (explicit suffixes)
    (re.compile(r'_color$', re.IGNORECASE), 'color'),
    (re.compile(r'_diffuse$', re.IGNORECASE), 'color'),
    (re.compile(r'_diffuseoriginal$', re.IGNORECASE), 'color'),
    (re.compile(r'_base$', re.IGNORECASE), 'color'),
    (re.compile(r'_albedo$', re.IGNORECASE), 'color'),
    (re.compile(r'_basecolor$', re.IGNORECASE), 'color'),
    (re.compile(r'_base_color$', re.IGNORECASE), 'color'),
]


@dataclass
class TextureGroup:
    """A group of related PBR texture files."""
    name: str
    maps: Dict[str, str] = field(default_factory=dict)  # map_type -> absolute path

    @property
    def has_pbr(self) -> bool:
        return any(k != 'color' for k in self.maps)


def _classify_stem(stem: str) -> Tuple[str, str]:
    """Classify a filename stem into (base_name, map_type).

    If no PBR suffix is found, map_type defaults to 'color'.
    """
    for pattern, map_type in _PBR_SUFFIX_MAP:
        match = pattern.search(stem)
        if match:
            base = stem[:match.start()]
            if base:
                return base, map_type
    return stem, 'color'


def _get_base_name(filepath: str) -> str:
    """Extract the PBR base name from a filepath.

    E.g. '/textures/brick_color.png' -> 'brick'
         '/textures/brick.png' -> 'brick'
    """
    stem = os.path.splitext(os.path.basename(filepath))[0]
    base_name, _ = _classify_stem(stem)
    return base_name


def _scan_directory_for_maps(directory: str, base_name: str) -> Dict[str, str]:
    """Scan a directory for PBR maps matching the given base name."""
    maps = {}
    try:
        for entry in os.scandir(directory):
            if not entry.is_file():
                continue
            name, ext = os.path.splitext(entry.name)
            if ext.lower() not in IMAGE_EXTENSIONS:
                continue
            file_base, map_type = _classify_stem(name)
            if file_base.lower() == base_name.lower() and map_type != 'color':
                if map_type not in maps:
                    maps[map_type] = entry.path
    except (OSError, PermissionError):
        pass
    return maps


def find_pbr_maps_for_file(filepath: str) -> Optional[TextureGroup]:
    """Find PBR maps associated with a selected texture file.

    Searches in:
    1. Same directory as the selected file
    2. A "pbr" subfolder in the same directory

    Args:
        filepath: Absolute path to the selected base color texture

    Returns:
        TextureGroup with detected PBR maps, or None if no PBR maps found
    """
    if not os.path.isfile(filepath):
        return None

    directory = os.path.dirname(filepath)
    base_name = _get_base_name(filepath)

    group = TextureGroup(name=base_name)
    group.maps['color'] = filepath

    # 1. Scan same directory
    sibling_maps = _scan_directory_for_maps(directory, base_name)
    group.maps.update(sibling_maps)

    # 2. Scan "pbr" subfolder (case-insensitive: pbr, PBR, Pbr, etc.)
    try:
        for entry in os.scandir(directory):
            if entry.is_dir() and entry.name.lower() == 'pbr':
                pbr_maps = _scan_directory_for_maps(entry.path, base_name)
                for map_type, path in pbr_maps.items():
                    if map_type not in group.maps:
                        group.maps[map_type] = path
                break
    except (OSError, PermissionError):
        pass

    return group if group.has_pbr else None
