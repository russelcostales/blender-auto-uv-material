bl_info = {
    'name': 'Auto UV Material',
    'author': 'Auto UV Material',
    'version': (1, 0, 0),
    'blender': (4, 2, 0),
    'location': 'View3D > Sidebar > Auto UV Material',
    'category': 'Material',
}

import bpy

GRID_NAME = 'Auto UV Material UV Grid'
GRID_SIZE = 1024


def get_grid():
    # Never overwrite an unrelated or externally loaded image.
    for img in bpy.data.images:
        if (img.get('materialcheck_grid') and img.source == 'GENERATED'
                and img.generated_type == 'UV_GRID'
                and tuple(img.size) == (GRID_SIZE, GRID_SIZE)):
            return img
    img = bpy.data.images.new(GRID_NAME, width=GRID_SIZE, height=GRID_SIZE,
                              alpha=False)
    img.generated_type = 'UV_GRID'
    img['materialcheck_grid'] = True
    return img


def valid_material(mat, grid):
    if not mat or not mat.use_nodes or not mat.node_tree:
        return False
    nodes = mat.node_tree.nodes
    if len(nodes) != 3:
        return False
    out = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None)
    if not out or not out.inputs['Surface'].is_linked:
        return False
    shader = out.inputs['Surface'].links[0].from_node
    if shader.type != 'BSDF_PRINCIPLED' or not shader.inputs['Base Color'].is_linked:
        return False
    link = shader.inputs['Base Color'].links[0]
    tex = link.from_node
    return (tex.type == 'TEX_IMAGE' and tex.image == grid
            and link.from_socket.name == 'Color'
            and not tex.inputs['Vector'].is_linked
            and tex.interpolation == 'Linear' and tex.projection == 'FLAT'
            and tex.extension == 'REPEAT'
            and len(mat.node_tree.links) == 2)


def configure(mat, grid):
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = grid
    tex.interpolation = 'Linear'
    tex.projection = 'FLAT'
    tex.extension = 'REPEAT'
    tex.location = (-360, 40)
    shader = nodes.new('ShaderNodeBsdfPrincipled')
    shader.location = (0, 40)
    out = nodes.new('ShaderNodeOutputMaterial')
    out.location = (340, 40)
    mat.node_tree.links.new(tex.outputs['Color'], shader.inputs['Base Color'])
    mat.node_tree.links.new(shader.outputs['BSDF'], out.inputs['Surface'])


def unique_material_name(obj):
    # If an unrelated material owns the exact name, rename only the selected
    # object, not the unrelated material or any unselected object.
    base = obj.name
    i = 1
    while bpy.data.materials.get(obj.name) is not None:
        candidate = f'{base[:48]}_{i:03d}'
        if bpy.data.objects.get(candidate) is None and bpy.data.materials.get(candidate) is None:
            obj.name = candidate
            break
        i += 1


class AUTO_UV_MATERIAL_OT_assign(bpy.types.Operator):
    bl_idname = 'auto_uv_material.assign_uv_materials'
    bl_label = 'Assign UV Materials'
    bl_description = 'Assign one uniquely named UV grid material per selected mesh'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        grid = get_grid()
        created = fixed = renamed = cleared = unchanged = skipped = deleted = 0
        old_materials = set()
        for obj in sorted(context.selected_objects, key=lambda o: o.name):
            if obj.type != 'MESH':
                continue
            if obj.library or obj.override_library:
                skipped += 1
                continue
            original = obj.name
            slots = [s.material for s in obj.material_slots]
            old_materials.update(m for m in slots if m)
            # Isolate shared mesh data so unselected objects remain untouched.
            if obj.data.users > 1 or obj.data.library:
                obj.data = obj.data.copy()
            # Reuse only a matching material that is exclusively used here.
            mat = bpy.data.materials.get(obj.name)
            local_refs = sum(1 for m in obj.data.materials if m == mat) if mat else 0
            if mat:
                local_refs += sum(1 for s in obj.material_slots if s.link == 'OBJECT' and s.material == mat)
            if not mat or mat.library or mat.override_library or mat.users > local_refs or mat.use_fake_user:
                if mat:
                    unique_material_name(obj)
                mat = bpy.data.materials.new(obj.name)
                configure(mat, grid)
                created += 1
                changed = True
            elif not valid_material(mat, grid):
                configure(mat, grid)
                fixed += 1
                changed = True
            else:
                changed = False
            if obj.name != original:
                renamed += 1
            if len(slots) != 1 or slots[0] != mat or obj.material_slots[0].link != 'DATA':
                cleared += sum(1 for m in slots if m != mat) + max(0, slots.count(mat) - 1)
                obj.data.materials.clear()
                obj.data.materials.append(mat)
                for s in obj.material_slots:
                    s.link = 'DATA'
                    s.material = mat
                changed = True
            for poly in obj.data.polygons:
                if poly.material_index != 0:
                    poly.material_index = 0
                    changed = True
            if not changed:
                unchanged += 1
        # Delete only orphaned materials removed by this operation.
        for mat in old_materials:
            if mat.users == 0 and not mat.use_fake_user and not mat.library:
                bpy.data.materials.remove(mat)
                deleted += 1
        self.report({'INFO'}, f'Auto UV Material: {created} created, {fixed} repaired, {renamed} renamed, '
                             f'{cleared} slots removed, {deleted} orphan materials deleted, '
                             f'{unchanged} unchanged, {skipped} skipped')
        return {'FINISHED'}


class AUTO_UV_MATERIAL_PT_panel(bpy.types.Panel):
    bl_label = 'Auto UV Material'
    bl_idname = 'AUTO_UV_MATERIAL_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Auto UV Material'

    def draw(self, context):
        self.layout.operator('auto_uv_material.assign_uv_materials')


def register():
    bpy.utils.register_class(AUTO_UV_MATERIAL_OT_assign)
    bpy.utils.register_class(AUTO_UV_MATERIAL_PT_panel)


def unregister():
    bpy.utils.unregister_class(AUTO_UV_MATERIAL_PT_panel)
    bpy.utils.unregister_class(AUTO_UV_MATERIAL_OT_assign)


if __name__ == '__main__':
    register()
