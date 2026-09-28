_VERSION = (1, 1, 1)

bl_info = {
    "name": "Switch UDIM",
    "author": "Maksim Kovalev",
    "version": _VERSION,
    "blender": (3, 0, 0),
    "location": "Shader Editor > N-Panel > UDIM",
    "description": "Переключение Image Texture между Single Image и UDIM Tiles + автоподключение текстур к Principled BSDF",
    "category": "Node",
}

import bpy
import os
import re
import json
import tempfile

from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
)

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

IMG_EXT = {".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff",
           ".exr", ".hdr", ".bmp", ".webp"}

# "Ассет_Роль.1001" → ("ассет_роль", 1001)
UDIM_RE = re.compile(r"^(.+?)[._](10\d\d)$")

# Хвостовые токены DX-нормалей: карта скипается с честным репортом
# (Blender хочет GL-нормали), как в Node Wrangler
DX_TOKENS = {"dx", "directx", "dxnormal", "normaldx"}

# Порядок важен:
# - ao после basecolor (микс собирается из basecolor-текстуры)
# - roughness раньше gloss (общий сокет Roughness)
# - normal раньше bump (bump цепляется в цепочку нормали)
ROLE_ORDER = ("basecolor", "ao", "emission", "roughness", "gloss", "metallic",
              "specular", "transmission", "opacity", "normal", "bump",
              "displacement")

# mask не подключается сама по себе — она.factor микса оверлея на Base Color
# (обрабатывается внутри роли basecolor). В ROLE_ORDER не входит.
ROLE_ALL = ROLE_ORDER + ("mask",)

# Порядок галок в панели: частые роли сверху (как в ТЗ юзера)
PANEL_ROLE_ORDER = ("basecolor", "roughness", "metallic", "normal",
                    "displacement", "opacity", "mask", "emission",
                    "specular", "transmission", "ao", "gloss", "bump")

ROLE_LABELS = {
    "basecolor": "Base Color",
    "ao": "AO",
    "emission": "Emission",
    "roughness": "Roughness",
    "gloss": "Gloss",
    "metallic": "Metallic",
    "specular": "Specular",
    "transmission": "Transmission",
    "opacity": "Opacity / Alpha",
    "normal": "Normal",
    "bump": "Bump",
    "displacement": "Displacement",
    "mask": "Mask",
}

# Сокеты Principled BSDF по ролям. Кандидаты через запятую —
# имена менялись между 3.x и 4.x ('Specular' → 'Specular IOR Level' и т.п.)
SOCKET_CANDIDATES = {
    "basecolor": ("Base Color",),
    "ao": ("Base Color",),
    "emission": ("Emission Color", "Emission"),
    "roughness": ("Roughness",),
    "gloss": ("Roughness",),
    "metallic": ("Metallic",),
    "specular": ("Specular IOR Level", "Specular"),
    "transmission": ("Transmission Weight", "Transmission"),
    "opacity": ("Alpha",),
    "normal": ("Normal",),
    "bump": ("Normal",),
}

# Роли, чьи текстуры несут цвет (остальные — data, см. _set_colorspace)
COLOR_ROLES = ("basecolor", "emission")

DEFAULT_KEYWORDS = {
    "basecolor": "basecolor, base color, albedo, diffuse, diff, col, color, bc",
    "ao": "ao, occlusion, ambient, ambientocclusion",
    "emission": "emission, emissive, emit",
    "roughness": "roughness, rough, rgh",
    "gloss": "gloss, glossy, glossiness",
    "metallic": "metallic, metalness, metal, mtl",
    "specular": "specular, specularity, spec, spc",
    "transmission": "transmission, transparency",
    "opacity": "opacity, alpha",
    "normal": "normal, normalmap, nrm, nrml, norm, nor",
    "bump": "bump, bmp",
    "displacement": "displacement, displace, disp, dsp, height, heightmap",
    "mask": "mask, msk, masks",
}

COLORSPACE_SRGB = ('sRGB', 'Utility - sRGB - Texture', 'sRGB - Texture',
                   'srgb_texture', 'Output - sRGB')


# ──────────────────────────────────────────────
# Helpers: нейминг и парсинг
# ──────────────────────────────────────────────

def _prefs():
    try:
        return bpy.context.preferences.addons[__name__].preferences
    except KeyError:
        return None


def _keywords(role):
    """Ключевые слова роли из преференсов (или дефолт)."""
    p = _prefs()
    raw = getattr(p, "kw_" + role, None) if p else None
    if not raw:
        raw = DEFAULT_KEYWORDS[role]
    return {w.strip().casefold().replace(" ", "") for w in raw.split(",") if w.strip()}


def _role_map():
    """[(keyword, role)] — длинные ключи первыми, чтобы 'basecolor' бился раньше 'color'."""
    pairs = []
    for role in ROLE_ALL:
        for kw in _keywords(role):
            pairs.append((kw, role))
    pairs.sort(key=lambda x: -len(x[0]))
    return pairs


def _norm(s):
    """Нормализация имени для сравнения: lower + выброс разделителей."""
    return re.sub(r"[^0-9a-zа-яё]+", "", s.lower())


def _strip_num_suffix(name):
    """'Материал.001' → 'Материал' (копии датаблоков)."""
    parts = name.rsplit(".", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) <= 3:
        return parts[0]
    return name


def _match_role(base, role_map):
    """Хвостовой роль-суффикс → (ключ, роль) или (base, None)."""
    for kw, role in role_map:
        m = re.search(r"[._\- ]" + re.escape(kw) + r"$", base)
        if m:
            return base[:m.start()], role
    return base, None


GENERIC_QUALIFIERS = {"raw", "acescg", "aces2065", "linear", "srgb", "scrgb"}


def _parse_stem(stem, role_map):
    """Имя файла (без расширения) → (ключ ассета, роль, тайл UDIM, is_dx,
    слой, под-имя). Порядок распознавания роли:
    1) хвостовой суффикс — 'Ассет_Роль.ext' (классика);
    2) слой: 'Ассет_Роль_2' (оверлей), цифра съедается только при валидной роли;
    3) роль-токен в середине — производственный нейминг 'asset.role_qual.tile':
       'mi24.basecolor_acescg.1001' → ключ 'mi24', роль basecolor, под-имя None;
       'mi24.mask_dirt01_raw.1001' → роль mask, под-имя 'dirt01'."""
    low = stem.lower()
    m = UDIM_RE.match(low)
    if m:
        base = m.group(1)
        tile = int(m.group(2))
    else:
        base = low
        tile = None
    is_dx = False
    tokens = re.split(r"[._\- ]+", base)
    if tokens and tokens[-1] in DX_TOKENS:
        is_dx = True
        base = re.sub(r"[._\- ]" + re.escape(tokens[-1]) + r"$", "", base)
    key, role = _match_role(base, role_map)
    layer = None
    sub = None
    if role is None:
        m2 = re.match(r"^(.+)[._\- ](\d{1,2})$", base)
        if m2:
            key2, role2 = _match_role(m2.group(1), role_map)
            if role2 is not None:
                key, role, layer = key2, role2, int(m2.group(2))
    if role is None:
        token_map = {kw: r for kw, r in role_map}
        parts = [t for t in re.split(r"[._\- ]+", base) if t]
        for i in range(len(parts) - 1, 0, -1):
            r2 = token_map.get(parts[i])
            if r2 is not None:
                key = "_".join(parts[:i])
                role = r2
                sub = "_".join(t for t in parts[i + 1:]
                               if t not in GENERIC_QUALIFIERS) or None
                break
    if role is None:
        return base, None, tile, is_dx, layer, sub
    return key, role, tile, is_dx, layer, sub


def _object_names(ob):
    """Все имена, по которым объект может совпасть с ключом ассета."""
    names = {_norm(ob.name)}
    if ob.data is not None:
        names.add(_norm(_strip_num_suffix(ob.data.name)))
        mats = getattr(ob.data, "materials", None)
        if mats:
            for slot in mats:
                if slot:
                    names.add(_norm(_strip_num_suffix(slot.name)))
    return names


# ──────────────────────────────────────────────
# Helpers: скан источников
# ──────────────────────────────────────────────

def _scan_folder(folder, role_map):
    """Папка → {ключ: {роль: {"paths": {0|1001..: ("path", путь)}, "dx": bool}}, "roleless": [...]}}"""
    groups = {}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        stem, ext = os.path.splitext(name)
        if ext.lower() not in IMG_EXT:
            continue
        key, role, tile, is_dx, layer, sub = _parse_stem(stem, role_map)
        g = groups.setdefault(key, {})
        if role is None:
            g.setdefault("roleless", []).append(name)
            continue
        if role == "mask" and sub:
            rk = f"mask#{sub}"
        elif not layer or layer == 1:
            rk = role
        else:
            rk = f"{role}#{layer}"
        entry = g.setdefault(rk, {"paths": {}})
        if is_dx:
            entry["dx"] = True
        entry["paths"][tile if tile else 0] = ("path", path)
    return groups


def _scan_blend(role_map):
    """Уже загруженные в файл изображения → та же структура групп."""
    groups = {}
    for img in bpy.data.images:
        if img.source not in {'FILE', 'TILED'}:
            continue
        if img.source == 'FILE' and not img.filepath.strip():
            continue
        stem = _strip_num_suffix(os.path.splitext(img.name)[0])
        key, role, tile, is_dx, layer, sub = _parse_stem(stem, role_map)
        g = groups.setdefault(key, {})
        if role is None:
            g.setdefault("roleless", []).append(img.name)
            continue
        if role == "mask" and sub:
            rk = f"mask#{sub}"
        elif not layer or layer == 1:
            rk = role
        else:
            rk = f"{role}#{layer}"
        entry = g.setdefault(rk, {"paths": {}})
        if is_dx:
            entry["dx"] = True
        entry["paths"][tile if tile else 0] = ("image", img)
    return groups


def _load_role_image(entry):
    """Загрузить/найти image для роли. UDIM-последовательность (2+ тайла) → TILED."""
    paths = entry["paths"]
    # Источник — уже существующий датаблок (Connect from Blend)
    for v in paths.values():
        if v[0] == "image":
            return v[1]
    tiles = sorted(t for t in paths if t != 0)
    if len(tiles) >= 2:
        first = paths[tiles[0]][1]
        img = bpy.data.images.load(first, check_existing=True)
        stem, ext = os.path.splitext(os.path.basename(first))
        m = UDIM_RE.match(stem.lower())
        base_stem = m.group(1) if m else stem
        img.source = 'TILED'
        img.filepath = os.path.join(os.path.dirname(first),
                                    base_stem + ".<UDIM>" + ext)
        have = {t.number for t in img.tiles}
        for t in tiles:
            if t not in have:
                try:
                    img.tiles.new(number=t)
                except RuntimeError:
                    pass
        return img
    v = paths.get(0) or paths[tiles[0]]
    return bpy.data.images.load(v[1], check_existing=True)


# ──────────────────────────────────────────────
# Helpers: сборка материала
# ──────────────────────────────────────────────

def _set_colorspace(img, role):
    """Data-карты → is_data=True, как в Node Wrangler (пространство данных
    текущего OCIO-конфига, работает везде).
    Цветовые карты — явное цветовое пространство, НО только если конфиг
    назначил data/raw (вымытое албедо). Если конфиг уже дал цветовое
    пространство по file rule (EXR → acescg) — не трогаем: перезатирать
    линейный EXR в sRGB значит испортить его."""
    if role in COLOR_ROLES:
        try:
            if not img.colorspace_settings.is_data:
                return
        except (TypeError, AttributeError):
            pass
        for name in COLORSPACE_SRGB:
            try:
                img.colorspace_settings.name = name
                return
            except TypeError:
                continue
    else:
        img.colorspace_settings.is_data = True


def _find_input(node, candidates):
    """Первый существующий сокет из кандидатов (имена менялись между версиями)."""
    for name in candidates:
        if name in node.inputs:
            return node.inputs[name]
    return None


def _new_mix_multiply(nt):
    """Микс MULTIPLY: legacy ShaderNodeMixRGB или новый ShaderNodeMix (3.4+).
    Возвращает (нода, Fac, вход1, вход2, выход)."""
    mix = None
    try:
        mix = nt.nodes.new('ShaderNodeMixRGB')
    except RuntimeError:
        pass
    if mix is not None:
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Fac'].default_value = 1.0
        return (mix, mix.inputs['Fac'], mix.inputs['Color1'],
                mix.inputs['Color2'], mix.outputs['Color'])
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    fac = next(s for s in mix.inputs if s.type == 'VALUE')
    fac.default_value = 1.0
    rgba_in = [s for s in mix.inputs if s.type == 'RGBA']
    return (mix, fac, rgba_in[0], rgba_in[1],
            next(s for s in mix.outputs if s.type == 'RGBA'))


def _find_material(ob, key):
    """СУЩЕСТВУЮЩИЙ материал ассета в слотах объекта. Без создания,
    без переименования, без глобального поиска по файлу — глобальный
    фолбэк как раз и захватывал чужие слоты (кейс glass/mi24)."""
    data = ob.data
    mats = getattr(data, "materials", None)
    if mats is None:
        return None
    want = _norm(key)
    for slot in mats:
        if slot and _norm(_strip_num_suffix(slot.name)) == want:
            return slot
    return None


def _create_material(ob, key):
    """Создать материал ассета и назначить — ТОЛЬКО если у объекта нет ни
    одного материала (чужие слоты не трогаем никогда)."""
    data = ob.data
    mats = getattr(data, "materials", None)
    if mats is None:
        return None
    if any(mats):
        return None  # есть чужие материалы — не создаём и не навязываем
    mat = bpy.data.materials.new(key)
    mat.use_nodes = True
    data.materials.append(mat)
    ob.active_material = mat
    return mat


def _ensure_bsdf(nt):
    """Principled BSDF + активный Material Output."""
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'
                and n.is_active_output), None)
    if out is None:
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    if bsdf is None:
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (-300, 0)
    if out is None:
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        out.location = (100, 0)
    if not out.inputs['Surface'].is_linked:
        nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return bsdf, out


def _wire_material(nt, g, key, scene, overwrite, st):
    """Разложить карты группы g по нодам материала. Счётчики и сообщения —
    в словаре состояния st (connected/skipped/masks/errors/notes)."""
    bsdf, out = _ensure_bsdf(nt)
    base_x, base_y = bsdf.location.x, bsdf.location.y
    y_off = 0
    nm_node = None
    bc_tex = None  # tex-нода Base Color — для AO-микса

    for role in ROLE_ORDER:
        if role not in g:
            continue
        if not getattr(scene, "swudim_use_" + role, True):
            continue  # роль выключена галкой в панели
        entry = g[role]
        if role == "normal" and entry.get("dx"):
            st["notes"].append(f"{key}/Normal: DX-карта пропущена (Blender хочет GL)")
            continue
        if role == "ao" and bc_tex is None:
            st["notes"].append(f"{key}/AO: нет Base Color — не с чем умножать")
            continue
        if role == "displacement":
            tgt = out.inputs['Displacement'] if out else None
        else:
            tgt = _find_input(bsdf, SOCKET_CANDIDATES[role])
        if tgt is None:
            st["notes"].append(f"{key}/{ROLE_LABELS[role]}: сокет не найден "
                               f"в этой версии Blender")
            continue
        if role == "ao":
            # Сокет занимает наша же basecolor-текстура — микс встанет в разрыв.
            # Сравнение ПО ИМЕНИ: bpy-обёртки каждый раз новые, `is` не работает
            if tgt.is_linked and tgt.links[0].from_node.name != bc_tex.name \
                    and not overwrite:
                st["skipped"] += 1
                continue
        elif tgt.is_linked and not overwrite:
            st["skipped"] += 1
            continue
        try:
            img = _load_role_image(entry)
        except RuntimeError:
            st["errors"].append(f"{key}/{ROLE_LABELS[role]}: файл не читается")
            continue
        if img is None:
            st["errors"].append(f"{key}/{ROLE_LABELS[role]}: файл не найден")
            continue
        _set_colorspace(img, role)

        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        tex.location = (base_x - 300, base_y - y_off)
        node = tex

        if role == "ao":
            mix, fac, c1, c2, mout = _new_mix_multiply(nt)
            mix.location = (base_x - 140, base_y - y_off + 110)
            nt.links.new(bc_tex.outputs['Color'], c1)
            nt.links.new(tex.outputs['Color'], c2)
            nt.links.new(mout, tgt)
            node = mix
        elif role == "gloss":
            inv = nt.nodes.new('ShaderNodeInvert')
            inv.location = (base_x - 140, base_y - y_off + 110)
            nt.links.new(tex.outputs['Color'], inv.inputs['Color'])
            nt.links.new(inv.outputs['Color'], tgt)
            node = inv
        elif role == "emission":
            nt.links.new(tex.outputs['Color'], tgt)
            if 'Emission Strength' in bsdf.inputs and \
                    bsdf.inputs['Emission Strength'].default_value == 0:
                bsdf.inputs['Emission Strength'].default_value = 1.0
        elif role == "normal":
            nm_node = nt.nodes.new('ShaderNodeNormalMap')
            nm_node.location = (base_x - 140, base_y - y_off + 110)
            nt.links.new(tex.outputs['Color'], nm_node.inputs['Color'])
            nt.links.new(nm_node.outputs['Normal'], tgt)
            node = nm_node
        elif role == "bump":
            bump = nt.nodes.new('ShaderNodeBump')
            bump.location = (base_x - 140, base_y - y_off + 110)
            nt.links.new(tex.outputs['Color'], bump.inputs['Height'])
            if nm_node is not None and overwrite:
                nt.links.new(nm_node.outputs['Normal'],
                             bump.inputs['Normal'])
            nt.links.new(bump.outputs['Normal'], tgt)
            node = bump
        elif role == "displacement":
            disp = nt.nodes.new('ShaderNodeDisplacement')
            disp.location = (base_x - 140, base_y - y_off + 110)
            nt.links.new(tex.outputs['Color'], disp.inputs['Height'])
            nt.links.new(disp.outputs['Displacement'], tgt)
            node = disp
        else:
            nt.links.new(tex.outputs['Color'], tgt)

        if role == "basecolor":
            bc_tex = tex
            # Оверлей по маске: Mix(C1=basecolor, C2=basecolor_2 или
            # константа, Fac=mask) → Base Color
            use_mask = getattr(scene, "swudim_use_mask", True)
            mask_entry = (g.get("mask") or g.get("mask#2")) \
                if use_mask else None
            o_entry = g.get("basecolor#2")
            if mask_entry is None and o_entry is not None:
                if not use_mask:
                    st["notes"].append(f"{key}: basecolor_2 есть, но маски "
                                       f"выключены галкой — не подключен")
                else:
                    st["notes"].append(f"{key}: basecolor_2 без mask — "
                                       f"не подключен")
            if mask_entry is not None:
                try:
                    m_img = _load_role_image(mask_entry)
                except RuntimeError:
                    m_img = None
                    st["errors"].append(f"{key}/Mask: файл не читается")
                if m_img is not None:
                    _set_colorspace(m_img, "mask")
                    m_tex = nt.nodes.new('ShaderNodeTexImage')
                    m_tex.image = m_img
                    m_tex.location = (base_x - 300, base_y - y_off)
                    o_tex = None
                    if o_entry is not None:
                        try:
                            o_img = _load_role_image(o_entry)
                        except RuntimeError:
                            o_img = None
                            st["errors"].append(f"{key}/basecolor_2: файл не читается")
                        if o_img is not None:
                            _set_colorspace(o_img, "basecolor")
                            o_tex = nt.nodes.new('ShaderNodeTexImage')
                            o_tex.image = o_img
                            o_tex.location = (base_x - 300,
                                              base_y - y_off + 220)
                    mix, fac, c1, c2, mout = _new_mix_multiply(nt)
                    mix.location = (base_x - 140, base_y - y_off + 110)
                    mix.label = "Overlay"
                    nt.links.new(bc_tex.outputs['Color'], c1)
                    if o_tex is not None:
                        nt.links.new(o_tex.outputs['Color'], c2)
                    else:
                        c2.default_value = (1.0, 1.0, 1.0, 1.0)
                    nt.links.new(m_tex.outputs['Color'], fac)
                    nt.links.new(mout, tgt)
                    y_off += 220
                    st["connected"] += 1 + (1 if o_tex is not None else 0)
        y_off += 220
        st["connected"] += 1

    # Маски (mask#имя): производственные сеты (Mari/Substance camo) несут
    # десятки именованных масок — грузим UDIM-наборы, вставляем ноды с
    # подписями БЕЗ связей: камуфляжную разводку художник делает руками
    if getattr(scene, "swudim_use_mask", True):
        mask_keys = sorted(k for k in g if k.startswith("mask#"))
        if mask_keys:
            # идемпотентность: маска с такой подписью уже вставлена — не дублируем
            placed = {n.label for n in nt.nodes
                      if n.type == 'TEX_IMAGE'
                      and (n.label or "").startswith("mask_")}
            m_y = base_y - y_off - 320
            for mk in mask_keys:
                sub_name = mk.split("#", 1)[1]
                if f"mask_{sub_name}" in placed:
                    continue
                m_entry = g[mk]
                if m_entry.get("dx"):
                    continue
                try:
                    m_img = _load_role_image(m_entry)
                except RuntimeError:
                    st["errors"].append(f"{key}/mask_{sub_name}: файл не читается")
                    continue
                _set_colorspace(m_img, "mask")
                mnode = nt.nodes.new('ShaderNodeTexImage')
                mnode.image = m_img
                mnode.label = f"mask_{sub_name}"
                mnode.location = (base_x - 300, m_y)
                m_y -= 220
                st["masks"] += 1


def _connect_groups(context, groups):
    """Подключить группы текстур к существующим материалам ассета.

    Правила пайплайна: существующие материалы — приоритет; чужие слоты
    и назначения не трогаем никогда; новый материал создаётся только на
    объекте вообще без материалов."""
    scene = context.scene
    overwrite = getattr(scene, "swudim_overwrite", False)
    vl = context.view_layer
    objs = list(vl.objects.selected)
    if not objs and vl.objects.active:
        objs = [vl.objects.active]

    st = {"connected": 0, "skipped": 0, "masks": 0, "errors": [],
          "notes": [], "mats": set(), "unmatched": [], "roleless": {}}

    only_mat = None
    if getattr(scene, "swudim_target", "ALL") == "ACTIVE":
        # «только выбранный»: материал открытый в шейдер-редакторе,
        # либо активный материал активного объекта
        only_mat = getattr(context, "material", None)
        if only_mat is None:
            ob_act = context.view_layer.objects.active
            if ob_act is not None:
                only_mat = ob_act.active_material
        if only_mat is None:
            st["notes"].append("Активный материал не найден — "
                               "подключаю по именам объектов")

    role_keys = [k for k in groups
                 if any(r in groups[k] for r in ROLE_ORDER)
                 or any(kk.startswith("mask#") for kk in groups[k])]
    single_asset = bool(objs) and len({_norm(k) for k in role_keys}) == 1
    fallback_noted = False

    for key in sorted(groups):
        g = groups[key]
        if g.get("roleless"):
            st["roleless"][key] = g["roleless"]
        if not any(r in g for r in ROLE_ORDER) and \
                not any(kk.startswith("mask#") for kk in g):
            continue  # только файлы без роли — не кандидат на подключение

        # Собираем материалы-цели группы. only_mat → один материал;
        # иначе: объекты с совпавшим именем, при фолбэке одного ассета —
        # все выделенные (каждый по своим правилам, чужие не трогаем).
        if only_mat is not None:
            target_mats = [only_mat]
        else:
            nkey = _norm(key)
            matched = [ob for ob in objs
                       if ob.data is not None and nkey in _object_names(ob)]
            pool = matched
            if not pool and single_asset:
                pool = list(objs)
                if not fallback_noted:
                    st["notes"].append(
                        f"'{key}': имя ассета не совпало с объектами — "
                        f"применяю ко всем выделенным (чужие материалы "
                        f"не трогаю)")
                    fallback_noted = True
            if not pool:
                st["unmatched"].append(key)
                continue
            target_mats = []
            for ob in pool:
                mat = _find_material(ob, key)
                if mat is not None:
                    # его же материал — можно показать активным
                    if ob.active_material != mat:
                        ob.active_material = mat
                else:
                    mat = _create_material(ob, key)
                    if mat is None:
                        others = [m.name for m in ob.data.materials if m]
                        st["notes"].append(
                            f"'{key}': у '{ob.name}' уже есть материалы "
                            f"({', '.join(others[:2])}) — не трогаю; "
                            f"подключите через режим 'Только выбранный'")
                        continue
                    st["notes"].append(f"'{key}': создан материал для "
                                       f"'{ob.name}' (материалов не было)")
                if mat not in target_mats:
                    target_mats.append(mat)
            if not target_mats:
                continue

        for mat in target_mats:
            if mat.name in st["mats"]:
                continue  # материал общий для нескольких объектов — один проход
            st["mats"].add(mat.name)
            _wire_material(mat.node_tree, g, key, scene, overwrite, st)

    return {
        "connected": st["connected"],
        "skipped": st["skipped"],
        "masks": st["masks"],
        "errors": st["errors"],
        "notes": st["notes"],
        "mats": sorted(st["mats"]),
        "unmatched": st["unmatched"],
        "roleless": st["roleless"],
    }


def _popup(context, draw, title, icon):
    """Попап только в GUI: в background (-b) context.window есть (фейковое
    окно), но popup_menu роняет Blender — выводим только в консоль."""
    if context.window is None or bpy.app.background:
        return
    context.window_manager.popup_menu(draw, title=title, icon=icon)


def _show_results(context, res, title):
    lines = [f"Подключено карт: {res['connected']}",
             f"Материалов затронуто: {len(res['mats'])}"]
    if res.get("masks"):
        lines.append(f"Масок вставлено без связей (ручная разводка): "
                     f"{res['masks']}")
    if res["skipped"]:
        lines.append(f"Пропущено (сокет уже занят): {res['skipped']}")
    if res["errors"]:
        lines.append("Ошибки: " + "; ".join(res["errors"][:4]))
    if res["notes"]:
        lines.append("Заметки: " + "; ".join(res["notes"][:4]))
    if res["unmatched"]:
        u = res["unmatched"]
        lines.append("Нет совпадения по имени: "
                     + ", ".join(u[:5]) + (" ..." if len(u) > 5 else ""))
    if res["roleless"]:
        r = [n for files in res["roleless"].values() for n in files]
        lines.append("Файлы без распознанной роли: "
                     + ", ".join(r[:5]) + (" ..." if len(r) > 5 else ""))
    if not res["connected"] and not res["skipped"]:
        lines.append("Ничего не подключено")

    def draw_popup(self, context):
        for l in lines:
            self.layout.label(text=l)

    _popup(context, draw_popup, title, 'CHECKMARK')
    for l in lines:
        print(f"[Switch UDIM] {l}")


# ──────────────────────────────────────────────
# Helpers: выделенные ноды
# ──────────────────────────────────────────────

def _selected_node_images(context):
    """Image-датаблоки выделенных TEX_IMAGE нод текущего шейдер-графа."""
    sd = getattr(context, "space_data", None)
    tree = getattr(sd, "edit_tree", None) if sd is not None else None
    if tree is None or getattr(tree, "type", "") != 'SHADER':
        return []
    seen = set()
    for n in tree.nodes:
        if n.select and n.type == 'TEX_IMAGE' and n.image:
            seen.add(n.image.name)
    return list(seen)


def _all_node_images():
    seen = set()
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                seen.add(node.image.name)
    return list(seen)


# ──────────────────────────────────────────────
# Operators: переключение (выделенные или все)
# ──────────────────────────────────────────────

class SWITCH_OT_to_udim(bpy.types.Operator):
    """Выделенные Image Texture (или все, если ничего не выделено) → UDIM Tiles"""
    bl_idname = "texture.switch_to_udim"
    bl_label = "Single → UDIM"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sel = _selected_node_images(context)
        imgs = sel if sel else _all_node_images()
        scope = "по выделению" if sel else "весь файл"
        switched = skipped = 0
        for name in imgs:
            img = bpy.data.images.get(name)
            if img is None:
                continue
            if img.source == 'FILE':
                img.source = 'TILED'
                switched += 1
            elif img.source == 'TILED':
                skipped += 1
        self.report({'INFO'},
                    f"Single→UDIM [{scope}]: {switched} switched, {skipped} skipped")
        return {'FINISHED'}


class SWITCH_OT_to_single(bpy.types.Operator):
    """Выделенные Image Texture (или все, если ничего не выделено) → Single Image"""
    bl_idname = "texture.switch_to_single"
    bl_label = "UDIM → Single"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sel = _selected_node_images(context)
        imgs = sel if sel else _all_node_images()
        scope = "по выделению" if sel else "весь файл"
        switched = skipped = 0
        for name in imgs:
            img = bpy.data.images.get(name)
            if img is None:
                continue
            if img.source == 'TILED':
                img.source = 'FILE'
                switched += 1
            elif img.source == 'FILE':
                skipped += 1
        self.report({'INFO'},
                    f"UDIM→Single [{scope}]: {switched} switched, {skipped} skipped")
        return {'FINISHED'}


class SWITCH_OT_udim_stats(bpy.types.Operator):
    """Показать статистику по UDIM текстурам в сцене"""
    bl_idname = "texture.udim_stats"
    bl_label = "UDIM Stats"
    bl_options = {'REGISTER'}

    def execute(self, context):
        images = bpy.data.images

        udim_imgs = [img for img in images if img.source == 'TILED']
        single_imgs = [img for img in images if img.source == 'FILE']
        total_imgs = len(udim_imgs) + len(single_imgs)

        total_tiles = 0
        total_size = 0
        missing_files = 0

        for img in udim_imgs:
            total_tiles += len(img.tiles)
            filepath = bpy.path.abspath(img.filepath)
            if filepath and os.path.isfile(filepath):
                total_size += os.path.getsize(filepath)
            else:
                missing_files += 1

        for img in single_imgs:
            filepath = bpy.path.abspath(img.filepath)
            if filepath and os.path.isfile(filepath):
                total_size += os.path.getsize(filepath)

        # Форматирование размера
        if total_size > 1073741824:
            size_str = f"{total_size / 1073741824:.1f} GB"
        elif total_size > 1048576:
            size_str = f"{total_size / 1048576:.1f} MB"
        elif total_size > 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        else:
            size_str = f"{total_size} B"

        def draw_message(self, context):
            layout = self.layout
            layout.label(text=f"Всего текстур: {total_imgs}", icon='IMAGE_DATA')
            layout.label(text=f"  UDIM Tiles: {len(udim_imgs)}")
            layout.label(text=f"  Single Image: {len(single_imgs)}")
            layout.separator()
            layout.label(text=f"UDIM тайлов: {total_tiles}", icon='MESH_GRID')
            layout.label(text=f"Размер на диске: {size_str}", icon='FILE_FOLDER')
            if missing_files:
                layout.separator()
                layout.label(text=f"Пропущено файлов: {missing_files}", icon='ERROR')

        _popup(context, draw_message, "UDIM Stats", 'INFO')

        print(f"=== UDIM Stats ===")
        print(f"Total images: {total_imgs}")
        print(f"  UDIM Tiles: {len(udim_imgs)} ({total_tiles} tiles)")
        print(f"  Single Image: {len(single_imgs)}")
        print(f"Disk size: {size_str}")
        if missing_files:
            print(f"Missing files: {missing_files}")

        return {'FINISHED'}


# ──────────────────────────────────────────────
# Reload Changed — перезагрузка изменившихся карт
# ──────────────────────────────────────────────

_SNAP_NAME = "switch_udim_filesnap.json"
_filesnap = None  # {abs_path: [mtime_ns, size]}


def _snap_path():
    return os.path.join(tempfile.gettempdir(), _SNAP_NAME)


def _load_filesnap():
    global _filesnap
    if _filesnap is None:
        try:
            with open(_snap_path(), "r", encoding="utf-8") as f:
                _filesnap = json.load(f)
            if not isinstance(_filesnap, dict):
                _filesnap = {}
        except (OSError, ValueError):
            _filesnap = {}
    return _filesnap


def _save_filesnap():
    global _filesnap
    if _filesnap is None:
        return
    try:
        with open(_snap_path(), "w", encoding="utf-8") as f:
            json.dump(_filesnap, f)
    except OSError:
        pass


def _image_files(img):
    """Абсолютные пути файлов изображения (для UDIM — все тайлы)."""
    paths = []
    if img.source == 'TILED':
        for t in img.tiles:
            fp = getattr(t, "filepath", "")
            if not fp:
                fp = img.filepath.replace("<UDIM>", str(t.number))
            if fp:
                paths.append(bpy.path.abspath(fp))
    else:
        if img.filepath:
            paths.append(bpy.path.abspath(img.filepath))
    return paths


def _file_sig(path):
    try:
        st = os.stat(path)
        return [st.st_mtime_ns, st.st_size]
    except OSError:
        return None


def _auto_snapshot(_=None):
    """Базовый снимок: дописывает только новые пути, существенные записи
    не трогает — правки между сессиями остаются детектируемыми."""
    try:
        images = bpy.data.images
    except AttributeError:
        return  # restricted-контекст enable/disable — снимок придёт из load_post/таймера
    snap = _load_filesnap()
    for img in images:
        if img.source not in {'FILE', 'TILED'}:
            continue
        for p in _image_files(img):
            if p not in snap:
                sig = _file_sig(p)
                if sig is not None:
                    snap[p] = sig
    _save_filesnap()


def _reload_changed():
    """Перезагрузить изображения, чьи файлы изменились на диске."""
    snap = _load_filesnap()
    first_run = not snap
    reloaded = []
    unchanged = 0
    missing = 0
    for img in bpy.data.images:
        if img.source not in {'FILE', 'TILED'}:
            continue
        paths = _image_files(img)
        if not paths:
            continue
        changed = False
        for p in paths:
            sig = _file_sig(p)
            if sig is None:
                missing += 1
                continue
            old = snap.get(p)
            if old is None:
                snap[p] = sig  # впервые видим — база, не reload
            elif old != sig:
                changed = True
                snap[p] = sig
        if changed:
            try:
                img.reload()
                reloaded.append(img.name)
            except RuntimeError:
                pass
        else:
            unchanged += 1
    _save_filesnap()
    return {"reloaded": reloaded, "unchanged": unchanged,
            "missing": missing, "first_run": first_run}


def _show_reload_results(context, res):
    lines = []
    if res["reloaded"]:
        lines.append(f"Перезагружено карт: {len(res['reloaded'])}")
        for n in res["reloaded"][:6]:
            lines.append(f"  {n}")
        if len(res["reloaded"]) > 6:
            lines.append(f"  ... и ещё {len(res['reloaded']) - 6}")
    else:
        lines.append("Изменённых карт нет")
    lines.append(f"Без изменений: {res['unchanged']}")
    if res["missing"]:
        lines.append(f"Файлов не хватает: {res['missing']}")
    if res["first_run"]:
        lines.append("Первый прогон: база зафиксирована")

    def draw_popup(self, context):
        for l in lines:
            self.layout.label(text=l)

    _popup(context, draw_popup, "Reload Changed", 'FILE_REFRESH')
    for l in lines:
        print(f"[Switch UDIM] {l}")


# ──────────────────────────────────────────────
# Operators: автоподключение к Principled BSDF
# ──────────────────────────────────────────────

class SWITCH_OT_connect_folder(bpy.types.Operator):
    """Подключить текстуры из папки (поле «Папка текстур» выше) к Principled BSDF по неймингу ассета"""
    bl_idname = "texture.connect_folder"
    bl_label = "Connect"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(subtype='DIR_PATH', name="Folder")

    @classmethod
    def poll(cls, context):
        vl = context.view_layer
        return bool(vl.objects.active or vl.objects.selected)

    def invoke(self, context, event):
        # папка уже указана в панели — подключаем сразу, без файл-браузера
        if (context.scene.swudim_folder or "").strip():
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        folder = (self.filepath or "").strip() or \
                 (context.scene.swudim_folder or "").strip()
        if not folder:
            self.report({'ERROR'}, "Укажите папку с текстурами (поле выше)")
            return {'CANCELLED'}
        folder = bpy.path.abspath(folder)
        if not os.path.isdir(folder):
            self.report({'ERROR'}, f"Папка не найдена: {folder}")
            return {'CANCELLED'}
        # запоминаем — дальше Connect работает в одно нажатие
        context.scene.swudim_folder = folder
        groups = _scan_folder(folder, _role_map())
        if not groups:
            self.report({'WARNING'}, "В папке нет изображений")
            return {'CANCELLED'}
        res = _connect_groups(context, groups)
        _show_results(context, res, "Connect from Folder")
        return {'FINISHED'}


class SWITCH_OT_connect_blend(bpy.types.Operator):
    """Подключить уже загруженные в файл изображения к Principled BSDF по неймингу ассета"""
    bl_idname = "texture.connect_blend"
    bl_label = "Connect Blend Images"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        vl = context.view_layer
        return bool(vl.objects.active or vl.objects.selected)

    def execute(self, context):
        groups = _scan_blend(_role_map())
        if not groups:
            self.report({'WARNING'}, "В файле нет подходящих изображений")
            return {'CANCELLED'}
        res = _connect_groups(context, groups)
        _show_results(context, res, "Connect Blend Images")
        return {'FINISHED'}


class SWITCH_OT_reload_changed(bpy.types.Operator):
    """Перезагрузить текстуры, чьи файлы изменились на диске (UDIM проверяется по тайлам)"""
    bl_idname = "texture.reload_changed"
    bl_label = "Reload Changed"
    bl_options = {'REGISTER'}

    def execute(self, context):
        res = _reload_changed()
        _show_reload_results(context, res)
        return {'FINISHED'}


class SWITCH_OT_copy_image_settings(bpy.types.Operator):
    """Настройки активной текстурной ноды (colorspace, интерполяция, extension, projection) → выделенным текстурным нодам"""
    bl_idname = "texture.copy_image_settings"
    bl_label = "Copy Image Settings"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        sd = getattr(context, "space_data", None)
        tree = getattr(sd, "edit_tree", None) if sd is not None else None
        if tree is None or getattr(tree, "type", "") != 'SHADER':
            return False
        active = tree.nodes.active if tree.nodes else None
        return active is not None and active.type == 'TEX_IMAGE'

    def execute(self, context):
        tree = context.space_data.edit_tree
        src = tree.nodes.active
        count = 0
        for n in tree.nodes:
            if n.name == src.name or not n.select or n.type != 'TEX_IMAGE':
                continue
            n.interpolation = src.interpolation
            n.extension = src.extension
            n.projection = src.projection
            if src.image and n.image:
                s_cs = src.image.colorspace_settings
                d_cs = n.image.colorspace_settings
                try:
                    d_cs.is_data = s_cs.is_data
                except TypeError:
                    pass
                try:
                    d_cs.name = s_cs.name
                except TypeError:
                    pass
            count += 1
        self.report({'INFO'}, f"Скопировано в {count} нод(ы)")
        return {'FINISHED'}


# ──────────────────────────────────────────────
# Preferences
# ──────────────────────────────────────────────

class SWITCH_Prefs(bpy.types.AddonPreferences):
    bl_idname = __name__

    kw_basecolor: StringProperty(name="Base Color",
                                 description="Суффиксы Base Color карты через запятую",
                                 default=DEFAULT_KEYWORDS["basecolor"])
    kw_ao: StringProperty(name="AO",
                          description="Суффиксы AO карты через запятую (умножается на Base Color)",
                          default=DEFAULT_KEYWORDS["ao"])
    kw_emission: StringProperty(name="Emission",
                                description="Суффиксы Emission карты через запятую",
                                default=DEFAULT_KEYWORDS["emission"])
    kw_roughness: StringProperty(name="Roughness",
                                 description="Суффиксы Roughness карты через запятую",
                                 default=DEFAULT_KEYWORDS["roughness"])
    kw_gloss: StringProperty(name="Gloss",
                             description="Суффиксы Gloss карты через запятую (инвертируется в Roughness)",
                             default=DEFAULT_KEYWORDS["gloss"])
    kw_metallic: StringProperty(name="Metallic",
                                description="Суффиксы Metallic карты через запятую",
                                default=DEFAULT_KEYWORDS["metallic"])
    kw_specular: StringProperty(name="Specular",
                                description="Суффиксы Specular карты через запятую",
                                default=DEFAULT_KEYWORDS["specular"])
    kw_transmission: StringProperty(name="Transmission",
                                    description="Суффиксы Transmission карты через запятую",
                                    default=DEFAULT_KEYWORDS["transmission"])
    kw_opacity: StringProperty(name="Opacity / Alpha",
                               description="Суффиксы альфы через запятую",
                               default=DEFAULT_KEYWORDS["opacity"])
    kw_normal: StringProperty(name="Normal",
                              description="Суффиксы Normal карты через запятую (DX-варианты пропускаются)",
                              default=DEFAULT_KEYWORDS["normal"])
    kw_bump: StringProperty(name="Bump",
                            description="Суффиксы Bump карты через запятую (через ноду Bump)",
                            default=DEFAULT_KEYWORDS["bump"])
    kw_displacement: StringProperty(name="Displacement",
                                    description="Суффиксы Displacement карты через запятую (в Material Output)",
                                    default=DEFAULT_KEYWORDS["displacement"])
    kw_mask: StringProperty(name="Mask",
                            description="Суффиксы масок через запятую (фактор микса оверлея на Base Color)",
                            default=DEFAULT_KEYWORDS["mask"])

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Суффиксы ролей в именах файлов (через запятую)",
                  icon='GREASEPENCIL')
        col = box.column(align=True)
        for role in ROLE_ALL:
            col.prop(self, "kw_" + role)
        box = layout.box()
        box.label(text="Формат: ИмяАссета_Суффикс.ext", icon='FILE_FOLDER')
        box.label(text="UDIM: ИмяАссета_Суффикс.1001.ext (2+ тайла → TILED)")
        box.label(text="Имя ассета = имя объекта/меши/материала")


# ──────────────────────────────────────────────
# Panel
# ──────────────────────────────────────────────

class SWITCH_PT_udim_panel(bpy.types.Panel):
    """Панель в N-меню Shader Editor"""
    bl_label = "UDIM Switch"
    bl_idname = "SWITCH_PT_udim_panel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "UDIM"

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'ShaderNodeTree'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("texture.switch_to_udim", icon='FORWARD')
        col.operator("texture.switch_to_single", icon='BACK')
        layout.separator()
        col = layout.column(align=True)
        col.operator("texture.udim_stats", icon='INFO')
        col.operator("texture.reload_changed", icon='FILE_REFRESH')

        layout.separator()
        head = layout.column(align=True)
        head.label(text="Auto Connect:", icon='NODE_TEXTURE')
        col = layout.column(align=True)
        col.prop(context.scene, "swudim_folder", text="")
        col.prop(context.scene, "swudim_target", text="")
        col.prop(context.scene, "swudim_overwrite", text="Заменять связи")

        box = layout.box()
        box.label(text="Карты к подключению:", icon='TEXTURE')
        # UILayout.grid в Blender 5.2 нет — две колонки через row/column
        row = box.row(align=True)
        col_l = row.column(align=True)
        col_r = row.column(align=True)
        half = (len(PANEL_ROLE_ORDER) + 1) // 2
        for i, role in enumerate(PANEL_ROLE_ORDER):
            col = col_l if i < half else col_r
            col.prop(context.scene, "swudim_use_" + role,
                     text=ROLE_LABELS[role])

        col = layout.column(align=True)
        col.operator("texture.connect_folder", icon='LINKED')
        col.operator("texture.connect_blend", icon='IMAGE_DATA')

        layout.separator()
        layout.operator("texture.copy_image_settings", icon='COPYDOWN')


# ──────────────────────────────────────────────
# Register
# ──────────────────────────────────────────────

classes = (
    SWITCH_OT_to_udim,
    SWITCH_OT_to_single,
    SWITCH_OT_udim_stats,
    SWITCH_OT_connect_folder,
    SWITCH_OT_connect_blend,
    SWITCH_OT_reload_changed,
    SWITCH_OT_copy_image_settings,
    SWITCH_Prefs,
    SWITCH_PT_udim_panel,
)


def register():
    # версия в заголовке панели — ПОСЛЕ названия (как у STUKACH);
    # bl_label читается при register_class, патчим атрибут заранее
    SWITCH_PT_udim_panel.bl_label = ("UDIM Switch v"
                                     + ".".join(str(x) for x in _VERSION))
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.swudim_overwrite = BoolProperty(
        name="Заменять связи",
        description="Переподключать сокеты, где уже есть связь",
        default=False,
    )
    bpy.types.Scene.swudim_folder = StringProperty(
        name="Папка текстур",
        description="Папка с текстурами для Auto Connect — запоминается, "
                    "Connect работает в одно нажатие",
        subtype='DIR_PATH',
        default="",
    )
    for role in PANEL_ROLE_ORDER:
        setattr(bpy.types.Scene, "swudim_use_" + role, BoolProperty(
            name=ROLE_LABELS[role],
            description="Подключать эту карту при Auto Connect",
            default=(role != "mask"),
        ))
    bpy.types.Scene.swudim_target = EnumProperty(
        name="Куда",
        description="Цель подключения карт",
        items=(
            ("ALL", "Все материалы ассета",
             "Материалы объектов, подобранных по имени ассета "
             "(+ активный объект при фолбэке)"),
            ("ACTIVE", "Только выбранный материал",
             "Материал, открытый в шейдер-редакторе, либо активный "
             "материал активного объекта"),
        ),
        default="ALL",
    )
    bpy.app.handlers.load_post.append(_auto_snapshot)
    # register() выполняется в restricted-контексте (bpy.data закрыт) —
    # снимок откладываем в таймер
    try:
        bpy.app.timers.register(_auto_snapshot, first_interval=1.0)
    except Exception:
        pass


def unregister():
    if _auto_snapshot in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_auto_snapshot)
    try:
        if bpy.app.timers.is_registered(_auto_snapshot):
            bpy.app.timers.unregister(_auto_snapshot)
    except Exception:
        pass
    # проп мог быть снесён чужим unregister'ом (тестовые циклы, дубль-регистрации)
    if hasattr(bpy.types.Scene, "swudim_overwrite"):
        del bpy.types.Scene.swudim_overwrite
    if hasattr(bpy.types.Scene, "swudim_folder"):
        del bpy.types.Scene.swudim_folder
    for role in PANEL_ROLE_ORDER:
        if hasattr(bpy.types.Scene, "swudim_use_" + role):
            delattr(bpy.types.Scene, "swudim_use_" + role)
    if hasattr(bpy.types.Scene, "swudim_target"):
        del bpy.types.Scene.swudim_target
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
