# filename: read_job_control
# author: Nicole J Smith
# version: 2.0
# LAGOS module(s): GEO
# tool type: re-usable (NOT in ArcGIS Toolbox)


import csv
import os
import time
import arcpy
import lagosGIS

ARG_NUMBERS = ['Arg1', 'Arg2', 'Arg3', 'Arg4', 'Arg5', 'Arg6', 'Arg7', 'Arg8']


def cook_string(input):
    """
    This function takes a "raw" string contained inside another string and makes it just a plain string.
    :param input: A string with contents that include r'[text'.
    :return: String
    """
    if input.startswith('r\'') and input.endswith('\''):
        result = input[2:-1]
    else:
        result = input
    if result.upper() == 'TRUE':
        result = True
    elif result.upper() == 'FALSE':
        result = False
    return result


def read_job_control(job_control_csv, start_line=-1, end_line=-1, validate=False, validate_args=[]):
    """
    Reads a job control file with the following CSV format: First column contains function name to run. Columns contain
    arguments to use, in order.
    :param job_control_csv: The path to the job control CSV file
    :param start_line: (Optional)The line number (row) to start the job from or a list of line numbers to run. Default
    runs all lines.
    :param end_line: (Optional) The line to end the job from. Default runs all lines.
    :param validate: (Optional) Boolean. Whether to validate the inputs only, do not actually execute commands.
    :param validate_args: (Optional) If validate=True, provide a list of the argument labels to validate. Use
    ['Arg1', 'Arg2', 'Arg3'] etc.
    :return: None
    """

    # Define valid CSV file header
    # Line is sequential integer identifying row number
    # Function is function call without parenthesis i.e. "lagosGIS.lake_density"
    # Arg1-Arg8 provide the arguments to the function, leave missing after last argument needed
    # Output repeats output path/location argument (which has variable position)
    # CSV specifies location for CSV export file
    csv_header = ['Line', 'Function', 'Arg1', 'Arg2', 'Arg3', 'Arg4', 'Arg5', 'Arg6', 'Arg7', 'Arg8', 'Output', 'CSV']

    # Validate inputs
    if validate and not validate_args:
        raise Exception("Provide validation arguments keyword as a list of 'Arg1', 'Arg2', etc.")
    for arg in validate_args:
        if arg not in ARG_NUMBERS:
            raise Exception("Provide validation arguments keyword as a list of 'Arg1', 'Arg2', etc.")

    # Read CSV and filter for line numbers requested in this batch run
    with open(job_control_csv) as csv_file:
        reader = csv.DictReader(csv_file)
        lines = [line for line in reader]
        if not list(lines[0].keys()).sort() == csv_header.sort():
            raise Exception("""CSV file is not in the required format. Please provide a file with the header as follows:
                            \n{}""".format(csv_header))
        if isinstance(start_line, int) and \
                (start_line > 0 or end_line > 0):
            lines = lines[start_line-1:end_line]
        elif isinstance(start_line, list):
            lines = [line for line in lines if int(line['Line']) in start_line]

    # Read the table and compose the calls
    calls = []
    outputs = []
    csv_paths = []
    for line in lines:
        function = cook_string(line['Function'])
        args = []
        # find last non-empty argument
        arg_vals = [line['Arg{}'.format(i)] for i in range(1,9)]
        args_length = arg_vals.index(next(arg for arg in reversed(arg_vals) if arg)) + 1
        for i in range(args_length):
            input_arg = line['Arg{}'.format(i+1)]
            if input_arg:
                args.append(cook_string(input_arg))
            else:
                args.append('')

        output = cook_string(line['Output'])
        csv_path = cook_string(line['CSV'])
        outputs.append(output)
        csv_paths.append(csv_path)
        formatted_args = ','.join(["r'{}'".format(arg) if isinstance(arg, str) else str(arg) for arg in args])
        call = "{}({})".format(function, formatted_args)
        calls.append(call)

        # validate (optional)
        for arg in validate_args:
            check_item = cook_string(line[arg])
            if check_item and not arcpy.Exists(check_item):
                print('WARNING: {} does not exist.'.format(check_item))

    # Call each tool and export the result to CSV
    if not validate:
        exceptions = []
        for call, output, csv_path in zip(calls, outputs, csv_paths):
            output_dir = os.path.dirname(output)
            if not arcpy.Exists(output_dir):
                raise Exception("Provide a valid geodatabase for the output.")
            if not arcpy.Exists(output):
                print(time.ctime())
                print(call)
                try:
                    eval(call)
                    out_folder = os.path.dirname(csv_path)
                    lagosGIS.export_to_csv(output, out_folder, rename_fields=False)
                except Exception as e:
                    exceptions.append(e.message)
                    print('WARNING: {}'.format(e.message))
            else:
                print("{} already exists.".format(output))

            # Keep in_memory workspace from carrying over to the next call
            arcpy.Delete_management('in_memory')

        # Finish
        print("ALL EXCEPTION MESSAGES FROM THIS RUN:----------------")
        for emsg in exceptions:
            print(emsg)

