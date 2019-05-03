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


# Panel
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

		col = layout.column()
		sub = col.column(align=True)
		if context.scene.render.engine in ["BLENDER_EEVEE", "BLENDER_WORKBENCH"]:
			sub.prop(cam.gpu_dof, 'fstop', text="Aperture")
		else:
			sub.prop(cam.cycles, 'aperture_fstop', text="Aperture")
		sub.prop(settings, 'shutter_speed')
		sub.prop(settings, 'iso')

		row = layout.row()
		row.prop(settings, 'af')
		sub = row.row(align=True)
		sub.active = settings.af
		if settings.af:
			sub.prop(settings, 'af_bake', icon='PLAY', text="Bake")
			sub.prop(settings, 'af_step', text="Step")

		split = layout.split()
		col = split.column(align=True)
		if not settings.af:
			col.prop(cam, 'dof_distance', text="Focus Point")
		col.prop(cam, 'lens', text="Focal Length")
		ev = calculate_ev(context)
		ev = str(ev)
		col = layout.column()
		col.prop(settings, 'ae')
		col.label(text="")
		row = col.row(align=True)
		row.alignment = 'CENTER'
		row.label(text="Exposure Value: "+ev, icon='LIGHT_SUN')


# Auto Exposure panel
class AUTOEXP_PT_Panel(Panel):
	bl_space_type = "VIEW_3D"
	bl_context = "objectmode"
	bl_region_type = "UI"
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

		# Drop Down Modes
		col = layout.column(align=True)
		row = col.row(align=True)
		row.alignment = "CENTER"
		row.label(text="Autoexposure Mode")
		row = col.row(align=True)
		row.scale_x = 1.5
		row.scale_y = 1.5
		row.alignment = "CENTER"
		row.prop(settings, 'ae_mode', expand=True)
		col.label(text="")


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
		update_aperture(context)
		update_shutter_speed(context)
		update_iso(context)
	else:
		# reset limits
		name = context.active_object.name
		bpy.data.cameras[name].show_limits = False
		# reset autofocus
		bpy.context.scene.camera_settings.af = False


# Update Aperture
def update_aperture(context):
	context.object.data.cycles.aperture_fstop = context.scene.camera_settings.aperture
	update_ev(context)
# Update Shutter Speed
def update_shutter_speed(context):
	fps = context.scene.render.fps
	sp = context.scene.camera_settings.shutter_speed
	motion = fps*(1/sp)
	context.scene.render.motion_blur_shutter = motion
	update_ev(context)
# Update ISO
def update_iso(context):
	update_ev(context)


# Update EV
def calculate_ev(context):
	settings = context.scene.camera_settings
	A = settings.aperture
	S = 1/settings.shutter_speed
	I = settings.iso
	EV = math.log((100*A**2/(I*S)), 2)
	EV = round(EV, 2)
	return EV


# Update EV in color management
def update_ev(context):
	settings = context.scene.camera_settings
	if settings.ae:
		EV = calculate_ev(context)
		# Filmic
		filmic = -0.68*EV+5.95
		context.scene.view_settings.exposure = filmic
	else:
		context.scene.view_settings.exposure = 0


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


def read_filmic_values(path):
	nums = []
	with open(path) as filmic_file:
		for line in filmic_file:
			nums.append(float(line))
	return nums


def function():
	shading = bpy.context.area.spaces.active.shading.type
	global flag
	if shading in ["MATERIAL" ,"RENDERED"] and flag:
		flag = False
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
			circles = 3
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

		s_curve = s_calculation(avg)
		log = math.pow(2, (16.5*s_curve-12.47393))
		ev = bpy.context.scene.view_settings.exposure
		scene = log/(math.pow(2, ev))
		exposure = -math.log2(scene/0.18)
		print("average: ", avg)
		print("scene: ", scene)
		print("")
		bpy.context.scene.view_settings.exposure = exposure


# Globals
flag = True
handle = ()
path = os.path.join(os.path.dirname(__file__), "looks/")
filmic_vhc = read_filmic_values(path + "Very High Contrast")
filmic_hc = read_filmic_values(path + "High Contrast")
filmic_mhc = read_filmic_values(path + "Medium High Contrast")
filmic_bc = read_filmic_values(path + "Base Contrast")
filmic_mlc = read_filmic_values(path + "Medium Low Contrast")
filmic_lc = read_filmic_values(path + "Low Contrast")
filmic_vlc = read_filmic_values(path + "Very Low Contrast")


def update_ae(self, context):
	ae = context.scene.camera_settings.enable_ae
	global handle
	if ae:
		handle = bpy.types.SpaceView3D.draw_handler_add(function, (), 'WINDOW', 'PRE_VIEW')
		bpy.app.timers.register(timer)
	else:
		bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
		bpy.app.timers.unregister(timer)


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
	# find value in middle of endpoints (binary search)
	while (end-begin) > 1:
		middle = math.ceil((end+begin)/2)
		if filmic[middle] > n:
			end = middle
		else:
			begin = middle
	return (middle + 1) / len(filmic)


def luminance(buf):
	lum = 0.2126*buf[0] + 0.7152*buf[1] + 0.0722*buf[2]
	return lum


# Handlers
@persistent
def camera_handler(scene):
	settings = scene.camera_settings
	if settings.enabled:
		update_aperture(bpy.context)
		update_shutter_speed(bpy.context)
		update_iso(bpy.context)


def update_aperture_handler(self, context):
	update_aperture(context)
def update_shutter_speed_handler(self, context):
	update_shutter_speed(context)
def update_iso_handler(self, context):
	update_iso(context)
def update_ev_handler(self, context):
	update_ev(context)


@persistent
def timer():
	global flag
	flag = True
	return 1.0


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
		update = update_aperture_handler
		)

	shutter_speed : bpy.props.IntProperty(
		name = "Shutter Speed",
		description = "Exposure time of the sensor in seconds (1/value). From 1/10000 to 1/1. Gives a motion blur effect",
		min = 1,
		max = 10000,
		default = 500,
		update = update_shutter_speed_handler
		)

	iso : bpy.props.IntProperty(
		name = "ISO",
		description = "Sensor sensitivity. From 1 to 102400. Gives more or less brightness",
		min = 1,
		max = 102400,
		default = 100,
		update = update_iso_handler
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

	ae : bpy.props.BoolProperty(
		name = "Autoexposure",
		description = "Automatically changes the exposure value of the scene",
		default = False,
		update = update_ev_handler
		)

	enable_ae : bpy.props.BoolProperty(
		name = "Auto Exposure",
		description = "Enable Auto Exposure",
		default = False,
		update = update_ae
		)

	# Auto Exposure
	ae_mode : bpy.props.EnumProperty(
		name="Mode",
		items= [
			("Center Spot", "", "Center Spot", 'PIVOT_BOUNDBOX', 0),
			("Center Weighted", "", "Center Weighted", 'CLIPUV_HLT', 1),
			("Full Window", "", "Full Window", 'FACESEL', 2),
			],
		description="Select an auto exposure mode",
		default="Center Weighted"
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
	bpy.app.handlers.frame_change_post.append(camera_handler)


# Unregister
def unregister():
	for cls in classes:
		bpy.utils.unregister_class(cls)
	del bpy.types.Scene.camera_settings
	bpy.app.handlers.frame_change_post.remove(camera_handler)


if __name__ == "__main__":
	register()
