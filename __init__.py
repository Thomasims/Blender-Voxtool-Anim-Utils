import bpy
import bpy_extras
import xml.etree.ElementTree as ElementTree
import mathutils
import math
import struct
import copy

bl_info = {
	"name": "VoxTool Animation Utils",
	"description": "Utilities for importing and exporting VoxTool animation files.",
	"blender": (2, 80, 0),
	"category": "Import-Export",
}

class PersistSettings(bpy.types.PropertyGroup):
	def item_callback(self, context):
		return [(' ','-','')] + [(a,a,'') for a in bpy.data.actions.keys()]
	idle_pose: bpy.props.EnumProperty(name="Idle Pose",
									  description="Pose for un-keyed bones",
									  items=item_callback,
									  default=None,
									  options={"ANIMATABLE"},
									  update=None,
									  get=None,
									  set=None) # type: ignore


def getfcurve(action, name, index, overwrite):
	if overwrite:
		fcurve = action.fcurves.find(name, index = index)
		if fcurve != None:
			fcurve.keyframe_points.clear()
			return fcurve
	return action.fcurves.new(name, index = index)

def readtransform(node, scale):
	pos_raw = [float(v) / scale for v in node.get('pos').split(' ')]
	rot_raw = [float(v) for v in node.get('rot').split(' ')]
	return (mathutils.Vector((pos_raw[0], pos_raw[1], pos_raw[2])), mathutils.Quaternion((rot_raw[3], rot_raw[0], rot_raw[1], rot_raw[2])))
class OpImportArmature(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
	"""
	Import the armature from an animdata file in XML format
	"""
	bl_idname = "armature.voxtoolutils_import"
	bl_label = "Import VoxTool animdata"
	bl_options = {'UNDO', 'PRESET'}

	filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'}) # type: ignore

	filename_ext = ".xml"
	filter_glob: bpy.props.StringProperty(default="*.xml", options={'HIDDEN'}) # type: ignore

	use_armature: bpy.props.BoolProperty(name="Import Armature", default=True)
	use_actions: bpy.props.BoolProperty(name="Import Animations", default=True)
	replace_actions: bpy.props.BoolProperty(name="Replace existing actions", default=True)
	adjust_framerate: bpy.props.BoolProperty(name="Adjust framerate to scene FPS", default=True)
	voxel_scale: bpy.props.FloatProperty(name="Voxel scale", default=0.5)
	
	def draw(self, context):
		self.layout.prop(self, "use_armature")
		self.layout.prop(self, "use_actions")
		self.layout.separator()
		self.layout.prop(self, "replace_actions")
		self.layout.prop(self, "adjust_framerate")
		self.layout.prop(self, "voxel_scale")

	def execute(self, context):
		if not self.filepath or not self.filepath.endswith(".xml"):
			return {'CANCELLED'}

		xml = ElementTree.parse(self.filepath)

		if self.use_armature:
			armature_name = xml.getroot().get('name') or 'Armature'
			armature = bpy.data.armatures.new(armature_name)
			arm_obj = bpy.data.objects.new(armature_name, armature)
			arm_obj.rotation_mode = 'QUATERNION'
			bpy.context.collection.objects.link(arm_obj)
			bpy.context.view_layer.objects.active = arm_obj
			bpy.ops.object.mode_set(mode='EDIT', toggle=False)

			bone_ref = dict()
			for bone in xml.findall('skeleton/bone'):
				(pos, rot) = readtransform(bone, self.voxel_scale)
				(axis, angle) = rot.to_axis_angle()
				mat = mathutils.Matrix.Translation(pos) @ mathutils.Matrix.Rotation(angle, 4, axis)
				if bone.get('parent') == '-1':
					arm_obj.matrix_local = mathutils.Matrix.Rotation(math.radians(90), 4, (1,0,0)) @ mat @ mathutils.Matrix.Rotation(math.radians(-90), 4, (0,0,1))
					arm_obj.name = bone.get('name')
					armature.name = bone.get('name')
					continue
				bonedata = armature.edit_bones.new(bone.get('name'))
				parent = bone_ref[bone.get('parent')] if bone.get('parent') in bone_ref else None
				if parent != None:
					bonedata.parent = parent[0]
					mat = parent[1] @ mat
				else:
					mat = mathutils.Matrix.Rotation(math.radians(90), 4, (0,0,1)) @ mat
				bone_ref[bone.get('index')] = (bonedata, mat, bone.get('name'), pos, rot.inverted())
				
				bonedata.length = 0.1
				bonedata.matrix = mat @ mathutils.Matrix.Rotation(math.radians(90), 4, (0,0,-1))
			bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

		if self.use_actions:
			bone_rot_fix = mathutils.Matrix(((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0))).to_quaternion()
			scene_framerate = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
			for anim in xml.findall('animations/animation'):
				action_name = anim.get('name')
				action = self.replace_actions and bpy.data.actions.get(action_name) or bpy.data.actions.new(action_name)
				action.use_fake_user = True
				if not self.use_armature:
					continue
				action.use_frame_range = True
				action.frame_start = 0
				action.frame_end = 0
				anim_framerate = float(anim.get('anim_rate'))
				import_framerate = self.adjust_framerate and scene_framerate or anim_framerate
				bone_offset = int(anim.get('start_bone'))
				sequences = anim.findall('sequence')
				is_looping = len(sequences) > 1 and len(sequences[0]) == len(sequences[1]) or False
				action.use_cyclic = is_looping
				for sequence in sequences:
					bone_index = str(bone_offset + int(sequence.get('bone_index')))
					if bone_index in bone_ref:
						bonename = bone_ref[bone_index][2]
						location_data_path = f'pose.bones["{bonename}"].location'
						rotation_data_path = f'pose.bones["{bonename}"].rotation_quaternion'
						bone_pos = bone_ref[bone_index][3]
						bone_rot = bone_ref[bone_index][4]
						rot_fix = mathutils.Quaternion()
					else:
						location_data_path = 'location'
						rotation_data_path = 'rotation_quaternion'
						bone_pos = mathutils.Vector((0, 0, 0))
						bone_rot = mathutils.Quaternion()
						rot_fix = bone_rot_fix
					fcurve_location_x = getfcurve(action, location_data_path, 0, self.replace_actions)
					fcurve_location_y = getfcurve(action, location_data_path, 1, self.replace_actions)
					fcurve_location_z = getfcurve(action, location_data_path, 2, self.replace_actions)
					fcurve_quat_w = getfcurve(action, rotation_data_path, 0, self.replace_actions)
					fcurve_quat_x = getfcurve(action, rotation_data_path, 1, self.replace_actions)
					fcurve_quat_y = getfcurve(action, rotation_data_path, 2, self.replace_actions)
					fcurve_quat_z = getfcurve(action, rotation_data_path, 3, self.replace_actions)
					keyframes = sequence.findall('keyframe')
					if is_looping:
						last_frame = copy.deepcopy(keyframes[0])
						last_frame.set("time", float(keyframes[len(keyframes) - 1].get("time")) + 1.0 / anim_framerate)
						keyframes.append(last_frame)
					for keyframe in keyframes:
						(pos, rot) = readtransform(keyframe, self.voxel_scale)
						pos = rot_fix @ (pos - bone_pos)
						rot = rot_fix @ (bone_rot @ rot)
						frame = float(keyframe.get('time')) * import_framerate
						if frame > action.frame_end:
							action.frame_end = frame
						fcurve_location_x.keyframe_points.insert(frame, -pos[1], options = {'FAST'}).interpolation = 'LINEAR'
						fcurve_location_y.keyframe_points.insert(frame, pos[0], options = {'FAST'}).interpolation = 'LINEAR'
						fcurve_location_z.keyframe_points.insert(frame, pos[2], options = {'FAST'}).interpolation = 'LINEAR'
						fcurve_quat_w.keyframe_points.insert(frame, rot[0], options = {'FAST'}).interpolation = 'LINEAR'
						fcurve_quat_x.keyframe_points.insert(frame, -rot[2], options = {'FAST'}).interpolation = 'LINEAR'
						fcurve_quat_y.keyframe_points.insert(frame, rot[1], options = {'FAST'}).interpolation = 'LINEAR'
						fcurve_quat_z.keyframe_points.insert(frame, rot[3], options = {'FAST'}).interpolation = 'LINEAR'


		return {'FINISHED'}
	
	def invoke(self, context, event):
		if self.filepath:
			return self.execute(context)
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}


class OpExportAnimations(bpy.types.Operator):
	"""
	Export all animations to a folder
	"""
	bl_idname = "armature.voxtoolutils_export"
	bl_label = "Export Animations"
	bl_options = {'UNDO', 'PRESET'}

	directory: bpy.props.StringProperty(name="Anim Path", options={'SKIP_SAVE'}) # type: ignore

	filename_ext = ""

	export_reference: bpy.props.BoolProperty(
			name="Export T-Pose",
			description="Export T-Pose reference file.",
			default=True,
			) # type: ignore

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
		bpy.context.scene.frame_current = startframe
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

class OpExportBonemap(bpy.types.Operator):
	"""
	Export VoxTool bonemap
	"""
	bl_idname = "armature.voxtoolutils_export_bonemap"
	bl_label = "Export VoxTool bonemap"
	bl_options = {'UNDO', 'PRESET'}

	filepath: bpy.props.StringProperty(name="Output path", options={'SKIP_SAVE'}) # type: ignore
	filename_ext = ".xml"
	filter_glob: bpy.props.StringProperty(default="*.xml", options={'HIDDEN'}) # type: ignore
	
	def execute(self, context):
		if not self.filepath:
			return {'CANCELLED'}
		
		armature = None
		for obj in bpy.context.selected_objects:
			if obj.type != 'ARMATURE': continue
			armature = obj
		if armature == None:
			return {'CANCELLED'}

		with open(self.filepath, "wt") as file:
			file.write('<bonemap global_offset="-0.5 -0.5 -0.5">\n')
			for bone in armature.data.bones:
				pos = armature.matrix_local @ bone.head_local
				file.write('<bone rig_name="{name}" name="{name}" offset="{x:.5f} {y:.5f} {z:.5f}"/>\n'.format(name=bone.name, x=pos.x*10, y=pos.y*10, z=pos.z*10))
			file.write('</bonemap>')
		
		with open(self.filepath + '.vox', "wb") as file:
			file.write(struct.pack("<4si4s2i", b"VOX ", 150, b"MAIN", 0, 0))
			file.write(struct.pack("<4s5i", b"SIZE", 12, 0, 1, 1, 1))
			file.write(struct.pack("<4s3i4B", b"XYZI", 8, 0, 1, 0, 0, 0, 1))
			file.write(struct.pack("<4s9i", b"nTRN", 28, 0, 0, 0, 1, -1, -1, 1, 0))
			file.write(struct.pack("<4s5i", b"nGRP", 12 + len(armature.data.bones) * 4, 0, 1, 0, len(armature.data.bones)))
			for i in range(0, len(armature.data.bones)):
				file.write(struct.pack("<i", i * 2 + 2))
			for i in range(0, len(armature.data.bones)):
				bone = armature.data.bones[i]
				nTRNid = i * 2 + 2
				file.write(struct.pack("<4s5i5si", b"nTRN", 41 + len(bone.name), 0, nTRNid, 1, 5, b"_name", len(bone.name)))
				file.write(str.encode(bone.name, encoding="ascii"))
				file.write(struct.pack("<5i", nTRNid + 1, -1, 0, 1, 0))
				file.write(struct.pack("<4s7i", b"nSHP", 20, 0, nTRNid + 1, 0, 1, 0, 0))
			written = file.tell()
			file.seek(16)
			file.write(struct.pack("<i", written - 20))


		return {"FINISHED"}

	def invoke(self, context, event):
		if self.filepath:
			return self.execute(context)
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}

def menu_func_import(self, context):
    self.layout.operator(OpImportArmature.bl_idname, text="VoxTool Animdata (.xml)")
def menu_func_export(self, context):
    self.layout.operator(OpExportAnimations.bl_idname, text="VoxTool Animations (.fbx)")
    self.layout.operator(OpExportBonemap.bl_idname, text="VoxTool Bonemap (.xml)")

classes = (
	PersistSettings,
	OpExportAnimations,
	OpExportBonemap,
	OpImportArmature
)

def register():
	for cls in classes:
		bpy.utils.register_class(cls)
	bpy.types.Scene.voxtoolutils_settings = bpy.props.PointerProperty(type=PersistSettings)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
	for cls in reversed(classes):
		bpy.utils.unregister_class(cls)

if __name__ == "__main__":
	register()