# -*- coding:utf-8 -*-
"""Switch UDIM headless smoke test - runs INSIDE Blender (-b).

Enables the installed extension, generates a folder of named texture
fixtures (roles, UDIM sequences, mask overlay, DX normal, roleless junk),
runs Connect from Folder, verifies the node graphs (sockets, chains,
colorspaces, UDIM tiles), exercises the selection-scoped switch operators,
Reload Changed (baseline / change / unchanged / missing) and Copy Image
Settings.

Prerequisite: the switch_udim extension is installed into a user resources
dir pointed to by BLENDER_USER_RESOURCES (see tests/run_smoke.py).

Exit code: 0 = all steps passed, 1 = at least one step failed.
Never returns through the normal interpreter teardown: Blender -b can hang
on exit on some setups, os._exit is safe everywhere.
"""

import bpy
import os
import sys
import tempfile
import traceback
from types import SimpleNamespace

MOD = "bl_ext.user_default.switch_udim"

RESULTS = []


def step(name, fn):
    try:
        info = fn() or ""
        RESULTS.append((name, True, info))
        print(f"[SMOKE] PASS {name} {info}", flush=True)
    except Exception as e:
        RESULTS.append((name, False, str(e)))
        print(f"[SMOKE] FAIL {name}: {e}", flush=True)
        traceback.print_exc()


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ── Enable the extension ─────────────────────────────────────────────────────

import addon_utils

enable_info = addon_utils.enable(MOD, default_set=True, persistent=True)
if MOD not in sys.modules:
    raise SystemExit(f"cannot enable {MOD}: {enable_info!r}")

mod = sys.modules[MOD]
FAKE_REPORT = lambda t, m: None  # noqa: E731


# ── Fixture ──────────────────────────────────────────────────────────────────

TEX_DIR = os.path.join(tempfile.gettempdir(), "switchudim_smoke_tex")

FIXTURES = [
    "cube01_basecolor.png", "cube01_roughness.png", "cube01_normal.png",
    "cube02_basecolor.1001.png", "cube02_basecolor.1002.png", "cube02_basecolor.1003.png",
    "cube02_roughness.1001.png", "cube02_roughness.1002.png",
    "cube03_basecolor.png", "cube03_ao.png", "cube03_emission.png",
    "cube03_gloss.png", "cube03_specular.png", "cube03_displacement.png",
    "cube03_normal_dx.png",
    "cube04_basecolor.png", "cube04_basecolor_2.png", "cube04_mask.png",
    "cube05_basecolor.png", "cube05_mask.png",
    "cube06.basecolor_acescg.1001.png", "cube06.basecolor_acescg.1002.png",
    "cube06.mask_dirt_raw.1001.png",
    "notes.txt", "t34_88.png",
]


def make_tex(name, size=4, val=0.3):
    img = bpy.data.images.new("SMOKETMP", size, size)
    img.pixels.foreach_set([val] * (size * size * 4))
    img.filepath_raw = os.path.join(TEX_DIR, name)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def st_fixture():
    import shutil
    shutil.rmtree(TEX_DIR, ignore_errors=True)
    os.makedirs(TEX_DIR)
    for n in FIXTURES:
        make_tex(n)
    expect(len(os.listdir(TEX_DIR)) == len(FIXTURES), "fixture files on disk")
    return f"{len(FIXTURES)} files"


def st_objects():
    vl = bpy.context.view_layer
    for ob in list(vl.objects.selected):
        ob.select_set(False)
    for nm in ("Cube01", "Cube02", "Cube03", "Cube04", "Cube05", "Cube06"):
        me = bpy.data.meshes.new(nm)
        ob = bpy.data.objects.new(nm, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.select_set(True)
    vl.objects.active = bpy.context.scene.objects["Cube01"]
    expect(len(vl.objects.selected) == 6, "6 objects selected")
    return "6 objects"


# ── Connect from Folder ──────────────────────────────────────────────────────

def st_connect():
    r = bpy.ops.texture.connect_folder("EXEC_DEFAULT", filepath=TEX_DIR)
    expect(r == {"FINISHED"}, f"op returned {r}")
    for nm in ("cube01", "cube02", "cube03", "cube04", "cube05", "cube06"):
        expect(bpy.data.materials.get(nm) is not None, f"material {nm} missing")


def _tex_nodes(mat):
    return [n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE"]


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def st_graphs():
    m1 = bpy.data.materials["cube01"]
    b1 = _bsdf(m1)
    expect(len(_tex_nodes(m1)) == 3, "cube01: expected 3 tex nodes")
    for s in ("Base Color", "Roughness", "Normal"):
        expect(b1.inputs[s].is_linked, f"cube01: {s} not linked")
    expect(not b1.inputs["Metallic"].is_linked, "cube01: Metallic should be free")
    nms = [n for n in m1.node_tree.nodes if n.type == "NORMAL_MAP"]
    expect(len(nms) == 1 and b1.inputs["Normal"].links[0].from_node.name == nms[0].name,
           "cube01: Normal must go through NormalMap node")
    bc1 = next(n.image for n in _tex_nodes(m1) if "basecolor" in n.image.name)
    expect(bc1.colorspace_settings.is_data is False, "cube01: basecolor must be a color space")
    expect("srgb" in bc1.colorspace_settings.name.lower(),
           f"cube01: basecolor cs '{bc1.colorspace_settings.name}' not sRGB-like")
    nr1 = next(n.image for n in _tex_nodes(m1) if "normal" in n.image.name)
    expect(nr1.colorspace_settings.is_data is True, "cube01: normal must be data")

    m2 = bpy.data.materials["cube02"]
    bc2 = next(n.image for n in _tex_nodes(m2) if "basecolor" in n.image.name)
    expect(bc2.source == "TILED" and len(bc2.tiles) == 3, "cube02: basecolor must be TILED with 3 tiles")
    expect("<UDIM>" in bc2.filepath, "cube02: basecolor path must carry <UDIM>")

    m3 = bpy.data.materials["cube03"]
    b3 = _bsdf(m3)
    expect(len(_tex_nodes(m3)) == 6, "cube03: 6 tex nodes (DX normal skipped)")
    mix3 = b3.inputs["Base Color"].links[0].from_node
    expect(mix3.type in ("MIX_RGB", "MIX") and getattr(mix3, "blend_type", "") == "MULTIPLY",
           "cube03: Base Color must come from MULTIPLY mix (AO)")
    rough3 = b3.inputs["Roughness"].links[0].from_node
    expect(rough3.type == "INVERT", "cube03: gloss must be inverted into Roughness")
    spec = "Specular IOR Level" if "Specular IOR Level" in b3.inputs else "Specular"
    expect(b3.inputs[spec].is_linked, "cube03: Specular must be linked")
    expect(b3.inputs["Emission Color"].is_linked if "Emission Color" in b3.inputs
           else b3.inputs["Emission"].is_linked, "cube03: Emission must be linked")
    out3 = next(n for n in m3.node_tree.nodes if n.type == "OUTPUT_MATERIAL")
    expect(out3.inputs["Displacement"].is_linked, "cube03: Displacement must reach Material Output")
    expect(not b3.inputs["Normal"].is_linked, "cube03: DX normal must NOT be linked")

    m4 = bpy.data.materials["cube04"]
    b4 = _bsdf(m4)
    mix4 = b4.inputs["Base Color"].links[0].from_node
    expect(mix4.type in ("MIX_RGB", "MIX"), "cube04: overlay mix missing")
    fac4 = mix4.inputs["Fac"] if "Fac" in mix4.inputs else next(
        s for s in mix4.inputs if s.type == "VALUE")
    expect(fac4.is_linked and "mask" in fac4.links[0].from_node.image.name,
           "cube04: mask must drive the mix factor")
    fed = {l.from_node.image.name for s in mix4.inputs if s.type == "RGBA"
           for l in s.links if getattr(l.from_node, "image", None)}
    expect(fed == {"cube04_basecolor.png", "cube04_basecolor_2.png"},
           f"cube04: mix must feed on basecolor + basecolor_2, got {fed}")
    mask_img = fac4.links[0].from_node.image
    expect(mask_img.colorspace_settings.is_data is True, "cube04: mask must be data")

    m5 = bpy.data.materials["cube05"]
    b5 = _bsdf(m5)
    mix5 = b5.inputs["Base Color"].links[0].from_node
    expect(mix5.type in ("MIX_RGB", "MIX"), "cube05: overlay mix missing")
    rgba5 = [s for s in mix5.inputs if s.type == "RGBA"]
    linked5 = [s for s in rgba5 if s.is_linked]
    expect(len(linked5) == 1, "cube05: only basecolor must feed the mix (constant overlay)")

    # production naming: 'cube06.basecolor_acescg.1001' → токен-роль в середине
    m6 = bpy.data.materials["cube06"]
    expect(m6 is not None, "cube06: material missing")
    b6 = _bsdf(m6)
    expect(b6.inputs["Base Color"].is_linked, "cube06: Base Color linked")
    bc6 = next(n.image for n in _tex_nodes(m6) if "basecolor" in n.image.name)
    expect(bc6.source == "TILED" and len(bc6.tiles) == 2,
           "cube06: UDIM 2 tiles from production naming")
    floats6 = [n for n in _tex_nodes(m6) if (n.label or "").startswith("mask_")]
    expect(len(floats6) == 1 and floats6[0].label == "mask_dirt",
           "cube06: one floating mask node labeled mask_dirt")
    expect(not any(s.is_linked for s in floats6[0].outputs),
           "cube06: mask node unlinked")
    return "6 materials verified"


def st_switch_selected():
    m1 = bpy.data.materials["cube01"]
    nt = m1.node_tree
    for n in nt.nodes:
        n.select = False
    texs = [n for n in nt.nodes if n.type == "TEX_IMAGE"]
    for n in texs:
        n.select = True
    fake_ctx = SimpleNamespace(space_data=SimpleNamespace(edit_tree=nt))
    mod.SWITCH_OT_to_udim.execute(SimpleNamespace(report=FAKE_REPORT), fake_ctx)
    expect(all(n.image.source == "TILED" for n in texs), "to_udim: selection not switched")
    mod.SWITCH_OT_to_single.execute(SimpleNamespace(report=FAKE_REPORT), fake_ctx)
    expect(all(n.image.source == "FILE" for n in texs), "to_single: selection not switched back")
    return f"{len(texs)} images switched by selection"


def st_reload_changed():
    # снимок в %TEMP% общий и переживает прогоны — вычищаем ключи фикстур,
    # чтобы baseline был детерминированным
    snap = mod._load_filesnap()
    for k in [k for k in list(snap) if k.lower().startswith(TEX_DIR.lower())]:
        del snap[k]
    mod._save_filesnap()
    r1 = mod._reload_changed()
    expect(r1["reloaded"] == [], f"baseline run must not reload, got {r1['reloaded']}")
    make_tex("cube01_basecolor.png", size=8, val=0.8)  # файл изменился
    r2 = mod._reload_changed()
    expect("cube01_basecolor.png" in r2["reloaded"],
           f"changed file not reloaded: {r2}")
    r3 = mod._reload_changed()
    expect(r3["reloaded"] == [], f"unchanged run reloaded something: {r3}")
    return "baseline → change → unchanged OK"


def st_copy_settings():
    m1 = bpy.data.materials["cube01"]
    nt = m1.node_tree
    for n in nt.nodes:
        n.select = False
    texs = [n for n in nt.nodes if n.type == "TEX_IMAGE"]
    src = next(n for n in texs if "roughness" in n.image.name)
    for n in texs:
        n.select = True
    nt.nodes.active = src
    src.extension = "CLIP"
    fake_ctx = SimpleNamespace(space_data=SimpleNamespace(edit_tree=nt))
    mod.SWITCH_OT_copy_image_settings.execute(
        SimpleNamespace(report=FAKE_REPORT), fake_ctx)
    bc_node = next(n for n in texs if "basecolor" in n.image.name)
    expect(bc_node.extension == "CLIP", "copy settings: extension not copied")
    expect(bc_node.image.colorspace_settings.is_data is True,
           "copy settings: colorspace not copied")
    return "extension+colorspace copied"


def st_stats():
    r = bpy.ops.texture.udim_stats("EXEC_DEFAULT")
    expect(r == {"FINISHED"}, f"stats op returned {r}")
    return "stats ran headless"


def st_version():
    # у extension-модулей Blender вырезает bl_info — версия живёт в манифесте
    v = getattr(mod, "bl_info", {}).get("version")
    if v is None:
        import tomllib
        manifest = os.path.join(os.path.dirname(mod.__file__),
                                "blender_manifest.toml")
        with open(manifest, "rb") as f:
            data = tomllib.load(f)
        v = tuple(int(x) for x in data["version"].split("."))
    expect(v >= (1, 1, 1), f"unexpected addon version {v}")
    expect(hasattr(bpy.types.Scene, "swudim_overwrite"), "scene prop missing")
    return f"v{'.'.join(map(str, v))}"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("[SMOKE] Switch UDIM headless smoke test")
    print("=" * 60)

    step("version", st_version)
    step("fixture", st_fixture)
    step("objects", st_objects)
    step("connect_folder", st_connect)
    step("graphs", st_graphs)
    step("switch_selected", st_switch_selected)
    step("reload_changed", st_reload_changed)
    step("copy_settings", st_copy_settings)
    step("stats", st_stats)

    failed = [r for r in RESULTS if not r[1]]
    print("=" * 60)
    for name, ok, info in RESULTS:
        if not ok:
            print(f"[SMOKE] FAILED STEP: {name}: {info}")
    verdict = "PASS" if not failed else "FAIL"
    print(f"SMOKE_RESULT: {verdict} ({len(RESULTS) - len(failed)}/{len(RESULTS)} steps)")
    print("=" * 60)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if not failed else 1)


main()
