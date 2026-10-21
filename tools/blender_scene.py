"""Фотореальна сцена ALUMA для Blender Cycles: виріб з aluma3d.js в інтер'єрі з CC0-матеріалів.

Запускає tools/render_photo.js (рамка запуску — там), напряму:
    blender -b -P tools/blender_scene.py -- --geo renders-master/geo/tavor.json --out x.png --shot hero

Геометрія — та сама, що в 3D-перегляді на сайті (експорт window.geo з tools/render_products.html), тож рендер
і перегляд не розходяться. Матеріали дерева — запечені альбедо renders-master/textures (ті самі тонування).
Підлога, стіна, льон, HDRI, декор — Poly Haven CC0 з $ALUMA_CC0 (tools/fetch_cc0.py, джерела — docs/ASSETS.md).
Стільці — наша проста модель (дуб + льон), чужих виробів у кадрі немає.
"""
import argparse, json, math, os, sys

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CC0 = os.environ.get("ALUMA_CC0", "/opt/ihor/aluma-table/tmp/cc0")
TEX = os.path.join(ROOT, "renders-master", "textures")

ap = argparse.ArgumentParser()
ap.add_argument("--geo", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--shot", default="hero")            # hero | angle | open
ap.add_argument("--finish", default="natural")
ap.add_argument("--albedo", default="")             # своє альбедо замість файлу тону (TONE_TEX)
ap.add_argument("--w", type=int, default=1600)
ap.add_argument("--h", type=int, default=1000)
ap.add_argument("--samples", type=int, default=160)
ap.add_argument("--threads", type=int, default=3)
ap.add_argument("--cam", default="{}")               # JSON: az, eye, lens, margin, target_z, fstop
ap.add_argument("--decor", default="dining")         # dining | none
ap.add_argument("--hdri", default="photo_studio_loft_hall_2k.hdr")
ap.add_argument("--blend", default="")               # зберегти сцену (.blend) для ручної правки
A = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
CAM = json.loads(A.cam)

# ---------------------------------------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
col = scene.collection


def img(path, non_color=False):
    im = bpy.data.images.load(path, check_existing=True)
    if non_color:
        im.colorspace_settings.name = "Non-Color"
    return im


def link_obj(name, me):
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob


def node_tex(nt, path, non_color=False, vector=None, proj="FLAT"):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img(path, non_color)
    t.projection = proj
    if proj == "BOX":
        t.projection_blend = 0.2
    if vector is not None:
        nt.links.new(vector, t.inputs["Vector"])
    return t


def pbr(name, base=None, rough=0.6, metal=0.0, coat=0.0, coat_rough=0.3, color=(0.8, 0.8, 0.8)):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = coat_rough
    return m, m.node_tree, b


# ---- дуб виробу -----------------------------------------------------------------------------------------
# тон -> (альбедо, скан нормалей і шорсткості, щільність повтору) — те саме, що FINISHES в aluma3d.js
# (tests/test_oak_tones.py звіряє); файли пише tools/oak_tones.py у renders-master/textures
TONE_TEX = {
    "natural": ("natural-albedo", "oak", 1.0),
    "light": ("tone-light-albedo", "washed-oak", 1.83),
    "honey": ("tone-honey-albedo", "oak", 1.0),
    "smoked": ("tone-smoked-albedo", "black-oak", 1.83),
    "black": ("tone-black-albedo", "black-oak", 1.83),
}


def oak_material(finish, albedo=""):
    """Дуб під сатиновим лаком: альбедо тону, нормалі й шорсткість його справжнього скану шпону."""
    stem, maps, scale = TONE_TEX.get(finish, TONE_TEX["natural"])
    alb = albedo or os.path.join(TEX, f"{stem}-2048.jpg")
    if not os.path.exists(alb):
        raise SystemExit(f"немає {alb} — python3 tools/oak_tones.py")
    m, nt, b = pbr(f"oak-{finish}", coat=0.22, coat_rough=0.28)
    uv = nt.nodes.new("ShaderNodeUVMap")
    mp = nt.nodes.new("ShaderNodeMapping")           # скани 1 м повторюються щільніше за 1,83-метровий oak_veneer_01
    mp.inputs["Scale"].default_value = (scale, scale, 1)
    nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
    vec = mp.outputs["Vector"]
    ta = node_tex(nt, alb, vector=vec)
    nt.links.new(ta.outputs["Color"], b.inputs["Base Color"])
    tr = node_tex(nt, os.path.join(TEX, f"{maps}-rough-2048.jpg"), True, vec)
    mr = nt.nodes.new("ShaderNodeMapRange")          # сатин: 0.38..0.62, без дзеркальних плям
    mr.inputs["To Min"].default_value = 0.38 if finish != "black" else 0.45
    mr.inputs["To Max"].default_value = 0.62 if finish != "black" else 0.7
    nt.links.new(tr.outputs["Color"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    tn = node_tex(nt, os.path.join(TEX, f"{maps}-normal-2048.jpg"), True, vec)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.35
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Specular IOR Level"].default_value = 0.45
    return m


OAK = oak_material(A.finish, A.albedo)
# стільці — декор, не товар: тонування міняє лише стіл, стільці завжди натуральний дуб
CHAIR_OAK = OAK if A.finish == "natural" and not A.albedo else oak_material("natural")
MATS = {
    "oak": OAK, "face": OAK,
    "under": pbr("under", rough=0.8, color=(0.62, 0.56, 0.48) if A.finish != "black" else (0.08, 0.075, 0.07))[0],
    "steel": pbr("steel", rough=0.42, metal=0.6, coat=0.3, coat_rough=0.35, color=(0.022, 0.021, 0.02))[0],
    "dark": pbr("dark", rough=0.9, color=(0.012, 0.01, 0.009))[0],
}


# ---- виріб з JSON ---------------------------------------------------------------------------------------
def product(path):
    d = json.load(open(path))
    obs = []
    for i, ms in enumerate(d["meshes"]):
        p, uv = ms["p"], ms["uv"]
        n = len(p) // 3
        verts = [(p[3 * k], -p[3 * k + 2], p[3 * k + 1]) for k in range(n)]   # three Y-вгору -> Blender Z-вгору
        faces = [(3 * t, 3 * t + 1, 3 * t + 2) for t in range(n // 3)]
        me = bpy.data.meshes.new(f"{ms['mat']}-{i}")
        me.from_pydata(verts, [], faces)
        if uv:
            lay = me.uv_layers.new(name="UVMap")
            for li, loop in enumerate(me.loops):
                lay.data[li].uv = (uv[2 * loop.vertex_index], uv[2 * loop.vertex_index + 1])
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(MATS.get(ms["mat"], OAK))
        ob = link_obj(me.name, me)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(35))
        bv = ob.modifiers.new("bevel", "BEVEL")         # м'яке ребро ловить світло — головна ознака «не CG»
        bv.width = 0.0012
        bv.segments = 3
        bv.limit_method = "ANGLE"
        bv.angle_limit = math.radians(40)
        bv.harden_normals = False
        obs.append(ob)
    b = d["bounds"]
    lo = Vector((b[0][0], -b[1][2], b[0][1]))
    hi = Vector((b[1][0], -b[0][2], b[1][1]))
    return obs, lo, hi, d.get("info", {})


OBS, LO, HI, INFO = product(A.geo)
SIZE = HI - LO
TOP = HI.z


# ---- кімната ---------------------------------------------------------------------------------------------
def tex_material(name, folder, scale, tint=None, sat=None, bright=0.0, contrast=0.0, rough=(0.4, 0.8), nstr=0.4,
                 disp=0.0):
    m, nt, b = pbr(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / scale, 1 / scale, 1 / scale)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    v = mp.outputs["Vector"]
    f = os.path.join(CC0, "tex", folder)
    c = node_tex(nt, os.path.join(f, "Diffuse.jpg"), vector=v).outputs["Color"]
    if sat is not None:
        hs = nt.nodes.new("ShaderNodeHueSaturation")
        hs.inputs["Saturation"].default_value = sat
        nt.links.new(c, hs.inputs["Color"])
        c = hs.outputs["Color"]
    if bright or contrast:
        bc = nt.nodes.new("ShaderNodeBrightContrast")
        bc.inputs["Bright"].default_value = bright
        bc.inputs["Contrast"].default_value = contrast
        nt.links.new(c, bc.inputs["Color"])
        c = bc.outputs["Color"]
    if tint:
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = "MULTIPLY"
        mx.inputs["Factor"].default_value = 1.0
        mx.inputs[7].default_value = (*tint, 1)
        nt.links.new(c, mx.inputs[6])
        c = mx.outputs[2]
    nt.links.new(c, b.inputs["Base Color"])
    tr = node_tex(nt, os.path.join(f, "Rough.jpg"), True, v)
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = rough
    nt.links.new(tr.outputs["Color"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    nf = os.path.join(f, "nor_gl.jpg")
    if os.path.exists(nf):
        tn = node_tex(nt, nf, True, v)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = nstr
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def plane(name, w, h, mat, loc=(0, 0, 0), rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)], [], [(0, 1, 2, 3)])
    me.materials.append(mat)
    ob = link_obj(name, me)
    ob.location = loc
    ob.rotation_euler = rot
    return ob


def cube(name, size, loc, mat, bevel=0.0, seg=3, rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = link_obj(name, me)
    ob.location = loc
    ob.rotation_euler = rot
    if bevel:
        bv = ob.modifiers.new("bevel", "BEVEL")
        bv.width = bevel
        bv.segments = seg
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(50))
    return ob


# підвісне (ofek) висить на стіні: стіна впритул до задньої стінки, як у 3D на сторінці (info.wallZ моделі)
WALL_Y = CAM.get("wall_y", -INFO["wallZ"] if INFO.get("floating") else HI.y + 1.15)
FLOOR = tex_material("microcement", "smooth_concrete_floor", 2.2, tint=(0.93, 0.9, 0.86), sat=0.12, bright=0.12,
                     contrast=-0.25, rough=(0.42, 0.7), nstr=0.25)
WALL = tex_material("plaster", "plastered_wall_04", 1.6, tint=(0.97, 0.94, 0.9), sat=0.3, bright=0.05,
                    rough=(0.75, 0.95), nstr=0.6)
plane("floor", 16, 14, FLOOR, loc=(0, WALL_Y - 7, 0))
GX = CAM.get("win_x", -3.2)                                       # ліва стіна з вікном
plane("wall", 8 - GX, 5, WALL, loc=((8 + GX) / 2, WALL_Y, 2.5), rot=(math.radians(90), 0, 0))
SKIRT = pbr("skirt", rough=0.55, color=(0.82, 0.8, 0.76))[0]
cube("skirting", (8 - GX, 0.012, 0.07), ((8 + GX) / 2, WALL_Y - 0.006, 0.035), SKIRT, bevel=0.002)


# ---- стільці: проста наша модель (дуб + лляна подушка) -------------------------------------------------
LINEN_SEAT = tex_material("linen-seat", "rough_linen", 0.18, tint=(0.74, 0.68, 0.58), sat=0.0, bright=0.0,
                          rough=(0.8, 1.0), nstr=0.8)


def chair(name, loc, yaw):
    parts = []
    h, sw, sd = 0.45, 0.46, 0.44
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(cube(f"{name}-leg", (0.034, 0.034, h - 0.03), (sx * (sw / 2 - 0.03), sy * (sd / 2 - 0.03),
                                                                           (h - 0.03) / 2), CHAIR_OAK, bevel=0.004))
    parts.append(cube(f"{name}-rail-f", (sw - 0.06, 0.02, 0.05), (0, -(sd / 2 - 0.03), h - 0.06), CHAIR_OAK, bevel=0.003))
    parts.append(cube(f"{name}-rail-b", (sw - 0.06, 0.02, 0.05), (0, (sd / 2 - 0.03), h - 0.06), CHAIR_OAK, bevel=0.003))
    parts.append(cube(f"{name}-seat", (sw, sd, 0.05), (0, 0, h), LINEN_SEAT, bevel=0.018, seg=5))
    for sx in (-1, 1):                                 # задні стійки спинки
        parts.append(cube(f"{name}-post", (0.03, 0.03, 0.36), (sx * (sw / 2 - 0.03), sd / 2 - 0.02, h + 0.18), CHAIR_OAK,
                          bevel=0.004, rot=(math.radians(-8), 0, 0)))
    parts.append(cube(f"{name}-back", (sw - 0.02, 0.022, 0.12), (0, sd / 2 + 0.01, h + 0.30), CHAIR_OAK, bevel=0.006,
                      rot=(math.radians(-8), 0, 0)))
    root = bpy.data.objects.new(name, None)
    col.objects.link(root)
    for p in parts:
        p.parent = root
    root.location = loc
    root.rotation_euler = (0, 0, yaw)
    return root


def gltf(name, loc, yaw=0.0, scale=1.0):
    path = os.path.join(CC0, "models", name, f"{name}.gltf")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(f"{name}-root", None)
    col.objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
    root.location = loc
    root.rotation_euler = (0, 0, yaw)
    root.scale = (scale, scale, scale)
    return root, new


def bounds_of(objs):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def drop_on(root, objs, z):
    lo, _ = bounds_of(objs)
    root.location.z += z - lo.z


def vase_with_branch(x, y, z, yaw=0.6):
    vroot, vobjs = gltf("ceramic_vase_01", (x, y, z), yaw=yaw)
    drop_on(vroot, vobjs, z + 0.0005)
    vlo, vhi = bounds_of(vobjs)
    broot, bobjs = gltf("dry_branches_medium_01", (0, 0, 0))
    meshes = [o for o in bobjs if o.type == "MESH"]
    if len(meshes) > 1:                             # з трьох гілок лишаємо одну найдовшу — в одну вазу
        keep = max(meshes, key=lambda o: max(o.dimensions))
        for o in meshes:
            if o is not keep:
                o.hide_render = o.hide_viewport = True
        bobjs = [keep]
    broot.rotation_euler = (math.radians(-80), math.radians(10), math.radians(25))
    bpy.context.view_layer.update()
    blo, bhi = bounds_of(bobjs)
    bc, vc = (blo + bhi) / 2, (vlo + vhi) / 2
    broot.location += Vector((vc.x - bc.x, vc.y - bc.y, (vhi.z - 0.10) - blo.z))


def centre_on(root, objs, x, y):
    lo, hi = bounds_of(objs)
    root.location += Vector((x - (lo.x + hi.x) / 2, y - (lo.y + hi.y) / 2, 0))


def pears_on(name, x, y, z, yaw=0.25):
    """Дошка або миска, на ній груші."""
    droot, dobjs = gltf(name, (x, y, z), yaw=yaw)
    drop_on(droot, dobjs, z + 0.0005)
    centre_on(droot, dobjs, x, y)
    dlo, dhi = bounds_of(dobjs)
    top = dhi.z if name == "wooden_cutting_board" else dlo.z + (dhi.z - dlo.z) * 0.35
    proot, pobjs = gltf("food_pears_asian_01", (x, y, top), yaw=1.1, scale=0.95)
    drop_on(proot, pobjs, top)
    centre_on(proot, pobjs, x, y)


def dining_decor():
    """Стільці, лляна доріжка, ваза з гілкою, дошка з грушами — для обідніх столів."""
    L, D = SIZE.x, SIZE.y
    cy = (LO.y + HI.y) / 2
    round_ = L / D < 1.2                               # SAHAR: круглий (і овальний, коли розсунутий)
    pull = D / 2 + (0.02 if round_ else 0.12)
    xs = [-0.3, 0.3] if round_ else [-L / 4, L / 4]
    # модель стільця дивиться на -Y (спинка на +Y): за столом — yaw 0, ближній — 180°, торцевий — -90°
    for i, x in enumerate(xs):
        yy = cy + (math.sqrt(max((D / 2) ** 2 - x * x, 0)) + 0.14 if round_ else pull + 0.06)
        chair(f"chair-b{i}", (x + (0.03 if i else -0.02), yy, 0), math.radians((4 if i else -3) + (-x * 30 if round_ else 0)))
    if CAM.get("end_chair", True):
        chair("chair-e", (HI.x + (0.16 if round_ else 0.24), cy + 0.03, 0), math.radians(-90 + 4))
    if not round_:                                     # доріжка з льону вздовж стільниці
        run_m = tex_material("linen-run", "rough_linen", 0.22, tint=(0.86, 0.8, 0.7), sat=0.0, rough=(0.85, 1.0),
                             nstr=0.9)
        r = cube("runner", (min(1.3, L * 0.62), 0.38, 0.003), (-0.05, cy, TOP + 0.0016), run_m)
        r.modifiers.new("sub", "SUBSURF").render_levels = 1
    vase_with_branch(-min(L * 0.18, 0.3) - (0.04 if round_ else 0), cy + 0.06, TOP + 0.003)
    pears_on("wooden_cutting_board", min(L * 0.16, 0.22), cy - 0.04, TOP + 0.003)


def top_decor():
    """Тумба, консоль, журнальний: ваза з гілкою з одного краю, миска з грушами — з другого."""
    L, cy = SIZE.x, (LO.y + HI.y) / 2
    vase_with_branch(LO.x + min(0.26, L * 0.22), cy + 0.02, TOP + 0.0005)
    pears_on("wooden_bowl_02", HI.x - min(0.3, L * 0.26), cy - 0.01, TOP + 0.0005, yaw=0.4)


if A.decor == "dining":
    dining_decor()
elif A.decor == "top":
    top_decor()


# ---- світло: денне з вікна ліворуч + HDRI інтер'єру --------------------------------------------------------
world = bpy.data.worlds.new("world")
scene.world = world
world.use_nodes = True
wn = world.node_tree
env = wn.nodes.new("ShaderNodeTexEnvironment")
env.image = img(os.path.join(CC0, "hdri", A.hdri))
mp = wn.nodes.new("ShaderNodeMapping")
mp.inputs["Rotation"].default_value = (0, 0, math.radians(CAM.get("hdri_rot", 110)))
wn.links.new(wn.nodes.new("ShaderNodeTexCoord").outputs["Generated"], mp.inputs["Vector"])
wn.links.new(mp.outputs["Vector"], env.inputs["Vector"])
bg = wn.nodes["Background"]
bg.inputs["Strength"].default_value = CAM.get("hdri_strength", 0.2)
wn.links.new(env.outputs["Color"], bg.inputs["Color"])

# вікно — велике м'яке джерело ліворуч, поза кадром
win = bpy.data.lights.new("window", "AREA")
win.shape = "RECTANGLE"
win.size, win.size_y = 2.4, 1.9
win.energy = CAM.get("window", 200)
win.color = tuple(CAM.get("window_color", (1.0, 0.97, 0.93)))
wo = bpy.data.objects.new("window", win)
col.objects.link(wo)

# ліва стіна з вікном (поза кадром): сонце заходить лише крізь проріз і кладе плями на стіну й підлогу
sun = bpy.data.lights.new("sun", "SUN")
sun.energy = CAM.get("sun", 5.0)
sun.angle = math.radians(1.5)
sun.color = tuple(CAM.get("sun_color", (1.0, 0.9, 0.78)))
so = bpy.data.objects.new("sun", sun)
col.objects.link(so)
sun_dir = Vector(CAM.get("sun_dir", (0.85, 0.3, -0.42))).normalized()   # куди світить
so.rotation_euler = sun_dir.to_track_quat("-Z", "Y").to_euler()
hide_m = WALL
gx = GX - 0.1
y0, y1, z0, z1 = WALL_Y - 3.6, WALL_Y - 0.6, 0.45, 2.45           # проріз вікна
side = [cube("sw-low", (0.2, 14, z0), (gx, WALL_Y - 7, z0 / 2), hide_m),
        cube("sw-high", (0.2, 14, 2.8 - z1), (gx, WALL_Y - 7, (2.8 + z1) / 2), hide_m),
        cube("sw-a", (0.2, WALL_Y - y1, z1 - z0), (gx, (y1 + WALL_Y) / 2, (z0 + z1) / 2), hide_m),
        cube("sw-b", (0.2, y0 - (WALL_Y - 14), z1 - z0), (gx, (y0 + WALL_Y - 14) / 2, (z0 + z1) / 2), hide_m)]
for k in range(1, 3):                                              # рама: дві вертикальні стійки й імпост
    side.append(cube("mullion", (0.08, 0.06, z1 - z0), (gx, y0 + (y1 - y0) * k / 3, (z0 + z1) / 2), hide_m))
side.append(cube("transom", (0.08, y1 - y0, 0.06), (gx, (y0 + y1) / 2, z0 + (z1 - z0) * 0.72), hide_m))
ceil = plane("ceiling", 8 - gx, 16, WALL, loc=((8 + gx) / 2, WALL_Y - 7, 2.75), rot=(math.radians(180), 0, 0))
ceil.visible_camera = False                                        # стеля: світло лише з вікна, як у кімнаті
wo.visible_camera = False
wo.location = (gx - 0.15, (y0 + y1) / 2, (z0 + z1) / 2)
win.size, win.size_y = (y1 - y0), (z1 - z0)
wo.rotation_euler = (0, math.radians(-90), 0)


# ---- підвісна лампа над столом (пара кадрів «ранок / вечір»): у кадрі однакова, світить лише ввечері -----------
def pendant(lit, energy, color):
    cx, cy, z = (LO.x + HI.x) / 2 + CAM.get("pendant_dx", 0.0), (LO.y + HI.y) / 2, TOP + CAM.get("pendant_h", 0.78)
    shade_m = pbr("shade", rough=0.7, color=(0.86, 0.83, 0.78))[0]
    bpy.ops.mesh.primitive_cone_add(vertices=64, radius1=0.2, radius2=0.06, depth=0.2, end_fill_type="NOTHING",
                                    location=(cx, cy, z + 0.1))
    sh = bpy.context.object
    sh.name = "pendant"
    sh.data.materials.append(shade_m)
    sh.modifiers.new("solid", "SOLIDIFY").thickness = 0.004
    sh.data.shade_smooth()
    cord_m = pbr("cord", rough=0.5, color=(0.05, 0.05, 0.05))[0]
    cube("cord", (0.006, 0.006, 2.75 - z - 0.2), (cx, cy, (2.75 + z + 0.2) / 2), cord_m)
    if not lit:
        return
    bulb_m = bpy.data.materials.new("bulb")
    bulb_m.use_nodes = True
    em = bulb_m.node_tree.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = 30.0
    bulb_m.node_tree.links.new(em.outputs["Emission"], bulb_m.node_tree.nodes["Material Output"].inputs["Surface"])
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.035, location=(cx, cy, z + 0.05))
    bpy.context.object.data.materials.append(bulb_m)
    la = bpy.data.lights.new("lamp", "AREA")
    la.shape, la.size = "DISK", 0.34
    la.energy, la.color = energy, color
    lo = bpy.data.objects.new("lamp", la)
    col.objects.link(lo)
    lo.location = (cx, cy, z + 0.02)                               # світить униз, у стільницю
    glow = bpy.data.lights.new("glow", "POINT")                    # слабке світло вгору й у кімнату крізь абажур
    glow.energy, glow.color, glow.shadow_soft_size = energy * CAM.get("glow", 0.12), color, 0.1
    go = bpy.data.objects.new("glow", glow)
    col.objects.link(go)
    go.location = (cx, cy, z + 0.14)


if CAM.get("pendant"):
    pendant(CAM["pendant"] == "on", CAM.get("lamp", 90.0), tuple(CAM.get("lamp_color", (1.0, 0.66, 0.36))))


# ---- камера: 50 мм на рівні очей, вписати виріб -----------------------------------------------------------
def look_rot(eye, target):
    return (target - eye).to_track_quat("-Z", "Y").to_euler()


def fit_camera():
    lens = CAM.get("lens", 50)
    az = math.radians(CAM.get("az", 32))
    eye_h = CAM.get("eye", 1.42)
    margin = CAM.get("margin", 0.12)

    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = lens
    cam_d.sensor_width = 36
    cam_d.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("cam", cam_d)
    col.objects.link(cam)
    scene.camera = cam
    aspect = A.w / A.h
    half_w = math.atan(18 / lens)
    half_h = math.atan(18 / lens / aspect)
    lo, hi = LO.copy(), HI.copy()
    if CAM.get("fit"):                           # частка габариту [[x0,y0,z0],[x1,y1,z1]] (0..1): кадр на частину виробу
        f0, f1 = CAM["fit"]
        lo = Vector([LO[i] + SIZE[i] * f0[i] for i in range(3)])
        hi = Vector([LO[i] + SIZE[i] * f1[i] for i in range(3)])
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    tgt = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, CAM.get("target_z", lo.z + (hi.z - lo.z) * 0.62)))
    dist = 3.0
    for _ in range(40):                          # дистанція, за якої виріб займає кадр з полем margin
        horiz = math.sqrt(max(dist * dist - (eye_h - tgt.z) ** 2, 0.5))
        eye = tgt + Vector((math.sin(az) * horiz, -math.cos(az) * horiz, eye_h - tgt.z))
        rot = look_rot(eye, tgt)
        inv = (Matrix.Translation(eye) @ rot.to_matrix().to_4x4()).inverted()
        sx = sy = 0
        for c in corners:
            p = inv @ c
            sx = max(sx, abs(p.x / -p.z) / math.tan(half_w))
            sy = max(sy, abs(p.y / -p.z) / math.tan(half_h))
        k = max(sx, sy) / (1 - margin)
        dist *= k ** 0.7
    cam.location = eye
    cam.rotation_euler = rot
    cam_d.shift_y = CAM.get("shift_y", 0.0)
    cam_d.dof.use_dof = True
    cam_d.dof.focus_distance = (tgt - eye).length
    cam_d.dof.aperture_fstop = CAM.get("fstop", 4.0)
    return cam


fit_camera()

# ---- рендер ----------------------------------------------------------------------------------------------
scene.render.engine = "CYCLES"
cy = scene.cycles
cy.device = "CPU"
cy.samples = A.samples
cy.use_adaptive_sampling = True
cy.adaptive_threshold = 0.02
cy.use_denoising = True
cy.denoiser = "OPENIMAGEDENOISE"
cy.max_bounces = 8
cy.diffuse_bounces = 4
cy.glossy_bounces = 3
cy.transparent_max_bounces = 8
cy.caustics_reflective = cy.caustics_refractive = False
cy.blur_glossy = 1.0
scene.render.threads_mode = "FIXED"
scene.render.threads = A.threads
scene.render.resolution_x, scene.render.resolution_y = A.w, A.h
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = CAM.get("look", "AgX - Medium High Contrast")
scene.view_settings.exposure = CAM.get("exposure", 0.95)
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_depth = "8"
scene.render.filepath = A.out
if A.blend:
    bpy.ops.wm.save_as_mainfile(filepath=A.blend, compress=True)
bpy.ops.render.render(write_still=True)
print("ALUMA_RENDER_OK", A.out)
