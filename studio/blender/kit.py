"""Small tools the build shares: meshes from code, bevels, collections and materials by name."""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector


def collection(name, parent=None):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if col.name not in (parent or bpy.context.scene.collection).children:
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def obj_from_bmesh(name, bm, col, mat=None, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    return ob


def box(name, lo, hi, col, mat=None, bevel=0.0, segments=2):
    """An axis-aligned box from corner lo to corner hi (metres), with rounded edges if bevel > 0."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    size = Vector(hi) - Vector(lo)
    mid = (Vector(hi) + Vector(lo)) / 2
    bmesh.ops.transform(bm, matrix=Matrix.Translation(mid) @ Matrix.Diagonal((*size, 1)), verts=bm.verts)
    ob = obj_from_bmesh(name, bm, col, mat)
    if bevel > 0:
        add_bevel(ob, min(bevel, min(size) * 0.45), segments)
    return ob


def add_bevel(ob, width, segments=2):
    m = ob.modifiers.new("bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.harden_normals = True
    ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
    return m


def subsurf(ob, levels=2):
    m = ob.modifiers.new("soft", "SUBSURF")
    m.levels = levels
    m.render_levels = levels
    ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
    return m


def cylinder(name, center, radius, height, col, mat=None, segments=48, bevel=0.0, axis="Z"):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius, depth=height)
    rot = {"Z": Matrix.Identity(4), "X": Matrix.Rotation(math.pi / 2, 4, "Y"), "Y": Matrix.Rotation(math.pi / 2, 4, "X")}[axis]
    bmesh.ops.transform(bm, matrix=Matrix.Translation(center) @ rot, verts=bm.verts)
    ob = obj_from_bmesh(name, bm, col, mat, smooth=True)
    if bevel > 0:
        add_bevel(ob, bevel, 2)
    return ob


def lathe(name, profile, col, mat=None, segments=64, at=(0, 0, 0)):
    """A turned shape from a profile [(radius, height), ...] spun round the vertical axis."""
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0, z)) for r, z in profile]
    for a, b in zip(verts, verts[1:]):
        bm.edges.new((a, b))
    bmesh.ops.spin(bm, geom=bm.verts[:] + bm.edges[:], cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=segments, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.translate(bm, vec=Vector(at), verts=bm.verts)
    return obj_from_bmesh(name, bm, col, mat, smooth=True)


def polygon_slab(name, poly, z0, z1, col, mat=None):
    """A flat slab with a polygon outline (metres, counter-clockwise or not)."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z0)) for x, y in poly]
    face = bm.faces.new(vs)
    bmesh.ops.recalc_face_normals(bm, faces=[face])
    if face.normal.z < 0:
        face.normal_flip()
    res = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [v for v in res["geom"] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, z1 - z0), verts=top)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bmesh(name, bm, col, mat)


def place(objects, at=(0, 0, 0), rot_z=0.0, name="group", col=None):
    """Parents objects to an empty, so a piece built at the origin can be put anywhere, turned about Z."""
    root = bpy.data.objects.new(name, None)
    (col or objects[0].users_collection[0]).objects.link(root)
    for ob in objects:
        ob.parent = root
    root.location = at
    root.rotation_euler = (0, 0, rot_z)
    return root
