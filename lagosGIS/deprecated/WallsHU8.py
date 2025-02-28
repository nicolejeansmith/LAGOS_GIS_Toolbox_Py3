# Filename: WallsHU8.py
# Purpose: Creates "walls" of higher elevation on the NED to force conformance to HU8 boundaries.

import os, re, shutil
import arcpy
from arcpy import env
from arcpy.sa import *


def wall(nhd_gdb, rasters_list, outfolder, height = '500',
                projection = arcpy.SpatialReference(102039)):
    """For one or more HU8s within the same subregion (nhd_gdb variable),
    adds walls at the boundaries to force flow direction that do not cross
    the boundary."""
    env.workspace = 'in_memory'
    env.outputCoordinateSystem = projection
    env.compression = "NONE"
    env.snapRaster = rasters_list[0] # they all have the same snap
    env.cellSize = '10'
    env.pyramids = "PYRAMIDS -1 SKIP_FIRST"
    arcpy.CheckOutExtension("Spatial")

    # HU8 layer
    huc12_fc = os.path.join(nhd_gdb, "WBDHU12")
    arcpy.MakeFeatureLayer_management(huc12_fc, "huc12_layer")

    # make the walls raster
    arcpy.PolygonToLine_management(huc12_fc, 'wall_lines')
    arcpy.AddField_management('wall_lines', "height", "DOUBLE")
    arcpy.CalculateField_management('wall_lines', "height", '500000', "PYTHON")
    arcpy.FeatureToRaster_conversion('wall_lines', "height", 'wall_raster')
    wallsObject = Raster('wall_raster')

    for raster in rasters_list:
        out_name = os.path.join(raster.replace('.tif', '_walled.tif'))
        arcpy.AddMessage('Creating output {0}'.format(out_name))
        env.extent = raster
        elevObject = Raster(raster)
        walled_ned = Con(IsNull(wallsObject), elevObject, Con(LessThan(elevObject, -58000), elevObject, wallsObject))

        walled_ned.save(out_name)

    for item in ['huc8_layer', 'wall_lines', 'wall_raster']:
        arcpy.Delete_management(item)
    arcpy.ResetEnvironments()
    arcpy.CheckInExtension("Spatial")

    return out_name

def main():
    nhd_gdb = arcpy.GetParameterAsText(0) # NHD Subregion file geodatabase
    rasters_list = arcpy.GetParameterAsText(1).split(';')
    outfolder = arcpy.GetParameterAsText(2) # Output Folder
    wall(nhd_gdb, rasters_list, outfolder)


def test():
    nhd_gdb = 'C:/GISData/Scratch/NHD0411/NHDH0411.gdb'
    env.workspace = 'C:/GISData/Scratch/NHD0411/huc8clips0411'
    rasters_list = [os.path.join(env.workspace, r) for r in arcpy.ListRasters('*tif')]
    outfolder = 'C:/GISData/Scratch/NHD0411'
    wall(nhd_gdb, rasters_list, outfolder)

if __name__ == '__main__':
    main()