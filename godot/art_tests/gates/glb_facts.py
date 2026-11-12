"""glb_facts.py - reads the facts a 3D gate needs straight out of a .glb file. No Blender needed.

A .glb is a small binary wrapper around a JSON document (the "glTF" scene description) plus
the raw mesh data. Most of what a game cares about is in the JSON: how many triangles, how big
the model is, which way is up, how many bones, which animations. Reading it directly takes
milliseconds, so these checks can run on every asset, in CI, without starting Blender.

    python glb_facts.py model.glb          prints the facts as JSON

glTF rules this relies on: +Y is up, units are metres, and -Z... is not fixed for "forward"
(Godot treats a model's front as +Z after import), so only up-axis and size are checked here.
"""
import json
import pathlib
import struct
import sys

import numpy as np


def read_gltf_json(path: pathlib.Path) -> dict:
    """Returns the JSON document inside a .glb (or loads a .gltf text file directly).

    GLB layout: 12-byte header ("glTF", version, total length), then chunks. Each chunk is
    a 4-byte length, a 4-byte type and the data; the first chunk is always the JSON.
    struct.unpack("<I", ...) reads a little-endian unsigned 32-bit integer.
    """
    data = path.read_bytes()
    if data[:4] != b"glTF":
        return json.loads(data.decode("utf-8"))
    json_length = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + json_length].decode("utf-8"))


def node_matrix(node: dict) -> np.ndarray:
    """A node's local transform as a 4x4 matrix, from either its "matrix" or its T/R/S parts."""
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T    # glTF stores columns first
    t = node.get("translation", [0, 0, 0])
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])                          # a quaternion
    s = node.get("scale", [1, 1, 1])
    rotation = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    matrix = np.eye(4)
    matrix[:3, :3] = rotation * np.array(s)          # scale each column, then rotate
    matrix[:3, 3] = t
    return matrix


def facts(path: pathlib.Path) -> dict:
    """Everything the gate needs to know about one model.

    Returns a dict with: triangles, meshes, materials, bounds_min/bounds_max/size (metres, in
    the model's own space, +Y up), bones, skins, max_influences (4 or 8), clips
    [{name, seconds}], textures, file_kb.
    """
    doc = read_gltf_json(path)
    accessors = doc.get("accessors", [])
    nodes = doc.get("nodes", [])
    meshes = doc.get("meshes", [])

    triangles = 0
    max_influences = 0
    for mesh in meshes:
        for primitive in mesh.get("primitives", []):
            if primitive.get("mode", 4) != 4:        # 4 = triangles; lines and points do not count
                continue
            attributes = primitive.get("attributes", {})
            if "indices" in primitive:
                triangles += accessors[primitive["indices"]]["count"] // 3
            elif "POSITION" in attributes:
                triangles += accessors[attributes["POSITION"]]["count"] // 3
            # Each JOINTS_n attribute holds 4 bone influences per vertex: JOINTS_0 alone = at
            # most 4 (what Godot's web renderer wants); JOINTS_1 present = up to 8.
            sets = sum(1 for name in attributes if name.startswith("JOINTS_"))
            max_influences = max(max_influences, sets * 4)

    # Walk the node tree from the scene roots, multiplying transforms on the way down, and
    # grow one bounding box from the 8 corners of every mesh's own box.
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    scene = doc.get("scenes", [{}])[doc.get("scene", 0)] if doc.get("scenes") else {}
    stack = [(index, np.eye(4)) for index in scene.get("nodes", range(len(nodes)))]
    while stack:
        index, parent = stack.pop()
        node = nodes[index]
        world = parent @ node_matrix(node)           # "@" is matrix multiplication
        if "mesh" in node:
            # A skinned mesh is placed by its bones, not its node: glTF says ignore the node transform.
            placement = np.eye(4) if "skin" in node else world
            for primitive in meshes[node["mesh"]].get("primitives", []):
                position = primitive.get("attributes", {}).get("POSITION")
                if position is None or "min" not in accessors[position]:
                    continue
                a, b = accessors[position]["min"], accessors[position]["max"]
                corners = np.array([[x, y, z, 1.0] for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])])
                moved = (placement @ corners.T).T[:, :3]
                lo = np.minimum(lo, moved.min(axis=0))
                hi = np.maximum(hi, moved.max(axis=0))
        stack.extend((child, world) for child in node.get("children", []))
    has_bounds = bool(np.isfinite(lo).all())

    clips = []
    for animation in doc.get("animations", []):
        # A clip's length is the largest keyframe time among its samplers' input accessors.
        ends = [accessors[sampler["input"]].get("max", [0.0])[0] for sampler in animation.get("samplers", [])]
        clips.append({"name": animation.get("name", ""), "seconds": round(max(ends, default=0.0), 3)})

    skins = doc.get("skins", [])
    return {
        "file": path.name,
        "file_kb": round(path.stat().st_size / 1024.0, 1),
        "triangles": triangles,
        "meshes": len(meshes),
        "materials": len(doc.get("materials", [])),
        "textures": len(doc.get("images", [])),
        "bounds_min": [round(float(v), 4) for v in lo] if has_bounds else None,
        "bounds_max": [round(float(v), 4) for v in hi] if has_bounds else None,
        "size": [round(float(v), 4) for v in (hi - lo)] if has_bounds else None,
        "skins": len(skins),
        "bones": max((len(skin.get("joints", [])) for skin in skins), default=0),
        "max_influences": max_influences,
        "clips": clips,
    }


if __name__ == "__main__":
    print(json.dumps(facts(pathlib.Path(sys.argv[1])), indent=2))
