# Changelog

## [1.1.1] - 2026-09-27 (dev, не публиковалась — копим фичи)

### Added
- Автоподключение текстур к Principled BSDF: **Connect from Folder** (скан папки) и **Connect Blend Images** (уже загруженные изображения)
- Сопоставление по неймингу `ИмяАссета_Роль.ext`, ключевые слова настраиваются в преференсах. 12 ролей:
  - basecolor → Base Color; emission → Emission Color (+ Strength 0 → 1)
  - roughness → Roughness; gloss → нода Invert → Roughness
  - metallic → Metallic; specular → Specular IOR Level; transmission → Transmission Weight
  - ao → нода Mix (MULTIPLY) с Base Color
  - normal → нода Normal Map (DX-нормали вида `Имя_normal_dx` пропускаются с репортом)
  - bump → нода Bump → Normal; displacement/height → нода Displacement → Material Output
  - opacity/alpha → Alpha
- Автоопределение UDIM-последовательностей: `ИмяАссета_Роль.1001.ext`, 2+ тайла → TILED с прописанными тайлами
- Создание недостающих материалов и Principled BSDF
- Корректный colorspace по паттерну Node Wrangler (`is_data` для data-карт, явное цветовое пространство для basecolor/emission) — работает и на ACES OCIO-конфигах
- **Copy Image Settings**: colorspace / интерполяция / extension / projection активной текстурной ноды → выделенным
- **Reload Changed**: перезагрузка только изменившихся на диске карт (mtime+size-снимок в %TEMP%, переживает рестарт Blender; UDIM проверяется по тайлам; база дополняется автоматически при открытии файла и включении аддона)
- **Оверлей по маске**: `<Ассет>_mask.png` собирает Mix Color (C1 = basecolor, C2 = `<Ассет>_basecolor_2.png` или константа-белый, Fac = маска) → Base Color; парсинг слоя `_N` после роли (`basecolor_2`, `mask_2`), цифра съедается только если дальше идёт валидная роль
- Галочка «Заменять связи» — переподключение уже занятых сокетов (влияет и на AO-микс, и на bump-цепочку)

### Changed
- Single → UDIM / UDIM → Single работают по выделенным нодам, если они есть (иначе — весь файл, как раньше)

## [1.1.0] - 2026-07-21

### Added
- Обратный свитч: UDIM Tiles → Single Image
- UDIM Stats: статистика по текстурам, тайлам, размеру на диске
- Popup окно с результатами статистики

## [1.0.0] - 2026-07-21

### Added
- Первоначальная версия
- Переключение Single Image → UDIM Tiles
- Панель в Shader Editor (N-Panel)
