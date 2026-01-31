#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, render_template, abort, redirect, url_for
import shortuuid
import os
import json
import datetime
import logging
import pandas as pd
from io import StringIO
import urllib.parse
import re

app = Flask(__name__)

DEFAULT_PORT = 5001

# Directory to store protocol files
PROTOCOL_DIR = 'protocols'
if not os.path.exists(PROTOCOL_DIR):
    os.makedirs(PROTOCOL_DIR)

chart_config = [{
    'csv_title': 'allowed_charging_current',
    'label':     'Erlaubter Ladestrom (mA)',
}, {
    'csv_title': 'cp_pwm_duty_cycle',
    'label':     'CP PWM (% Duty Cycle)',
    'edit_func':  lambda df: list(map(lambda v: v/10.0, df)),
}, {
    'csv_title': 'iec61851_state',
    'label':     'IEC61851 State',
}, {
    'csv_title': 'power',
    'label':     'Leistung (W)',
}, {
    'csv_title': 'current_0',
    'label':     'Strom L1 (mA)',
}, {
    'csv_title': 'current_1',
    'label':     'Strom L2 (mA)',
}, {
    'csv_title': 'current_2',
    'label':     'Strom L3 (mA)',
}, { # old title
    'csv_title': 'resistance_cp_pe',
    'label':     'Widerstand CP/PE (Ohm)',
    'hidden':    True
}, { # new title
    'csv_title': 'CP/PE',
    'label':     'Widerstand CP/PE (Ohm)',
    'hidden':    True
}, {
    'csv_title': 'contactor_state',
    'label':     'Zustand Schütz',
    'hidden':    True
}, {
    'csv_title': 'contactor_error',
    'label':     'Fehlerzustand Schütz',
    'hidden':    True
}, {
    'csv_title': 'phase_0_active',
    'label':     'Phase 0 Aktiv',
    'hidden':    True
}, {
    'csv_title': 'phase_1_active',
    'label':     'Phase 1 Aktiv',
    'hidden':    True
}, {
    'csv_title': 'phase_2_active',
    'label':     'Phase 2 Aktiv',
    'hidden':    True
}, {
    'csv_title': 'phase_0_connected',
    'label':     'Phase 0 Verbunden',
    'hidden':    True
}, {
    'csv_title': 'phase_1_connected',
    'label':     'Phase 1 Verbunden',
    'hidden':    True
}, {
    'csv_title': 'phase_2_connected',
    'label':     'Phase 2 Verbunden',
    'hidden':    True
}, {
    'csv_title': 'time_since_state_change',
    'label':     'Zeit seit Zustandswechsel',
    'hidden':    True
}, { # old title
    'csv_title': 'voltage_plus_12v',
    'label':     'Spannung +12V',
    'hidden':    True
}, {
    'csv_title': 'voltage_minus_12v',
    'label':     'Spannung -12V',
    'hidden':    True
}]

def extract_real_timestamp(before_protocol_log, first_millis):
    if not before_protocol_log or first_millis is None:
        return None

    # Find the last timestamp before CSV data starts
    timestamp_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})'
    matches = re.findall(timestamp_pattern, before_protocol_log)

    if not matches:
        return None

    # Use the last timestamp found (closest to CSV start)
    last_match = matches[-1]
    timestamp_str = f"{last_match[0]}.{last_match[1]}"

    try:
        # Parse the timestamp
        real_timestamp = datetime.datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')

        # Calculate the offset between real time and millis
        # millis is milliseconds since microcontroller boot
        millis_as_datetime = datetime.datetime.fromtimestamp(first_millis / 1000)
        offset = real_timestamp - millis_as_datetime

        return {
            'real_timestamp': real_timestamp,
            'offset': offset,
            'first_millis': first_millis
        }
    except ValueError:
        return None

def convert_millis_to_real_time(millis_values, timestamp_info):
    if not timestamp_info:
        # Fallback to original behavior (fake timestamps)
        return [datetime.datetime.fromtimestamp(v/1000).strftime('%H:%M:%S') for v in millis_values]

    real_timestamps = []
    for millis in millis_values:
        # Convert millis to datetime and add the real time offset
        millis_datetime = datetime.datetime.fromtimestamp(millis / 1000)
        real_datetime = millis_datetime + timestamp_info['offset']
        real_timestamps.append(real_datetime.strftime('%H:%M:%S'))

    return real_timestamps

# Route for the main page
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # upload file flask
        f = request.files.get('file')

        uuid = shortuuid.uuid()
        file_path = os.path.join(PROTOCOL_DIR, uuid)
        f.save(file_path)

        return redirect('/' + uuid)

    # Render the form with available languages
    return render_template('index.html')

# Route to view a specific protocol by its ID - shows configuration page
@app.route('/<uuid>')
def view_id(uuid):
    # Create the file path for the protocol
    file_path = os.path.join(PROTOCOL_DIR, uuid)
    if not os.path.exists(file_path):
        abort(404)  # Return a 404 error if the protocol does not exist

    data = open(file_path, 'r').read().split('\n\n')
    try:
        is_report = (len(data[0]) < 100) and ('Scroll down for event log!' in data[0])
    except:
        abort(400)

    if is_report:
        return handle_report(data)
    else:
        # Check if configuration parameter is provided
        config_param = request.args.get('configuration')
        if config_param:
            return handle_protocol_chart(data, config_param)
        else:
            return handle_protocol_config(data, uuid)

# Route to show the chart with selected columns
@app.route('/<uuid>/chart')
def view_chart(uuid):
    # Create the file path for the protocol
    file_path = os.path.join(PROTOCOL_DIR, uuid)
    if not os.path.exists(file_path):
        abort(404)  # Return a 404 error if the protocol does not exist

    data = open(file_path, 'r').read().split('\n\n')
    try:
        is_report = (len(data[0]) < 100) and ('Scroll down for event log!' in data[0])
    except:
        abort(400)

    if is_report:
        return handle_report(data)
    else:
        config_param = request.args.get('configuration', '')
        return handle_protocol_chart(data, config_param)

# Coredump parsing constants and helpers (based on esp32-firmware/software/coredump.py)
TF_COREDUMP_PREFIX = b"___tf_coredump_info_start___"
TF_COREDUMP_SUFFIX = b"___tf_coredump_info_end___"
EXTRA_INFO_HEADER = b'\xA5\x02\x00\x00ESP_EXTRA_INFO'

# Exception cause dictionary from Xtensa ISA Reference Manual
XTENSA_EXCEPTION_CAUSE_DICT = {
    0: ('IllegalInstructionCause', 'Illegal instruction'),
    1: ('SyscallCause', 'SYSCALL instruction'),
    2: ('InstructionFetchErrorCause', 'Processor internal physical address or data error during instruction fetch'),
    3: ('LoadStoreErrorCause', 'Processor internal physical address or data error during load or store'),
    4: ('Level1InterruptCause', 'Level-1 interrupt as indicated by set level-1 bits in the INTERRUPT register'),
    5: ('AllocaCause', 'MOVSP instruction, if caller\'s registers are not in the register file'),
    6: ('IntegerDivideByZeroCause', 'QUOS, QUOU, REMS, or REMU divisor operand is zero'),
    8: ('PrivilegedCause', 'Attempt to execute a privileged operation when CRING != 0'),
    9: ('LoadStoreAlignmentCause', 'Load or store to an unaligned address'),
    12: ('InstrPIFDataErrorCause', 'PIF data error during instruction fetch'),
    13: ('LoadStorePIFDataErrorCause', 'Synchronous PIF data error during LoadStore access'),
    14: ('InstrPIFAddrErrorCause', 'PIF address error during instruction fetch'),
    15: ('LoadStorePIFAddrErrorCause', 'Synchronous PIF address error during LoadStore access'),
    16: ('InstTLBMissCause', 'Error during Instruction TLB refill'),
    17: ('InstTLBMultiHitCause', 'Multiple instruction TLB entries matched'),
    18: ('InstFetchPrivilegeCause', 'An instruction fetch referenced a virtual address at a ring level less than CRING'),
    20: ('InstFetchProhibitedCause', 'An instruction fetch referenced a page mapped with an attribute that does not permit instruction fetch'),
    24: ('LoadStoreTLBMissCause', 'Error during TLB refill for a load or store'),
    25: ('LoadStoreTLBMultiHitCause', 'Multiple TLB entries matched for a load or store'),
    26: ('LoadStorePrivilegeCause', 'A load or store referenced a virtual address at a ring level less than CRING'),
    28: ('LoadProhibitedCause', 'A load referenced a page mapped with an attribute that does not permit loads'),
    29: ('StoreProhibitedCause', 'A store referenced a page mapped with an attribute that does not permit stores'),
    32: ('Coprocessor0Disabled', 'Coprocessor 0 instruction when cp0 disabled'),
    33: ('Coprocessor1Disabled', 'Coprocessor 1 instruction when cp1 disabled'),
    34: ('Coprocessor2Disabled', 'Coprocessor 2 instruction when cp2 disabled'),
    35: ('Coprocessor3Disabled', 'Coprocessor 3 instruction when cp3 disabled'),
    36: ('Coprocessor4Disabled', 'Coprocessor 4 instruction when cp4 disabled'),
    37: ('Coprocessor5Disabled', 'Coprocessor 5 instruction when cp5 disabled'),
    38: ('Coprocessor6Disabled', 'Coprocessor 6 instruction when cp6 disabled'),
    39: ('Coprocessor7Disabled', 'Coprocessor 7 instruction when cp7 disabled'),
    0xFFFF: ('InvalidCauseRegister', 'Invalid EXCCAUSE register value or current task is broken and was skipped'),
    # ESP panic pseudo reasons (XCHAL_EXCCAUSE_NUM = 64)
    64: ('UnknownException', 'Unknown exception'),
    65: ('DebugException', 'Unhandled debug exception'),
    66: ('DoubleException', 'Double exception'),
    67: ('KernelException', 'Unhandled kernel exception'),
    68: ('CoprocessorException', 'Coprocessor exception'),
    69: ('InterruptWDTTimeoutCPU0', 'Interrupt watchdog timeout on CPU0'),
    70: ('InterruptWDTTimeoutCPU1', 'Interrupt watchdog timeout on CPU1'),
    71: ('CacheError', 'Cache disabled but cached memory region accessed'),
}

def extra_info_reg_name(reg):
    return {
        232: 'EXCCAUSE',
        238: 'EXCVADDR',
        177: 'EPC1',
        178: 'EPC2',
        179: 'EPC3',
        180: 'EPC4',
        181: 'EPC5',
        182: 'EPC6',
        183: 'EPC7',
        194: 'EPS2',
        195: 'EPS3',
        196: 'EPS4',
        197: 'EPS5',
        198: 'EPS6',
        199: 'EPS7'
    }.get(reg, None)

def parse_coredump(coredump_blocks):
    """
    Parse coredump data from debug report blocks.
    Returns a dictionary with parsed information or None if no valid coredump.
    """
    import base64

    result = {
        'has_coredump': False,
        'firmware_name': None,
        'firmware_commit_id': None,
        'crashed_task_handle': None,
        'exception_cause': None,
        'registers': {},
        'raw_dump': None,
        'error': None
    }

    # Join blocks and extract base64 data
    raw_text = '\n\n'.join(coredump_blocks)

    # Check for "no coredump" message
    if 'Es befindet sich kein Coredump' in raw_text:
        return result

    # Extract base64 data
    try:
        if 'base64,' in raw_text:
            # Format: data:application/octet-stream;base64,...
            b64_data = raw_text.split('base64,')[-1].strip()
        else:
            # Raw base64 data (e.g., starts with ELF header: f0VMRg... = \x7fELF)
            b64_data = raw_text.strip()

        coredump_bytes = base64.b64decode(b64_data)

        # Fix ELF header if needed
        if not coredump_bytes.startswith(b'\x7fELF'):
            coredump_bytes = b'\x7fELF' + coredump_bytes

        result['has_coredump'] = True
        result['raw_dump'] = raw_text
    except Exception as e:
        result['error'] = f'Failed to decode base64: {str(e)}'
        return result

    # Extract TF coredump info JSON
    try:
        start_idx = coredump_bytes.find(TF_COREDUMP_PREFIX)
        if start_idx >= 0:
            end_idx = coredump_bytes.find(TF_COREDUMP_SUFFIX, start_idx)
            if end_idx >= 0:
                tf_json_bytes = coredump_bytes[start_idx + len(TF_COREDUMP_PREFIX):end_idx]
                tf_data = json.loads(tf_json_bytes.decode('utf-8', errors='ignore'))

                result['firmware_name'] = tf_data.get('firmware_file_name')
                result['firmware_commit_id'] = tf_data.get('firmware_commit_id')
    except Exception as e:
        result['error'] = f'Failed to parse TF coredump info: {str(e)}'

    # Extract ESP32 extra info (registers)
    try:
        extra_info_idx = coredump_bytes.find(EXTRA_INFO_HEADER)
        if extra_info_idx >= 0 and (len(coredump_bytes) - extra_info_idx >= len(EXTRA_INFO_HEADER) + 2 + 108):
            # Skip header and two bytes
            extra_info_idx += len(EXTRA_INFO_HEADER) + 2
            extra_info = coredump_bytes[extra_info_idx:extra_info_idx + 108]

            # First 4 bytes are crashed task handle
            result['crashed_task_handle'] = hex(int.from_bytes(extra_info[:4], byteorder='little'))

            # Parse register values
            for i in range(4, len(extra_info), 8):
                reg_id = int.from_bytes(extra_info[i:i+4], byteorder='little')
                if reg_id == 0:
                    continue

                reg_value = int.from_bytes(extra_info[i+4:i+8], byteorder='little')
                reg_name = extra_info_reg_name(reg_id)

                if reg_name:
                    result['registers'][reg_name] = hex(reg_value)

                    # If this is EXCCAUSE, also add the exception description
                    if reg_name == 'EXCCAUSE' and reg_value in XTENSA_EXCEPTION_CAUSE_DICT:
                        cause_name, cause_desc = XTENSA_EXCEPTION_CAUSE_DICT[reg_value]
                        result['exception_cause'] = {
                            'code': reg_value,
                            'name': cause_name,
                            'description': cause_desc
                        }
    except Exception as e:
        if not result['error']:
            result['error'] = f'Failed to parse ESP32 extra info: {str(e)}'

    return result

def handle_report(data):
    try:
        # Fix json syntax error that can happen in report
        data_json     = data[1].replace('": ,', '": {},')
        report_json   = json.loads(data_json)
    except:
        report_json   = {}

    try:
        report_log    = data[2]
    except:
        report_log    = ""

    inside_trace = False
    report_trace_blocks = []
    inside_dump = False
    report_dump_blocks = []

    for block in data[3:]:
        if '___TRACE_LOG_START___' in block:
            inside_trace = True
        elif '___CORE_DUMP_START___' in block:
            inside_trace = False
            inside_dump = True
        elif inside_trace:
            report_trace_blocks.append(block)
        elif inside_dump:
            report_dump_blocks.append(block)

    if len(report_dump_blocks) == 0:
        report_dump_blocks.append('Es befindet sich kein Coredump im Debug-Report')

    # Parse module sections from trace log
    # Sections are delimited by __begin_MODULE__ and __end_MODULE__
    trace_modules = {}
    trace_remaining = []
    full_trace = '\n\n'.join(report_trace_blocks)

    # Find all module sections using regex
    module_pattern = re.compile(r'__begin_(\w+)__(.*?)__end_\1__', re.DOTALL)
    last_end = 0

    for match in module_pattern.finditer(full_trace):
        module_name = match.group(1)
        module_content = match.group(2).strip()

        # Collect text before this module (not part of any module)
        before_text = full_trace[last_end:match.start()].strip()
        if before_text:
            trace_remaining.append(before_text)

        if module_content:
            trace_modules[module_name] = module_content

        last_end = match.end()

    # Collect any remaining text after the last module
    after_text = full_trace[last_end:].strip()
    if after_text:
        trace_remaining.append(after_text)

    # If no modules found, use the full trace as remaining
    if not trace_modules and not trace_remaining:
        if report_trace_blocks and report_trace_blocks[0] != 'Es befindet sich kein Trace-Log im Debug-Report':
            trace_remaining = [full_trace]

    # Parse coredump for structured display
    coredump_info = parse_coredump(report_dump_blocks)

    data = {
        'report_json':  report_json,
        'report_log':   report_log,
        'report_trace': '\n\n'.join(trace_remaining) if trace_remaining else '',
        'trace_modules': trace_modules,
        'coredump_info': coredump_info,
    }

    # Render the protocol with syntax highlighting
    return render_template('report.html', data = data)

def parse_protocol_data(data):
    # Parse protocol data and extract available columns
    try:
        before_protocol_json = json.loads(data[0])
    except:
        before_protocol_json = {}
    try:
        before_protocol_log  = data[1]
    except:
        before_protocol_log  = ""
    try:
        protocol_csv         = data[2]
    except:
        protocol_csv         = ""
    try:
        after_protocol_json  = json.loads(data[3])
    except:
        after_protocol_json  = {}
    try:
        after_protocol_log   = data[4]
    except:
        after_protocol_log   = ""

    try:
        # Get timestamp data from CSV
        df = pd.read_csv(StringIO(protocol_csv))

        # Extract real timestamp info from the log
        first_millis = df['millis'].iloc[0] if len(df) > 0 else None
        timestamp_info = extract_real_timestamp(before_protocol_log, first_millis)

        # Convert millis to real timestamps
        millis = convert_millis_to_real_time(df['millis'].tolist(), timestamp_info)
    except:
        millis = []
        df = None
        timestamp_info = None

    # Get available columns for dynamic selection
    available_columns = []
    if df is not None:
        # Filter out placeholder columns (all uppercase) and 'millis' column
        available_columns = [col for col in df.columns
                           if col != 'millis' and not col.isupper()]

    return {
        'before_protocol_json': before_protocol_json,
        'before_protocol_log': before_protocol_log,
        'protocol_csv': protocol_csv,
        'after_protocol_json': after_protocol_json,
        'after_protocol_log': after_protocol_log,
        'df': df,
        'millis': millis,
        'available_columns': available_columns,
        'timestamp_info': timestamp_info,
        'has_real_timestamps': timestamp_info is not None
    }

def handle_protocol_config(data, uuid):
    # Show configuration page where user can select columns
    parsed = parse_protocol_data(data)

    # Create column metadata for the configuration page
    column_metadata = []

    # Add predefined columns from chart_config
    predefined_columns = {cc['csv_title']: cc for cc in chart_config}

    # First, add predefined columns in the order they appear in chart_config
    for cc in chart_config:
        col_name = cc['csv_title']
        if col_name in parsed['available_columns']:
            column_metadata.append({
                'name': col_name,
                'label': cc.get('label', col_name),
                'predefined': True,
                'hidden_by_default': cc.get('hidden', False)
            })

    # Then, add non-predefined columns
    for col_name in parsed['available_columns']:
        if col_name not in predefined_columns:
            # Check if column is numeric
            is_numeric = True
            if parsed['df'] is not None:
                try:
                    col = parsed['df'][col_name]
                    is_numeric = col.dtype not in ['object', 'string']
                except:
                    is_numeric = False

            if is_numeric:
                column_metadata.append({
                    'name': col_name,
                    'label': col_name,
                    'predefined': False,
                    'hidden_by_default': True
                })

    config_data = {
        'uuid': uuid,
        'column_metadata': column_metadata,
        'before_protocol_json': parsed['before_protocol_json'],
        'after_protocol_json': parsed['after_protocol_json'],
        'before_protocol_log': parsed['before_protocol_log'],
        'after_protocol_log': parsed['after_protocol_log'],
    }

    return render_template('protocol_config.html', data=config_data)

def handle_protocol_chart(data, config_param):
    # Show chart with only selected columns
    parsed = parse_protocol_data(data)

    # Decode configuration parameter
    selected_columns = []
    if config_param:
        try:
            # Decode URL-encoded column names
            selected_columns = urllib.parse.unquote(config_param).split(',')
            selected_columns = [col.strip() for col in selected_columns if col.strip()]
        except:
            selected_columns = []

    # If no columns selected, show default visible columns
    if not selected_columns:
        selected_columns = [cc['csv_title'] for cc in chart_config if not cc.get('hidden', False)]

    dataset = []

    # Process only selected columns
    predefined_columns = {cc['csv_title']: cc for cc in chart_config}

    for col_name in selected_columns:
        if parsed['df'] is not None and col_name in parsed['df'].columns:
            try:
                col = parsed['df'][col_name]

                # Use predefined config if available
                if col_name in predefined_columns:
                    cc = predefined_columns[col_name]
                    new_data = {
                        'label': cc.get('label', col_name),
                        'csv_column': col_name
                    }

                    edit_func = cc.get('edit_func')
                    if edit_func:
                        new_data['data'] = edit_func(col)
                    else:
                        new_data['data'] = list(col)
                else:
                    # Skip non-numeric columns
                    if col.dtype in ['object', 'string']:
                        continue

                    new_data = {
                        'label': col_name,
                        'csv_column': col_name,
                        'data': list(col)
                    }

                dataset.append(new_data)
            except Exception as e:
                print(f"Error processing column {col_name}: {e}")
                pass

    # Show 0 values as 0.01 since chart.js can't show 0 in log view...
    # see https://github.com/chartjs/Chart.js/issues/9629
    for d in dataset:
        d['data'] = list(map(lambda v: 0.01 if v == 0 else v, d['data']))

    # Create list of human-readable column labels for display
    selected_column_labels = [d['label'] for d in dataset]

    chart_data = {
        'chart': {'labels': parsed['millis'], 'datasets': dataset},
        'selected_columns': selected_columns,
        'selected_column_labels': selected_column_labels,
        'configuration': config_param,
        'before_protocol_json': parsed['before_protocol_json'],
        'after_protocol_json': parsed['after_protocol_json'],
        'before_protocol_log': parsed['before_protocol_log'],
        'after_protocol_log': parsed['after_protocol_log'],
    }

    # Render the protocol with syntax highlighting
    return render_template('protocol.html', data=chart_data)

def handle_protocol(data):
    # Legacy function - now redirects to configuration page
    # This is kept for backward compatibility, but should not be used
    return handle_protocol_chart(data, '')

logging.basicConfig(filename='debug.log', level=logging.DEBUG, format="[%(asctime)s %(levelname)-8s%(filename)s:%(lineno)s] %(message)s", datefmt='%Y-%m-%d %H:%M:%S')
port = int(os.environ.get('PORT', DEFAULT_PORT))
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=port)
