#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, render_template, abort, redirect, url_for, Response
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
import struct
import shutil
import subprocess
import gzip
import xml.etree.ElementTree as ET
from io import BytesIO
from i18n import get_translations, SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB upload limit

UUID_PATTERN = re.compile(r'^[a-zA-Z0-9]+$')


@app.url_defaults
def _static_cache_busting(endpoint, values):
    if endpoint == 'static' and 'filename' in values:
        path = os.path.join(app.static_folder, values['filename'])
        try:
            values['v'] = int(os.stat(path).st_mtime)
        except OSError:
            pass


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

        # --- censored flag ----------------------------------------------
        if getattr(elem, 'censored', False) or getattr(elem, 'censored_in_debug_report', False):
            entry['censored'] = True

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
    }, { # new title (bare CP/PE is unique in the CSV)
        'csv_title': 'CP/PE',
        'label':     t['chart_resistance_cp_pe'],
        'hidden':    True
    }, { # old title
        'csv_title': 'resistance_pp_pe',
        'label':     t['chart_resistance_pp_pe'],
        'hidden':    True
    }, { # new title (disambiguated by _disambiguate_csv_columns)
        'csv_title': 'RESISTANCES PP/PE',
        'label':     t['chart_resistance_pp_pe'],
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

def _load_iso15118_pcap(lang, uuid):
    """Shared request handling for the iso15118 endpoints.

    Validates the request, reads the protocol file and builds the pcap.
    Returns (pcap_bytes, has_boot_epoch); aborts with 404 on any problem.
    """
    if lang not in SUPPORTED_LANGUAGES:
        abort(404)
    # Validate UUID format to prevent path traversal
    if not UUID_PATTERN.match(uuid):
        abort(404)
    file_path = os.path.join(PROTOCOL_DIR, uuid)
    if not os.path.exists(file_path):
        abort(404)

    with open(file_path, 'r') as fh:
        content = fh.read()

    try:
        pcap_bytes, has_boot_epoch = extract_iso15118_pcap(content)
    except Exception as e:
        print(f"Warning: Failed to convert iso15118_ll trace to pcap: {e}")
        pcap_bytes, has_boot_epoch = None, False

    if pcap_bytes is None:
        abort(404)

    return pcap_bytes, has_boot_epoch

@app.route('/<lang>/<uuid>/iso15118.pcap')
def download_iso15118_pcap(lang, uuid):
    pcap_bytes, _ = _load_iso15118_pcap(lang, uuid)
    return Response(pcap_bytes, mimetype='application/vnd.tcpdump.pcap',
                    headers={'Content-Disposition': f'attachment; filename={uuid}-iso15118.pcap'})

@app.route('/<lang>/<uuid>/iso15118.json')
def iso15118_packets_json(lang, uuid):
    """Dissected iso15118_ll packet data for the Wireshark-style viewer.

    The result only depends on the (immutable) uploaded protocol file, so it
    is cached gzip-compressed on disk next to the protocol file.
    """
    if not UUID_PATTERN.match(uuid):
        abort(404)
    # v4: column extraction fixed for tshark <= 4.0
    cache_path = os.path.join(PROTOCOL_DIR, f'{uuid}.iso15118.v4.json.gz')

    gz_payload = None
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'rb') as fh:
                gz_payload = fh.read()
        except OSError:
            gz_payload = None

    if gz_payload is None:
        pcap_bytes, has_boot_epoch = _load_iso15118_pcap(lang, uuid)

        if TSHARK_PATH is None:
            return {'error': 'tshark-unavailable'}, 503

        try:
            packets = dissect_iso15118_pcap(pcap_bytes)
        except Exception as e:
            print(f"Warning: Failed to dissect iso15118_ll pcap: {e}")
            packets = None

        if packets is None:
            return {'error': 'dissection-failed'}, 503

        payload = json.dumps({
            'has_boot_epoch': has_boot_epoch,
            'packets': packets,
        }, separators=(',', ':'))
        gz_payload = gzip.compress(payload.encode('utf-8'))

        # Write the cache atomically; a failing cache write is not fatal
        try:
            tmp_path = f'{cache_path}.tmp.{os.getpid()}'
            with open(tmp_path, 'wb') as fh:
                fh.write(gz_payload)
            os.replace(tmp_path, cache_path)
        except OSError as e:
            print(f"Warning: Failed to write iso15118 cache: {e}")

    if 'gzip' in request.headers.get('Accept-Encoding', ''):
        return Response(gz_payload, mimetype='application/json',
                        headers={'Content-Encoding': 'gzip'})
    return Response(gzip.decompress(gz_payload), mimetype='application/json')

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

    The table header is a pair of lines: a group line ("PM    PV | L1 ...")
    followed by a column line ("mtr(W) [bat(W)] avl(W) raw ..."). Note that
    "PM" is just a marker meaning "power manager values follow", not a
    column group heading: mtr/bat/avl semantically belong to the PV group.

    Returns (has_pv, has_phases, has_bat) indicating which optional columns
    are present in the charge manager trace. ``bat(W)`` (battery storage
    power) was added to the column line by newer firmwares.
    """
    has_pv = False
    has_phases = False
    has_bat = False
    for line in lines:
        stripped = line.strip()
        is_group_header = stripped.startswith('PM')
        is_column_header = stripped.startswith('mtr') and 'avl' in stripped
        if not (is_group_header or is_column_header):
            continue
        if 'PV' in stripped:
            has_pv = True
        if 'L1' in stripped:
            has_phases = True
        if 'bat' in stripped:
            has_bat = True
        if is_column_header:
            # The column line follows the group line, so the header pair
            # has been fully seen at this point.
            break
    return has_pv, has_phases, has_bat


# Shared name list for summary columns (raw/min/spread × total/L1-L3 + max_pv)
_CM_SUMMARY_NAMES = [
    f'{prefix}_{suffix}'
    for prefix in ('raw', 'min', 'spread')
    for suffix in ('total', 'L1', 'L2', 'L3')
] + ['max_pv']


def _build_cm_columns(has_pv, has_phases, has_bat):
    """Build column definitions for a charge manager trace.

    Returns (columns, col_keys, summary_cols, alloc_cols) where:
      - columns: list of {key, label, group} dicts (all columns incl. summary)
      - col_keys: list of keys for table-data columns only
      - summary_cols: list of keys for summary columns
      - alloc_cols: list of keys for allocation columns
    """
    columns = []
    col_keys = []

    # Power manager columns (always present). Semantically these belong to
    # the PV group ("relevant values for PV excess charging"), the "PM" in
    # the trace header is only a marker, not a column group heading.
    # bat(W) (battery storage power) only exists in newer firmwares.
    # The keys keep their historic pm_ prefix so that column selections
    # stored in shared URL hashes remain valid.
    pm_names = ['mtr', 'bat', 'avl'] if has_bat else ['mtr', 'avl']
    for name in pm_names:
        key = f'pm_{name}'
        columns.append({'key': key, 'label': f'PV {name}(W)', 'group': 'PV'})
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
      - row_count: int -> total number of table rows (or iterations if no table)

    When no PM/PV table data is present (e.g. PV excess mode not enabled),
    the parser falls back to an iteration-based mode where each timestamp
    marks a new data point and summary/hysteresis/allocation values are
    plotted against these iterations.
    """
    lines = content.split('\n')

    has_pv, has_phases, has_bat = _detect_cm_header(lines)
    columns, col_keys, summary_cols, alloc_cols = _build_cm_columns(has_pv, has_phases, has_bat)
    expected_cols = len(col_keys)

    # --- Parse data ---
    table_data = {k: [] for k in col_keys}
    summary_data = {k: [] for k in summary_cols + alloc_cols + ['hysteresis']}
    timestamps = []
    events = []

    # Iteration-level tracking for table-less traces (no PM/PV table data).
    # Each timestamp starts a new iteration.
    iter_count = 0
    iter_timestamps_list = []
    iter_summary = {k: [] for k in summary_cols + alloc_cols + ['hysteresis']}

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
            # Track iteration-level timestamps for table-less fallback
            iter_timestamps_list.append(ts_m.group(1))
            iter_count += 1
            continue

        # Hysteresis
        hyst_m = hysteresis_re.match(stripped)
        if hyst_m:
            hyst_val = int(hyst_m.group(1))
            if row_idx > 0:
                summary_data['hysteresis'].append([row_idx - 1, hyst_val])
            if iter_count > 0:
                iter_summary['hysteresis'].append([iter_count - 1, hyst_val])
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
            if iter_count > 0:
                for name, val in zip(_CM_SUMMARY_NAMES, vals):
                    iter_summary[prefix + name].append([iter_count - 1, val])
            continue

        # Allocation result: 9: [ ... ]
        alloc_m = alloc_re.match(stripped)
        if alloc_m:
            inner = alloc_m.group(1).strip()
            # Parse "0 32000@3p" or just "0" (no allocation)
            at_m = re.search(r'(\d+)@(\d+)p', inner)
            if at_m:
                alloc_current = int(at_m.group(1))
                alloc_phases = int(at_m.group(2))
            else:
                alloc_current = 0
                alloc_phases = 0
            if row_idx > 0:
                summary_data['alloc_current'].append([row_idx - 1, alloc_current])
                summary_data['alloc_phases'].append([row_idx - 1, alloc_phases])
            if iter_count > 0:
                iter_summary['alloc_current'].append([iter_count - 1, alloc_current])
                iter_summary['alloc_phases'].append([iter_count - 1, alloc_phases])
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

    # If we have table data, return the table-based result (existing behavior).
    if row_idx > 0:
        return {
            'columns': columns,
            'table_data': table_data,
            'summary_data': {k: v for k, v in summary_data.items() if v},
            'timestamps': timestamps,
            'events': events,
            'row_count': row_idx,
        }

    # Fallback: no table data (e.g. PV excess mode not enabled).
    # Use iteration-based indexing where each timestamp is one data point.
    if iter_count > 0:
        # Exclude PM/PV/phase table columns since they have no data
        table_col_keys = set(col_keys)
        iter_columns = [c for c in columns if c['key'] not in table_col_keys]

        return {
            'columns': iter_columns,
            'table_data': {},
            'summary_data': {k: v for k, v in iter_summary.items() if v},
            'timestamps': [[i, ts] for i, ts in enumerate(iter_timestamps_list)],
            'events': events,
            'row_count': iter_count,
        }

    # No data at all
    return {
        'columns': columns,
        'table_data': table_data,
        'summary_data': {},
        'timestamps': timestamps,
        'events': events,
        'row_count': 0,
    }


# ---------------------------------------------------------------------------
# Meters history/live parsing
# ---------------------------------------------------------------------------
def parse_meters(report_json):
    """Extract meters/history and meters/live samples from the report JSON.

    Each section contains 'samples': one entry per meter slot, which is either
    null (no meter configured for that slot) or an array of floats/nulls.
    'offset' is the age of the newest sample in milliseconds. For live data
    'samples_per_second' gives the sample rate (approaches 2 Hz); history has
    a fixed rate of one sample every 4 minutes (720 samples over 48 hours).

    Returns a dict {'history': {...}, 'live': {...}, 'report_time': ...}
    where each section is {'offset': ms, 'samples_per_second': float|None,
    'slots': [...]} with one slot entry per configured meter ({'slot': N,
    'name': str, 'samples': [...]}), and 'report_time' is the report's
    creation time as UTC epoch seconds (from rtc/time, None if unknown).
    Returns None if neither section contains data.
    """
    def slot_name(slot):
        # meters/N/config is [meter_class, {config...}]
        config = report_json.get(f'meters/{slot}/config')
        try:
            name = config[1].get('display_name')
            if name:
                return name
        except (TypeError, IndexError, KeyError, AttributeError):
            pass
        return f'Meter #{slot}'

    result = {}
    for key in ('history', 'live'):
        section = report_json.get(f'meters/{key}')
        if not isinstance(section, dict):
            continue
        samples = section.get('samples')
        if not isinstance(samples, list):
            continue
        slots = []
        for slot, values in enumerate(samples):
            if not isinstance(values, list):
                continue  # null => no meter configured for this slot
            slots.append({
                'slot': slot,
                'name': slot_name(slot),
                'samples': values,
            })
        if slots:
            result[key] = {
                'offset': section.get('offset', 0),
                'samples_per_second': section.get('samples_per_second'),
                'slots': slots,
            }

    if result:
        # Absolute time reference (UTC epoch seconds) for the x-axis
        result['report_time'] = _report_timestamp(report_json)

    return result if result else None


def _report_timestamp(report_json):
    """Determine when the report was created, from rtc/time (UTC).

    Returns UTC epoch seconds or None if no plausible time is available
    (e.g. the RTC was never synchronized).
    """
    rtc = report_json.get('rtc/time')
    if not isinstance(rtc, dict):
        return None
    try:
        dt = datetime.datetime(
            rtc['year'], rtc['month'], rtc['day'],
            rtc['hour'], rtc['minute'], rtc['second'],
            tzinfo=datetime.timezone.utc,
        )
    except (KeyError, TypeError, ValueError):
        return None
    if dt.year < 2020:
        return None  # RTC not synchronized
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# Firmware version check
# ---------------------------------------------------------------------------
FIRMWARE_INDEX_MAP = {
    'warp':  'warp_firmware_v2.txt',
    'warp2': 'warp2_firmware_v2.txt',
    'warp3': 'warp3_firmware_v2.txt',
    'warp4': 'warp4_firmware_v3.txt',
    'wem':   'energy_manager_firmware_v2.txt',
    'wem2':  'energy_manager_v2_firmware_v2.txt',
    'seb':   'smart_energy_broker_firmware_v2.txt',
}

FIRMWARES_DIR = os.path.join(os.path.dirname(__file__), 'firmwares')

# Cache: filename -> (mtime, [versions])
_firmware_index_cache = {}


def _read_firmware_index(filename):
    """Read a firmware version index file with mtime-based caching.

    Returns a list of full version strings (e.g. '2.12.1+6a4f9137'),
    newest first, or None if the file is not available.
    """
    path = os.path.join(FIRMWARES_DIR, filename)
    try:
        mtime = os.stat(path).st_mtime
        cached = _firmware_index_cache.get(filename)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        with open(path, 'r', encoding='utf-8') as f:
            versions = [line.strip() for line in f if line.strip()]
        _firmware_index_cache[filename] = (mtime, versions)
        return versions
    except OSError:
        return None


def _parse_base_version(version):
    """Parse the numeric part of a version string like '2.12.1+6a4f9137'.

    Returns a tuple of ints or None if unparseable.
    """
    base = version.split('+')[0].split('-')[0]
    try:
        return tuple(int(p) for p in base.split('.'))
    except ValueError:
        return None


def check_firmware_version(report_json):
    """Compare the report's firmware version against the released versions.

    Returns None if everything is fine (or the check is not possible),
    otherwise a dict:
      {'level': 'danger'|'info', 'reported': str, 'latest': str}
    - danger: reported base version is older than the latest release
    - info:   reported version is not a released build (hash mismatch or
              newer than the latest release)
    """
    try:
        reported = report_json['info/version']['firmware']
        device_type = report_json['info/name']['type']
    except (KeyError, TypeError):
        return None

    index_file = FIRMWARE_INDEX_MAP.get(device_type)
    if index_file is None:
        return None

    versions = _read_firmware_index(index_file)
    if not versions:
        return None

    latest = versions[0]
    reported_base = _parse_base_version(reported)
    latest_base = _parse_base_version(latest)
    if reported_base is None or latest_base is None:
        return None

    if reported_base < latest_base:
        return {'level': 'danger', 'reported': reported, 'latest': latest}

    if reported not in versions:
        # Same or newer base version, but not a released build
        # (dev/custom build or newer than the latest release).
        return {'level': 'info', 'reported': reported, 'latest': latest}

    return None


# ---------------------------------------------------------------------------
# ISO 15118 low-level trace (iso15118_ll) parsing
# ---------------------------------------------------------------------------
# The iso15118_ll trace module contains raw QCA700X ethernet frames, one line
# per SPI transfer: "<millis> <hexdata>". Received buffers are wrapped in a
# QCA700X header/footer, sent buffers are raw ethernet frames.
# (See esp32-firmware iso15118/tools/debug_report_to_pcap.py)
QCA700X_ETHERNET_FRAME_MIN_SIZE = 60
QCA700X_RECV_HEADER_SIZE = 4 + 4 + 2 + 2
QCA700X_RECV_FOOTER_SIZE = 2
QCA700X_RECV_BUFFER_MIN_SIZE = (QCA700X_ETHERNET_FRAME_MIN_SIZE +
                                QCA700X_RECV_HEADER_SIZE +
                                QCA700X_RECV_FOOTER_SIZE)

TSHARK_PATH = shutil.which('tshark')
TSHARK_TIMEOUT = 30  # seconds


def _replace_mac_bitshifted(data, mac, cmac):
    """Replace bit-shifted (non byte-aligned) occurrences of a MAC address.

    The EVCCID field in EXI-encoded V2G messages contains the EV MAC address
    bit-packed at an arbitrary bit offset, so a plain byte-level replacement
    misses it. This scans for the MAC at all seven non-zero bit shifts and
    replaces the 48 matching bits in place (surrounding bits are preserved).
    A 48-bit match at a random position is practically impossible, so false
    positives are not a concern.
    """
    mac_int = int.from_bytes(mac, 'big')
    cmac_int = int.from_bytes(cmac, 'big')

    for s in range(1, 8):
        shift = 8 - s  # MAC starts at bit s of the 7-byte window
        win = mac_int << shift
        cwin = cmac_int << shift
        mask = ((1 << 48) - 1) << shift
        # The middle 5 bytes of the 7-byte window are fully determined by
        # the MAC; use them for a fast byte-level search.
        mid = win.to_bytes(7, 'big')[1:6]

        start = 1
        while True:
            i = data.find(mid, start)
            if i < 0:
                break
            start = i + 1
            j = i - 1
            if j + 7 > len(data):
                continue
            window = int.from_bytes(data[j:j + 7], 'big')
            if window & mask != win:
                continue
            window = (window & ~mask) | cwin
            data = data[:j] + window.to_bytes(7, 'big') + data[j + 7:]

    return data


def _fix_ipv6_checksums(frame):
    """Recompute the upper-layer checksum of an IPv6 ethernet frame.

    MAC censoring modifies IPv6 addresses (EUI-64) and payloads (NDP targets,
    EXI content), which invalidates TCP/UDP/ICMPv6 checksums covering the
    pseudo-header. Walks hop-by-hop/routing/destination extension headers
    (e.g. MLDv2 reports carry a Router Alert option); anything unhandled is
    returned unchanged.
    """
    if len(frame) < 54 or frame[12:14] != b'\x86\xdd':
        return frame

    plen = int.from_bytes(frame[18:20], 'big')
    end = 54 + plen
    if len(frame) < end:
        return frame  # truncated capture

    # Walk extension headers to the upper-layer protocol
    nh = frame[20]
    offset = 54
    while nh in (0, 43, 60):  # hop-by-hop, routing, destination options
        if offset + 2 > end:
            return frame
        nh = frame[offset]
        offset += (frame[offset + 1] + 1) * 8

    checksum_offset = {6: 16, 17: 6, 58: 2}.get(nh)  # TCP, UDP, ICMPv6
    if checksum_offset is None:
        return frame

    payload = frame[offset:end]
    if len(payload) < checksum_offset + 2:
        return frame

    # Pseudo-header (src, dst, upper-layer length, next header) + payload
    # with the checksum field zeroed
    buf = (frame[22:54] + len(payload).to_bytes(4, 'big') + b'\x00\x00\x00' + bytes([nh]) +
           payload[:checksum_offset] + b'\x00\x00' + payload[checksum_offset + 2:])
    if len(buf) % 2:
        buf += b'\x00'

    checksum = 0
    for i in range(0, len(buf), 2):
        checksum += (buf[i] << 8) | buf[i + 1]
    while checksum >> 16:
        checksum = (checksum & 0xffff) + (checksum >> 16)
    checksum = (~checksum) & 0xffff
    if nh == 17 and checksum == 0:
        checksum = 0xffff  # UDP: zero means "no checksum"

    return (frame[:offset + checksum_offset] + checksum.to_bytes(2, 'big') +
            frame[offset + checksum_offset + 2:])


class _MacCensor:
    """Censors the last three octets of unicast MAC addresses in ethernet frames.

    Each distinct MAC keeps its OUI (vendor prefix) and gets the last three
    octets replaced by a sequential pseudonym (00:00:01, 00:00:02, ...), so
    distinct devices stay distinguishable without leaking the real address.
    Besides the ethernet header the replacement also covers:
      - byte-aligned occurrences in payloads (SLAC messages, NDP options, ...)
      - EUI-64 interface identifiers in IPv6 link-local addresses
      - solicited-node multicast addresses/MACs (contain the last 3 octets)
      - bit-shifted occurrences in EXI payloads (EVCCID = EV MAC)
    Upper-layer checksums of modified IPv6 frames are recomputed.
    """

    def __init__(self):
        self.mapping = {}  # original MAC bytes -> censored MAC bytes

    def _register(self, mac):
        if mac[0] & 0x01 or mac == b'\x00\x00\x00\x00\x00\x00':
            return  # keep multicast/broadcast and null MACs
        if mac not in self.mapping:
            idx = len(self.mapping) + 1
            self.mapping[mac] = mac[:3] + bytes([(idx >> 16) & 0xff,
                                                 (idx >> 8) & 0xff, idx & 0xff])

    def censor_frame(self, frame):
        if len(frame) < 14:
            return frame
        self._register(frame[0:6])
        self._register(frame[6:12])

        orig = frame
        for mac, cmac in self.mapping.items():
            # Byte-aligned MAC (ethernet header, SLAC payloads, NDP options)
            frame = frame.replace(mac, cmac)
            # EUI-64 interface identifier (IPv6 link-local addresses)
            eui = bytes([mac[0] ^ 0x02]) + mac[1:3] + b'\xff\xfe' + mac[3:6]
            ceui = eui[:5] + cmac[3:6]
            frame = frame.replace(eui, ceui)
            # Solicited-node multicast (ff02::1:ffXX:XXXX and 33:33:ff:XX:XX:XX)
            sol = b'\xff' + mac[3:6]
            csol = b'\xff' + cmac[3:6]
            frame = frame.replace(sol, csol)
            # Bit-packed EXI content (EVCCID in SessionSetupReq = EV MAC)
            frame = _replace_mac_bitshifted(frame, mac, cmac)

        if frame != orig:
            frame = _fix_ipv6_checksums(frame)
        return frame


def iso15118_ll_to_pcap(content, boot_epoch=0, censor_macs=True):
    """Convert an iso15118_ll trace section to pcap bytes (DLT_EN10MB).

    Strips the QCA700X header/footer from received buffers and reassembles
    ethernet frames that were split across multiple SPI reads. With
    censor_macs the last three octets of all unicast MAC addresses are
    pseudonymized (see _MacCensor). Returns None if no packets could be
    extracted.
    """
    out = bytearray()
    # pcap global header: magic, v2.4, thiszone 0, sigfigs 0, snaplen, ethernet
    out += struct.pack('<IHHiIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)

    censor = _MacCensor() if censor_macs else None
    packet_count = 0
    qca = []
    t = 0

    for line in content.splitlines():
        parts = line.split(' ')
        if len(parts) != 2:
            continue
        try:
            t = int(parts[0])
            qca.extend(int(parts[1][i:i + 2], 16) for i in range(0, len(parts[1]), 2))
        except ValueError:
            continue

        # Note: This is not perfect. If there is a recv-buffer without footer
        #       and the next packet is a send-buffer it will append the send
        #       buffer to the recv-buffer. (Same limitation as the offline
        #       debug_report_to_pcap.py converter.)

        if len(qca) < 8:
            continue

        minimum = QCA700X_RECV_BUFFER_MIN_SIZE
        if qca[4:8] != [0xaa, 0xaa, 0xaa, 0xaa]:
            minimum = QCA700X_ETHERNET_FRAME_MIN_SIZE

        while len(qca) >= minimum:
            # Remove QCA header and footer if it is in the data.
            # The QCA framing is in received data, but not in written data.
            if qca[4:8] == [0xaa, 0xaa, 0xaa, 0xaa]:
                frame_len = qca[8] | (qca[9] << 8)
                packet = bytes(qca[QCA700X_RECV_HEADER_SIZE:QCA700X_RECV_HEADER_SIZE + frame_len])
                qca = qca[QCA700X_RECV_HEADER_SIZE + frame_len + QCA700X_RECV_FOOTER_SIZE:]
            else:
                packet = bytes(qca)
                qca = []

            if not packet:
                continue

            if censor is not None:
                packet = censor.censor_frame(packet)

            epoch_ms = int(boot_epoch * 1000) + t
            out += struct.pack('<IIII', epoch_ms // 1000, (epoch_ms % 1000) * 1000,
                               len(packet), len(packet))
            out += packet
            packet_count += 1

    if packet_count == 0:
        return None

    return bytes(out)


def _run_tshark(pcap_bytes, extra_args):
    """Run tshark on in-memory pcap bytes, return stdout bytes or None."""
    try:
        proc = subprocess.run([TSHARK_PATH, '-r', '-'] + extra_args,
                              input=pcap_bytes, capture_output=True,
                              timeout=TSHARK_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Warning: tshark failed: {e}")
        return None
    if proc.returncode != 0:
        print(f"Warning: tshark exited with {proc.returncode}: "
              f"{proc.stderr.decode('utf-8', errors='replace')[:500]}")
        return None
    return proc.stdout


# Maximum length of a single protocol tree label (EXI hex dumps etc. can be
# several kB per field, which needlessly bloats the JSON payload).
ISO15118_MAX_LABEL_LEN = 1500

# Column field variants for the packet-list pass, in order of preference:
# lowercase canonical names (Wireshark >= 4.2) and title-based names
# (Wireshark <= 4.0, still accepted by 4.2+ for backwards compatibility).
# The first working variant is moved to the front at runtime.
_ISO15118_COLUMN_FIELDS = [
    ['_ws.col.def_src', '_ws.col.def_dst', '_ws.col.protocol', '_ws.col.info'],
    ['_ws.col.Source', '_ws.col.Destination', '_ws.col.Protocol', '_ws.col.Info'],
]


def _parse_iso15118_summaries(fields_out):
    """Parse tshark -T fields output (7 tab-separated columns) into a dict
    {frame_number: [number, epoch, src, dst, protocol, length, info]}."""
    summaries = {}
    for line in fields_out.decode('utf-8', errors='replace').splitlines():
        parts = line.split('\t')
        if len(parts) != 7:
            continue
        try:
            number = int(parts[0])
            epoch = float(parts[1])
            length = int(parts[5])
        except ValueError:
            continue
        summaries[number] = [number, epoch, parts[2], parts[3], parts[4], length, parts[6]]
    return summaries


def _pdml_node(el):
    """Convert a PDML <field>/<proto> element to a compact tree node.

    Returns a plain string for leaves, [label, [children...]] for inner
    nodes, or None for empty/hidden elements. The labels are the same
    strings Wireshark shows in its packet detail pane.
    """
    label = el.get('showname') or el.get('show') or el.get('name') or ''
    if len(label) > ISO15118_MAX_LABEL_LEN:
        label = label[:ISO15118_MAX_LABEL_LEN] + ' […]'

    children = []
    for child in el:
        if child.tag != 'field' or child.get('hide') == 'yes':
            continue
        node = _pdml_node(child)
        if node is not None:
            children.append(node)

    if not children:
        return label if label else None
    if not label:
        # Hoist children of label-less wrappers
        return children[0] if len(children) == 1 else ['', children]
    return [label, children]


def dissect_iso15118_pcap(pcap_bytes):
    """Dissect a pcap with tshark into Wireshark-like packet data.

    Returns a list of packets, each [number, epoch_time, src, dst, protocol,
    length, info, tree] where tree is a nested list of the protocol detail
    labels (see _pdml_node), or None if tshark is unavailable or failed.
    """
    if TSHARK_PATH is None:
        print("Warning: tshark not found, cannot dissect iso15118_ll trace")
        return None

    # Pass 1: packet list columns (same columns as the Wireshark packet list).
    # The lowercase column field names (_ws.col.def_src, ...) were introduced
    # in Wireshark 4.2; older versions only support the title-based names
    # (_ws.col.Source, ...), which 4.2+ still accepts for backwards
    # compatibility. Old tshark does not reject unknown _ws.col.* names, it
    # silently prints empty columns, so a variant only counts as working if
    # it actually produced column text. The working variant is remembered.
    summaries = None
    for variant in _ISO15118_COLUMN_FIELDS:
        col_src, col_dst, col_proto, col_info = variant
        fields_out = _run_tshark(pcap_bytes, [
            '-T', 'fields', '-E', 'separator=/t',
            '-e', 'frame.number', '-e', 'frame.time_epoch',
            '-e', col_src, '-e', col_dst,
            '-e', col_proto, '-e', 'frame.len', '-e', col_info,
        ])
        if fields_out is None:
            continue

        parsed = _parse_iso15118_summaries(fields_out)
        if summaries is None:
            summaries = parsed  # degraded last resort if no variant validates

        # The protocol column is never empty for a real packet
        if parsed and any(entry[4] for entry in parsed.values()):
            summaries = parsed
            # Move the working variant to the front for subsequent calls
            if variant is not _ISO15118_COLUMN_FIELDS[0]:
                _ISO15118_COLUMN_FIELDS.remove(variant)
                _ISO15118_COLUMN_FIELDS.insert(0, variant)
            break
        print(f"Warning: tshark produced no column text for fields {variant}")

    if summaries is None:
        return None

    # Pass 2: protocol detail tree (PDML contains the exact strings Wireshark
    # shows in its packet detail pane)
    pdml_out = _run_tshark(pcap_bytes, ['-T', 'pdml'])
    if pdml_out is None:
        return None

    packets = []
    try:
        for _, elem in ET.iterparse(BytesIO(pdml_out), events=('end',)):
            if elem.tag != 'packet':
                continue
            number = None
            tree = []
            for proto in elem:
                if proto.tag != 'proto':
                    continue
                if proto.get('name') == 'geninfo':
                    for field in proto:
                        if field.get('name') == 'num':
                            number = int(field.get('show'))
                    continue
                if proto.get('name') == 'fake-field-wrapper':
                    # PDML wraps top-level non-proto fields (reassembly info,
                    # payload data, ...) in this pseudo proto; hoist them like
                    # Wireshark does in its detail pane.
                    for field in proto:
                        if field.tag != 'field' or field.get('hide') == 'yes':
                            continue
                        node = _pdml_node(field)
                        if node is not None:
                            tree.append(node)
                    continue
                node = _pdml_node(proto)
                if node is None:
                    continue
                if isinstance(node, list) and node[0] == '':
                    # Hoisted label-less wrapper (e.g. reassembly info)
                    tree.extend(node[1])
                else:
                    tree.append(node)
            summary = summaries.get(number)
            if summary is not None:
                packets.append(summary + [tree])
            elem.clear()
    except ET.ParseError as e:
        print(f"Warning: failed to parse tshark PDML output: {e}")
        return None

    return packets if packets else None


def extract_iso15118_pcap(content):
    """Extract the iso15118_ll section from raw report text and build a pcap.

    Returns (pcap_bytes, has_boot_epoch) or (None, False) if the report
    contains no usable iso15118_ll trace data.
    """
    m = re.search(r'__begin_iso15118_ll__(.*?)__end_iso15118_ll__', content, re.DOTALL)
    if not m:
        return None, False

    # Determine the boot epoch from the raw report text (first "uptime" key
    # and rtc/time), mirroring the offline debug_report_to_pcap.py converter.
    boot_epoch = 0
    uptime_m = re.search(r'"uptime":\s*(\d+)', content)
    rtc_m = re.search(r'"rtc/time":\s*(\{[^}]+\})', content)
    if uptime_m and rtc_m:
        try:
            rtc = json.loads(rtc_m.group(1))
            rtc_dt = datetime.datetime(rtc['year'], rtc['month'], rtc['day'],
                                       rtc['hour'], rtc['minute'], rtc['second'],
                                       tzinfo=datetime.timezone.utc)
            if rtc_dt.year >= 2020:
                boot_epoch = rtc_dt.timestamp() - int(uptime_m.group(1)) / 1000.0
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    pcap_bytes = iso15118_ll_to_pcap(m.group(1), boot_epoch)
    return pcap_bytes, boot_epoch != 0


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

    # Parse meters/history and meters/live for chart visualization
    try:
        meters_parsed = parse_meters(report_json)
    except Exception as e:
        print(f"Warning: Failed to parse meters history/live: {e}")
        meters_parsed = None

    # The iso15118_ll trace (raw QCA700X ethernet frames) is dissected lazily
    # via the /<lang>/<uuid>/iso15118.json endpoint; here we only flag its
    # presence so the template renders the packet list UI.
    iso15118_ll_available = 'iso15118_ll' in trace_modules and TSHARK_PATH is not None
    if iso15118_ll_available:
        # Don't ship the raw hex dump to the client: the packet list and the
        # pcap download supersede it, and unlike them it would contain the
        # uncensored MAC addresses.
        trace_modules['iso15118_ll'] = ''

    # Check whether the report's firmware is a current release
    try:
        firmware_check = check_firmware_version(report_json)
    except Exception as e:
        print(f"Warning: Failed to check firmware version: {e}")
        firmware_check = None

    data = {
        'report_json':  report_json,
        'report_log':   report_log,
        'report_trace': '\n\n'.join(trace_remaining) if trace_remaining else '',
        'trace_modules': trace_modules,
        'coredump_info': coredump_info,
        'cm_parsed': cm_parsed,
        'iso15118_ll_available': iso15118_ll_available,
        'meters_parsed': meters_parsed,
        'firmware_check': firmware_check,
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

_CSV_SECTION_HEADINGS = {
    'STATE', 'HARDWARE CONFIG', 'ENERGY METER', 'ENERGY METER ERRORS',
    'LL-State', 'ADC VALUES', 'VOLTAGES', 'RESISTANCES', 'GPIOs',
}

def _disambiguate_csv_columns(protocol_csv):
    """Prefix duplicate column names with their section heading.

    The CSV uses certain columns (e.g. RESISTANCES, VOLTAGES, ADC VALUES) as
    section headings.  When a column name like ``CP/PE`` appears under multiple
    sections, pandas would silently append ``.1``, ``.2`` etc. which is fragile
    across firmware versions.  Instead, we rename duplicates by prefixing them
    with their section heading, e.g. ``RESISTANCES CP/PE``.  Only the *second
    and subsequent* occurrences are renamed so that the first occurrence keeps
    its original name for backwards compatibility.
    """
    lines = protocol_csv.split('\n')
    if not lines:
        return protocol_csv

    headers = lines[0].split(',')
    seen = {}          # name -> count of previous occurrences
    current_section = None
    new_headers = []

    for h in headers:
        stripped = h.strip()
        if stripped in _CSV_SECTION_HEADINGS:
            current_section = stripped

        if stripped in seen and seen[stripped] >= 1:
            # Duplicate – prefix with current section heading if available
            if current_section:
                new_name = f"{current_section} {stripped}"
            else:
                new_name = f"{stripped}.{seen[stripped]}"
            new_headers.append(new_name)
        else:
            new_headers.append(h)

        seen[stripped] = seen.get(stripped, 0) + 1

    lines[0] = ','.join(new_headers)
    return '\n'.join(lines)

def parse_protocol_data(data):
    # Parse protocol data and extract available columns
    before_protocol_json = _get_block(data, 0, {}, parse_json=True)
    before_protocol_log  = _get_block(data, 1, "")
    protocol_csv         = _get_block(data, 2, "")
    after_protocol_json  = _get_block(data, 3, {}, parse_json=True)
    after_protocol_log   = _get_block(data, 4, "")

    try:
        # Disambiguate duplicate column names using section headings
        protocol_csv = _disambiguate_csv_columns(protocol_csv)

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
        # Filter out section heading columns and 'millis' column.
        # Section headings contain all-NaN data but we exclude them early.
        available_columns = [col for col in df.columns
                           if col != 'millis' and col not in _CSV_SECTION_HEADINGS]

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
