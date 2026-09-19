# Switch UDIM

Аддон Blender для быстрого переключения нод Image Texture между режимами **Single Image** и **UDIM Tiles**.

*English documentation: [README.md](README.md)*

![Blender](https://img.shields.io/badge/Blender-3.0%2B-orange)
![License](https://img.shields.io/badge/License-GPLv3-green)
![Version](https://img.shields.io/badge/Version-1.1.0-blue)

## Установка

### Blender 4.2+ (Extension)

1. Скачайте `switch_udim_extension.zip`
2. Blender → **Edit** → **Preferences** → **Get Extensions** → **⚙** → **Install from Disk...**
3. Выберите `switch_udim_extension.zip`

### Blender 3.0–4.1 (Legacy Add-on)

1. Скачайте `switch_udim_legacy.zip`
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
| **Single → UDIM** | Переключить все Image Textures из Single Image в UDIM Tiles |
| **UDIM → Single** | Переключить все Image Textures из UDIM Tiles в Single Image |
| **UDIM Stats** | Статистика: количество текстур, тайлов, размер на диске, отсутствующие файлы |

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
| [FILTER](https://github.com/abyrvalg379/FILTER) | Видимость/выделение по типу, имени, коллекции |
| [KARUSELKA](https://github.com/abyrvalg379/karuselka) | Быстрый турнтейбл-риг: орбита или спин объекта |
