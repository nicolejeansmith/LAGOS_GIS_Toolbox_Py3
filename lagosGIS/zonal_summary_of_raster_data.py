# filename: zonal_summary_of_raster_data.py
# author: Nicole J Smith
# version: 2.0
# LAGOS module(s): GEO
# tool type: re-usable (ArcGIS Toolbox)

import csv
import os
import arcpy
from arcpy import management as DM
from arcpy import env
from collections import defaultdict

import lagosGIS


def calc(zone_fc, zone_field, in_value_raster, out_table, is_thematic, unflat_table='',
         rename_tag='', units=''):
    """
    Calculates the mean raster value in each zone or summarizes categorical raster data as a percent of each zone
    depending on the input raster type.
    :param zone_fc: Zones polygon feature class
    :param zone_field: Unique identifier for each zone
    :param in_value_raster: Raster dataset for which to summarize all values for each zone
    :param out_table: Output table to save the result
    :param is_thematic: Boolean. Whether the raster dataset to be summarized is thematic/categorical data (True), or
    continuous/numerical data (False).
    :param unflat_table: (Optional) If the zones provided are derived from zones that originally overlapped, provide
    the location of the overlapping vs. non-overlapping identifier mapping table.
    :param rename_tag: (Optional) A variable name to include in all output columns
    :param units: (Optional) A units suffix to append to all output columns
    :return: Out_table location
    """

    orig_env = env.workspace
    env.workspace = 'in_memory'
    arcpy.SetLogHistory(False)
    arcpy.CheckOutExtension("Spatial")

    # ---DEFINE FUNCTIONS-----------------------------------------------------------------------------------------
    def stats_area_table(zone_fc=zone_fc, zone_field=zone_field, in_value_raster=in_value_raster,
                         out_table=out_table, is_thematic=is_thematic):
        """
        Runs Zonal Statistics as Table for continuous data or Tabulate Area for thematic/categorical data and refines
        the output to prepare the table for being included in LAGOS-US.
        :param zone_fc: Zones feature class
        :param zone_field: Unique identifier for each zone
        :param in_value_raster: Raster dataset for which to summarize all values for each zone
        :param out_table: Output table to save the result
        :param is_thematic: Boolean. Whether the raster dataset to be summarized is thematic/categorical data (True), or
    continuous/numerical data (False).
        :return:
        """

        def refine_zonal_output(t):
            """Makes a nicer output for this tool. Rename some fields, drop unwanted
                ones, calculate percentages using raster AREA before deleting that
                field."""
            if is_thematic:
                value_fields = arcpy.ListFields(t, "VALUE*")
                pct_fields = ['{}_pct'.format(f.name) for f in
                              value_fields]  # VALUE_41_pct, etc. Field can't start with number.

                # add all the new fields needed
                for f, pct_field in zip(value_fields, pct_fields):
                    arcpy.AddField_management(t, pct_field, f.type)

                # calculate the percents
                cursor_fields = ['AREA'] + [f.name for f in value_fields] + pct_fields
                uCursor = arcpy.da.UpdateCursor(t, cursor_fields)
                for uRow in uCursor:
                    # unpacks area + 3 tuples of the right fields for each, no matter how many there are
                    vf_i_end = len(value_fields) + 1
                    pf_i_end = vf_i_end + len(pct_fields)

                    # pct_values and ha_values are both null at this point but unpack for clarity
                    area, value_values, pct_values = uRow[0], uRow[1:vf_i_end], uRow[vf_i_end:pf_i_end]
                    new_pct_values = [100 * vv / area for vv in value_values]
                    new_row = [area] + value_values + new_pct_values
                    uCursor.updateRow(new_row)

                for vf in value_fields:
                    arcpy.DeleteField_management(t, vf.name)

            arcpy.AlterField_management(t, 'COUNT', 'CELL_COUNT')
            drop_fields = ['ZONE_CODE', 'COUNT', 'AREA', 'MAJORITY', 'MEDIAN', 'MINORITY', 'RANGE', 'SUM', 'VARIETY']
            for df in drop_fields:
                try:
                    arcpy.DeleteField_management(t, df)
                except:
                    continue

        # SETUP---------------------------------------------------------------------------------------------------
        # Set up environments for alignment between zone raster and theme raster
        if isinstance(zone_fc, arcpy.Result):
            zone_fc = zone_fc.getOutput(0)
        this_files_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(this_files_dir)
        common_grid = os.path.abspath('../common_grid.tif')
        env.snapRaster = common_grid
        env.cellSize = common_grid
        env.extent = zone_fc

        # Convert zones to raster if provided as polygon feature class
        zone_desc = arcpy.Describe(zone_fc)
        zone_raster = 'convertraster'
        if zone_desc.dataType not in ['RasterDataset', 'RasterLayer']:
            zone_raster = arcpy.PolygonToRaster_conversion(zone_fc, zone_field, zone_raster, 'CELL_CENTER',
                                                           cellsize=env.cellSize)
            print('cell size is {}'.format(env.cellSize))
            zone_size = int(env.cellSize)
        else:
            zone_raster = zone_fc
            zone_size = min(arcpy.Describe(zone_raster).meanCellHeight, arcpy.Describe(zone_raster).meanCellWidth)
            raster_size = min(arcpy.Describe(in_value_raster).meanCellHeight, arcpy.Describe(in_value_raster).meanCellWidth)
            env.cellSize = min([zone_size, raster_size])
            print('cell size is {}'.format(env.cellSize))

        # I tested and there is no need to resample the raster being summarized. It will be resampled correctly
        # internally in the following tool given that the necessary environments are set above (cell size, snap).
        # # in_value_raster = arcpy.Resample_management(in_value_raster, 'in_value_raster_resampled', CELL_SIZE)

        # ---RUN STATS---------------------------------------------------------------------------------------------
        if not is_thematic:
            arcpy.AddMessage("Calculating Zonal Statistics...")
            if 'elevation' in rename_tag:
                temp_entire_table = arcpy.sa.ZonalStatisticsAsTable(zone_raster, zone_field, in_value_raster,
                                                                    'temp_zonal_table', 'DATA', 'ALL')
            else:
                temp_entire_table = arcpy.sa.ZonalStatisticsAsTable(zone_raster, zone_field, in_value_raster,
                                                                'temp_zonal_table', 'DATA', 'MEAN')


        # POST-PROCESSING OUTPUT-----------------------------------------------------------------------------------
        if is_thematic:
            # for some reason env.cellSize doesn't work
            # calculate/doit
            arcpy.AddMessage("Tabulating areas...")
            temp_entire_table = arcpy.sa.TabulateArea(zone_raster, zone_field, in_value_raster, 'Value',
                                                      'temp_area_table', processing_cell_size = env.cellSize)
            # TabulateArea capitalizes the zone for some annoying reason and ArcGIS is case-insensitive to field names
            # so we have this work-around:
            zone_field_t = '{}_t'.format(zone_field)
            DM.AddField(temp_entire_table, zone_field_t, 'TEXT', field_length = 20)
            expr = '!{}!'.format(zone_field.upper())
            DM.CalculateField(temp_entire_table, zone_field_t, expr, 'PYTHON')
            DM.DeleteField(temp_entire_table, zone_field.upper())
            DM.AlterField(temp_entire_table, zone_field_t, zone_field, clear_field_alias=True)

            # replaces join to Zonal Stats in previous versions of tool
            # no joining, just calculate the area/count from what's produced by TabulateArea
            arcpy.AddField_management(temp_entire_table, 'AREA', 'DOUBLE')
            arcpy.AddField_management(temp_entire_table, 'COUNT', 'DOUBLE')

            cursor_fields = ['AREA', 'COUNT']
            value_fields = [f.name for f in arcpy.ListFields(temp_entire_table, 'VALUE*')]
            cursor_fields.extend(value_fields)
            with arcpy.da.UpdateCursor(temp_entire_table, cursor_fields) as uCursor:
                for uRow in uCursor:
                    area, count, value_fields = uRow[0], uRow[1], uRow[2:]
                    area = sum(value_fields)
                    count = round(area / (int(env.cellSize) * int(env.cellSize)), 0)
                    new_row = [area, count] + value_fields
                    uCursor.updateRow(new_row)

        arcpy.AddMessage("Refining output table...")

        arcpy.AddField_management(temp_entire_table, 'datacoveragepct', 'DOUBLE')
        arcpy.AddField_management(temp_entire_table, 'ORIGINAL_COUNT', 'LONG')

        # calculate datacoveragepct by comparing to original areas in zone raster
        # alternative to using JoinField, which is prohibitively slow if zones exceed hu12 count
        zone_raster_dict = {row[0]: row[1] for row in arcpy.da.SearchCursor(zone_raster, [zone_field, 'Count'])}
        temp_entire_table_dict = {row[0]: row[1] for row in
                                  arcpy.da.SearchCursor(temp_entire_table, [zone_field, 'COUNT'])}

        sum_cell_area = float(env.cellSize) * float(env.cellSize)
        orig_cell_area = zone_size * zone_size

        with arcpy.da.UpdateCursor(temp_entire_table, [zone_field, 'datacoveragepct', 'ORIGINAL_COUNT']) as cursor:
            for uRow in cursor:
                key_value, data_pct, count_orig = uRow
                count_orig = zone_raster_dict[key_value]
                if key_value in temp_entire_table_dict:
                    count_summarized = temp_entire_table_dict[key_value]
                    data_pct = 100 * float((count_summarized * sum_cell_area) / (count_orig * orig_cell_area))
                else:
                    data_pct = None
                cursor.updateRow((key_value, data_pct, count_orig))

        # Refine the output
        refine_zonal_output(temp_entire_table)

        # in order to add vector capabilities back, need to do something with this
        # right now we just can't fill in polygon zones that didn't convert to raster in our system
        stats_result = lagosGIS.one_in_one_out(temp_entire_table, zone_fc, zone_field, out_table)

        # Convert "datacoveragepct" and "ORIGINAL_COUNT" values to 0 for zones with no metrics calculated
        with arcpy.da.UpdateCursor(out_table,
                                   [zone_field, 'datacoveragepct', 'ORIGINAL_COUNT', 'CELL_COUNT']) as u_cursor:
            for row in u_cursor:
                # data_coverage pct to 0
                if row[1] is None:
                    row[1] = 0
                # original count filled in if a) zone outside raster bounds or b) zone too small to be rasterized
                if row[2] is None:
                    if row[0] in zone_raster_dict:
                        row[2] = zone_raster_dict[row[0]]
                    else:
                        row[2] = 0
                # cell count set to 0
                if row[3] is None:
                    row[3] = 0
                u_cursor.updateRow(row)

        # count whether all zones got an output record or not)
        out_count = int(arcpy.GetCount_management(temp_entire_table).getOutput(0))
        in_count = int(arcpy.GetCount_management(zone_fc).getOutput(0))
        count_diff = in_count - out_count

        # cleanup
        for item in ['temp_zonal_table', temp_entire_table, 'convertraster']:  # don't add zone_raster, orig
            arcpy.Delete_management(item)
        arcpy.ResetEnvironments()
        env.workspace = orig_env  # hope this prevents problems using list of FCs from workspace as batch
        arcpy.CheckInExtension("Spatial")

        return [stats_result, count_diff]

    def unflatten(intermediate_table):
        """
        Uses a weighted average to reconstitute mean value for original zone when provided a stats table based on
        the "flattened" zone regions.
        :param intermediate_table: Output of stats_area_table
        :return: A list containing two elements 1) the output stats table with the final value calculated for each zone
        2) The count of rows missing any data
        """

        # ---SETUP-----------------------------------------------------------------------------------------------
        # names
        flat_zoneid = zone_field
        unflat_zoneid = zone_field.replace('flat', '')
        zone_type = [f.type for f in arcpy.ListFields(zone_fc, flat_zoneid)][0]

        # create table and get fields to add
        unflat_result = DM.CreateTable('in_memory', os.path.basename(out_table))
        editable_fields = [f for f in arcpy.ListFields(intermediate_table)
                           if f.editable and f.name.lower() != flat_zoneid.lower()]

        # populate the new table schema
        DM.AddField(unflat_result, unflat_zoneid, zone_type)
        for f in editable_fields:
            DM.AddField(unflat_result, f.name, f.type, field_length=f.length)

        # ---FIND ORIGINAL VS FLAT ZONE MAPPING-----------------------------------------------------------------
        original_flat = defaultdict(list)
        with arcpy.da.SearchCursor(unflat_table, [unflat_zoneid, flat_zoneid]) as cursor:
            for row in cursor:
                if row[1] not in original_flat[row[0]]:
                    original_flat[row[0]].append(row[1])

        # ---DO THE CALCULATION----------------------------------------------------------------------------------
        # Use CELL_COUNT as weight for means to calculate final values for each zone.
        fixed_fields = [unflat_zoneid, 'ORIGINAL_COUNT', 'CELL_COUNT', 'datacoveragepct']
        other_field_names = [f.name for f in editable_fields if f.name not in fixed_fields]
        i_cursor = arcpy.da.InsertCursor(unflat_result, fixed_fields + other_field_names)  # open output table cursor
        # read component stats
        flat_stats = {r[0]: r[1:] for r in arcpy.da.SearchCursor(
            intermediate_table, [flat_zoneid, 'ORIGINAL_COUNT', 'CELL_COUNT', 'datacoveragepct'] + other_field_names)}

        count_diff = 0
        for zid, unflat_ids in original_flat.items():
            # get values needed to do the math
            valid_unflat_ids = [id for id in unflat_ids if id in flat_stats] # skip flatpolys not rasterized
            area_vec = [flat_stats[id][0] for id in valid_unflat_ids]  # ORIGINAL_COUNT specified in 0 index earlier
            cell_vec = [flat_stats[id][1] for id in valid_unflat_ids]
            coverage_vec = [flat_stats[id][2] for id in valid_unflat_ids]  # datacoveragepct special handling
            stat_vectors_by_id = [flat_stats[id][3:] for id in valid_unflat_ids]  # "the rest", list of lists

            # calc the new summarized values
            original_count = sum(filter(None, area_vec))  # None area is functionally equivalent to 0, all Nones = 0 too
            cell_count = sum(filter(None, cell_vec))
            if cell_count > 0:
                weighted_coverage = sum([a * b for a, b in zip(area_vec, coverage_vec)]) / original_count

                # this calculation accounts for fractional missing values, both kinds (whole zone is no data, or zone
                # was missing some data and had data coverage % < 100). This is done by converting None to 0
                # and by using the cell_count (count of cells with data present)
                # instead of the full zone original_count. You have to do both or the mean will be distorted.
                # hand-verification that this works as intended using test GIS data on was completed 2019-11-01 by NJS
                crossprods = []
                for i in range(0, len(valid_unflat_ids)):
                    crossprods.append([cell_vec[i] * float(s or 0) for s in stat_vectors_by_id[i]])

                weighted_stat_means = []
                for i in range(0, len(other_field_names)):
                    weighted_stat_means.append(sum(zip(*crossprods)[i]) / cell_count)
            else:
                weighted_coverage = 0
                weighted_stat_means = [None] * len(other_field_names)
                count_diff += 1

            new_row = [zid, original_count, cell_count, weighted_coverage] + weighted_stat_means
            i_cursor.insertRow(new_row)
        del i_cursor

        DM.Delete(intermediate_table)

        return [unflat_result, count_diff]

    def rename_to_standard(table):
        """Construct output variable names from the rename_tag, units, and zone feature class name.
        Substitutes variable name parts from the mappings in geo_metric_provenance.csv if the variables
        are to fit the LAGOS-US standard."""
        arcpy.AddMessage("Renaming.")
        # datacoverage just gets tag
        new_datacov_name = '{}_datacoveragepct'.format(rename_tag)
        lagosGIS.rename_field(table, 'datacoveragepct', new_datacov_name, deleteOld=True)

        if not is_thematic:
            if 'elevation' in rename_tag:
                new_mean_name = '{}_mean_{}'.format(rename_tag, units).rstrip('_')
                lagosGIS.rename_field(table, 'MEAN', new_mean_name, deleteOld=True)

                new_min_name = '{}_min_{}'.format(rename_tag, units).rstrip('_')
                lagosGIS.rename_field(table, 'MIN', new_min_name, deleteOld=True)

                new_max_name = '{}_max_{}'.format(rename_tag, units).rstrip('_')
                lagosGIS.rename_field(table, 'MAX', new_max_name, deleteOld=True)

                new_sd_name = '{}_sd_{}'.format(rename_tag, units).rstrip('_')
                lagosGIS.rename_field(table, 'STD', new_sd_name, deleteOld=True)
            else:
                new_mean_name = '{}_{}'.format(rename_tag, units).rstrip('_')  # if no units, just rename_tag
                lagosGIS.rename_field(table, 'MEAN', new_mean_name, deleteOld=True)

        else:
            # look up the values based on the rename tag
            geo_file = os.path.abspath('../geo_metric_provenance.csv')
            with open(geo_file) as csv_file:
                reader = csv.DictReader(csv_file)
                mapping = {row['subgroup_original_code']: row['subgroup']
                           for row in reader if row['main_feature'] and row['main_feature'] in rename_tag}
                print(mapping)

            # update them
            for old, new in mapping.items():
                old_fname = 'VALUE_{}_pct'.format(old)
                new_fname = '{}_{}_pct'.format(rename_tag, new)
                if arcpy.ListFields(table, old_fname):
                    try:
                        # same problem with AlterField limit of 31 characters here.
                        DM.AlterField(table, old_fname, new_fname, clear_field_alias=True)
                    except:
                        lagosGIS.rename_field(table, old_fname, new_fname, deleteOld=True)
        return table

    # ---RUN ------------------------------------------------------------------------------------------------------
    # Determine whether user provided "flattened zones" that need re-constitution and run stats
    if unflat_table:
        if not arcpy.Exists(unflat_table):
            raise Exception('Unflat_table must exist.')
        intermediate_stats = stats_area_table(out_table='intermediate_stats')
        named_as_original = unflatten(intermediate_stats[0])
    else:
        named_as_original = stats_area_table(out_table='named_as_original')

    # Rename all fields to match desired output, if elected
    if rename_tag:
        named_as_standard = rename_to_standard(named_as_original[0])
        out_table = DM.CopyRows(named_as_standard, out_table)
    else:
        out_table = DM.CopyRows(named_as_original[0], out_table)

    # Check counts and alert user if there are fewer zones in the output than were in the input
    total_count_diff = named_as_original[1]
    if total_count_diff > 0:
        warn_msg = ("WARNING: {0} zones have null zonal statistics. There are 2 possible reasons:\n"
                    "1) Presence of zones that are fully outside the extent of the raster summarized.\n"
                    "2) Zones are too small relative to the raster resolution.".format(total_count_diff))
        arcpy.AddWarning(warn_msg)

    # Clean up
    arcpy.SetLogHistory(True)
    return out_table


def main():
    zone_fc = arcpy.GetParameterAsText(0)
    zone_field = arcpy.GetParameterAsText(1)
    unflat_table = arcpy.GetParameterAsText(2)
    in_value_raster = arcpy.GetParameterAsText(3)
    is_thematic = arcpy.GetParameter(4)  # boolean
    out_table = arcpy.GetParameterAsText(5)
    rename_tag = arcpy.GetParameterAsText(6)  # optional
    units = arcpy.GetParameterAsText(7)  # optional
    calc(zone_fc, zone_field, in_value_raster, out_table, is_thematic, unflat_table,
         rename_tag, units)


if __name__ == '__main__':
    main()