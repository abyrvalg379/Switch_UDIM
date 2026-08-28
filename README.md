# Switch UDIM

Blender addon for quickly switching Image Texture nodes between **Single Image** and **UDIM Tiles** modes.

![Blender](https://img.shields.io/badge/Blender-3.0%2B-orange)
![License](https://img.shields.io/badge/License-GPLv3-green)
![Version](https://img.shields.io/badge/Version-1.1.0-blue)

## Installation

### Blender 4.2+ (Extension)

1. Download `switch_udim_extension.zip`
2. Blender → **Edit** → **Preferences** → **Get Extensions** → **⚙** → **Install from Disk...**
3. Select `switch_udim_extension.zip`

### Blender 3.0–4.1 (Legacy Add-on)

1. Download `switch_udim_legacy.zip`
2. Blender → **Edit** → **Preferences** → **Add-ons** → **Install...**
3. Select `switch_udim_legacy.zip`
4. Enable the addon with the checkbox

### From Repository

Copy the `switch_udim` folder to:
- **Windows:** `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`
- **macOS:** `~/Library/Application Support/Blender/<version>/scripts/addons/`
- **Linux:** `~/.config/blender/<version>/scripts/addons/`

## Usage

Open **Shader Editor** → press **N** → **UDIM** tab.

| Button | Action |
|--------|--------|
| **Single → UDIM** | Switch all Image Textures from Single Image to UDIM Tiles |
| **UDIM → Single** | Switch all Image Textures from UDIM Tiles to Single Image |
| **UDIM Stats** | Statistics: texture count, tile count, disk size, missing files |

## Screenshots

<!-- TODO: add panel screenshots -->

## Requirements

- Blender 3.0+

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE)

## Author

**Maksim Kovalev**


---

## 🔗 Related Tools

| Tool | Description |
|------|-------------|
| [STUKACH](https://github.com/abyrvalg379/STUKACH) | Pipeline asset validator for Blender |
| [LAMPOCHKA](https://github.com/abyrvalg379/LAMPOCHKA) | Scene light manager |
| [FLOMASTER](https://github.com/abyrvalg379/FLOMASTER) | OCIO launcher for DCC apps |
| [FILTER](https://github.com/abyrvalg379/FILTER) | Toggle visibility/selection by type, name, collection |
