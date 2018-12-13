# Addon Info
bl_info = {
	"name": "Real Camera",
	"description": "Physical camera controls",
	"author": "Wolf",
	"version": (2, 2),
	"blender": (2, 79, 0),
	"location": "Properties > Camera",
	"wiki_url": "https://www.3d-wolf.com/products/camera.html",
	"tracker_url": "https://www.3d-wolf.com/products/camera.html",
	"support": "COMMUNITY",
	"category": "Render"
	}


# Import
import bpy
import math
from bpy.props import *
from mathutils import Vector
from bpy.app.handlers import persistent
from . import addon_updater_ops


# Panel
class RealCameraPanel(bpy.types.Panel):
	# Create a Panel in the Camera Properties
	bl_category = "Real Camera"
	bl_label = "Real Camera"
	bl_space_type = 'PROPERTIES'
	bl_region_type = "WINDOW"
	bl_context = "data"

	@classmethod
	def poll(cls, context):
		return context.camera and context.scene.render.engine == 'CYCLES'

	def draw_header(self, context):
		settings = context.scene.camera_settings
		layout = self.layout
		layout.prop(settings, 'enabled', text='')

	def draw(self, context):
		addon_updater_ops.check_for_update_background()
		settings = context.scene.camera_settings
		layout = self.layout
		layout.enabled = settings.enabled

		col = layout.column()
		sub = col.column(align=True)
		sub.prop(settings, 'aperture')
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
			col.prop(settings, 'focus_point')
		col.prop(settings, 'zoom')
		ev = calculate_ev(context)
		ev = str(ev)
		col = layout.column()
		col.prop(settings, 'ae')
		row = col.row(align=True)
		row.alignment = 'CENTER'
		row.label("Exposure Value: " + ev, icon='LAMP_SUN')

		addon_updater_ops.update_notice_box_ui(self, context)


# Enable camera
def toggle_update(self, context):
	settings = context.scene.camera_settings
	if settings.enabled:
		# set limits
		name = context.active_object.name
		bpy.data.cameras[name].show_limits = True
		# set metric system
		bpy.context.scene.unit_settings.system = 'METRIC'
		# change aperture to FSTOP
		bpy.data.cameras[name].cycles.aperture_type = 'FSTOP'
		# initial values Issue
		update_aperture(context)
		update_shutter_speed(context)
		update_iso(context)
		update_zoom(context)
		update_focus_point(context)
	else:
		# reset limits
		name = context.active_object.name
		bpy.data.cameras[name].show_limits = False
		# reset autofocus
		bpy.context.scene.camera_settings.af = False
		# reset motion blur
		bpy.context.scene.render.use_motion_blur = False


# Update Aperture
def update_aperture(context):
	bpy.context.object.data.cycles.aperture_fstop = bpy.context.scene.camera_settings.aperture
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
# Update Zoom
def update_zoom(context):
	bpy.context.object.data.lens = bpy.context.scene.camera_settings.zoom
# Update Focus Point
def update_focus_point(context):
	bpy.context.object.data.dof_distance = bpy.context.scene.camera_settings.focus_point


# Update EV
def calculate_ev(context):
	settings = bpy.context.scene.camera_settings
	A = settings.aperture
	S = 1/settings.shutter_speed
	I = settings.iso
	EV = math.log((100*A**2/(I*S)), 2)
	EV = round(EV, 2)
	return EV


# Update EV in color management
def update_ev(context):
	settings = bpy.context.scene.camera_settings
	if settings.ae:
		EV = calculate_ev(context)
		# Filmic
		filmic = -0.68*EV+5.95
		bpy.context.scene.view_settings.exposure = filmic
	else:
		bpy.context.scene.view_settings.exposure = 0


# Update Autofocus
def update_af(self, context):
	af = context.scene.camera_settings.af
	if af:
		name = context.active_object.name
		obj = bpy.data.objects[name]
		# ray Cast
		ray = bpy.context.scene.ray_cast(obj.location, obj.matrix_world.to_quaternion() * Vector((0.0, 0.0, -1.0)) )
		distance = (ray[1]-obj.location).magnitude
		bpy.data.cameras[name].dof_distance = distance
	else:
		# reset DOF
		bpy.context.object.data.dof_distance = bpy.context.scene.camera_settings.focus_point
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
	scene.frame_current = start
	name = context.active_object.name
	cam = bpy.data.cameras[name]
	if bake:
		# every step frames, place a keyframe
		for i in range(n+1):
			update_af(self, context)
			cam.keyframe_insert('dof_distance')
			scene.frame_set(scene.frame_current+steps)
	else:
		# delete dof keyframes
		try:
			fcurves = bpy.data.cameras[0].animation_data.action.fcurves
		except AttributeError:
			a=0
		else:
			for c in fcurves:
				if c.data_path.startswith("dof_distance"):
					fcurves.remove(c)
	# current Frame
	scene.frame_current = current_frame


# Handler
@persistent
def camera_handler(scene):
	settings = bpy.context.scene.camera_settings
	if not settings.af_bake:
		update_focus_point(bpy.context)
	update_aperture(bpy.context)
	update_shutter_speed(bpy.context)
	update_iso(bpy.context)
	update_zoom(bpy.context)


def update_aperture_handler(self, context):
	update_aperture(context)
def update_shutter_speed_handler(self, context):
	update_shutter_speed(context)
def update_iso_handler(self, context):
	update_iso(context)
def update_focus_point_handler(self, context):
	update_focus_point(context)
def update_zoom_handler(self, context):
	update_zoom(context)
def update_ev_handler(self, context):
	update_ev(context)


#Settings############################################################
class CameraSettings(bpy.types.PropertyGroup):
	# Toggle
	enabled = bpy.props.BoolProperty(
		name = "Enabled",
		description = "Enable Real Camera",
		default = False,
		update = toggle_update
	)
	# Exposure Triangle
	aperture = bpy.props.FloatProperty(
		name = "Aperture",
		description = "Aperture of the lens in f-stops. From 0.1 to 64. Gives a depth of field effect",
		min = 0.1,
		max = 64,
		step = 1,
		precision = 2,
		default = 5.6,
		update = update_aperture_handler
	)
	shutter_speed = bpy.props.IntProperty(
		name = "Shutter Speed",
		description = "Exposure time of the sensor in seconds (1/value). From 1/10000 to 1/1. Gives a motion blur effect",
		min = 1,
		max = 10000,
		default = 500,
		update = update_shutter_speed_handler
	)
	iso = bpy.props.IntProperty(
		name = "ISO",
		description = "Sensor sensitivity. From 1 to 102400. Gives more or less brightness",
		min = 1,
		max = 102400,
		default = 100,
		update = update_iso_handler
	)
	# Mechanics
	af = bpy.props.BoolProperty(
		name = "Autofocus",
		description = "Enable Autofocus",
		default = False,
		update = update_af
	)
	af_bake = bpy.props.BoolProperty(
		name = "Autofocus Baking",
		description = "Bake Autofocus for the entire animation",
		default = False,
		update = update_af_bake
	)
	af_step = bpy.props.IntProperty(
		name = "Step",
		description = "Every step frames insert a keyframe",
		min = 1,
		max = 10000,
		default = 24
	)
	focus_point = bpy.props.FloatProperty(
		name = "Focus Point",
		description = "Distance from the camera to the point of focus in meters",
		unit = 'LENGTH',
		min = 0,
		max = float('inf'),
		precision = 2,
		step = 1,
		default = 1,
		update = update_focus_point_handler
	)
	zoom = bpy.props.FloatProperty(
		name = "Focal Length",
		description = "Zoom in millimeters",
		min = 0,
		max = float('inf'),
		precision = 2,
		step = 1,
		default = 35,
		update = update_zoom_handler
	)
	ae = bpy.props.BoolProperty(
		name = "Autoexposure",
		description = "Automatically changes the exposure value of the scene",
		default = False,
		update = update_ev_handler
	)


# Preferences ###############################################
class RealCameraPreferences(bpy.types.AddonPreferences):
	bl_idname = __package__

	auto_check_update = bpy.props.BoolProperty(
	name = "Auto-check for Update",
	description = "If enabled, auto-check for updates using an interval",
	default = True,
	)
	updater_intrval_months = bpy.props.IntProperty(
	name='Months',
	description = "Number of months between checking for updates",
	default=0,
	min=0
	)
	updater_intrval_days = bpy.props.IntProperty(
	name='Days',
	description = "Number of days between checking for updates",
	default=1,
	min=0,
	)
	updater_intrval_hours = bpy.props.IntProperty(
	name='Hours',
	description = "Number of hours between checking for updates",
	default=0,
	min=0,
	max=23
	)
	updater_intrval_minutes = bpy.props.IntProperty(
	name='Minutes',
	description = "Number of minutes between checking for updates",
	default=0,
	min=0,
	max=59
	)

	def draw(self, context):
		layout = self.layout
		addon_updater_ops.update_settings_ui(self, context)


############################################################################
# Register
def register():
	addon_updater_ops.register(bl_info)
	bpy.utils.register_class(RealCameraPreferences)
	bpy.utils.register_module(__name__)
	bpy.types.Scene.camera_settings = bpy.props.PointerProperty(type=CameraSettings)
	bpy.app.handlers.frame_change_post.append(camera_handler)

# Unregister
def unregister():
	bpy.utils.unregister_class(RealCameraPreferences)
	bpy.utils.unregister_module(__name__)
	del bpy.types.Scene.camera_settings
	bpy.app.handlers.frame_change_post.remove(camera_handler)

if __name__ == "__main__":
    register()
