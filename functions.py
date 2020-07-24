# Libraries
import bpy
import os


def read_filmic(path):
    nums = []
    with open(path) as filmic_file:
        for line in filmic_file:
            nums.append(float(line))
    return nums


# Globals
path = os.path.join(os.path.dirname(__file__), "looks/")
filmic_vhc = read_filmic(path + "Very High Contrast")
filmic_hc = read_filmic(path + "High Contrast")
filmic_mhc = read_filmic(path + "Medium High Contrast")
filmic_mc = read_filmic(path + "Medium Contrast")
filmic_mlc = read_filmic(path + "Medium Low Contrast")
filmic_lc = read_filmic(path + "Low Contrast")
filmic_vlc = read_filmic(path + "Very Low Contrast")


def contrast(log):
    if log < 1:
        look = bpy.context.scene.view_settings.look
        if look=="None":
            filmic = filmic_mc
        elif look=="Very High Contrast":
            filmic = filmic_vhc
        elif look=="High Contrast":
            filmic = filmic_hc
        elif look=="Medium High Contrast":
            filmic = filmic_mhc
        elif look=="Medium Contrast":
            filmic = filmic_mc
        elif look=="Medium Low Contrast":
            filmic = filmic_mlc
        elif look=="Low Contrast":
            filmic = filmic_lc
        elif look=="Very Low Contrast":
            filmic = filmic_vlc
        x = int(log * 4095)
        return filmic[x]
    else:
        return 1


def rgb_to_luminance(buf):
    lum = 0.2126 * buf[0] + 0.7152 * buf[1] + 0.0722 * buf[2]
    return lum



def register():
    return None

def unregister():
    return None
