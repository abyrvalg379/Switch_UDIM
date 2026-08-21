# Switch UDIM

Blender-аддон для быстрого переключения Image Texture нод между режимами **Single Image** и **UDIM Tiles**.

![Blender](https://img.shields.io/badge/Blender-3.0%2B-orange)
![License](https://img.shields.io/badge/License-MIT-green)
![Version](https://img.shields.io/badge/Version-1.1.0-blue)

## Установка

### Из ZIP

1. Скачайте `switch_udim.zip`
2. Blender → **Edit** → **Preferences** → **Add-ons** → **Install...**
3. Выберите `switch_udim.zip`
4. Включите аддон галочкой

### Из репозитория

Скопируйте папку `switch_udim` в:
- **Windows:** `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`
- **macOS:** `~/Library/Application Support/Blender/<version>/scripts/addons/`
- **Linux:** `~/.config/blender/<version>/scripts/addons/`

## Использование

Откройте **Shader Editor** → нажмите **N** → вкладка **UDIM**.

| Кнопка | Действие |
|--------|----------|
| **Single → UDIM** | Переключить все Image Texture с Single Image на UDIM Tiles |
| **UDIM → Single** | Переключить все Image Texture с UDIM Tiles на Single Image |
| **UDIM Stats** | Статистика: количество текстур, тайлов, размер на диске, пропущенные файлы |

## Скриншоты

<!-- TODO: добавить скриншоты панели -->

## Требования

- Blender 3.0+

## Лицензия

MIT License — см. [LICENSE](LICENSE)

## Автор

**Maksim Kovalev**
