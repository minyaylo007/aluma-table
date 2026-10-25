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
# фотореальний прохід №21 (25.10, кадр life): шпон по листах, подряпини й пил, плитка з перепадами, стіна «хвилею»,
# справжня тканина доріжки, плетене сидіння, розетка й вимикач, чашка, світле вікно з ореолом, оптика камери.
# Лише за прапорцем: решта кадрів (hero, home, angle…) з тим самим cam рендериться байт-у-байт як раніше.
PHOTO = bool(CAM.get("photo"))

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


def rgb(nt, color):
    """Сталий колір як сокет (щоб пропустити його через vary)."""
    n = nt.nodes.new("ShaderNodeRGB")
    n.outputs[0].default_value = (*color, 1)
    return n.outputs[0]


def math_node(nt, op, a, b=None, clamp=False):
    """Вузол Math: a і b — сокет або число."""
    mn = nt.nodes.new("ShaderNodeMath")
    mn.operation = op
    mn.use_clamp = clamp
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            mn.inputs[i].default_value = x
        else:
            nt.links.new(x, mn.inputs[i])
    return mn.outputs["Value"]


def rand_of(nt, *socks):
    """Детерміноване випадкове 0..1 від одного-трьох чисел (номер листа шпону, номер плитки)."""
    wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
    if len(socks) == 1:
        wn.noise_dimensions = "1D"
        nt.links.new(socks[0], wn.inputs["W"])
    else:
        wn.noise_dimensions = "3D"
        cb = nt.nodes.new("ShaderNodeCombineXYZ")
        for i, s in enumerate(socks):
            nt.links.new(s, cb.inputs[i])
        nt.links.new(cb.outputs["Vector"], wn.inputs["Vector"])
    return wn.outputs["Value"], wn.outputs["Color"]


def veneer_leaves(nt, vec, leaf=0.1):
    """Стільниця з листів шпону (№21), а не одним аркушем скану: лист ~18 см поперек волокна (вісь X розгортки),
    кожен — свій шматок скану (зсув уздовж волокна й поперек на цілу кількість листів), половина дзеркальна
    («книжкою», як склеюють шпон на фабриці). Повертає вектор і випадкове листа (для відтінку й шорсткості)."""
    sp = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(vec, sp.inputs["Vector"])
    x, y = sp.outputs["X"], sp.outputs["Y"]
    lid = math_node(nt, "FLOOR", math_node(nt, "DIVIDE", x, leaf))
    r1, rc = rand_of(nt, lid)
    sc = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(rc, sc.inputs["Color"])
    # дзеркало всередині листа: x' = 2·lid·leaf + leaf − x
    mirrored = math_node(nt, "SUBTRACT", math_node(nt, "ADD", math_node(nt, "MULTIPLY", lid, 2 * leaf), leaf), x)
    flip = math_node(nt, "GREATER_THAN", sc.outputs["Green"], 0.5)
    xm = math_node(nt, "ADD", x, math_node(nt, "MULTIPLY", flip, math_node(nt, "SUBTRACT", mirrored, x)))
    jump = math_node(nt, "MULTIPLY", math_node(nt, "FLOOR", math_node(nt, "MULTIPLY", sc.outputs["Blue"], 7)), leaf)
    cb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(math_node(nt, "ADD", xm, jump), cb.inputs["X"])
    nt.links.new(math_node(nt, "ADD", y, math_node(nt, "MULTIPLY", r1, 3.7)), cb.inputs["Y"])
    nt.links.new(sp.outputs["Z"], cb.inputs["Z"])
    return cb.outputs["Vector"], r1


def wear(nt, rough, color, scale=18.0, coords="Object", dust=0.3):
    """Життя на поверхні (№21): волосяні подряпини (тонкі ізолінії шуму — видно лише у відблиску вікна) і пил на
    горизонталях (дрібні світлі цятки там, де нормаль дивиться вгору). Повертає (шорсткість, колір)."""
    n = noise(nt, scale, 1.0, coords)
    line = math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", n, 0.5))
    scratch = math_node(nt, "SUBTRACT", 1.0, math_node(nt, "DIVIDE", line, 0.006), clamp=True)
    sparse = nt.nodes.new("ShaderNodeMapRange")                     # подряпини не всюди: плямами
    sparse.inputs["From Min"].default_value, sparse.inputs["From Max"].default_value = 0.45, 0.65
    nt.links.new(noise(nt, 1.6, 2.0, coords), sparse.inputs["Value"])
    scratch = math_node(nt, "MULTIPLY", scratch, sparse.outputs["Result"])
    rough = math_node(nt, "ADD", rough, math_node(nt, "MULTIPLY", scratch, 0.14))
    if dust:
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sp = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Normal"], sp.inputs["Vector"])
        up = nt.nodes.new("ShaderNodeMapRange")
        up.inputs["From Min"].default_value, up.inputs["From Max"].default_value = 0.85, 1.0
        nt.links.new(sp.outputs["Z"], up.inputs["Value"])
        tc = nt.nodes.new("ShaderNodeTexCoord")
        fine = nt.nodes.new("ShaderNodeTexNoise")
        fine.inputs["Scale"].default_value = 700.0
        fine.inputs["Detail"].default_value = 0.0
        nt.links.new(tc.outputs[coords], fine.inputs["Vector"])
        speck = nt.nodes.new("ShaderNodeMapRange")
        speck.inputs["From Min"].default_value, speck.inputs["From Max"].default_value = 0.68, 0.78
        nt.links.new(fine.outputs["Fac"], speck.inputs["Value"])
        d = math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", speck.outputs["Result"], up.outputs["Result"]), dust)
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        nt.links.new(d, mx.inputs["Factor"])
        nt.links.new(color, mx.inputs[6])
        mx.inputs[7].default_value = (0.74, 0.72, 0.69, 1)
        color = mx.outputs[2]
        rough = math_node(nt, "ADD", rough, math_node(nt, "MULTIPLY", d, 0.5))
    return math_node(nt, "MINIMUM", rough, 1.0), color


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
    leaf = None
    if PHOTO and not box:                            # №21: листи шпону, а не один аркуш скану
        vec, leaf = veneer_leaves(nt, vec)
    proj = "BOX" if box else "FLAT"
    ta = node_tex(nt, alb, vector=vec, proj=proj)
    smudge = noise(nt, 2.2, 4.0)
    color = vary(nt, ta.outputs["Color"], noise(nt, 0.9, 2.0), 0.97, 1.03)
    if leaf is not None:                             # листи з різних колод: ±4 % тону, середнє те саме
        color = vary(nt, color, leaf, 0.96, 1.04)
    tr = node_tex(nt, os.path.join(TEX, f"{maps}-rough-2048.jpg"), True, vec, proj)
    mr = nt.nodes.new("ShaderNodeMapRange")          # олія: 0.35..0.47 — живий сатиновий відблиск, без дзеркала
    mr.inputs["To Min"].default_value = 0.35 if finish != "black" else 0.42
    mr.inputs["To Max"].default_value = 0.47 if finish != "black" else 0.55
    nt.links.new(tr.outputs["Color"], mr.inputs["Value"])
    # №21: сліди долонь і серветки у відблиску вікна — сильніші, ніж «ледь помітні» 22.10
    rough = vary(nt, mr.outputs["Result"], smudge, *((0.72, 1.3) if PHOTO else (0.9, 1.12)), "VALUE")
    if PHOTO:
        if leaf is not None:
            rough = vary(nt, rough, leaf, 0.92, 1.08, "VALUE")
        rough, color = wear(nt, rough, color, dust=0.0 if box else 0.3)
        b.inputs["Coat Weight"].default_value = 0.2   # олія з воском: м'який відблиск вікна на стільниці
        b.inputs["Coat Roughness"].default_value = 0.22
    nt.links.new(color, b.inputs["Base Color"])
    nt.links.new(rough, b.inputs["Roughness"])
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
                 disp=0.0, mottle=None, tiles=0, wave=0.0):
    """CC0-матеріал з теки. mottle=(сила, масштаб): велика пляма тону й шорсткості поверх тайла — вапно, сліди,
    нерівно витерта підлога; без неї тайл повторюється рівно, і стіна читається як шпалери.
    tiles=N (№21): у тайлі текстури N×N плиток (шви на кратних 1/N) — кожна плитка свого відтінку й шорсткості і
    трохи нахилена (перепад укладки): відблиск вікна ламається на швах, як на справжній підлозі.
    wave (№21): сила великої «хвилі» поверхні — штукатурка рукою не буває площиною, косе сонце це показує."""
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
    tile_r = None
    if tiles:
        sp = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(v, sp.inputs["Vector"])
        tx = math_node(nt, "FLOOR", math_node(nt, "MULTIPLY", sp.outputs["X"], tiles))
        ty = math_node(nt, "FLOOR", math_node(nt, "MULTIPLY", sp.outputs["Y"], tiles))
        tile_r, tile_c = rand_of(nt, tx, ty)
        c = vary(nt, c, tile_r, 0.95, 1.05)
        sc_ = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(tile_c, sc_.inputs["Color"])
        fx = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", sp.outputs["X"], tiles))
        fy = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", sp.outputs["Y"], tiles))
        tilt = math_node(nt, "ADD", math_node(nt, "MULTIPLY", fx, math_node(nt, "SUBTRACT", sc_.outputs["Green"], 0.5)),
                         math_node(nt, "MULTIPLY", fy, math_node(nt, "SUBTRACT", sc_.outputs["Blue"], 0.5)))
    nt.links.new(c, b.inputs["Base Color"])
    tr = node_tex(nt, os.path.join(f, "Rough.jpg"), True, v)
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = rough
    nt.links.new(tr.outputs["Color"], mr.inputs["Value"])
    r_out = mr.outputs["Result"]
    if mottle:
        r_out = vary(nt, r_out, noise(nt, mottle[1] * 1.7, 3.0), 0.85, 1.15, "VALUE")
    if tile_r is not None:
        r_out = vary(nt, r_out, tile_r, 0.8, 1.2, "VALUE")
    nt.links.new(r_out, b.inputs["Roughness"])
    nf = os.path.join(f, "nor_gl.jpg")
    nrm = None
    if os.path.exists(nf):
        tn = node_tex(nt, nf, True, v)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = nstr
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nrm = nm.outputs["Normal"]
    for height, dist in ((tilt, 0.004) if tiles else (None, 0), (noise(nt, 1.1, 2.0) if wave else None, 0.004 * wave)):
        if height is None:
            continue
        bp = nt.nodes.new("ShaderNodeBump")              # плитка: нахил ~1,5 мм на 30 см; стіна: хвиля кельми
        bp.inputs["Distance"].default_value = dist
        bp.inputs["Strength"].default_value = 1.0
        nt.links.new(height, bp.inputs["Height"])
        if nrm is not None:
            nt.links.new(nrm, bp.inputs["Normal"])
        nrm = bp.outputs["Normal"]
    if nrm is not None:
        nt.links.new(nrm, b.inputs["Normal"])
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
    FLOOR = tex_material("balata", "Tiles110", 1.85, sat=0.85, bright=0.03, rough=(0.2, 0.45), nstr=0.6,
                         **(dict(tiles=6, mottle=(0.035, 0.5)) if PHOTO else {}))   # №21: плитки різні, витерта доріжка
else:
    # 22.10: замість рівного мікроцементу — великі світлі кам'яні плити 75 см (Poly Haven large_floor_tiles_02,
    # перефарбовані в теплий вапняк), матова полировка з м'яким відблиском вікна, шви й нерівність каменю видно
    FLOOR = tex_material("limestone", "large_floor_tiles_02", 2.25, tint=(1.0, 0.92, 0.8), sat=0.1, bright=0.26,
                         contrast=0.05, rough=(0.2, 0.48), nstr=0.7, mottle=(0.05, 0.6))
# стіна: вапняна штукатурка — та сама plastered_wall_04, але з великою плямою тону (вапно лягає нерівно)
WALL = tex_material("plaster", "plastered_wall_04", 1.6, tint=(0.98, 0.94, 0.88), sat=0.3, bright=0.06,
                    rough=(0.78, 0.97), nstr=0.9, mottle=(0.06, 0.45), wave=1.0 if PHOTO else 0.0)
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


def cord_material():
    """Сидіння з паперового шнура (№21): чотири трикутники, у кожному шнур іде паралельно своєму краю (як плетуть
    данські стільці), шнур ~5 мм з рельєфом і ледь різним тоном — замість розмазаної текстури кошика."""
    m, nt, b = pbr("cord", rough=0.8)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sp = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sp.inputs["Vector"])
    ax, ay = math_node(nt, "ABSOLUTE", sp.outputs["X"]), math_node(nt, "ABSOLUTE", sp.outputs["Y"])
    side = math_node(nt, "GREATER_THAN", ax, ay)                  # 1 — лівий/правий трикутник
    coord = math_node(nt, "ADD", math_node(nt, "MULTIPLY", side, ax),
                      math_node(nt, "MULTIPLY", math_node(nt, "SUBTRACT", 1.0, side), ay))
    cb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(coord, cb.inputs["X"])
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type, wv.bands_direction, wv.wave_profile = "BANDS", "X", "SIN"
    wv.inputs["Scale"].default_value = 36.0                         # період 2π/(20·36) ≈ 9 мм: дрібніший OIDN змазує
    wv.inputs["Distortion"].default_value = 0.6
    wv.inputs["Detail"].default_value = 1.0
    nt.links.new(cb.outputs["Vector"], wv.inputs["Vector"])
    ridge = nt.nodes.new("ShaderNodeMapRange")                      # жолобок між шнурами темніший
    ridge.inputs["To Min"].default_value, ridge.inputs["To Max"].default_value = 0.38, 1.05
    nt.links.new(wv.outputs["Fac"], ridge.inputs["Value"])
    col = vary(nt, rgb(nt, (0.6, 0.47, 0.3)), noise(nt, 40.0, 3.0), 0.85, 1.12)
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type, mx.blend_type = "RGBA", "MULTIPLY"
    mx.inputs["Factor"].default_value = 1.0
    nt.links.new(col, mx.inputs[6])
    nt.links.new(ridge.outputs["Result"], mx.inputs[7])
    # шнур бічних трикутників лежить поперек світла, переднього й заднього — уздовж: тон різний, і ці діагоналі
    # видно навіть у розфокусі, де самі шнури (9 мм) змазуються
    tri = nt.nodes.new("ShaderNodeMix")
    tri.data_type, tri.blend_type = "RGBA", "MULTIPLY"
    tri.inputs["Factor"].default_value = 1.0
    nt.links.new(mx.outputs[2], tri.inputs[6])
    nt.links.new(math_node(nt, "ADD", 0.84, math_node(nt, "MULTIPLY", side, 0.16)), tri.inputs[7])
    nt.links.new(tri.outputs[2], b.inputs["Base Color"])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value, bp.inputs["Distance"].default_value = 1.0, 0.003
    nt.links.new(wv.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Sheen Weight"].default_value = 0.25
    return m


WICKER = cord_material() if PHOTO else wicker_material()


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


def boost(objs, sat=1.0, val=1.0, hue=0.5, sss=0.0):
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
            hs.inputs["Hue"].default_value = hue
            if sss:                                   # шкірка лимона пропускає світло — без цього «пластик»
                b.inputs["Subsurface Weight"].default_value = sss
                b.inputs["Subsurface Radius"].default_value = (0.004, 0.003, 0.0015)
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
        boost(lobjs, *((1.85, 1.25, 0.497, 0.25) if PHOTO else (1.35, 1.12)))   # №21: жовтий, не оливковий
        lroot.rotation_euler = (math.radians(90 + 25 * (i % 3 - 1)), math.radians(17 * i), 1.3 * i)
        drop_on(lroot, lobjs, base + dz)
        centre_on(lroot, lobjs, x + dx, y + dy)


def jug_on(x, y, z, yaw=2.2):
    """Ваза з сирої глини (CC0 ceramic_vase_02, 25 см) — матова кераміка замість білої вази з сухою гілкою."""
    root, objs = gltf("ceramic_vase_02", (x, y, z), yaw=yaw, scale=0.8)
    drop_on(root, objs, z + 0.0005)
    centre_on(root, objs, x, y)


def book_on(x, y, z, yaw=0.3, size=(0.155, 0.235, 0.024), cover=(0.36, 0.17, 0.1), stack=True):
    """Книжка, покладена на стіл (24.10, «як живе фото»): наша модель — палітурка і блок сторінок, чужих видань нема.
    №21: палітурка — тканина (рельєф і злегка витерті краї), обріз — тонкі смуги аркушів; під нею — друга, більша
    й тонша, трохи повернута: дві книжки купкою — так кладе людина, а не стиліст."""
    if PHOTO and stack:
        book_on(x + 0.01, y - 0.006, z, yaw - 0.13, (0.17, 0.245, 0.016), (0.62, 0.6, 0.52), stack=False)
        z += 0.016
    w, h, t = size
    cov = pbr("book-cover", color=cover, rough=0.78)[0]
    pages = pbr("book-pages", color=(0.86, 0.83, 0.76), rough=0.9)[0]
    if PHOTO:
        nt = cov.node_tree
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value, bp.inputs["Distance"].default_value = 0.6, 0.0004
        nt.links.new(noise(nt, 900.0, 2.0), bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
        bc = nt.nodes["Principled BSDF"].inputs["Base Color"]
        nt.links.new(vary(nt, rgb(nt, cover), noise(nt, 30.0, 3.0), 0.9, 1.12), bc)
        nt = pages.node_tree
        tc = nt.nodes.new("ShaderNodeTexCoord")
        wv = nt.nodes.new("ShaderNodeTexWave")
        wv.wave_type, wv.bands_direction = "BANDS", "Z"
        wv.inputs["Scale"].default_value = 900.0
        wv.inputs["Distortion"].default_value = 3.0
        nt.links.new(tc.outputs["Object"], wv.inputs["Vector"])
        nt.links.new(vary(nt, rgb(nt, (0.86, 0.83, 0.76)), wv.outputs["Fac"], 0.9, 1.04),
                     nt.nodes["Principled BSDF"].inputs["Base Color"])
    c, s = math.cos(yaw), math.sin(yaw)

    def at(dx, dz):                                   # зсув від центру книжки вздовж її ширини, повернутий на yaw
        return (x + dx * c, y + dx * s, z + dz)
    rot = (0, 0, yaw)
    cube("book-pages", (w - 0.006, h - 0.008, t - 0.004), at(0.002, t / 2), pages, bevel=0.0015, rot=rot)
    cube("book-cover-top", (w, h, 0.0022), at(0, t - 0.0011), cov, bevel=0.0008, rot=rot)
    cube("book-cover-bot", (w, h, 0.0022), at(0, 0.0011), cov, bevel=0.0008, rot=rot)
    cube("book-spine", (0.0026, h, t), at(-w / 2 + 0.0013, t / 2), cov, bevel=0.001, rot=rot)


def mug_on(x, y, z, yaw=0.0, color=(0.74, 0.72, 0.66)):
    """Керамічна чашка 8 см (№21, наша модель): глазур із відблиском, ручка — півтора тора. Чашку лишили на столі —
    стіл живий, а не виставковий."""
    glaze = pbr("glaze", rough=0.14, coat=0.3, coat_rough=0.08, color=color)[0]
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.04, depth=0.088, location=(x, y, z + 0.044))
    mg = bpy.context.object
    mg.name = "mug"
    bm = bmesh.new()
    bm.from_mesh(mg.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z > 0.9], context="FACES")
    bm.to_mesh(mg.data)
    bm.free()
    mg.data.materials.append(glaze)
    so = mg.modifiers.new("solid", "SOLIDIFY")
    so.thickness, so.offset = 0.004, -1.0
    bv = mg.modifiers.new("bevel", "BEVEL")
    bv.width, bv.segments = 0.0015, 3
    mg.data.shade_smooth()
    c, s = math.cos(yaw), math.sin(yaw)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.024, minor_radius=0.0055, major_segments=48, minor_segments=16,
                                     location=(x + 0.045 * c, y + 0.045 * s, z + 0.047), rotation=(math.radians(90), 0, yaw))
    hd = bpy.context.object
    hd.name = "mug-handle"
    hd.data.materials.append(glaze)
    hd.data.shade_smooth()


def cloth(name, w, d, loc, mat, seed=3):
    """Лляна доріжка (№21): сітка 1 см, підйом лише вгору (лежить на стільниці, не провалюється) — дрібні хвилі
    тканини, поздовжній залом від складання і трохи піднятий край; товщина 1,2 мм, кромка-підгин 1 см."""
    from mathutils import noise as mnoise
    nx, ny = max(int(w / 0.01), 8), max(int(d / 0.01), 8)
    vs, fs = [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            x, y = -w / 2 + w * i / nx, -d / 2 + d * j / ny
            h = 0.0012 * (1 + mnoise.noise(Vector((x * 9 + seed, y * 9, 0.3))))          # м'які хвилі
            h += 0.0016 * math.exp(-((y - d * 0.08) / 0.006) ** 2)                       # залом від складання
            edge = min(x + w / 2, w / 2 - x, y + d / 2, d / 2 - y)
            h += 0.0012 * max(0.0, 1 - edge / 0.012)                                     # підгин по краю
            vs.append((x, y, h))
    for j in range(ny):
        for i in range(nx):
            k = j * (nx + 1) + i
            fs.append((k, k + 1, k + nx + 2, k + nx + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.materials.append(mat)
    me.shade_smooth()
    ob = link_obj(name, me)
    ob.location = loc
    so = ob.modifiers.new("solid", "SOLIDIFY")
    so.thickness, so.offset = 0.0012, 1.0
    return ob


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
        if PHOTO:                                      # №21: тканина з товщиною, м'якими складками й заломом
            cloth("runner", min(1.3, L * 0.62), 0.38, (-0.05, cy, TOP + 0.0002), run_m)
        else:
            r = cube("runner", (min(1.3, L * 0.62), 0.38, 0.003), (-0.05, cy, TOP + 0.0016), run_m)
            r.modifiers.new("sub", "SUBSURF").render_levels = 1
    # 22.10: глечик і миска з лимонами (як живе фото), замість вази з сухою гілкою й дошки з грушами
    jug_on(-min(L * 0.18, 0.3) - (0.04 if round_ else 0), cy + 0.07, TOP + 0.003)
    lemons_in_bowl(min(L * 0.14, 0.2), cy - 0.03, TOP + 0.003)
    if CAM.get("book"):                                # кадр life: розгорнута на столі книжка ближче до камери
        book_on(min(L * 0.3, 0.5), cy - D * 0.22, TOP + 0.003, yaw=0.35)
    if PHOTO and CAM.get("mug", True):
        mx_, my_ = CAM.get("mug_at", [min(L * 0.3, 0.5) - 0.25, -D * 0.2])
        mug_on(mx_, cy + my_, TOP + 0.0005, yaw=CAM.get("mug_yaw", -0.6))


def top_decor():
    """Тумба, консоль, журнальний: ваза з гілкою з одного краю, миска з грушами — з другого."""
    L, cy = SIZE.x, (LO.y + HI.y) / 2
    jug_on(LO.x + min(0.26, L * 0.22), cy + 0.02, TOP + 0.0005)
    lemons_in_bowl(HI.x - min(0.3, L * 0.26), cy - 0.01, TOP + 0.0005, n=4)
    if CAM.get("book"):
        book_on((LO.x + HI.x) / 2 + L * 0.06, cy + 0.005, TOP + 0.0005, yaw=-0.18)
    if PHOTO and CAM.get("mug", True):
        mx_, my_ = CAM.get("mug_at", [-L * 0.08, -0.1])
        mug_on((LO.x + HI.x) / 2 + mx_, cy + my_, TOP + 0.0005, yaw=CAM.get("mug_yaw", -0.6))


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


def wall_plate(name, x, z, kind="socket"):
    """Біла рамка 8×8 см на стіні (№21): розетка (ізраїльська, три круглі гнізда) або клавішний вимикач."""
    plate = pbr("plate", rough=0.35, color=(0.86, 0.85, 0.82))[0]
    hole = pbr("hole", rough=0.9, color=(0.02, 0.02, 0.02))[0]
    cube(name, (0.082, 0.009, 0.082), (x, WALL_Y - 0.0045, z), plate, bevel=0.004, seg=4)
    if kind == "socket":
        for dx, dz in ((-0.0095, 0.006), (0.0095, 0.006), (0.0, -0.011)):
            bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.0024, depth=0.002,
                                                location=(x + dx, WALL_Y - 0.0085, z + dz), rotation=(math.radians(90), 0, 0))
            bpy.context.object.data.materials.append(hole)
    else:
        cube(name + "-key", (0.034, 0.006, 0.05), (x, WALL_Y - 0.0105, z), plate, bevel=0.003, seg=3,
             rot=(math.radians(-3), 0, 0))


if WIN_BACK:
    home_decor(WIN_BACK)
    if PHOTO:
        sx, sz = CAM.get("socket", [0.35, 0.32])
        wall_plate("socket", HI.x + sx, sz)
        if CAM.get("switch", True):
            wall_plate("switch", WIN_BACK["x1"] + 0.28, 1.1, "switch")
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
    if CAM.get("roll"):                          # з рук, не зі штатива: горизонт на пів градуса не рівний
        from mathutils import Quaternion
        cam.rotation_euler = (rot.to_quaternion() @ Quaternion((0, 0, 1), math.radians(CAM["roll"]))).to_euler()
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
    №21: distort — легка бочка об'єктива (k від краю кадру, кути підрізаються, а не розтягуються); bloom — ореол
    навколо світлих місць (вікно, відблиск на склі): два розмиття, теплий відтінок, додається «екраном».
    """
    import numpy as np
    vig, ca, grain = CAM.get("vignette", 0.14), CAM.get("ca", 0.6), CAM.get("grain", 0.008)
    distort, bloom = CAM.get("distort", 0.0), CAM.get("bloom", 0.0)
    if not (vig or ca or grain or distort or bloom):
        return
    im = bpy.data.images.load(path)
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    rgb = a[..., :3].copy()
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy_ = (w - 1) / 2, (h - 1) / 2
    if ca or distort:                            # латеральна хроматика: R трохи більший, B трохи менший від центру
        k = ca / cx
        base = 1.0
        if distort:                              # бочка: пиксель на радіусі r бере джерело з r·(1 + d·r²), кадр підрізано
            r2n = ((xx - cx) ** 2 + (yy - cy_) ** 2) / (cx * cx)
            base = (1 + distort * r2n) / (1 + distort * r2n.max())

        def resample(ch, s):
            sx = np.clip(cx + (xx - cx) * s, 0, w - 1.001)
            sy = np.clip(cy_ + (yy - cy_) * s, 0, h - 1.001)
            x0, y0_ = sx.astype(np.int32), sy.astype(np.int32)
            fx, fy = sx - x0, sy - y0_
            return ((ch[y0_, x0] * (1 - fx) + ch[y0_, x0 + 1] * fx) * (1 - fy)
                    + (ch[y0_ + 1, x0] * (1 - fx) + ch[y0_ + 1, x0 + 1] * fx) * fy)
        rgb[..., 0] = resample(rgb[..., 0], base * (1 - k))
        rgb[..., 2] = resample(rgb[..., 2], base * (1 + k))
        if distort:
            rgb[..., 1] = resample(rgb[..., 1], base)
    if bloom:
        def blur(x, r):                          # три проходи коробкою ≈ гаус, окремо по осях
            for _ in range(3):
                for ax in (0, 1):
                    c = np.cumsum(np.pad(x, [(r + 1, r) if i == ax else (0, 0) for i in range(3)], mode="edge"), axis=ax)
                    x = (np.take(c, range(2 * r + 1, c.shape[ax]), axis=ax) - np.take(c, range(0, c.shape[ax] - 2 * r - 1), axis=ax)) / (2 * r + 1)
            return x
        lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        hi = (np.clip((lum - 0.8) / 0.2, 0, 1) ** 2)[..., None] * rgb
        glow = (0.6 * blur(hi, max(2, w // 260)) + 0.4 * blur(hi, max(4, w // 70))) * np.array([1.0, 0.93, 0.84], np.float32)
        glow *= bloom
        rgb = 1 - (1 - rgb) * (1 - np.clip(glow, 0, 1))
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
