#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, render_template, abort, redirect
import shortuuid
import os
import json
import datetime
import logging
import pandas as pd
from io import StringIO

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
}, #{ # new title: This captures +12V and -12V are ADC values, not voltages...
#    'csv_title': '+12V',
#    'label':     'Spannung +12V',
#    'hidden':    True
#}, {
#    'csv_title': '-12V',
#    'label':     'Spannung -12V',
#    'hidden':    True
#}

# Slots may be interesting, but they use up so much space...
#{
#    'csv_title': 'incoming_cable',
#    'label':     'Slot incoming_cable',
#    'hidden':    True
#}, {
#    'csv_title': 'outgoing_cable',
#    'label':     'Slot outgoing_cable',
#    'hidden':    True
#}, {
#    'csv_title': 'shutdown_input',
#    'label':     'Slot shutdown_input',
#    'hidden':    True
#}, {
#    'csv_title': 'gp_input',
#    'label':     'Slot gp_input',
#    'hidden':    True
#}, {
#    'csv_title': 'autostart_button',
#    'label':     'Slot autostart_button',
#    'hidden':    True
#}, {
#    'csv_title': 'global',
#    'label':     'Slot global',
#    'hidden':    True
#}, {
#    'csv_title': 'user',
#    'label':     'Slot user',
#    'hidden':    True
#}, {
#    'csv_title': 'charge_manager',
#    'label':     'Slot charge_manager',
#    'hidden':    True
#}, {
#    'csv_title': 'external',
#    'label':     'Slot external',
#    'hidden':    True
#}, {
#    'csv_title': 'modbus_tcp',
#    'label':     'Slot modbus_tcp',
#    'hidden':    True
#}, {
#    'csv_title': 'modbus_tcp_enable',
#    'label':     'Slot modbus_tcp_enable',
#    'hidden':    True
#}, {
#    'csv_title': 'ocpp',
#    'label':     'Slot ocpp',
#    'hidden':    True
#}, {
#    'csv_title': 'charge_limits',
#    'label':     'Slot charge_limits',
#    'hidden':    True
#}, {
#    'csv_title': 'require_meter',
#    'label':     'Slot require_meter',
#    'hidden':    True
#}
]

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

# Route to view a specific protocol by its ID
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
        return handle_protocol(data)

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

    if len(report_trace_blocks) == 0:
        report_trace_blocks.append('Es befindet sich kein Trace-Log im Debug-Report')

    if len(report_dump_blocks) == 0:
        report_dump_blocks.append('Es befindet sich kein Coredump im Debug-Report')

    data = {
        'report_json':  report_json,
        'report_log':   report_log,
        'report_trace': '\n\n'.join(report_trace_blocks),
        'report_dump':  '\n\n'.join(report_dump_blocks),
    }

    # Render the protocol with syntax highlighting
    return render_template('report.html', data = data)

def handle_protocol(data):
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
        # Get important data from CSV
        df = pd.read_csv(StringIO(protocol_csv))
        millis = list(map(lambda v: datetime.datetime.fromtimestamp(v/1000).strftime('%H:%M:%S'), df['millis']))
    except:
        millis = []

    dataset = []
    for cc in chart_config:
        try:
            col = (df[cc['csv_title']])
            new_data = {
                'label': cc.get('label')
            }

            edit_func = cc.get('edit_func')
            if edit_func:
                new_data['data'] = edit_func(col)
            else:
                new_data['data'] = list(col) #list(df['current_0']), #list(col),

            hidden = cc.get('hidden')
            if hidden:
                new_data['hidden'] = hidden

            dataset.append(new_data)
        except:
            pass

    # Show 0 values as 0.1 since chart.js can't show 0 in log view...
    # see https://github.com/chartjs/Chart.js/issues/9629
    for d in dataset:
        d['data'] = list(map(lambda v: 0.01 if v == 0 else v, d['data']))

    data = {
        'chart':                {'labels': millis, 'datasets': dataset},
        'before_protocol_json': before_protocol_json,
        'after_protocol_json':  after_protocol_json,
        'before_protocol_log':  before_protocol_log,
        'after_protocol_log':   after_protocol_log,
    }

    # Render the protocol with syntax highlighting
    return render_template('protocol.html', data = data)

logging.basicConfig(filename='debug.log', level=logging.DEBUG, format="[%(asctime)s %(levelname)-8s%(filename)s:%(lineno)s] %(message)s", datefmt='%Y-%m-%d %H:%M:%S')
port = int(os.environ.get('PORT', DEFAULT_PORT))
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=port)
