# Switch UDIM

![Switch UDIM](cover.png)

Аддон Blender для быстрого переключения нод Image Texture между режимами **Single Image** и **UDIM Tiles**.

*English documentation: [README.md](README.md)*

![Blender](https://img.shields.io/badge/Blender-3.0%2B-orange)
![Smoke](https://github.com/abyrvalg379/Switch_UDIM/actions/workflows/smoke.yml/badge.svg)
![License](https://img.shields.io/badge/License-GPLv3-green)
![Version](https://img.shields.io/badge/Version-1.1.1-blue)

## Установка

### Blender 4.2+ (Extension)

1. Скачайте `switch_udim_extension.zip` со страницы [последнего релиза](https://github.com/abyrvalg379/Switch_UDIM/releases/latest)
2. Blender → **Edit** → **Preferences** → **Get Extensions** → **⚙** → **Install from Disk...**
3. Выберите `switch_udim_extension.zip`

### Blender 3.0–4.1 (Legacy Add-on)

1. Скачайте `switch_udim_legacy.zip` со страницы [последнего релиза](https://github.com/abyrvalg379/Switch_UDIM/releases/latest)
2. Blender → **Edit** → **Preferences** → **Add-ons** → **Install...**
3. Выберите `switch_udim_legacy.zip`
4. Включите аддон галочкой

### Из репозитория

Скопируйте папку `switch_udim` в:
- **Windows:** `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`
- **macOS:** `~/Library/Application Support/Blender/<version>/scripts/addons/`
- **Linux:** `~/.config/blender/<version>/scripts/addons/`

## Использование

Откройте **Shader Editor** → нажмите **N** → вкладка **UDIM**.

| Кнопка | Действие |
|--------|--------|
| **Single → UDIM** | Переключить выделенные ноды Image Texture (или все, если ничего не выделено) из Single Image в UDIM Tiles |
| **UDIM → Single** | Переключить выделенные ноды Image Texture (или все) из UDIM Tiles в Single Image |
| **UDIM Stats** | Статистика: количество текстур, тайлов, размер на диске, отсутствующие файлы |
| **Reload Changed** | Перезагрузить только те текстуры, чьи файлы изменились на диске (UDIM проверяется по тайлам); снимок диска переживает рестарт Blender — правки, сделанные вне Blender, подхватятся |

### Автоподключение

Сканирует папку (или уже загруженные в .blend изображения) и подключает PBR-карты к **Principled BSDF** по неймингу ассета.

- **Connect from Folder** — укажите папку с текстурами
- **Connect Blend Images** — использовать уже загруженные в файл изображения
- **Заменять связи** — переподключать сокеты, где связь уже есть
- **Copy Image Settings** — скопировать colorspace / интерполяцию / extension / projection с активной текстурной ноды на выделенные

Формат имени: `ИмяАссета_Роль.ext`, UDIM: `ИмяАссета_Роль.1001.ext` (2+ тайла → автоматом UDIM Tiles). Имя ассета должно совпадать с именем объекта, меши или материала.

| Суффикс (по умолчанию) | Куда подключается |
|--------|--------|
| basecolor, albedo, diffuse, color | Base Color (sRGB) |
| ao, occlusion | Умножается на Base Color (Non-Color) |
| emission, emissive | Emission Color (sRGB) |
| roughness | Roughness (Non-Color) |
| gloss, glossiness | Нода Invert → Roughness (Non-Color) |
| metallic | Metallic (Non-Color) |
| specular | Specular IOR Level (Non-Color) |
| transmission | Transmission Weight (Non-Color) |
| opacity, alpha | Alpha (Non-Color) |
| normal | Нода Normal Map (Non-Color); DX-нормали пропускаются с репортом |
| bump | Нода Bump → Normal (Non-Color) |
| displacement, height | Нода Displacement → Material Output (Non-Color) |
| mask, msk | Фактор микса-оверлея на Base Color (Non-Color) |

**Оверлей по маске**: `<Ассет>_mask.png` замешивает `<Ассет>_basecolor.png` с `<Ассет>_basecolor_2.png` (нода Mix Color) и подаёт в Base Color. Нет файла `basecolor_2`? В миксе будет константа-белый — покрасите оверлей руками. Нет `basecolor`? Маску не к чему применять — будет репорт.

Ключевые слова суффиксов настраиваются в **Edit → Preferences → Add-ons → Switch UDIM**. Colorspace ставится как в Node Wrangler (`is_data`) и работает и на стандартном, и на ACES OCIO-конфиге.

**Производственный нейминг** тоже распознаётся: `asset.role_kvalifikator.1001.ext` (например `mi24.basecolor_acescg.1001.exr`). Роль ищется токеном в любом месте имени, служебные квалификаторы (`raw`, `acescg`, ...) отбрасываются. Именованные маски (`mi24.mask_dirt01_raw.1001.exr` — в камуфляжных сетах их десяток) грузятся как подписанные UDIM-ноды без связей — разводку камуфляжа художник делает руками. Цветовые EXR сохраняют colorspace от file rule OCIO — линейное остаётся линейным.

## Скриншоты

<!-- TODO: добавить скриншоты панели -->

## Требования

- Blender 3.0+

## Лицензия

GNU General Public License v3.0 — см. [LICENSE](LICENSE)

## Автор

**Maksim Kovalev**


---

## 🔗 Связанные инструменты

| Инструмент | Описание |
|------|-------------|
| [STUKACH](https://github.com/abyrvalg379/STUKACH) | Пайплайн-валидатор ассетов для Blender |
| [LAMPOCHKA](https://github.com/abyrvalg379/LAMPOCHKA) | Менеджер света сцены |
| [FLOMASTER](https://github.com/abyrvalg379/FLOMASTER) | OCIO-лаунчер для DCC |
| [FILTER](https://github.com/abyrvalg379/FILTER) | Видимость/выделение по типу, имени, коллекции + массовое управление модификаторами |
| [KARUSELKA](https://github.com/abyrvalg379/karuselka) | Быстрый турнтейбл-риг: орбита или спин объекта |
