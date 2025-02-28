# filename: lake_connectivity_classification.py
# author: Nicole J Smith
# version: 2.0
# LAGOS module(s): LOCUS
# tool type: re-usable (ArcGIS Toolbox)

import os
import arcpy
from . import NHDNetwork


def classify(nhd_gdb, output_table):
    """
    Classifies lakes based on freshwater hydrologic connectivity. The classification is performed twice to obtain both
    the maximum and the permanent-only (intermittent & ephemeral flowlines excluded) connectivity. Additionally, after
    calculating both the maximum and permanent-only connectivity for the lake, it assigns 'Y' or "N' to the
    lake_connectivity_fluctuates flag. This tool relies on NHDNetwork.classify_waterbody_connectivity.

    The four lake connectivity classifications:
        Isolated--traces in both directions were empty (no network connectivity)
        Headwater--only the downstream trace contains network connectivity
        DrainageLk--traces either in both directions or only the upstream trace has network connectivity, and the
        upstream trace contains the identifier of one or more lakes over 10 hectares (as defined by the NHDNetwork
        class)
        Drainage--all lakes that do not meet one of the prior three criteria; traces either in both directions or only
        the upstream trace has network connectivity

    This tool will generate the following fields in a new table, using the lagoslakeid as the main identifier:
    lake_connectivity_class:        maximum hydrologic connectivity class of the focal lake determined from the NHD
                                    network considering both permanent and intermittent-ephemeral flow
    lake_connectivity_permanent:    hydrologic connectivity class of the focal lake determined from the NHD network
                                    considering only permanent flow
    lake_connectivity_fluctuates:   indicates whether the lake connectivity classification depends on non-permanent flow

    :param nhd_gdb: The file path for a high-resolution NHD or NHDPlus geodatabase for a single subregion/HU4.
    :param output_table: The path to save the output table to (suggested: FileGDB table)
    :return: The output table path
    """
    nhd_network = NHDNetwork.NHDNetwork(nhd_gdb)
    nhd_network.define_lakes(strict_minsize=False, force_lagos=True)
    waterbody_ids = list(nhd_network.lakes_areas.keys())
    nhd_network.define_lakes(strict_minsize=False, force_lagos=False)

    arcpy.AddMessage("Calculating all connectivity...")
    # calc all connectivity, see NHDNetwork script for details
    conn_class = {id:nhd_network.classify_waterbody_connectivity(id) for id in waterbody_ids}

    # permanent only
    arcpy.AddMessage("Calculating permanent connectivity...")
    nhd_network.drop_intermittent_flow()
    conn_permanent = {id:nhd_network.classify_waterbody_connectivity(id) for id in waterbody_ids}

    # make an output table
    arcpy.AddMessage("Saving output...")
    output = arcpy.CreateTable_management(os.path.dirname(output_table), os.path.basename(output_table))
    arcpy.AddField_management(output, 'lake_connectivity_class', 'TEXT', field_length=10)
    arcpy.AddField_management(output, 'lake_connectivity_permanent', 'TEXT', field_length=10)
    arcpy.AddField_management(output, 'lake_connectivity_fluctuates', 'TEXT', field_length=2)
    insert_fields = ['lake_connectivity_class',
                     'lake_connectivity_permanent',
                     'lake_connectivity_fluctuates']

    arcpy.AddMessage("Writing output...")

    # get all the ids
    arcpy.AddField_management(output, 'Permanent_Identifier', 'TEXT', field_length=40)
    write_id_names = ['Permanent_Identifier']
    if arcpy.ListFields(nhd_network.waterbody, 'lagoslakeid'):
        write_id_names.append('lagoslakeid')
        arcpy.AddField_management(output, 'lagoslakeid', 'LONG')
    if arcpy.ListFields(nhd_network.waterbody, 'nhd_merge_id'):
        write_id_names.append('nhd_merge_id')
        arcpy.AddField_management(output, 'nhd_merge_id', 'TEXT', field_length=100)

    write_id_map = {r[0]: list(r)
                    for r in arcpy.da.SearchCursor(nhd_network.waterbody, write_id_names)}

    # write the table
    cursor_fields = write_id_names + insert_fields
    rows = arcpy.da.InsertCursor(output, cursor_fields)

    for id in waterbody_ids:
        write_ids = write_id_map[id]
        if conn_class[id] == conn_permanent[id]:
            fluctuates = 'N'
        else:
            fluctuates = 'Y'

        row = write_ids + [conn_class[id], conn_permanent[id], fluctuates]
        rows.insertRow(row)
    return output


def main():
    nhd_gdb = arcpy.GetParameterAsText(0)
    output_table = arcpy.GetParameterAsText(1)

    classify(nhd_gdb, output_table)


if __name__ == '__main__':
    main()
