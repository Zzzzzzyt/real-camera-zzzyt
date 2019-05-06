# Addon Info
bl_info = {
	"name": "Real Camera",
	"description": "Physical camera controls",
	"author": "Wolf",
	"version": (3, 0),
	"blender": (2, 80, 0),
	"location": "Camera Properties",
	"wiki_url": "https://3d-wolf.com/products/camera.html",
	"tracker_url": "https://3d-wolf.com/products/camera.html",
	"support": "COMMUNITY",
	"category": "Render"
	}


# Libraries
import bpy
import bgl
import math
import os
from bpy.props import *
from bpy.types import PropertyGroup, Panel, Operator
from mathutils import Vector
from bpy.app.handlers import persistent


# Real Camera panel
class REALCAMERA_PT_Panel(Panel):
	bl_category = "Real Camera"
	bl_label = "Real Camera"
	bl_space_type = 'PROPERTIES'
	bl_region_type = "WINDOW"
	bl_context = "data"

	@classmethod
	def poll(cls, context):
		return context.camera

	def draw_header(self, context):
		settings = context.scene.camera_settings
		layout = self.layout
		layout.prop(settings, 'enabled', text='')

	def draw(self, context):
		settings = context.scene.camera_settings
		cam = context.camera
		layout = self.layout
		layout.enabled = settings.enabled

		# Exposure triangle
		layout.use_property_split = True
		layout.use_property_decorate = False
		flow = layout.grid_flow(row_major=True, columns=0, even_columns=False, even_rows=False, align=True)
		col = flow.column()
		sub = col.column(align=True)
		if context.scene.render.engine in ["BLENDER_EEVEE", "BLENDER_WORKBENCH"]:
			sub.prop(cam.gpu_dof, 'fstop', text="Aperture")
		else:
			sub.prop(cam.cycles, 'aperture_fstop', text="Aperture")
		sub.prop(settings, 'shutter_speed')

		# Mechanics
		layout.use_property_split = False
		row = layout.row()
		row.prop(settings, 'af')
		sub = row.row(align=True)
		sub.active = settings.af
		if settings.af:
			sub.prop(settings, 'af_bake', icon='PLAY', text="Bake")
			sub.prop(settings, 'af_step', text="Step")
		layout.use_property_split = True
		split = layout.split()
		col = split.column(align=True)
		if not settings.af:
			col.prop(cam, 'dof_distance', text="Focus Point")
		col.prop(cam, 'lens', text="Focal Length")


# Auto Exposure panel
class AUTOEXP_PT_Panel(Panel):
	bl_space_type = "PROPERTIES"
	bl_context = "render"
	bl_region_type = "WINDOW"
	bl_category = "Real Camera"
	bl_label = "Auto Exposure"

	def draw_header(self, context):
		settings = context.scene.camera_settings
		layout = self.layout
		layout.prop(settings, 'enable_ae', text='')

	def draw(self, context):
		settings = context.scene.camera_settings
		layout = self.layout
		layout.enabled = settings.enable_ae

		# Modes
		col = layout.column(align=True)
		row = col.row(align=True)
		row.alignment = "CENTER"
		row.label(text="Metering Mode")
		row = col.row(align=True)
		row.scale_x = 1.5
		row.scale_y = 1.5
		row.alignment = "CENTER"
		row.prop(settings, 'ae_mode', text="", expand=True)
		col.label(text="")
		# Settings
		layout.use_property_split = True
		layout.use_property_decorate = False
		flow = layout.grid_flow(row_major=True, columns=0, even_columns=False, even_rows=False, align=True)
		col = flow.column()
		col.prop(settings, 'ec', slider=True)
		


# Enable camera
def toggle_update(self, context):
	settings = context.scene.camera_settings
	if settings.enabled:
		name = context.active_object.name
		# set limits
		bpy.data.cameras[name].show_limits = True
		# change aperture to FSTOP
		bpy.data.cameras[name].cycles.aperture_type = 'FSTOP'
		# initial values Issue
		update_aperture(self, context)
		update_shutter_speed(self, context)
	else:
		# reset limits
		name = context.active_object.name
		bpy.data.cameras[name].show_limits = False
		# reset autofocus
		bpy.context.scene.camera_settings.af = False


# Update Aperture
def update_aperture(self, context):
	context.object.data.cycles.aperture_fstop = context.scene.camera_settings.aperture
# Update Shutter Speed
def update_shutter_speed(self, context):
	fps = context.scene.render.fps
	shutter = context.scene.camera_settings.shutter_speed
	motion = fps*shutter
	context.scene.render.motion_blur_shutter = motion


# Update Autofocus
def update_af(self, context):
	af = context.scene.camera_settings.af
	if af:
		name = context.active_object.name
		obj = bpy.data.objects[name]
		# ray Cast
		ray = context.scene.ray_cast(context.scene.view_layers[0], obj.location, obj.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0)))
		distance = (ray[1]-obj.location).magnitude
		bpy.data.cameras[name].dof_distance = distance
	else:
		# reset baked af
		context.scene.camera_settings.af_bake = False
		update_af_bake(self, context)


# Autofocus Bake
def update_af_bake(self, context):
	scene = bpy.context.scene
	bake = scene.camera_settings.af_bake
	start = scene.frame_start
	end = scene.frame_end
	frames = end-start+1
	steps = scene.camera_settings.af_step
	n = int(float(frames/steps))
	current_frame = scene.frame_current
	name = context.active_object.name
	cam = bpy.data.cameras[name]
	if bake:
		scene.frame_current = start
		# every step frames, place a keyframe
		for i in range(n+1):
			update_af(self, context)
			cam.keyframe_insert('dof_distance')
			scene.frame_set(scene.frame_current+steps)
		# current Frame
		scene.frame_current = current_frame
	else:
		# delete dof keyframes
		try:
			fcurves = cam.animation_data.action.fcurves
		except AttributeError:
			a=0
		else:
			for c in fcurves:
				if c.data_path.startswith("dof_distance"):
					fcurves.remove(c)


# Enable Auto Exposure
def update_ae(self, context):
	ae = context.scene.camera_settings.enable_ae
	global handle
	if ae:
		handle = bpy.types.SpaceView3D.draw_handler_add(ae_calc, (), 'WINDOW', 'PRE_VIEW')
	else:
		bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')


# Read filmic values from files
def read_filmic_values(path):
	nums = []
	with open(path) as filmic_file:
		for line in filmic_file:
			nums.append(float(line))
	return nums


# Auto Exposure algorithms
def ae_calc():
	shading = bpy.context.area.spaces.active.shading.type
	if shading=="RENDERED":
		settings = bpy.context.scene.camera_settings
		# width and height of the viewport
		viewport = bgl.Buffer(bgl.GL_INT, 4)
		bgl.glGetIntegerv(bgl.GL_VIEWPORT, viewport)
		width = viewport[2]
		height = viewport[3]
		bgl.glDisable(bgl.GL_DEPTH_TEST)
		buf = bgl.Buffer(bgl.GL_FLOAT, 3)

		# Center Spot
		if settings.ae_mode=="Center Spot":
			x = width//2
			y = height//2
			bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
			avg = luminance(buf)

		# Full Window
		if settings.ae_mode=="Full Window":
			grid = 7
			values = 0
			step = 1/(grid+1)
			for i in range (grid):
				for j in range (grid):
					x = int(step*(j+1)*width)
					y = int(step*(i+1)*height)
					bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
					lum = luminance(buf)
					values = values+lum
			avg = values/(grid*grid)

		# Center Weighted
		if settings.ae_mode=="Center Weighted":
			circles = 4
			if width>=height:
				max = width
			else:
				max = height
			half = max//2
			step = max//(circles*2+2)
			values = 0
			weights = 0
			for i in range (circles):
				x = half-(i+1)*step
				y = x
				n_steps = i*2+2
				weight = (circles-1-i)/circles
				for n in range (n_steps):
					x = x+step
					bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
					lum = luminance(buf)
					values = values+lum*weight
					weights = weights+weight
				for n in range (n_steps):
					y = y+step
					bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
					lum = luminance(buf)
					values = values+lum*weight
					weights = weights+weight
				for n in range (n_steps):
					x = x-step
					bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
					lum = luminance(buf)
					values = values+lum*weight
					weights = weights+weight
				for n in range (n_steps):
					y = y-step
					bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
					lum = luminance(buf)
					values = values+lum*weight
					weights = weights+weight

			avg = values/weights

		ec = bpy.context.scene.camera_settings.ec
		if ec!=0:
			middle = 0.18*math.pow(2, ec)
			log = (math.log2(middle/0.18)+10)/16.5
			s = s_calc(log)
			avg_min = s-0.01
			avg_max = s+0.01
		else:
			avg_min = 0.49
			avg_max = 0.51
			middle = 0.18
		print("average: ", avg)
		if not (avg>avg_min and avg<avg_max):
			# Measure scene referred value and change the exposure value
			s_curve = s_calculation(avg)
			log = math.pow(2, (16.5*s_curve-12.47393))
			past = bpy.context.scene.view_settings.exposure
			scene = log/(math.pow(2, past))
			future = -math.log2(scene/middle)
			exposure = past-((past-future)/5)
			bpy.context.scene.view_settings.exposure = exposure


# Global values
handle = ()
path = os.path.join(os.path.dirname(__file__), "looks/")
filmic_vhc = read_filmic_values(path + "Very High Contrast")
filmic_hc = read_filmic_values(path + "High Contrast")
filmic_mhc = read_filmic_values(path + "Medium High Contrast")
filmic_bc = read_filmic_values(path + "Base Contrast")
filmic_mlc = read_filmic_values(path + "Medium Low Contrast")
filmic_lc = read_filmic_values(path + "Low Contrast")
filmic_vlc = read_filmic_values(path + "Very Low Contrast")


# Calculate value after filmic log
def s_calc(log):
	look = bpy.context.scene.view_settings.look
	if look=="None":
		filmic = filmic_bc
	elif look=="Filmic - Very High Contrast":
		filmic = filmic_vhc
	elif look=="Filmic - High Contrast":
		filmic = filmic_hc
	elif look=="Filmic - Medium High Contrast":
		filmic = filmic_mhc
	elif look=="Filmic - Base Contrast":
		filmic = filmic_bc
	elif look=="Filmic - Medium Low Contrast":
		filmic = filmic_mlc
	elif look=="Filmic - Low Contrast":
		filmic = filmic_lc
	elif look=="Filmic - Very Low Contrast":
		filmic = filmic_vlc
	print("log: ", log)
	x = int(log*4096)
	return filmic[x]


# Calculate value after filmic log inverse
def s_calculation(n):
	look = bpy.context.scene.view_settings.look
	if look=="None":
		filmic = filmic_bc
	elif look=="Filmic - Very High Contrast":
		filmic = filmic_vhc
	elif look=="Filmic - High Contrast":
		filmic = filmic_hc
	elif look=="Filmic - Medium High Contrast":
		filmic = filmic_mhc
	elif look=="Filmic - Base Contrast":
		filmic = filmic_bc
	elif look=="Filmic - Medium Low Contrast":
		filmic = filmic_mlc
	elif look=="Filmic - Low Contrast":
		filmic = filmic_lc
	elif look=="Filmic - Very Low Contrast":
		filmic = filmic_vlc
	begin = 0
	end = len(filmic)
	middle = begin
	# find value in middle (binary search)
	while (end-begin) > 1:
		middle = math.ceil((end+begin)/2)
		if filmic[middle] > n:
			end = middle
		else:
			begin = middle
	return (middle + 1) / len(filmic)


# RGB to Luminance
def luminance(buf):
	lum = 0.2126*buf[0] + 0.7152*buf[1] + 0.0722*buf[2]
	return lum


'''# Handlers
@persistent
def camera_handler(scene):
	settings = scene.camera_settings
	if settings.enabled:
		update_aperture(bpy.context)
		update_shutter_speed(bpy.context)


def update_aperture_handler(self, context):
	update_aperture(context)
def update_shutter_speed_handler(self, context):
	update_shutter_speed(context)'''


class CameraSettings(PropertyGroup):
	# Toggle
	enabled : bpy.props.BoolProperty(
		name = "Enable Real Camera",
		description = "Enable Real Camera",
		default = False,
		update = toggle_update
		)

	# Exposure Triangle
	aperture : bpy.props.FloatProperty(
		name = "Aperture",
		description = "Aperture of the lens in f-stops. From 0.1 to 64. Gives a depth of field effect",
		min = 0.1,
		max = 64,
		step = 1,
		precision = 2,
		default = 5.6,
		update = update_aperture
		)

	shutter_speed : bpy.props.FloatProperty(
		name = "Shutter Speed",
		description = "Exposure time of the sensor in seconds. From 1/10000 to 10. Gives a motion blur effect",
		min = 0.0001,
		max = 100,
		step = 10,
		precision = 4,
		default = 0.5,
		update = update_shutter_speed
		)

	# Mechanics
	af : bpy.props.BoolProperty(
		name = "Autofocus",
		description = "Enable Autofocus",
		default = False,
		update = update_af
		)

	af_bake : bpy.props.BoolProperty(
		name = "Autofocus Baking",
		description = "Bake Autofocus for the entire animation",
		default = False,
		update = update_af_bake
		)

	af_step : bpy.props.IntProperty(
		name = "Step",
		description = "Every step frames insert a keyframe",
		min = 1,
		max = 10000,
		default = 24
		)

	# Auto Exposure
	enable_ae : bpy.props.BoolProperty(
		name = "Auto Exposure",
		description = "Enable Auto Exposure",
		default = False,
		update = update_ae
		)

	ae_mode : bpy.props.EnumProperty(
		name="Mode",
		items= [
			("Center Spot", "Center Spot", "Sample the pixel in the center of the window", 'PIVOT_BOUNDBOX', 0),
			("Center Weighted", "Center Weighted", "Sample a grid of pixels and gives more weight to the ones near the center", 'CLIPUV_HLT', 1),
			("Full Window", "Full Window", "Sample a grid of pixels among the whole window", 'FACESEL', 2),
			],
		description="Select an auto exposure metering mode",
		default="Center Weighted"
		)

	ec : bpy.props.FloatProperty(
		name = "EV Compensation",
		description = "Exposure Compensation value: add or subtract brightness",
		min = -3,
		max = 3,
		step = 1,
		precision = 2,
		default = 0
		)


# Preferences ###############################################


############################################################################
classes = (
	REALCAMERA_PT_Panel,
	AUTOEXP_PT_Panel,
	CameraSettings
	)

register, unregister = bpy.utils.register_classes_factory(classes)

# Register
def register():
	for cls in classes:
		bpy.utils.register_class(cls)
	bpy.types.Scene.camera_settings = bpy.props.PointerProperty(type=CameraSettings)
	#bpy.app.handlers.frame_change_post.append(camera_handler)


# Unregister
def unregister():
	for cls in classes:
		bpy.utils.unregister_class(cls)
	del bpy.types.Scene.camera_settings
	#bpy.app.handlers.frame_change_post.remove(camera_handler)


if __name__ == "__main__":
	register()
