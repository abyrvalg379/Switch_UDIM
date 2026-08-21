bl_info = {
    "name": "Switch UDIM",
    "author": "Maksim Kovalev",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "Shader Editor > N-Panel > UDIM",
    "description": "Переключение Image Texture между Single Image и UDIM Tiles + статистика",
    "category": "Node",
}

import bpy
import os


# ──────────────────────────────────────────────
# Operators
# ──────────────────────────────────────────────

class SWITCH_OT_to_udim(bpy.types.Operator):
    """Переключить все Image Texture с Single Image на UDIM Tiles"""
    bl_idname = "texture.switch_to_udim"
    bl_label = "Single → UDIM"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        switched = 0
        skipped = 0

        for mat in bpy.data.materials:
            if not mat.use_nodes:
                continue
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    if node.image.source == 'FILE':
                        node.image.source = 'TILED'
                        switched += 1
                    elif node.image.source == 'TILED':
                        skipped += 1

        self.report({'INFO'}, f"Single→UDIM: {switched} switched, {skipped} skipped")
        return {'FINISHED'}


class SWITCH_OT_to_single(bpy.types.Operator):
    """Переключить все Image Texture с UDIM Tiles на Single Image"""
    bl_idname = "texture.switch_to_single"
    bl_label = "UDIM → Single"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        switched = 0
        skipped = 0

        for mat in bpy.data.materials:
            if not mat.use_nodes:
                continue
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    if node.image.source == 'TILED':
                        node.image.source = 'FILE'
                        switched += 1
                    elif node.image.source == 'FILE':
                        skipped += 1

        self.report({'INFO'}, f"UDIM→Single: {switched} switched, {skipped} skipped")
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

        context.window_manager.popup_menu(draw_message, title="UDIM Stats", icon='INFO')

        print(f"=== UDIM Stats ===")
        print(f"Total images: {total_imgs}")
        print(f"  UDIM Tiles: {len(udim_imgs)} ({total_tiles} tiles)")
        print(f"  Single Image: {len(single_imgs)}")
        print(f"Disk size: {size_str}")
        if missing_files:
            print(f"Missing files: {missing_files}")

        return {'FINISHED'}


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
        layout.operator("texture.udim_stats", icon='INFO')


# ──────────────────────────────────────────────
# Register
# ──────────────────────────────────────────────

classes = (
    SWITCH_OT_to_udim,
    SWITCH_OT_to_single,
    SWITCH_OT_udim_stats,
    SWITCH_PT_udim_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
