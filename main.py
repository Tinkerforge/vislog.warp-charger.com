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
    try:
        report_title2 = data[3]
    except:
        report_title2 = ""
    try:
        if '___CORE_DUMP_START___' in report_title2:
            report_dump   = data[4]
        else:
            raise
    except:
        report_dump = "Es befindet sich kein Coredump im Debug-Report"

    data = {
        'report_json': report_json,
        'report_log':  report_log,
        'report_dump': report_dump,
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
    try:
        dataset.append({
            'label': 'Erlaubter Ladestrom (mA)',
            'data': list(df['allowed_charging_current'])
        })
    except:
        pass
    try:
        dataset.append({
            'label': 'CP PWM (% Duty Cycle)',
            'data': list(map(lambda v: v/10.0, (df['cp_pwm_duty_cycle']))),
        })
    except:
        pass
    try:
        dataset.append({
            'label': 'IEC61851 State',
            'data': list(df['iec61851_state']),
        })
    except:
        pass
    try:
        dataset.append({
            'label': 'Leistung (W)',
            'data': list(df['power']),
        })
    except:
        pass
    try:
        dataset.append({
            'label': 'Strom L1 (mA)',
            'data': list(df['current_0']),
        })
    except:
        pass
    try:
        dataset.append({
            'label': 'Strom L2 (mA)',
            'data': list(df['current_1']),
        })
    except:
        pass
    try:
        dataset.append({
            'label': 'Strom L3 (mA)',
            'data': list(df['current_2']),
        })
    except:
        pass
    try:
        dataset.append({
            'label': 'Widerstand CP/PE (Ohm)',
            'data': list(df['resistance_cp_pe']),
            'hidden': True
        })
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
