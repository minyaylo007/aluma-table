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
    "natural": ("tone-natural-albedo", "oak", 1.0),
    "light": ("tone-light-albedo", "washed-oak", 1.83),
    "honey": ("tone-honey-albedo", "oak", 1.0),
    "smoked": ("tone-smoked-albedo", "black-oak", 1.83),
    "black": ("tone-black-albedo", "black-oak", 1.83),
}


def noise(nt, scale, detail=3.0, coords="Object"):
    """Велика м'яка пляма (0..1) — нерівність, якої немає в тайлі скану: вапно на стіні, сліди на стільниці."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail
    nz.inputs["Roughness"].default_value = 0.55
    nt.links.new(tc.outputs[coords], nz.inputs["Vector"])
    return nz.outputs["Fac"]


def vary(nt, sock, fac, lo, hi, kind="RGBA"):
    """sock × (lo..hi за плямою fac): середнє не зсувається, якщо lo і hi симетричні навколо 1."""
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.3, 0.7
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = lo, hi
    nt.links.new(fac, mr.inputs["Value"])
    if kind == "VALUE":
        mm = nt.nodes.new("ShaderNodeMath")
        mm.operation = "MULTIPLY"
        nt.links.new(sock, mm.inputs[0])
        nt.links.new(mr.outputs["Result"], mm.inputs[1])
        return mm.outputs["Value"]
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.blend_type = "MULTIPLY"
    mx.inputs["Factor"].default_value = 1.0
    nt.links.new(sock, mx.inputs[6])
    nt.links.new(mr.outputs["Result"], mx.inputs[7])
    return mx.outputs[2]


def oak_material(finish, albedo="", box=False):
    """Дуб під олією: альбедо тону, нормалі й шорсткість його справжнього скану шпону.

    Фотореальний прохід (22.10): шорсткість 0.35–0.47 з картою скану і ледь помітними «слідами» поверх, легка
    анізотропія вздовж волокна, пори — рельєф з темних волокон альбедо, плівка олії тонша (не «пластик»).
    Колір тону не міняється: варіація симетрична навколо 1 (±3 %), середнє лишається середнім тону з oak_tones.py.
    box — проєкція з координат об'єкта (стільці: в їхніх кубів і циліндрів немає розгортки).
    """
    stem, maps, scale = TONE_TEX.get(finish, TONE_TEX["natural"])
    alb = albedo or os.path.join(TEX, f"{stem}-2048.jpg")
    if not os.path.exists(alb):
        raise SystemExit(f"немає {alb} — python3 tools/oak_tones.py")
    m, nt, b = pbr(f"oak-{finish}{'-box' if box else ''}", coat=0.1, coat_rough=0.32)
    mp = nt.nodes.new("ShaderNodeMapping")           # скани 1 м повторюються щільніше за 1,83-метровий oak_veneer_01
    if box:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        k = scale / 1.83                             # 1 м сцени = 1 / 1,83 скану oak_veneer_01
        mp.inputs["Scale"].default_value = (k, k, k)
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    else:
        uv = nt.nodes.new("ShaderNodeUVMap")
        mp.inputs["Scale"].default_value = (scale, scale, 1)
        nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
    vec = mp.outputs["Vector"]
    proj = "BOX" if box else "FLAT"
    ta = node_tex(nt, alb, vector=vec, proj=proj)
    smudge = noise(nt, 2.2, 4.0)
    nt.links.new(vary(nt, ta.outputs["Color"], noise(nt, 0.9, 2.0), 0.97, 1.03), b.inputs["Base Color"])
    tr = node_tex(nt, os.path.join(TEX, f"{maps}-rough-2048.jpg"), True, vec, proj)
    mr = nt.nodes.new("ShaderNodeMapRange")          # олія: 0.35..0.47 — живий сатиновий відблиск, без дзеркала
    mr.inputs["To Min"].default_value = 0.35 if finish != "black" else 0.42
    mr.inputs["To Max"].default_value = 0.47 if finish != "black" else 0.55
    nt.links.new(tr.outputs["Color"], mr.inputs["Value"])
    nt.links.new(vary(nt, mr.outputs["Result"], smudge, 0.9, 1.12, "VALUE"), b.inputs["Roughness"])
    tn = node_tex(nt, os.path.join(TEX, f"{maps}-normal-2048.jpg"), True, vec, proj)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.45
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    bump = nt.nodes.new("ShaderNodeBump")            # пори: темні волокна альбедо трохи «нижче» за поверхню
    bump.invert = True
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.0004
    nt.links.new(ta.outputs["Color"], bump.inputs["Height"])
    nt.links.new(nm.outputs["Normal"], bump.inputs["Normal"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    if not box:                                      # анізотропія вздовж волокна (V розгортки)
        tg = nt.nodes.new("ShaderNodeTangent")
        tg.direction_type = "UV_MAP"
        tg.uv_map = "UVMap"
        b.inputs["Anisotropic"].default_value = 0.3
        b.inputs["Anisotropic Rotation"].default_value = 0.25
        nt.links.new(tg.outputs["Tangent"], b.inputs["Tangent"])
    b.inputs["Specular IOR Level"].default_value = 0.45
    return m


OAK = oak_material(A.finish, A.albedo)
# стільці — декор, не товар: тонування міняє лише стіл, стільці завжди натуральний дуб (проєкція з об'єкта:
# без неї куби стільців брали один тексель скану й виходили рівно-рудими — головна «комп'ютерна» прикмета 22.10)
CHAIR_OAK = oak_material("natural", box=True)
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
        bv.width = 0.0018
        bv.segments = 4
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
                 disp=0.0, mottle=None):
    """CC0-матеріал з теки. mottle=(сила, масштаб): велика пляма тону й шорсткості поверх тайла — вапно, сліди,
    нерівно витерта підлога; без неї тайл повторюється рівно, і стіна читається як шпалери."""
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
    r_out = None
    if mottle:
        amt, sc = mottle
        fac = noise(nt, sc, 4.0)
        c = vary(nt, c, fac, 1 - amt, 1 + amt)
    nt.links.new(c, b.inputs["Base Color"])
    tr = node_tex(nt, os.path.join(f, "Rough.jpg"), True, v)
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = rough
    nt.links.new(tr.outputs["Color"], mr.inputs["Value"])
    r_out = mr.outputs["Result"]
    if mottle:
        r_out = vary(nt, r_out, noise(nt, mottle[1] * 1.7, 3.0), 0.85, 1.15, "VALUE")
    nt.links.new(r_out, b.inputs["Roughness"])
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
# room: studio — мікроцемент і гладка стіна (кадри галереї); home — жилий кадр (21.10): ізраїльська квартира з
# плиткою-терацо «балата», вікном у кадрі (розсувна алюмінієва рама, мармурове підвіконня, жалюзі-«тріс»), фіранкою,
# рослинами й килимом. Виріб і його матеріал ті самі — міняється лише кімната.
ROOM = CAM.get("room", "studio")
if ROOM == "home":
    # плитка 31 см (ambientCG Tiles110: 6 плиток на 1,85 м), полірована — м'який відблиск вікна, темні шви
    FLOOR = tex_material("balata", "Tiles110", 1.85, sat=0.85, bright=0.03, rough=(0.2, 0.45), nstr=0.6)
else:
    # 22.10: замість рівного мікроцементу — великі світлі кам'яні плити 75 см (Poly Haven large_floor_tiles_02,
    # перефарбовані в теплий вапняк), матова полировка з м'яким відблиском вікна, шви й нерівність каменю видно
    FLOOR = tex_material("limestone", "large_floor_tiles_02", 2.25, tint=(1.0, 0.92, 0.8), sat=0.1, bright=0.26,
                         contrast=0.05, rough=(0.2, 0.48), nstr=0.7, mottle=(0.05, 0.6))
# стіна: вапняна штукатурка — та сама plastered_wall_04, але з великою плямою тону (вапно лягає нерівно)
WALL = tex_material("plaster", "plastered_wall_04", 1.6, tint=(0.98, 0.94, 0.88), sat=0.3, bright=0.06,
                    rough=(0.78, 0.97), nstr=0.9, mottle=(0.06, 0.45))
plane("floor", 16, 14, FLOOR, loc=(0, WALL_Y - 7, 0))
GX = CAM.get("win_x", -3.2)                                       # ліва стіна з вікном


def wall_with_hole(name, xa, xb, height, x0, x1, z0, z1, y, mat):
    """Стіна-площина з прорізом: один меш, одні координати текстури — без швів штукатурки навколо вікна."""
    vs, fs = [], []
    for a, b, za, zb in ((xa, x0, 0, height), (x1, xb, 0, height), (x0, x1, 0, z0), (x0, x1, z1, height)):
        k = len(vs)
        vs += [(a, za, 0), (b, za, 0), (b, zb, 0), (a, zb, 0)]
        fs.append((k, k + 1, k + 2, k + 3))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.materials.append(mat)
    ob = link_obj(name, me)
    ob.location = (0, y, 0)
    ob.rotation_euler = (math.radians(90), 0, 0)
    return ob


def home_back_wall():
    """Вікно в задній стіні, у кадрі: проріз у товщі стіни 20 см, рама, підвіконня, жалюзі трохи опущені."""
    w = CAM.get("win_w", 1.3)
    x1 = CAM.get("win_x1", LO.x - 0.15)
    x0, z0, z1, T = x1 - w, CAM.get("win_z0", 0.85), CAM.get("win_z1", 2.3), 0.2
    wall_with_hole("wall", GX, 8.0, 5.0, x0, x1, z0, z1, WALL_Y, WALL)
    reveal = pbr("reveal", rough=0.9, color=(0.86, 0.84, 0.8))[0]
    yc = WALL_Y + T / 2
    cube("jamb-l", (0.01, T, z1 - z0), (x0 - 0.005, yc, (z0 + z1) / 2), reveal)
    cube("jamb-r", (0.01, T, z1 - z0), (x1 + 0.005, yc, (z0 + z1) / 2), reveal)
    cube("head", (w + 0.02, T, 0.01), ((x0 + x1) / 2, yc, z1 + 0.005), reveal)
    marble = pbr("marble", rough=0.18, coat=0.2, color=(0.86, 0.84, 0.8))[0]
    cube("sill", (w + 0.1, T + 0.05, 0.025), ((x0 + x1) / 2, yc - 0.025, z0 - 0.0125), marble, bevel=0.003)
    alu = pbr("alu", rough=0.35, metal=0.7, color=(0.8, 0.8, 0.78))[0]
    yf, p = WALL_Y + T * 0.6, 0.045                                 # рама посередині товщі стіни
    for nm, size, loc in (("fr-b", (w, 0.06, p), ((x0 + x1) / 2, yf, z0 + p / 2)),
                          ("fr-t", (w, 0.06, p), ((x0 + x1) / 2, yf, z1 - p / 2)),
                          ("fr-l", (p, 0.06, z1 - z0), (x0 + p / 2, yf, (z0 + z1) / 2)),
                          ("fr-r", (p, 0.06, z1 - z0), (x1 - p / 2, yf, (z0 + z1) / 2)),
                          ("fr-m", (0.07, 0.08, z1 - z0), ((x0 + x1) / 2 + 0.03, yf, (z0 + z1) / 2))):   # стулки внахлест
        cube(nm, size, loc, alu, bevel=0.002)
    drop = CAM.get("shutter", 0.3)                                  # тріс: ламелі 4 см ззовні, опущені на 30 см
    shut = pbr("shutter", rough=0.5, color=(0.82, 0.81, 0.78))[0]
    for k in range(int(drop / 0.04)):
        cube(f"slat{k}", (w, 0.012, 0.036), ((x0 + x1) / 2, WALL_Y + T - 0.02, z1 - 0.02 - k * 0.04), shut, bevel=0.003)
    return {"x0": x0, "x1": x1, "z0": z0, "z1": z1, "T": T, "w": w}


WIN_BACK = home_back_wall() if ROOM == "home" else None
if not WIN_BACK:
    plane("wall", 8 - GX, 5, WALL, loc=((8 + GX) / 2, WALL_Y, 2.5), rot=(math.radians(90), 0, 0))
SKIRT = pbr("skirt", rough=0.55, color=(0.82, 0.8, 0.76))[0]
cube("skirting", (8 - GX, 0.012, 0.07), ((8 + GX) / 2, WALL_Y - 0.006, 0.035), SKIRT, bevel=0.002)


# ---- стільці: наша модель (22.10) — круглі ніжки, що звужуються, вигнута спинка, плетене сидіння ------------
def wicker_material():
    """Плетіння сидіння — текстура з CC0-кошика wicker_basket_02 (Poly Haven), проєкція з координат об'єкта."""
    m, nt, b = pbr("wicker", rough=0.75)
    f = os.path.join(CC0, "models", "wicker_basket_02", "textures")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (5.0, 5.0, 5.0)           # плетіння ~1 см, як паперовий шнур
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    v = mp.outputs["Vector"]
    c = node_tex(nt, os.path.join(f, "wicker_basket_02_diff_2k.jpg"), vector=v, proj="BOX").outputs["Color"]
    bw = nt.nodes.new("ShaderNodeRGBToBW")                         # світлий пісочний шнур, не темна лоза кошика:
    nt.links.new(c, bw.inputs["Color"])                            # малюнок плетіння з яскравості, колір — свій
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.0, 0.45
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 0.3, 1.0
    nt.links.new(bw.outputs["Val"], mr.inputs["Value"])
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type, mx.blend_type = "RGBA", "MULTIPLY"
    mx.inputs["Factor"].default_value = 1.0
    nt.links.new(mr.outputs["Result"], mx.inputs[6])
    mx.inputs[7].default_value = (0.72, 0.56, 0.36, 1)
    nt.links.new(mx.outputs[2], b.inputs["Base Color"])
    tn = node_tex(nt, os.path.join(f, "wicker_basket_02_nor_gl_2k.jpg"), True, v, "BOX")
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 1.0
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Sheen Weight"].default_value = 0.3
    return m


WICKER = wicker_material()


def rod(name, p0, p1, r0, r1, mat):
    """Кругла деталь від p0 до p1, радіус r0 -> r1 (ніжка, що звужується, царга-перекладина)."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    bpy.ops.mesh.primitive_cone_add(vertices=28, radius1=r0, radius2=r1, depth=d.length, location=(p0 + p1) / 2)
    ob = bpy.context.object
    ob.name = name
    ob.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    ob.data.materials.append(mat)
    ob.data.shade_smooth()
    ob.data.set_sharp_from_angle(angle=math.radians(50))
    bv = ob.modifiers.new("bevel", "BEVEL")
    bv.width, bv.segments, bv.limit_method = 0.003, 3, "ANGLE"
    return ob


def back_rest(name, sw, y, z, h, mat, bend=0.035, tilt=-10):
    """Вигнута спинка: дошка 18 мм по дузі (центр відступає назад на bend), край скруглений."""
    n = 24
    vs, fs = [], []
    for i in range(n + 1):
        x = -sw / 2 + sw * i / n
        dy = bend * (1 - (2 * x / sw) ** 2)
        vs += [(x, dy, -h / 2), (x, dy, h / 2)]
    for i in range(n):
        fs.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.materials.append(mat)
    ob = link_obj(name, me)
    so = ob.modifiers.new("solid", "SOLIDIFY")
    so.thickness, so.offset = 0.018, 0
    bv = ob.modifiers.new("bevel", "BEVEL")
    bv.width, bv.segments = 0.006, 4
    me.shade_smooth()
    ob.location = (0, y, z)
    ob.rotation_euler = (math.radians(tilt), 0, 0)
    return ob


def chair(name, loc, yaw):
    """Обідній стілець у дусі скандинавської класики: дуб, сидіння з паперового шнура. Модель дивиться на -Y."""
    parts = []
    h, sw, sd, top = 0.45, 0.45, 0.42, 0.82
    fx, fy, ry = sw / 2 - 0.025, -(sd / 2 - 0.025), sd / 2 - 0.025
    rake = 0.05                                                    # задні ніжки відхилені назад угорі
    for sx in (-1, 1):
        parts.append(rod(f"{name}-leg-f", (sx * fx, fy, 0), (sx * fx, fy, h - 0.02), 0.0135, 0.0175, CHAIR_OAK))
        parts.append(rod(f"{name}-leg-b", (sx * fx, ry - 0.01, 0), (sx * fx, ry + rake, top), 0.0135, 0.0155, CHAIR_OAK))
        parts.append(rod(f"{name}-str-s", (sx * fx, fy, 0.19), (sx * fx, ry, 0.19), 0.009, 0.009, CHAIR_OAK))
    parts.append(rod(f"{name}-str-f", (-fx, fy, 0.24), (fx, fy, 0.24), 0.009, 0.009, CHAIR_OAK))
    parts.append(rod(f"{name}-str-b", (-fx, ry, 0.15), (fx, ry, 0.15), 0.009, 0.009, CHAIR_OAK))
    for nm, size, loc_ in ((f"{name}-rail-f", (sw - 0.03, 0.026, 0.03), (0, fy, h - 0.02)),
                           (f"{name}-rail-b", (sw - 0.03, 0.026, 0.03), (0, ry + 0.003, h - 0.02)),
                           (f"{name}-rail-l", (0.026, sd - 0.03, 0.03), (-fx, 0, h - 0.02)),
                           (f"{name}-rail-r", (0.026, sd - 0.03, 0.03), (fx, 0, h - 0.02))):
        parts.append(cube(nm, size, loc_, CHAIR_OAK, bevel=0.008, seg=4))
    seat = cube(f"{name}-seat", (sw - 0.02, sd - 0.02, 0.026), (0, -0.002, h - 0.002), WICKER, bevel=0.011, seg=4)
    seat.modifiers.new("sub", "SUBSURF").render_levels = 1         # шнур трохи провисає й скруглює край
    parts.append(seat)
    parts.append(back_rest(f"{name}-back", sw - 0.01, ry + rake * 0.9 + 0.006, top - 0.07, 0.085, CHAIR_OAK))
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


def centre_on(root, objs, x, y):
    lo, hi = bounds_of(objs)
    root.location += Vector((x - (lo.x + hi.x) / 2, y - (lo.y + hi.y) / 2, 0))


def boost(objs, sat=1.0, val=1.0):
    """Насиченість і яскравість імпортованого CC0-предмета: під AgX і теплим світлом лимон виходив оливковим."""
    for o in objs:
        for slot in getattr(o, "material_slots", []):
            m = slot.material
            if not m or not m.use_nodes:
                continue
            nt = m.node_tree
            b = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if not b or not b.inputs["Base Color"].links:
                continue
            src = b.inputs["Base Color"].links[0].from_socket
            hs = nt.nodes.new("ShaderNodeHueSaturation")
            hs.inputs["Saturation"].default_value, hs.inputs["Value"].default_value = sat, val
            nt.links.new(src, hs.inputs["Color"])
            nt.links.new(hs.outputs["Color"], b.inputs["Base Color"])


def lemons_in_bowl(x, y, z, yaw=0.4, n=5):
    """Дерев'яна миска 22 см (CC0 wooden_bowl_02 ×1,7) з лимонами (CC0 lemon) — гіркою, кожен трохи повернутий."""
    droot, dobjs = gltf("wooden_bowl_02", (x, y, z), yaw=yaw, scale=1.7)
    drop_on(droot, dobjs, z + 0.0005)
    centre_on(droot, dobjs, x, y)
    dlo, dhi = bounds_of(dobjs)
    base = dlo.z + (dhi.z - dlo.z) * 0.5
    spots = [(0, 0, 0), (0.05, 0.02, 0), (-0.045, 0.025, 0), (0.01, -0.05, 0), (0.015, 0.01, 0.045)][:n]
    for i, (dx, dy, dz) in enumerate(spots):
        lroot, lobjs = gltf("lemon", (0, 0, 0), yaw=1.3 * i + 0.4)
        boost(lobjs, 1.35, 1.12)
        lroot.rotation_euler = (math.radians(90 + 25 * (i % 3 - 1)), math.radians(17 * i), 1.3 * i)
        drop_on(lroot, lobjs, base + dz)
        centre_on(lroot, lobjs, x + dx, y + dy)


def jug_on(x, y, z, yaw=2.2):
    """Ваза з сирої глини (CC0 ceramic_vase_02, 25 см) — матова кераміка замість білої вази з сухою гілкою."""
    root, objs = gltf("ceramic_vase_02", (x, y, z), yaw=yaw, scale=0.8)
    drop_on(root, objs, z + 0.0005)
    centre_on(root, objs, x, y)


def book_on(x, y, z, yaw=0.3, size=(0.155, 0.235, 0.024), cover=(0.36, 0.17, 0.1)):
    """Книжка, покладена на стіл (24.10, «як живе фото»): наша модель — палітурка і блок сторінок, чужих видань нема."""
    w, h, t = size
    cov = pbr("book-cover", color=cover, rough=0.78)[0]
    pages = pbr("book-pages", color=(0.86, 0.83, 0.76), rough=0.9)[0]
    c, s = math.cos(yaw), math.sin(yaw)

    def at(dx, dz):                                   # зсув від центру книжки вздовж її ширини, повернутий на yaw
        return (x + dx * c, y + dx * s, z + dz)
    rot = (0, 0, yaw)
    cube("book-pages", (w - 0.006, h - 0.008, t - 0.004), at(0.002, t / 2), pages, bevel=0.0015, rot=rot)
    cube("book-cover-top", (w, h, 0.0022), at(0, t - 0.0011), cov, bevel=0.0008, rot=rot)
    cube("book-cover-bot", (w, h, 0.0022), at(0, 0.0011), cov, bevel=0.0008, rot=rot)
    cube("book-spine", (0.0026, h, t), at(-w / 2 + 0.0013, t / 2), cov, bevel=0.001, rot=rot)


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
    # 22.10: глечик і миска з лимонами (як живе фото), замість вази з сухою гілкою й дошки з грушами
    jug_on(-min(L * 0.18, 0.3) - (0.04 if round_ else 0), cy + 0.07, TOP + 0.003)
    lemons_in_bowl(min(L * 0.14, 0.2), cy - 0.03, TOP + 0.003)
    if CAM.get("book"):                                # кадр life: розгорнута на столі книжка ближче до камери
        book_on(min(L * 0.3, 0.5), cy - D * 0.22, TOP + 0.003, yaw=0.35)


def top_decor():
    """Тумба, консоль, журнальний: ваза з гілкою з одного краю, миска з грушами — з другого."""
    L, cy = SIZE.x, (LO.y + HI.y) / 2
    jug_on(LO.x + min(0.26, L * 0.22), cy + 0.02, TOP + 0.0005)
    lemons_in_bowl(HI.x - min(0.3, L * 0.26), cy - 0.01, TOP + 0.0005, n=4)
    if CAM.get("book"):
        book_on((LO.x + HI.x) / 2 + L * 0.06, cy + 0.005, TOP + 0.0005, yaw=-0.18)


if A.decor == "dining":
    dining_decor()
elif A.decor == "top":
    top_decor()


# ---- жилий кадр: фіранка, рослини, килим, кошик -------------------------------------------------------------
def curtain(xa, xb, y, top, along="x", name="curtain", amp=None):
    """Легка лляна фіранка: нерівні складки (дві синусоїди), частково просвічує (транслюцентність + прозорість).
    along="y" — фіранка вздовж бічної стіни (x = y-аргумент), перед вікном поза кадром: м'якшить сонце."""
    n, period = 160, 0.12
    amp = CAM.get("curtain_amp", 0.03) if amp is None else amp
    vs, fs = [], []
    for i in range(n + 1):
        x = xa + (xb - xa) * i / n
        t = 2 * math.pi * (x - xa) / period
        dy = amp * (math.sin(t) + 0.35 * math.sin(2.3 * t + 1.1))
        if along == "y":
            vs += [(y + dy, x, 0.015), (y + dy, x, top)]
        else:
            vs += [(x, y + dy, 0.015), (x, y + dy, top)]
    for i in range(n):
        fs.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    m, nt, b = pbr("sheer", rough=0.95, color=CAM.get("curtain_color", (0.94, 0.92, 0.87)))
    out = nt.nodes["Material Output"]
    tl = nt.nodes.new("ShaderNodeBsdfTranslucent")
    tl.inputs["Color"].default_value = (0.95, 0.92, 0.86, 1)
    tp = nt.nodes.new("ShaderNodeBsdfTransparent")
    m1, m2 = nt.nodes.new("ShaderNodeMixShader"), nt.nodes.new("ShaderNodeMixShader")
    m1.inputs["Fac"].default_value = 0.45
    m2.inputs["Fac"].default_value = CAM.get("curtain_sheer", 0.3)
    nt.links.new(b.outputs["BSDF"], m1.inputs[1])
    nt.links.new(tl.outputs["BSDF"], m1.inputs[2])
    nt.links.new(m1.outputs["Shader"], m2.inputs[1])
    nt.links.new(tp.outputs["BSDF"], m2.inputs[2])
    nt.links.new(m2.outputs["Shader"], out.inputs["Surface"])
    me.materials.append(m)
    me.shade_smooth()
    link_obj(name, me)
    rod_m = pbr("rod", rough=0.4, metal=0.8, color=(0.12, 0.1, 0.08))[0]
    mid = (xa + xb) / 2
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.011, depth=xb - xa + 0.12,
                                        location=(mid, y, top + 0.03) if along == "x" else (y, mid, top + 0.03),
                                        rotation=(0, math.radians(90), 0) if along == "x" else (math.radians(90), 0, 0))
    bpy.context.object.data.materials.append(rod_m)


def floor_obj(name, x, y, yaw=0.0, scale=1.0):
    root, objs = gltf(name, (x, y, 0), yaw=yaw, scale=scale)
    drop_on(root, objs, 0.0005)
    centre_on(root, objs, x, y)
    return root, objs


def home_decor(wb):
    x0, x1, z0, z1 = wb["x0"], wb["x1"], wb["z0"], wb["z1"]
    ca = CAM.get("curtain", [-0.5, 0.28])                           # від лівого краю прорізу: де висить фіранка
    curtain(x0 + ca[0], x0 + ca[1], WALL_Y - 0.09, z1 + 0.16)
    if CAM.get("sill_plant", True):                                 # сукулент на підвіконні
        root, objs = gltf("potted_plant_04", (x1 - 0.32, WALL_Y + 0.07, z0), yaw=0.7)
        drop_on(root, objs, z0 + 0.0005)
        centre_on(root, objs, x1 - 0.32, WALL_Y + 0.07)
    # велика рослина в горщику: біля вікна, або "right" — праворуч від виробу, щоб не закривала вікно
    px, py = {"right": [HI.x + 0.4, WALL_Y - 0.3]}.get(CAM.get("plant"), CAM.get("plant", [x0 + ca[0] - 0.32, WALL_Y - 0.36]))
    floor_obj("potted_plant_02", px, py, yaw=CAM.get("plant_yaw", 0.4), scale=CAM.get("plant_scale", 1.25 if CAM.get("plant") != "right" else 0.9))
    if CAM.get("basket"):
        bx, by = CAM["basket"]
        floor_obj("wicker_basket_02", bx, by, yaw=0.3)
    if CAM.get("rug"):                                              # джутовий килим: [ширина, глибина, зсув y від центру виробу]
        rw, rd, dy = CAM["rug"]
        rug_m = tex_material("rug", "hessian_380", 2.0, tint=tuple(CAM.get("rug_color", (0.95, 0.92, 0.86))), sat=0.7,
                             rough=(0.85, 1.0), nstr=1.0)
        cube("rug", (rw, rd, 0.01), ((LO.x + HI.x) / 2, (LO.y + HI.y) / 2 + dy, 0.005), rug_m, bevel=0.004)


if WIN_BACK:
    home_decor(WIN_BACK)
elif A.decor != "none" and CAM.get("studio_plant", True):
    # студійна кімната (22.10): деревце в теракоті в глибині ліворуч — глибина кадру й жива зелень, як на фото
    floor_obj("potted_plant_01", LO.x - CAM.get("plant_dx", 0.6), WALL_Y - 0.4, yaw=0.8, scale=1.1)


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
if WIN_BACK:
    # за вікном у кадрі — вулиця (сонце, оливкове дерево, будинок), але лише для променів камери: світло кімнати
    # і далі дає HDRI інтер'єру, тож вид не перефарбовує виріб
    view = wn.nodes.new("ShaderNodeTexEnvironment")
    view.image = img(os.path.join(CC0, "hdri", CAM.get("view_hdri", "bloem_olive_house_2k.hdr")))
    vmp = wn.nodes.new("ShaderNodeMapping")
    vmp.inputs["Rotation"].default_value = (0, 0, math.radians(CAM.get("view_rot", 152)))
    wn.links.new(wn.nodes.new("ShaderNodeTexCoord").outputs["Generated"], vmp.inputs["Vector"])
    wn.links.new(vmp.outputs["Vector"], view.inputs["Vector"])
    vbg = wn.nodes.new("ShaderNodeBackground")
    vbg.inputs["Strength"].default_value = CAM.get("view_strength", 2.5)
    wn.links.new(view.outputs["Color"], vbg.inputs["Color"])
    lp = wn.nodes.new("ShaderNodeLightPath")
    mix = wn.nodes.new("ShaderNodeMixShader")
    wn.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    wn.links.new(bg.outputs["Background"], mix.inputs[1])
    wn.links.new(vbg.outputs["Background"], mix.inputs[2])
    wn.links.new(mix.outputs["Shader"], wn.nodes["World Output"].inputs["Surface"])
    # денне світло крізь вікно в кадрі: м'яке джерело в прорізі, світить у кімнату, саме в кадрі не видно
    bl = bpy.data.lights.new("back-window", "AREA")
    bl.shape = "RECTANGLE"
    bl.size, bl.size_y = WIN_BACK["w"], WIN_BACK["z1"] - WIN_BACK["z0"]
    bl.energy = CAM.get("back_window", 90)
    bl.color = (0.96, 0.97, 1.0)
    blo = bpy.data.objects.new("back-window", bl)
    col.objects.link(blo)
    blo.location = ((WIN_BACK["x0"] + WIN_BACK["x1"]) / 2, WALL_Y + WIN_BACK["T"] + 0.05, (WIN_BACK["z0"] + WIN_BACK["z1"]) / 2)
    blo.rotation_euler = (math.radians(-90), 0, 0)
    blo.visible_camera = False

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
if not WIN_BACK and A.decor != "none" and CAM.get("side_curtain", True):
    # лляна фіранка на частині бічного вікна (22.10): частина сонця йде розсіяною — м'які й різкі тіні разом, як удома
    curtain(y0 - 0.15, y0 + (y1 - y0) * 0.42, gx + 0.16, z1 + 0.25, along="y", name="side-curtain")
    # друге полотно, відсунуте за ближній край вікна (22.10): видно в кутку кадру, проріз лишається відкритим для сонця
    curtain(y1 - 0.15, WALL_Y - 0.06, gx + 0.16, z1 + 0.25, along="y", name="corner-curtain", amp=0.05)
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
cy.adaptive_threshold = 0.01 if A.samples >= 256 else 0.02     # герої (512+): чистіші тіні під денойзом
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


def camera_post(path):
    """Те, що робить справжня камера (22.10): віньєтка, ледь помітна хроматика по краях і плівкове зерно.

    Зерно — яскравісне, сильніше в напівтонах, злегка розмите (зерно «грудками», а не піксельний шум) і
    детерміноване (seed), щоб повторний рендер давав ті самі байти. Сила — CAM grain/vignette/ca; 0 вимикає.
    """
    import numpy as np
    vig, ca, grain = CAM.get("vignette", 0.14), CAM.get("ca", 0.6), CAM.get("grain", 0.008)
    if not (vig or ca or grain):
        return
    im = bpy.data.images.load(path)
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    rgb = a[..., :3].copy()
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy_ = (w - 1) / 2, (h - 1) / 2
    if ca:                                       # латеральна хроматика: R трохи більший, B трохи менший від центру
        k = ca / cx

        def resample(ch, s):
            sx = np.clip(cx + (xx - cx) * s, 0, w - 1.001)
            sy = np.clip(cy_ + (yy - cy_) * s, 0, h - 1.001)
            x0, y0_ = sx.astype(np.int32), sy.astype(np.int32)
            fx, fy = sx - x0, sy - y0_
            return ((ch[y0_, x0] * (1 - fx) + ch[y0_, x0 + 1] * fx) * (1 - fy)
                    + (ch[y0_ + 1, x0] * (1 - fx) + ch[y0_ + 1, x0 + 1] * fx) * fy)
        rgb[..., 0] = resample(rgb[..., 0], 1 - k)
        rgb[..., 2] = resample(rgb[..., 2], 1 + k)
    if vig:                                      # плавне падіння до кутів (~cos⁴ ширококутника, але м'якше)
        r2 = ((xx - cx) / cx) ** 2 + ((yy - cy_) / cx) ** 2
        r2 /= r2.max()
        rgb *= (1 - vig * r2 ** 1.4)[..., None]
    if grain:
        rng = np.random.default_rng(22102026)
        g = rng.normal(0, 1, (h + 1, w + 1)).astype(np.float32)
        g = (g[:-1, :-1] + g[1:, :-1] + g[:-1, 1:] + g[1:, 1:]) / 2      # 2×2: зерно грудками, σ ≈ 1
        lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        rgb += (grain * g * (0.35 + 2.6 * lum * (1 - lum)))[..., None]
    a[..., :3] = np.clip(rgb, 0, 1)
    im.pixels.foreach_set(a.ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()


camera_post(A.out)
print("ALUMA_RENDER_OK", A.out)
