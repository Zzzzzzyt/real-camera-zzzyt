# Add-on Info
bl_info = {
    "name": "Real Camera (Zzzyt fork)",
    "description": "Physical camera controls",
    "author": "Zzzyt <zzzyt205@gmail.com>",
    "version": (3, 4),
    "blender": (2, 91, 0),
    "location": "View 3D > Properties Panel",
    "doc_url": "https://github.com/Zzzzzzyt/real-camera-zzzyt",
    "tracker_url": "https://github.com/Zzzzzzyt/real-camera-zzzyt/issues",
    "support": "COMMUNITY",
    "category": "Render",
    }


# Libraries
from math import log2, pow
from mathutils import Vector
from . import functions

import bpy
import bgl
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Panel, PropertyGroup, Operator


# Panel
class REALCAMERA_PT_Camera(Panel):
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
        sub.prop(cam.dof, "aperture_fstop", text="Aperture")
        sub.prop(settings, 'shutter_speed')

        # Mechanics
        col = flow.column()
        col.prop(settings, 'enable_af')
        if settings.enable_af:
            row = col.row(align=True)
            row.prop(settings, 'af_step', text="Bake")
            row.prop(settings, 'af_bake', text="", icon='PLAY')
        col = flow.column()
        sub = col.column(align=True)
        if not settings.enable_af:
            sub.prop(cam.dof, "focus_distance", text="Focus Point")
        sub.prop(cam, 'lens', text="Focal Length")


# Auto Exposure panel
class REALCAMERA_PT_Exposure(Panel):
    bl_space_type = "PROPERTIES"
    bl_context = "render"
    bl_region_type = "WINDOW"
    bl_category = "Real Camera"
    bl_label = "Auto Exposure"
    COMPAT_ENGINES = {'BLENDER_EEVEE', 'CYCLES'}

    @classmethod
    def poll(cls, context):
        return (context.engine in cls.COMPAT_ENGINES)

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
        col.prop(settings, 'ev_compensation', slider=True)
        if settings.ae_mode=="Center Weighed":
            col.prop(settings, 'center_grid')
        if settings.ae_mode=="Full Window":
            col.prop(settings, 'full_grid')


def enable_camera(self, context):
	settings = context.scene.camera_settings
	camera = context.object.data
	if settings.enabled:
		# set limits
		camera.show_limits = True
		# enable DOF
		camera.dof.use_dof = True
		# set camera size
		camera.display_size = 0.2
		# set initial values
		update_aperture(self, context)
		update_shutter_speed(self, context)
	else:
		# disable DOF
		camera.dof.use_dof = False
		# disable limits
		camera.show_limits = False
		# disable autofocus
		context.scene.camera_settings.enable_af = False


def update_aperture(self, context):
    context.object.data.cycles.aperture_fstop = context.scene.camera_settings.aperture


def update_shutter_speed(self, context):
    fps = context.scene.render.fps
    shutter = context.scene.camera_settings.shutter_speed
    motion = fps * shutter
    # set motion blur for Cycles and Eevee
    context.scene.render.motion_blur_shutter = motion
    context.scene.eevee.motion_blur_shutter = motion


def update_autofocus(self, context):
    autofocus = context.scene.camera_settings.enable_af

    if autofocus:
        name = context.active_object.name
        obj = bpy.data.objects[name]
        # shoot ray from center of camera until it hits a mesh and calculate distance
        ray = context.scene.ray_cast(context.window.view_layer.depsgraph, obj.location, obj.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0)))
        distance = (ray[1] - obj.location).magnitude
        bpy.context.object.data.dof.focus_distance = distance
    else:
        # reset baked af
        context.scene.camera_settings.af_bake = False
        autofocus_bake(self, context)


def autofocus_bake(self, context):
    scene = bpy.context.scene
    bake = scene.camera_settings.af_bake
    start = scene.frame_start
    end = scene.frame_end
    frames = end - start + 1
    steps = scene.camera_settings.af_step
    n = int(float(frames / steps))
    current_frame = scene.frame_current
    camera = context.object.data

    if bake:
        scene.frame_current = start
        # every step frames, place a keyframe
        for i in range(n + 1):
            update_autofocus(self, context)
            camera.dof.keyframe_insert('focus_distance')
            scene.frame_set(scene.frame_current + steps)
        # current Frame
        scene.frame_current = current_frame
    else:
        # delete dof keyframes
        try:
            fcurves = camera.animation_data.action.fcurves
        except AttributeError:
            pass
        else:
            for c in fcurves:
                if c.data_path.startswith("dof.focus_distance"):
                    fcurves.remove(c)


def auto_exposure():
    shading = bpy.context.area.spaces.active.shading.type

    # check if viewport is set to Rendered mode
    if shading == "RENDERED":
        settings = bpy.context.scene.camera_settings
        # viewport width and height
        viewport = bgl.Buffer(bgl.GL_INT, 4)
        bgl.glGetIntegerv(bgl.GL_VIEWPORT, viewport)
        width = viewport[2]
        height = viewport[3]
        buf = bgl.Buffer(bgl.GL_FLOAT, 3)

        # Center Spot
        if settings.ae_mode=="Center Spot":
            x = width // 2
            y = height // 2
            bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
            average = functions.rgb_to_luminance(buf)

        # Full Window
        if settings.ae_mode == "Full Window":
            grid = settings.full_grid
            values = []
            step = 1 / (grid + 1)
            for i in range(grid):
                for j in range(grid):
                    x = int(step * (j + 1) * width)
                    y = int(step * (i + 1) * height)
                    bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
                    lum = functions.rgb_to_luminance(buf)
                    values.append(lum)
            values.sort()
            if len(values) > 5:
                values = values[2:-2]
            average = sum(values) / len(values)

        # Center Weighed
        if settings.ae_mode == "Center Weighed":
            circles = settings.center_grid
            max = width if width >= height else height
            half = max // 2
            step = max // (circles * 2 + 2)
            res = []
            for i in range(circles):
                x = half - (i + 1) * step
                y = x
                n_steps = i * 2 + 2
                weight = (circles - 1 - i) / circles
                for n in range(n_steps):
                    x = x + step
                    bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
                    lum = functions.rgb_to_luminance(buf)
                    res.append((lum, lum*weight, weight))
                for n in range(n_steps):
                    y = y + step
                    bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
                    lum = functions.rgb_to_luminance(buf)
                    res.append((lum, lum*weight, weight))
                for n in range(n_steps):
                    x = x - step
                    bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
                    lum = functions.rgb_to_luminance(buf)
                    res.append((lum, lum*weight, weight))
                for n in range(n_steps):
                    y = y - step
                    bgl.glReadPixels(x, y, 1, 1, bgl.GL_RGB, bgl.GL_FLOAT, buf)
                    lum = functions.rgb_to_luminance(buf)
                    res.append((lum, lum*weight, weight))
            res.sort()
            if len(res) > 5:
                res = res[2:-2]
            values = 0
            weights = 0
            for i in res:
                values += i[1]
                weights += i[2]
            average = values / weights

        # expose scene based on average
        if average > 0:
            actual_exposure = bpy.context.scene.view_settings.exposure
            ev_compensation = bpy.context.scene.camera_settings.ev_compensation
            # current
            scene_exposed = average * pow(2, actual_exposure)
            log = (log2(scene_exposed / 0.18) + 10) / 16.5
            display = functions.contrast(log)
            # target
            middle_gray = 0.18 * pow(2, ev_compensation)
            log_target = (log2(middle_gray / 0.18) + 10) / 16.5
            display_target = functions.contrast(log_target)
            avg_min = display_target - 0.01
            avg_max = display_target + 0.01

            # if not inside target threshold, update exposure
            if not (display > avg_min and display < avg_max):
                future = -log2(average / middle_gray)
                exposure = actual_exposure - (actual_exposure - future) / 5
                bpy.context.scene.view_settings.exposure = exposure


class AUTOEXP_OT_Toggle:
    bl_idname = "autoexp.toggle_ae"
    bl_label = "Enable AE"
    bl_description = "Enable Auto Exposure handler"

    _handle = None

    @staticmethod
    def add_handler():
        if AUTOEXP_OT_Toggle._handle is None:
            AUTOEXP_OT_Toggle._handle = bpy.types.SpaceView3D.draw_handler_add(auto_exposure, (), 'WINDOW', 'PRE_VIEW')

    @staticmethod
    def remove_handler():
        if AUTOEXP_OT_Toggle._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(AUTOEXP_OT_Toggle._handle, 'WINDOW')
            AUTOEXP_OT_Toggle._handle = None


def enable_auto_exposure(self, context):
    ae = context.scene.camera_settings.enable_ae
    if ae:
        AUTOEXP_OT_Toggle.add_handler()
    else:
        AUTOEXP_OT_Toggle.remove_handler()


class CameraSettings(PropertyGroup):
    # Enable
    enabled : BoolProperty(
        name = "Real Camera",
        description = "Enable Real Camera",
        default = False,
        update = enable_camera
        )

    # Exposure Triangle
    aperture : FloatProperty(
        name = "Aperture",
        description = "Aperture of the lens in f-stops. From 0.1 to 64. Gives a depth of field effect",
        min = 0.1,
        max = 64,
        step = 1,
        precision = 2,
        default = 5.6,
        update = update_aperture
        )

    shutter_speed : FloatProperty(
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
    enable_af : BoolProperty(
        name = "Autofocus",
        description = "Enable Autofocus",
        default = False,
        update = update_autofocus
        )

    af_bake : BoolProperty(
        name = "Autofocus Baking",
        description = "Bake Autofocus for the entire animation",
        default = False,
        update = autofocus_bake
        )

    af_step : IntProperty(
        name = "Step",
        description = "Every step frames insert a keyframe",
        min = 1,
        max = 10000,
        default = 24
        )

    # Auto Exposure
    enable_ae : BoolProperty(
        name = "Auto Exposure",
        description = "Enable Auto Exposure",
        default = False,
        update = enable_auto_exposure
        )

    ae_mode : EnumProperty(
        name = "Mode",
        items = [
            ("Center Spot", "Center Spot", "Sample the pixel in the center of the window", 'PIVOT_BOUNDBOX', 0),
            ("Center Weighed", "Center Weighed", "Sample a grid of pixels and gives more weight to the ones near the center", 'CLIPUV_HLT', 1),
            ("Full Window", "Full Window", "Sample a grid of pixels among the whole window", 'FACESEL', 2),
            ],
        description = "Select an auto exposure metering mode",
        default = "Center Weighed"
        )

    ev_compensation : FloatProperty(
        name = "EV Compensation",
        description = "Exposure Compensation value: overexpose or lowerexpose the scene",
        min = -3,
        max = 3,
        step = 1,
        precision = 2,
        default = 0
        )

    center_grid : IntProperty(
        name = "Circles",
        description = "Number of circles to sample: more circles means more accurate auto exposure, but also means slower viewport",
        min = 2,
        max = 20,
        default = 4
        )

    full_grid : IntProperty(
        name = "Grid",
        description = "Number of rows and columns to sample: more rows and columns means more accurate auto exposure, but also means slower viewport",
        min = 2,
        max = 20,
        default = 7
        )


############################################################################
classes = (
    REALCAMERA_PT_Camera,
    REALCAMERA_PT_Exposure,
    CameraSettings
    )

register, unregister = bpy.utils.register_classes_factory(classes)


# Register
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    functions.register()
    bpy.types.Scene.camera_settings = bpy.props.PointerProperty(type=CameraSettings)


# Unregister
def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    functions.unregister()
    del bpy.types.Scene.camera_settings
    # Remove draw handler if it exists
    AUTOEXP_OT_Toggle.remove_handler()


if __name__ == "__main__":
    register()
