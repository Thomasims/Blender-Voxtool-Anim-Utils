import bpy
import bpy_extras
import xml.etree.ElementTree as ElementTree
import mathutils
import math

bl_info = {
	"name": "VoxTool Animation Utils",
	"description": "Utilities for importing and exporting VoxTool animation files.",
	"blender": (2, 80, 0),
	"category": "Animation",
}

class action_voxtool_settings(bpy.types.PropertyGroup):
	def item_callback(self, context):
		return [(' ','-','')] + [(a,a,'') for a in bpy.data.actions.keys()]
	idle_pose: bpy.props.EnumProperty(name="Idle Pose",
									  description="Pose for un-keyed bones",
									  items=item_callback,
									  default=None,
									  options={"ANIMATABLE"},
									  update=None,
									  get=None,
									  set=None)


class action_voxtool_import(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
	"""
	Import the armature from an animdata file in XML format
	"""
	bl_idname = "armature.voxtool_import"
	bl_label = "Import Voxtool animdata"
	bl_options = {'UNDO', 'PRESET'}

	filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})

	filename_ext = ".xml"
	filter_glob: bpy.props.StringProperty(default="*.xml", options={'HIDDEN'})
	
	def execute(self, context):
		if not self.filepath or not self.filepath.endswith(".xml"):
			return {'CANCELLED'}

		#with open(self.filepath) as file:
		#	text_curve = bpy.data.curves.new(type="FONT", name="Text")
		#	text_curve.body = ''.join(file.readlines())
		#	text_object = bpy.data.objects.new(name="Text", object_data=text_curve)
		#	bpy.context.scene.collection.objects.link(text_object)
		xml = ElementTree.parse(self.filepath)
		armature_name = xml.getroot().get('name') or 'Armature'
		armature = bpy.data.armatures.new(armature_name)
		arm_obj = bpy.data.objects.new(armature_name, armature)
		bpy.context.collection.objects.link(arm_obj)
		bpy.context.view_layer.objects.active = arm_obj
		bpy.ops.object.mode_set(mode='EDIT', toggle=False)

		bone_ref = dict()
		for bone in xml.findall('skeleton/bone'):
			pos_raw = [float(v) for v in bone.get('pos').split(' ')]
			pos = mathutils.Vector((pos_raw[0], pos_raw[1], pos_raw[2])) * 2
			rot_raw = [float(v) for v in bone.get('rot').split(' ')]
			rot = mathutils.Quaternion((rot_raw[3], rot_raw[0], rot_raw[1], rot_raw[2]))
			if bone.get('parent') == '-1':
				rot_fix = mathutils.Euler((math.radians(90),0,0))
				pos.rotate(rot_fix)
				rot.rotate(rot_fix)
				arm_obj.location = pos
				arm_obj.rotation_quaternion = rot
				arm_obj.name = bone.get('name')
				armature.name = bone.get('name')
				continue
			bonedata = armature.edit_bones.new(bone.get('name'))
			parent = bone_ref[bone.get('parent')] if bone.get('parent') in bone_ref else None
			if parent != None:
				bonedata.parent = parent[0]
				pos.rotate(parent[2])
				pos = pos + parent[1]
				rot.rotate(parent[2])
			bone_ref[bone.get('index')] = (bonedata, pos, rot)
			print(bone.get('name'), bone.get('index'), bone.get('parent'), pos, rot)
			
			bonedata.head = pos.to_tuple()
			tail = mathutils.Vector((0.1, 0.0, 0.0))
			tail.rotate(rot)
			bonedata.tail = (pos + tail).to_tuple()
		return {'FINISHED'}
	
	def invoke(self, context, event):
		if self.filepath:
			return self.execute(context)
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}


class action_voxtool_export(bpy.types.Operator):
	"""
	Export all animations to a folder
	"""
	bl_idname = "armature.voxtool_export"
	bl_label = "Export Animations"
	bl_options = {'UNDO', 'PRESET'}

	directory: bpy.props.StringProperty(name="Anim Path", options={'SKIP_SAVE'})

	filename_ext = ""

	export_reference: bpy.props.BoolProperty(
			name="Export T-Pose",
			description="Export T-Pose reference file.",
			default=True,
			)

	def draw(self, context):
		self.layout.prop(self, "export_reference")
		self.layout.prop(context.scene.voxtoolutils_settings, "idle_pose")

	def execute(self, context):
		folder = self.directory
		prop_idle = context.scene.voxtoolutils_settings.idle_pose
		idle_action = bpy.data.actions[prop_idle] if prop_idle in bpy.data.actions else None
		startframe = bpy.context.scene.frame_start
		endframe = bpy.context.scene.frame_end
		bpy.ops.object.mode_set(mode='POSE')
		bpy.context.scene.frame_current = 0
		bpy.ops.pose.select_all(action="SELECT")
		if self.export_reference:
			bpy.ops.pose.blend_with_rest(factor=1.0)
			bpy.ops.export_scene.fbx(
				filepath=folder + "_reference.fbx",
				check_existing=False,
				use_selection=True,
				object_types={'ARMATURE'},
				add_leaf_bones=False,
				bake_anim=False)
		for action in bpy.data.actions:
			if action.use_frame_range:
				bpy.context.scene.frame_start = int(action.frame_start)
				bpy.context.scene.frame_end = int(action.frame_end)
			for obj in bpy.context.selected_objects:
				if obj.type != 'ARMATURE': continue
				if idle_action != None:
					obj.pose.apply_pose_from_action(idle_action)
				if obj.animation_data:
					obj.animation_data.action = action
			bpy.ops.export_scene.fbx(
				filepath=folder + action.name + ".fbx",
				check_existing=False,
				use_selection=True,
				object_types={'ARMATURE'},
				add_leaf_bones=False,
				bake_anim=True,
				bake_anim_use_all_bones=False,
				bake_anim_use_nla_strips=False,
				bake_anim_use_all_actions=False,
				bake_anim_force_startend_keying=False,
				bake_anim_simplify_factor=0.0)
		bpy.context.scene.frame_start = startframe
		bpy.context.scene.frame_end = endframe
		return {"FINISHED"}
	
	def invoke(self, context, event):
		if self.directory:
			return self.execute(context)
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}

def menu_func_import(self, context):
    self.layout.operator(action_voxtool_import.bl_idname, text="VoxTool Animdata (.xml)")
def menu_func_export(self, context):
    self.layout.operator(action_voxtool_export.bl_idname, text="VoxTool Animations (.fbx)")

classes = (
	action_voxtool_settings,
	action_voxtool_export,
	action_voxtool_import
)

def register():
	for cls in classes:
		bpy.utils.register_class(cls)
	bpy.types.Scene.voxtoolutils_settings = bpy.props.PointerProperty(type=action_voxtool_settings)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)

if __name__ == "__main__":
	register()