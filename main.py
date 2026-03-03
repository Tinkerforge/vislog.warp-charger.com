#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, render_template, abort, redirect, url_for
from werkzeug.exceptions import RequestEntityTooLarge
import shortuuid
import os
import sys
import json
import datetime
import logging
import pandas as pd
from io import StringIO
import urllib.parse
import re
import math
import socket
from i18n import get_translations, SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB upload limit

UUID_PATTERN = re.compile(r'^[a-zA-Z0-9]+$')


def _detect_language():
    accept = request.headers.get('Accept-Language', '')
    # Simple parser: look for 'en' or 'de' with highest quality
    best_lang = DEFAULT_LANGUAGE
    best_q = -1
    for part in accept.split(','):
        part = part.strip()
        if ';' in part:
            lang_tag, q_str = part.split(';', 1)
            try:
                q = float(q_str.strip().replace('q=', ''))
            except ValueError:
                q = 0
        else:
            lang_tag = part
            q = 1.0
        lang_tag = lang_tag.strip().split('-')[0].lower()
        if lang_tag in SUPPORTED_LANGUAGES and q > best_q:
            best_lang = lang_tag
            best_q = q
    return best_lang


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    lang = _detect_language()
    return redirect(f'/{lang}/')


# ---------------------------------------------------------------------------
# API doc constants extraction
# ---------------------------------------------------------------------------
def _build_api_constants(locale='de'):
    """Import api_doc_generator modules and build a lookup dict for API field docs.

    Returns a nested dict:
        { "evse/state": {
            "charger_state": {
                "desc": "Description of the field in the given locale",
                "unit": {"abbr": "mA", "name": "Milliampere"} or null,
                "constants": [ {val, desc, version}, ... ]
            },
            ...
          },
          ...
        }

    Every leaf field that has at least a description, a unit, or constants
    is included.  ``_array_members`` and ``_union_*`` sub-dicts follow the
    same per-field shape.
    """
    api_doc_dir = os.path.join(os.path.dirname(__file__), 'api_doc_generator')
    if not os.path.isdir(api_doc_dir):
        return {}

    # Temporarily add api_doc_generator to sys.path so its internal imports work
    prev_path = sys.path.copy()
    sys.path.insert(0, api_doc_dir)
    try:
        from mods import mods  # noqa: imports all 30 module definitions
        from api_doc_common import EType
    except Exception as e:
        print(f"Warning: Could not import api_doc_generator: {e}")
        return {}
    finally:
        sys.path = prev_path

    def _clean(text):
        """Strip HTML tags and collapse whitespace."""
        text = re.sub(r'<[^>]+>', ' ', text).strip()
        return re.sub(r'\s+', ' ', text)

    result = {}

    def _extract_elem(elem, path_prefix, field_name, out):
        """Recursively extract docs from an Elem tree into *out*."""
        entry = {}

        # --- description --------------------------------------------------
        desc_text = elem.desc.get(locale) if elem.desc else None
        if desc_text and desc_text.strip():
            entry['desc'] = _clean(desc_text)

        # --- unit ---------------------------------------------------------
        if elem.unit is not None:
            unit_name = elem.unit.name.get(locale) if elem.unit.name else elem.unit.abbr
            entry['unit'] = {'abbr': elem.unit.abbr, 'name': unit_name}

        # --- constants ----------------------------------------------------
        if elem.constants:
            constants = []
            for c in elem.constants:
                val = c.val
                if elem.type_ == EType.BOOL:
                    val = str(val).lower()  # True -> "true", False -> "false"
                cdesc = c.desc.get(locale)
                constants.append({
                    'val': val,
                    'desc': _clean(cdesc),
                    'version': int(c.version),
                })
            if constants:
                entry['constants'] = constants

        # Store the entry if it carries any useful information
        if entry:
            out[field_name] = entry

        # --- recurse into children ----------------------------------------
        if elem.type_ == EType.OBJECT and elem.val:
            for child_name, child_elem in elem.val.items():
                _extract_elem(child_elem, path_prefix, child_name, out)

        elif elem.type_ == EType.ARRAY and elem.val:
            for idx, child_elem in enumerate(elem.val):
                child_out = {}
                _extract_elem(child_elem, path_prefix, str(idx), child_out)
                if child_out:
                    arr_key = '_array_members'
                    if arr_key not in out:
                        out[arr_key] = {}
                    out[arr_key].update(child_out)

        elif elem.type_ in (EType.UNION, EType.HIDDEN_UNION) and elem.val:
            for tag_val, child_elem in elem.val.items():
                child_out = {}
                _extract_elem(child_elem, path_prefix, str(tag_val), child_out)
                if child_out:
                    tag_key = f'_union_{tag_val}'
                    if tag_key not in out:
                        out[tag_key] = {}
                    out[tag_key].update(child_out)

    for mod in mods:
        for func in mod.functions:
            api_path = func.api_name(mod.name)
            func_out = {}
            root = func.root

            if root.type_ == EType.OBJECT and root.val:
                for field_name, elem in root.val.items():
                    _extract_elem(elem, api_path, field_name, func_out)
            elif root.type_ == EType.ARRAY and root.val:
                for idx, elem in enumerate(root.val):
                    child_out = {}
                    _extract_elem(elem, api_path, str(idx), child_out)
                    if child_out:
                        if '_array_members' not in func_out:
                            func_out['_array_members'] = {}
                        func_out['_array_members'].update(child_out)
            elif root.constants or (root.desc and root.desc.get(locale)):
                _extract_elem(root, api_path, '_root', func_out)

            if func_out:
                result[api_path] = func_out

    return result


# Build API constants for both locales at startup
api_constants = {lang: _build_api_constants(lang) for lang in SUPPORTED_LANGUAGES}

DEFAULT_PORT = 5001

# Directory to store protocol files
PROTOCOL_DIR = 'protocols'
if not os.path.exists(PROTOCOL_DIR):
    os.makedirs(PROTOCOL_DIR)

def get_chart_config(t):
    """Return chart_config with translated labels."""
    return [{
        'csv_title': 'allowed_charging_current',
        'label':     t['chart_allowed_charging_current'],
    }, {
        'csv_title': 'cp_pwm_duty_cycle',
        'label':     t['chart_cp_pwm_duty_cycle'],
        'edit_func':  lambda df: list(map(lambda v: v/10.0, df)),
    }, {
        'csv_title': 'iec61851_state',
        'label':     t['chart_iec61851_state'],
    }, {
        'csv_title': 'power',
        'label':     t['chart_power'],
    }, {
        'csv_title': 'current_0',
        'label':     t['chart_current_0'],
    }, {
        'csv_title': 'current_1',
        'label':     t['chart_current_1'],
    }, {
        'csv_title': 'current_2',
        'label':     t['chart_current_2'],
    }, { # old title
        'csv_title': 'resistance_cp_pe',
        'label':     t['chart_resistance_cp_pe'],
        'hidden':    True
    }, { # new title
        'csv_title': 'CP/PE',
        'label':     t['chart_resistance_cp_pe'],
        'hidden':    True
    }, {
        'csv_title': 'contactor_state',
        'label':     t['chart_contactor_state'],
        'hidden':    True
    }, {
        'csv_title': 'contactor_error',
        'label':     t['chart_contactor_error'],
        'hidden':    True
    }, {
        'csv_title': 'phase_0_active',
        'label':     t['chart_phase_0_active'],
        'hidden':    True
    }, {
        'csv_title': 'phase_1_active',
        'label':     t['chart_phase_1_active'],
        'hidden':    True
    }, {
        'csv_title': 'phase_2_active',
        'label':     t['chart_phase_2_active'],
        'hidden':    True
    }, {
        'csv_title': 'phase_0_connected',
        'label':     t['chart_phase_0_connected'],
        'hidden':    True
    }, {
        'csv_title': 'phase_1_connected',
        'label':     t['chart_phase_1_connected'],
        'hidden':    True
    }, {
        'csv_title': 'phase_2_connected',
        'label':     t['chart_phase_2_connected'],
        'hidden':    True
    }, {
        'csv_title': 'time_since_state_change',
        'label':     t['chart_time_since_state_change'],
        'hidden':    True
    }, { # old title
        'csv_title': 'voltage_plus_12v',
        'label':     t['chart_voltage_plus_12v'],
        'hidden':    True
    }, {
        'csv_title': 'voltage_minus_12v',
        'label':     t['chart_voltage_minus_12v'],
        'hidden':    True
    }]

def read_and_preprocess_protocol(file_path):
    """
    Read a protocol file and preprocess it to handle truncated CSV data.

    When the charge log gets too long, a message like
    "105636 lines have been dropped from the following table."
    is inserted before the CSV data. This function removes that message
    and returns the number of dropped lines (if any).

    Returns:
        tuple: (data_blocks, dropped_lines_count)
            - data_blocks: list of strings split by '\n\n'
            - dropped_lines_count: int or None if no lines were dropped
    """
    with open(file_path, 'r') as fh:
        content = fh.read()

    # Check for "X lines have been dropped from the following table." message
    dropped_lines_match = re.search(r'\n\n(\d+) lines have been dropped from the following table\.', content)
    dropped_lines_count = None

    if dropped_lines_match:
        dropped_lines_count = int(dropped_lines_match.group(1))
        # Remove the message from content
        content = re.sub(r'\n\n\d+ lines have been dropped from the following table\.', '', content)

    data = content.split('\n\n')
    return data, dropped_lines_count

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

def _handle_upload(lang):
    """Handle file upload from POST request. Returns redirect response or None."""
    f = request.files.get('file')
    if not f or f.filename == '':
        return redirect(f'/{lang}/')
    uuid = shortuuid.uuid()
    file_path = os.path.join(PROTOCOL_DIR, uuid)
    f.save(file_path)
    return redirect(f'/{lang}/{uuid}')

# Route for the main page
@app.route('/', methods=['GET', 'POST'])
def index_redirect():
    if request.method == 'POST':
        lang = _detect_language()
        return _handle_upload(lang)

    # Redirect to language-prefixed index
    lang = _detect_language()
    return redirect(f'/{lang}/')


@app.route('/<lang>/', methods=['GET', 'POST'])
def index(lang):
    if lang not in SUPPORTED_LANGUAGES:
        abort(404)
    if request.method == 'POST':
        return _handle_upload(lang)

    t = get_translations(lang)
    return render_template('index.html', t=t, lang=lang)


# Legacy route without language prefix, redirect with auto-detect
@app.route('/<uuid>')
def view_id_legacy(uuid):
    # Validate UUID format to prevent path traversal
    if not UUID_PATTERN.match(uuid):
        abort(404)
    # Don't redirect if uuid matches a language code (handled by index route)
    if uuid in SUPPORTED_LANGUAGES:
        abort(404)
    lang = _detect_language()
    # Preserve query string
    qs = request.query_string.decode()
    target = f'/{lang}/{uuid}'
    if qs:
        target += f'?{qs}'
    return redirect(target)


@app.route('/<lang>/<uuid>')
def view_id(lang, uuid):
    if lang not in SUPPORTED_LANGUAGES:
        abort(404)
    # Validate UUID format to prevent path traversal
    if not UUID_PATTERN.match(uuid):
        abort(404)
    # Create the file path for the protocol
    file_path = os.path.join(PROTOCOL_DIR, uuid)
    if not os.path.exists(file_path):
        abort(404)  # Return a 404 error if the protocol does not exist

    t = get_translations(lang)
    data, dropped_lines_count = read_and_preprocess_protocol(file_path)
    try:
        is_report = (len(data[0]) < 100) and ('Scroll down for event log!' in data[0])
    except (IndexError, TypeError):
        abort(400)

    if is_report:
        return handle_report(data, lang, t)
    else:
        # Old ?configuration= and ?selected= params are converted to hash
        # on the client side for backward compatibility.
        return handle_protocol(data, lang, t, dropped_lines_count)

# Legacy /chart route, redirect to base URL, client handles old params via hash
@app.route('/<lang>/<uuid>/chart')
def view_chart(lang, uuid):
    if lang not in SUPPORTED_LANGUAGES:
        abort(404)
    if not UUID_PATTERN.match(uuid):
        abort(404)
    # Redirect to base URL; the JS will pick up ?configuration= and convert to hash
    qs = request.query_string.decode()
    target = f'/{lang}/{uuid}'
    if qs:
        target += f'?{qs}'
    return redirect(target)

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

def _detect_cm_header(lines):
    """Scan lines for CM header format flags.

    Returns (has_pv, has_phases) indicating which optional column groups
    are present in the charge manager trace.
    """
    has_pv = False
    has_phases = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('PM') or (stripped.startswith('mtr') and 'avl' in stripped):
            if 'PV' in stripped:
                has_pv = True
            if 'L1' in stripped:
                has_phases = True
            if has_pv or has_phases:
                break
    return has_pv, has_phases


# Shared name list for summary columns (raw/min/spread × total/L1-L3 + max_pv)
_CM_SUMMARY_NAMES = [
    f'{prefix}_{suffix}'
    for prefix in ('raw', 'min', 'spread')
    for suffix in ('total', 'L1', 'L2', 'L3')
] + ['max_pv']


def _build_cm_columns(has_pv, has_phases):
    """Build column definitions for a charge manager trace.

    Returns (columns, col_keys, summary_cols, alloc_cols) where:
      - columns: list of {key, label, group} dicts (all columns incl. summary)
      - col_keys: list of keys for table-data columns only
      - summary_cols: list of keys for summary columns
      - alloc_cols: list of keys for allocation columns
    """
    columns = []
    col_keys = []

    # PM columns (always present)
    for name in ['mtr', 'avl']:
        key = f'pm_{name}'
        columns.append({'key': key, 'label': f'PM {name}(W)', 'group': 'PM'})
        col_keys.append(key)

    # PV columns (if PV present in header)
    if has_pv:
        for name in ['raw', 'max', 'min', 'spread']:
            key = f'pv_{name}'
            columns.append({'key': key, 'label': f'PV {name}', 'group': 'PV'})
            col_keys.append(key)

    # Phase columns
    if has_phases:
        for phase in ['L1', 'L2', 'L3']:
            for name in ['meter', 'preprc', 'error', 'adjust', 'raw', 'min', 'spread']:
                key = f'{phase.lower()}_{name}'
                columns.append({'key': key, 'label': f'{phase} {name}', 'group': phase})
                col_keys.append(key)

    # Summary column definitions (step 0 and step 9)
    summary_cols = []
    for step in ['0', '9']:
        for name in _CM_SUMMARY_NAMES:
            key = f's{step}_{name}'
            summary_cols.append(key)
            columns.append({'key': key, 'label': f'Step {step} {name}', 'group': f'Step {step}'})

    # Allocation columns (step 9 result)
    alloc_cols = ['alloc_current', 'alloc_phases']
    columns.append({'key': 'alloc_current', 'label': 'Alloc current (mA)', 'group': 'Allocation'})
    columns.append({'key': 'alloc_phases', 'label': 'Alloc phases', 'group': 'Allocation'})

    # Hysteresis column
    columns.append({'key': 'hysteresis', 'label': 'Hysteresis', 'group': 'Summary'})

    return columns, col_keys, summary_cols, alloc_cols


def parse_charge_manager_trace(content):
    """Parse the charge_manager trace section into structured chart data.

    Returns a dict with:
      - columns: [{key, label, group}, ...] -> metadata for each column
      - table_data: {column_key: [values...]} -> dense arrays, one value per table row
      - summary_data: {column_key: [[row_idx, value], ...]} -> sparse pairs
      - timestamps: [[row_idx, "YYYY-MM-DD HH:MM:SS,mmm"], ...] -> sparse
      - events: [[row_idx, "RECV ..."], ...] -> sparse
      - row_count: int -> total number of table rows
    """
    lines = content.split('\n')

    has_pv, has_phases = _detect_cm_header(lines)
    columns, col_keys, summary_cols, alloc_cols = _build_cm_columns(has_pv, has_phases)
    expected_cols = len(col_keys)

    # --- Parse data ---
    table_data = {k: [] for k in col_keys}
    summary_data = {k: [] for k in summary_cols + alloc_cols + ['hysteresis']}
    timestamps = []
    events = []

    row_idx = 0
    in_table = False
    step_line_re = re.compile(r'^-?\d+:')
    timestamp_re = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})')
    summary_re = re.compile(r'^([09]): raw\((-?\d+) (-?\d+) (-?\d+) (-?\d+)\) min\((-?\d+) (-?\d+) (-?\d+) (-?\d+)\) spread\((-?\d+) (-?\d+) (-?\d+) (-?\d+)\) max_pv (-?\d+)')
    alloc_re = re.compile(r'^9: \[(.+)\]')
    hysteresis_re = re.compile(r'^Hysteresis (-?\d+)')

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Skip header lines
        if stripped.startswith('PM') or (stripped.startswith('mtr') and 'avl' in stripped):
            in_table = True
            continue

        # Timestamp
        ts_m = timestamp_re.match(stripped)
        if ts_m:
            in_table = False
            if row_idx > 0:
                timestamps.append([row_idx - 1, ts_m.group(1)])
            continue

        # Hysteresis
        hyst_m = hysteresis_re.match(stripped)
        if hyst_m:
            if row_idx > 0:
                summary_data['hysteresis'].append([row_idx - 1, int(hyst_m.group(1))])
            continue

        # Summary lines (0: raw(...) or 9: raw(...))
        sum_m = summary_re.match(stripped)
        if sum_m:
            step = sum_m.group(1)
            vals = [int(sum_m.group(i)) for i in range(2, 15)]
            prefix = f's{step}_'
            if row_idx > 0:
                for name, val in zip(_CM_SUMMARY_NAMES, vals):
                    summary_data[prefix + name].append([row_idx - 1, val])
            continue

        # Allocation result: 9: [ ... ]
        alloc_m = alloc_re.match(stripped)
        if alloc_m:
            inner = alloc_m.group(1).strip()
            # Parse "0 32000@3p" or just "0" (no allocation)
            at_m = re.search(r'(\d+)@(\d+)p', inner)
            if at_m and row_idx > 0:
                summary_data['alloc_current'].append([row_idx - 1, int(at_m.group(1))])
                summary_data['alloc_phases'].append([row_idx - 1, int(at_m.group(2))])
            elif row_idx > 0:
                summary_data['alloc_current'].append([row_idx - 1, 0])
                summary_data['alloc_phases'].append([row_idx - 1, 0])
            continue

        # RECV event lines
        if stripped.startswith('RECV'):
            events.append([row_idx, stripped])
            continue

        # Skip section markers and algorithm step lines
        if stripped.startswith('__') and stripped.endswith('__'):
            continue
        if step_line_re.match(stripped) and '|' not in stripped:
            continue
        if stripped.startswith('Wnd') or stripped.startswith('Calc Wnd'):
            continue
        # Skip deeply indented algorithm text (5+ leading spaces with non-table content)
        if len(line) > 0 and len(line) - len(line.lstrip()) >= 5 and '(' in stripped:
            continue

        # Table data rows, try to parse as numbers separated by | groups
        if in_table:
            # Remove | separators and split into numbers
            parts = stripped.replace('|', ' ').split()
            try:
                values = [int(p) for p in parts]
            except ValueError:
                continue

            if len(values) == expected_cols:
                for key, val in zip(col_keys, values):
                    table_data[key].append(val)
                row_idx += 1

    return {
        'columns': columns,
        'table_data': table_data,
        'summary_data': {k: v for k, v in summary_data.items() if v},
        'timestamps': timestamps,
        'events': events,
        'row_count': row_idx,
    }


def handle_report(data, lang, t):
    try:
        # Fix json syntax error that can happen in report
        data_json     = data[1].replace('": ,', '": {},')
        report_json   = json.loads(data_json)
    except (IndexError, KeyError, json.JSONDecodeError, TypeError, ValueError):
        report_json   = {}

    try:
        report_log    = data[2]
    except (IndexError, KeyError):
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

    # Parse charge_manager trace for structured chart visualization
    cm_parsed = None
    if 'charge_manager' in trace_modules:
        try:
            cm_parsed = parse_charge_manager_trace(trace_modules['charge_manager'])
            if cm_parsed['row_count'] == 0:
                cm_parsed = None
        except Exception as e:
            print(f"Warning: Failed to parse charge_manager trace: {e}")
            cm_parsed = None

    data = {
        'report_json':  report_json,
        'report_log':   report_log,
        'report_trace': '\n\n'.join(trace_remaining) if trace_remaining else '',
        'trace_modules': trace_modules,
        'coredump_info': coredump_info,
        'cm_parsed': cm_parsed,
        'api_constants': api_constants[lang],
    }

    # Render the protocol with syntax highlighting
    return render_template('report.html', data=data, t=t, lang=lang)

def _get_block(data, idx, default, parse_json=False):
    """Safely get a block from protocol data by index, with optional JSON parsing."""
    try:
        value = data[idx]
        return json.loads(value) if parse_json else value
    except (IndexError, KeyError, json.JSONDecodeError, TypeError, ValueError):
        return default

def _sanitize_for_json(values):
    """Replace NaN/inf values with None for JSON serialization."""
    return [None if not math.isfinite(v) else v for v in values]

def parse_protocol_data(data):
    # Parse protocol data and extract available columns
    before_protocol_json = _get_block(data, 0, {}, parse_json=True)
    before_protocol_log  = _get_block(data, 1, "")
    protocol_csv         = _get_block(data, 2, "")
    after_protocol_json  = _get_block(data, 3, {}, parse_json=True)
    after_protocol_log   = _get_block(data, 4, "")

    try:
        # Get timestamp data from CSV
        df = pd.read_csv(StringIO(protocol_csv))

        # Extract real timestamp info from the log
        first_millis = df['millis'].iloc[0] if len(df) > 0 else None
        timestamp_info = extract_real_timestamp(before_protocol_log, first_millis)

        # Convert millis to real timestamps
        millis = convert_millis_to_real_time(df['millis'].tolist(), timestamp_info)
    except (KeyError, ValueError, TypeError, pd.errors.EmptyDataError):
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

def handle_protocol(data, lang, t, dropped_lines_count=None):
    """Unified protocol handler: sends ALL column data + metadata to a single template.

    The client-side JS handles column selection, chart rendering, and URL hash
    persistence. Old ``?configuration=`` and ``?selected=`` query params are
    forwarded to the template so the JS can convert them to hash state on load.
    """
    parsed = parse_protocol_data(data)
    chart_config = get_chart_config(t)

    # Build column metadata and pre-compute all column data (with transforms)
    predefined_columns = {cc['csv_title']: cc for cc in chart_config}

    column_metadata = []  # sent to template for checkbox rendering
    all_column_data = {}  # column_name -> [values...], sent to template for chart

    # --- Predefined columns first (in chart_config order) ---
    for cc in chart_config:
        col_name = cc['csv_title']
        if col_name not in parsed['available_columns']:
            continue
        if parsed['df'] is None:
            continue

        try:
            col = parsed['df'][col_name]
            edit_func = cc.get('edit_func')
            if edit_func:
                values = edit_func(col)
            else:
                values = list(col)

            # Convert NaN/inf to None for JSON serialization
            values = _sanitize_for_json(values)

            column_metadata.append({
                'name': col_name,
                'label': cc.get('label', col_name),
                'predefined': True,
                'hidden_by_default': cc.get('hidden', False),
                'group': t['group_predefined'],
                'group_order': 0,
            })
            all_column_data[col_name] = values
        except Exception as e:
            print(f"Warning: Failed to process predefined column {col_name}: {e}")

    # --- Non-predefined columns ---
    for col_name in parsed['available_columns']:
        if col_name in predefined_columns:
            continue
        if parsed['df'] is None:
            continue

        try:
            col = parsed['df'][col_name]
            if col.dtype in ['object', 'string']:
                continue  # skip non-numeric

            # Skip all-NaN columns (section headings like GPIOs, VOLTAGES, etc.)
            if col.isna().all():
                continue

            values = list(col)
            values = _sanitize_for_json(values)

            # Assign group based on column name patterns.
            # Check gpio_ and slot_ prefixes first (more specific), then
            # voltage-related patterns which use substring matching.
            lower = col_name.lower()
            if lower.startswith('gpio_'):
                group = t['group_gpio']
                group_order = 2
            elif lower.startswith('slot_'):
                group = t['group_slots']
                group_order = 3
            elif 'voltage' in lower or 'cp_' in lower or 'pp_' in lower or lower.startswith('adc_'):
                group = t['group_voltages']
                group_order = 1
            else:
                group = t['group_other']
                group_order = 4

            column_metadata.append({
                'name': col_name,
                'label': col_name,
                'predefined': False,
                'hidden_by_default': True,
                'group': group,
                'group_order': group_order,
            })
            all_column_data[col_name] = values
        except Exception as e:
            print(f"Warning: Failed to process column {col_name}: {e}")

    # Split large groups into two equal columns
    for order, threshold in [(2, 16), (3, 6)]:  # GPIO, Slots
        indices = [i for i, m in enumerate(column_metadata) if m.get('group_order') == order]
        if len(indices) > threshold:
            mid = len(indices) // 2
            for i in indices[mid:]:
                column_metadata[i]['group_order'] = order + 0.5

    # Carry forward old query params so the client JS can convert them to hash
    legacy_config = request.args.get('configuration', '')
    legacy_selected = request.args.get('selected', '')

    protocol_data = {
        'column_metadata': column_metadata,
        'all_column_data': all_column_data,
        'labels': parsed['millis'],
        'before_protocol_json': parsed['before_protocol_json'],
        'after_protocol_json': parsed['after_protocol_json'],
        'before_protocol_log': parsed['before_protocol_log'],
        'after_protocol_log': parsed['after_protocol_log'],
        'dropped_lines_count': dropped_lines_count,
        'api_constants': api_constants[lang],
        'legacy_config': legacy_config,
        'legacy_selected': legacy_selected,
    }

    return render_template('protocol.html', data=protocol_data, t=t, lang=lang)

logging.basicConfig(filename='debug.log', level=logging.DEBUG, format="[%(asctime)s %(levelname)-8s%(filename)s:%(lineno)s] %(message)s", datefmt='%Y-%m-%d %H:%M:%S')
port = int(os.environ.get('PORT', DEFAULT_PORT))
if __name__ == '__main__':
    # Only scan for a free port in the main process, not in the
    # reloader child (which inherits PORT via the environment).
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        while True:
            try:
                s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                s.bind(('::', port))
                s.close()
                break
            except OSError:
                print(f"Port {port} already in use, trying {port + 1}")
                port += 1
        os.environ['PORT'] = str(port)
        print(f" * Running on http://localhost:{port}/")

    app.run(debug=True, host="0.0.0.0", port=port)
