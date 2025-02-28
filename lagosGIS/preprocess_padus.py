# filename: preprocess_padus.py
# author: Nicole J Smith
# version: 2.0
# LAGOS module(s): GEO
# tool type: re-usable (ArcGIS Toolbox)


import time
import arcpy
from arcpy import management as DM
import lagosGIS


def preprocess(padus_combined_fc, output_fc):
    """
    The Protected Areas Database of the U.S. feature class contains overlapping polygons representing multiple
    protection types. This tool "flattens" the PADUS2_0Combined_Marined_Fee_Designation_Easement dataset so that the
    Own_Type, GAP_Sts, and IUCN_Cat fields are values are retained, renamed, and filtered for one primary value per
    region according to the following rules:
    Own_Type -> "agency" variable in LAGOS-US. Rule is FeatClass "Fee" > "Easement" > "Marine" > "Designation"
    GAP_Sts -> "gap" . Highest GAP status preferentially retained.
    IUCN_Cat -> "iucn". Lowest number codes preferentially retained, then "Other", last "Unassigned".
    :param padus_combined_fc: The PADUS2_0Combined_Marined_Fee_Designation_Easement dataset from the PADUS database
    :param output_fc: Output feature class to save the result
    :return: Result object for output feature class
    """

    # Prep: Select only the fields needed, remove curves (densify) which prevents problems with geometry
    # that prevents DeleteIdentical based on Shape
    arcpy.env.workspace = 'in_memory'
    padus_fields = ['FeatClass', 'Own_Type', 'GAP_Sts', 'IUCN_Cat']
    padus_select = lagosGIS.select_fields(padus_combined_fc, 'padus_select', padus_fields, convert_to_table=False)
    arcpy.Densify_edit(padus_select, 'OFFSET', max_deviation = '1 Meters')
    arcpy.AddMessage('{} union...'.format(time.ctime()))

    # Self-union to create new features from overlapping regions between polygons
    union = arcpy.Union_analysis([padus_select, padus_select], 'union', 'ALL', cluster_tolerance='1 Meters')

    # Remove full duplicates resulting from self-union before further processing
    fid1 = 'FID_padus_select'
    fid2 = 'FID_padus_select_1'
    padus_fields_1 = padus_fields + [f + '_1' for f in padus_fields]
    padus_fields_1.extend([fid1, fid2])
    arcpy.AddMessage('{} delete identical round 1...'.format(time.ctime()))
    DM.DeleteIdentical(union, padus_fields_1)

    # Setup for new class fields
    new_fields = ['agency', 'gap', 'iucn', 'merge_flag', 'area_m2']
    cursor_fields = sorted(padus_fields_1) + new_fields + ['SHAPE@AREA']
    DM.AddField(union, 'agency', 'TEXT', field_length=5)
    DM.AddField(union, 'gap', 'TEXT', field_length=1)
    DM.AddField(union, 'iucn', 'TEXT', field_length=24)
    DM.AddField(union, 'merge_flag', 'TEXT', field_length=1)
    DM.AddField(union, 'area_m2', 'DOUBLE')

    # Establish rules for class priority for each polygon
    # If polygon was an overlapping region, these rules will select which class value is assigned from the multiple
    # originals, if they were not the same already
    owner_rule = {'Fee': 1, 'Easement': 2, 'Marine': 3, 'Designation': 4}
    iucn_rule = {'Ia': 1,
                 'Ib': 2,
                 'II': 3,
                 'III': 4,
                 'IV': 5,
                 'V': 6,
                 'VI': 7,
                 'Other Conservation Area': 8,
                 'Unassigned': 9}

    # Calculate the new class values according to the rules above
    with arcpy.da.UpdateCursor(union, cursor_fields) as cursor:
        for row in cursor:
            id1, id2, fc1, fc2, gap1, gap2, iucn1, iucn2, own1, own2, agency, gap, iucn, flag, areacalc, areashp = row
            flag = 'N'
            # Take Fee feature class type first, Designation fc type last. Pull owner value from that feature class type
            if owner_rule[fc1] < owner_rule[fc2]:
                agency = own1
            else:
                agency = own2

            # Take most protected GAP value
            gap = min([gap1, gap2])

            # Take numbered IUCN over "other" or "unassigned"; use numbers as priority order
            if iucn_rule[iucn1] < iucn_rule[iucn2]:
                iucn = iucn1
            else:
                iucn = iucn2

            # Set merge flag to 'Y' if any output field contains a value that had to be resolved among multiple
            # original polygons
            if fc1 != fc2 or own1 != own2 or gap1 != gap2 or iucn1 != iucn2:
                flag = 'Y'

            areacalc = areashp

            row = (id1, id2, fc1, fc2, gap1, gap2, iucn1, iucn2, own1, own2, agency, gap, iucn, flag, areacalc, areashp)
            cursor.updateRow(row)

    # Prep for DeleteIdentical: Dispose of polygons under 4 sq. m (they cause trouble, don't effect
    # stats enough to bother) and repair geometry on the rest.
    large_enough = arcpy.Select_analysis(union, 'large_enough', 'area_m2 > 4')
    arcpy.AddMessage('{} repair...'.format(time.ctime()))
    DM.RepairGeometry(large_enough)

    # Sort so that merged polygons are highest/retained in DeleteIdentical
    # Delete identical shapes to end up with just the merged polygons and polygons from non-overlapping regions
    arcpy.AddMessage('{} sort...'.format(time.ctime()))
    sorted_fc = DM.Sort(large_enough, 'sorted_fc', [['merge_flag', 'DESCENDING']])

    arcpy.AddMessage('{} delete identical shape...'.format(time.ctime()))
    DM.DeleteIdentical(sorted_fc, "Shape")
    output_fields = [fid1, fid2] + new_fields
    output_fc = lagosGIS.select_fields(sorted_fc, output_fc, output_fields)

    # Clean up
    for item in [padus_select, union, sorted_fc, large_enough]:
        DM.Delete(item)
    return output_fc


def main():
    padus_combined_fc = arcpy.GetParameterAsText(0)
    output_fc = arcpy.GetParameterAsText(1)
    preprocess(padus_combined_fc, output_fc)


if __name__ == '__main__':
    main()





