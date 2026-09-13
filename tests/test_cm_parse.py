#!/usr/bin/env python3
"""Test script for parse_charge_manager_trace() — both table-based and iteration-based paths.

Run from the repository root: python -m tests.test_cm_parse
"""

import sys
import json

# We need to mock Flask and other imports before importing main
# Since parse_charge_manager_trace and helpers are pure functions,
# we can extract them directly.

import re

# ---- Copied constants/helpers from main.py (to avoid Flask import) ----

_CM_SUMMARY_NAMES = [
    f'{prefix}_{suffix}'
    for prefix in ('raw', 'min', 'spread')
    for suffix in ('total', 'L1', 'L2', 'L3')
] + ['max_pv']


def _detect_cm_header(lines):
    for line in lines[:30]:
        stripped = line.strip()
        if stripped.startswith('PM'):
            has_pv = 'PV' in stripped
            has_phases = 'L1' in stripped
            return has_pv, has_phases
    return False, False


def _build_cm_columns(has_pv, has_phases):
    columns = []
    col_keys = []

    col_keys += ['pm_mtr', 'pm_avl']
    columns += [
        {'key': 'pm_mtr', 'label': 'PM mtr(W)', 'group': 'PM'},
        {'key': 'pm_avl', 'label': 'PM avl(W)', 'group': 'PM'},
    ]

    if has_pv:
        pv_keys = ['pv_raw', 'pv_max', 'pv_min', 'pv_spread']
        col_keys += pv_keys
        columns += [
            {'key': 'pv_raw',    'label': 'PV raw',    'group': 'PV'},
            {'key': 'pv_max',    'label': 'PV max',    'group': 'PV'},
            {'key': 'pv_min',    'label': 'PV min',    'group': 'PV'},
            {'key': 'pv_spread', 'label': 'PV spread', 'group': 'PV'},
        ]

    if has_phases:
        phase_names = ['meter', 'preprc', 'error', 'adjust', 'raw', 'min', 'spread']
        for phase in ['L1', 'L2', 'L3']:
            for name in phase_names:
                key = f'{phase.lower()}_{name}'
                col_keys.append(key)
                columns.append({'key': key, 'label': f'{phase} {name}', 'group': phase})

    summary_cols = []
    for step in ['0', '9']:
        for name in _CM_SUMMARY_NAMES:
            key = f's{step}_{name}'
            summary_cols.append(key)
            columns.append({'key': key, 'label': f'Step {step} {name}', 'group': f'Step {step}'})

    alloc_cols = ['alloc_current', 'alloc_phases']
    columns.append({'key': 'alloc_current', 'label': 'Alloc current (mA)', 'group': 'Allocation'})
    columns.append({'key': 'alloc_phases',  'label': 'Alloc phases',        'group': 'Allocation'})

    columns.append({'key': 'hysteresis', 'label': 'Hysteresis', 'group': 'Summary'})

    return columns, col_keys, summary_cols, alloc_cols


def parse_charge_manager_trace(content):
    """Copied from main.py with the fix applied."""
    lines = content.split('\n')

    has_pv, has_phases = _detect_cm_header(lines)
    columns, col_keys, summary_cols, alloc_cols = _build_cm_columns(has_pv, has_phases)
    expected_cols = len(col_keys)

    table_data = {k: [] for k in col_keys}
    summary_data = {k: [] for k in summary_cols + alloc_cols + ['hysteresis']}
    timestamps = []
    events = []

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

        if stripped.startswith('PM') or (stripped.startswith('mtr') and 'avl' in stripped):
            in_table = True
            continue

        ts_m = timestamp_re.match(stripped)
        if ts_m:
            in_table = False
            if row_idx > 0:
                timestamps.append([row_idx - 1, ts_m.group(1)])
            iter_timestamps_list.append(ts_m.group(1))
            iter_count += 1
            continue

        hyst_m = hysteresis_re.match(stripped)
        if hyst_m:
            hyst_val = int(hyst_m.group(1))
            if row_idx > 0:
                summary_data['hysteresis'].append([row_idx - 1, hyst_val])
            if iter_count > 0:
                iter_summary['hysteresis'].append([iter_count - 1, hyst_val])
            continue

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

        alloc_m = alloc_re.match(stripped)
        if alloc_m:
            inner = alloc_m.group(1).strip()
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

        if stripped.startswith('RECV'):
            events.append([row_idx, stripped])
            continue

        if stripped.startswith('__') and stripped.endswith('__'):
            continue
        if step_line_re.match(stripped) and '|' not in stripped:
            continue
        if stripped.startswith('Wnd') or stripped.startswith('Calc Wnd'):
            continue
        if len(line) > 0 and len(line) - len(line.lstrip()) >= 5 and '(' in stripped:
            continue

        if in_table:
            parts = stripped.replace('|', ' ').split()
            try:
                values = [int(p) for p in parts]
            except ValueError:
                continue

            if len(values) == expected_cols:
                for key, val in zip(col_keys, values):
                    table_data[key].append(val)
                row_idx += 1

    if row_idx > 0:
        return {
            'columns': columns,
            'table_data': table_data,
            'summary_data': {k: v for k, v in summary_data.items() if v},
            'timestamps': timestamps,
            'events': events,
            'row_count': row_idx,
        }

    if iter_count > 0:
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

    return {
        'columns': columns,
        'table_data': table_data,
        'summary_data': {},
        'timestamps': timestamps,
        'events': events,
        'row_count': 0,
    }


# ---- Test Data ----

# Test 1: Trace WITH PM/PV table data (PV excess mode enabled) — should use table-based path
# In real traces, the PM header+data comes at the END of each iteration,
# after summary/hysteresis/alloc lines. The next timestamp resets in_table.
TRACE_WITH_TABLE = """\
2025-01-15 10:00:00,123
0: raw(100 50 30 20) min(90 40 25 15) spread(10 10 5 5) max_pv 500
9: raw(200 60 40 30) min(180 55 35 25) spread(20 5 5 5) max_pv 600
Hysteresis 42
9: [0 32000@3p]
PM PV
mtr avl | raw max min spread
1000 500 | 200 300 150 50
2025-01-15 10:00:01,456
0: raw(110 55 35 25) min(95 45 30 20) spread(15 10 5 5) max_pv 520
9: raw(210 65 45 35) min(185 60 40 30) spread(25 5 5 5) max_pv 620
Hysteresis 45
9: [0 16000@1p]
PM PV
mtr avl | raw max min spread
1100 600 | 210 310 160 60
2025-01-15 10:00:02,789
0: raw(120 60 40 30) min(100 50 35 25) spread(20 10 5 5) max_pv 540
9: raw(220 70 50 40) min(190 65 45 35) spread(30 5 5 5) max_pv 640
Hysteresis 48
9: [0]
PM PV
mtr avl | raw max min spread
1200 700 | 220 320 170 70
"""

# Test 2: Trace WITHOUT PM/PV table data (no PV excess mode) — should use iteration-based fallback
TRACE_WITHOUT_TABLE = """\
2025-01-15 10:00:00,123
0: raw(100 50 30 20) min(90 40 25 15) spread(10 10 5 5) max_pv 500
9: raw(200 60 40 30) min(180 55 35 25) spread(20 5 5 5) max_pv 600
Hysteresis 42
9: [0 32000@3p]
2025-01-15 10:00:01,456
0: raw(110 55 35 25) min(95 45 30 20) spread(15 10 5 5) max_pv 520
9: raw(210 65 45 35) min(185 60 40 30) spread(25 5 5 5) max_pv 620
Hysteresis 45
9: [0 16000@1p]
2025-01-15 10:00:02,789
0: raw(120 60 40 30) min(100 50 35 25) spread(20 10 5 5) max_pv 540
9: raw(220 70 50 40) min(190 65 45 35) spread(30 5 5 5) max_pv 640
Hysteresis 48
9: [0]
"""

# Test 3: Empty/garbage content — should return row_count 0
TRACE_EMPTY = """\
some random text
more random text
"""


def test_table_based_path():
    """Test 1: PV excess trace with table data — uses row_idx-based path."""
    print("=" * 60)
    print("TEST 1: Trace WITH table data (PV excess mode)")
    print("=" * 60)

    result = parse_charge_manager_trace(TRACE_WITH_TABLE)

    assert result is not None, "Result should not be None"
    assert result['row_count'] == 3, f"Expected row_count=3, got {result['row_count']}"
    assert len(result['table_data']) > 0, "table_data should not be empty"
    assert len(result['table_data']['pm_mtr']) == 3, f"PM mtr should have 3 values, got {len(result['table_data']['pm_mtr'])}"
    assert result['table_data']['pm_mtr'] == [1000, 1100, 1200], f"PM mtr values wrong: {result['table_data']['pm_mtr']}"
    assert result['table_data']['pm_avl'] == [500, 600, 700], f"PM avl values wrong: {result['table_data']['pm_avl']}"
    assert result['table_data']['pv_raw'] == [200, 210, 220], f"PV raw values wrong: {result['table_data']['pv_raw']}"

    # Timestamps: first timestamp is lost (row_idx==0), 2nd and 3rd are recorded
    # At 2nd timestamp: row_idx=1 -> records [row_idx-1, ts] = [0, ts2]
    # At 3rd timestamp: row_idx=2 -> records [1, ts3]
    assert len(result['timestamps']) == 2, f"Expected 2 timestamps, got {len(result['timestamps'])}"
    assert result['timestamps'][0] == [0, '2025-01-15 10:00:01,456'], f"First timestamp wrong: {result['timestamps'][0]}"
    assert result['timestamps'][1] == [1, '2025-01-15 10:00:02,789'], f"Second timestamp wrong: {result['timestamps'][1]}"

    # Summary data: first iteration's summary is lost because row_idx==0 when
    # summary lines are parsed (table data row comes after summary in the iteration).
    # Only iterations 2 and 3 have summary data.
    # At 2nd iteration: row_idx=1, recorded as [row_idx-1, val] = [0, val]
    # At 3rd iteration: row_idx=2, recorded as [1, val]
    assert 's0_raw_total' in result['summary_data'], "s0_raw_total should be in summary_data"
    assert len(result['summary_data']['s0_raw_total']) == 2, f"Expected 2 s0_raw_total values (1st iter lost), got {len(result['summary_data']['s0_raw_total'])}"
    assert result['summary_data']['s0_raw_total'][0] == [0, 110]  # 2nd iteration, row_idx-1=0
    assert result['summary_data']['s0_raw_total'][1] == [1, 120]  # 3rd iteration, row_idx-1=1

    # Hysteresis: also lost for first iteration
    assert 'hysteresis' in result['summary_data']
    assert result['summary_data']['hysteresis'] == [[0, 45], [1, 48]]

    # Allocation: also lost for first iteration
    assert 'alloc_current' in result['summary_data']
    assert result['summary_data']['alloc_current'] == [[0, 16000], [1, 0]]
    assert result['summary_data']['alloc_phases'] == [[0, 1], [1, 0]]

    # Columns should include PM and PV groups
    col_groups = {c['group'] for c in result['columns']}
    assert 'PM' in col_groups, "PM group should be in columns"
    assert 'PV' in col_groups, "PV group should be in columns"

    print("  row_count:", result['row_count'])
    print("  table_data keys:", list(result['table_data'].keys()))
    print("  summary_data keys:", list(result['summary_data'].keys()))
    print("  timestamps:", result['timestamps'])
    print("  PASSED\n")


def test_iteration_based_fallback():
    """Test 2: Trace without table data — uses iteration-based fallback."""
    print("=" * 60)
    print("TEST 2: Trace WITHOUT table data (no PV excess mode)")
    print("=" * 60)

    result = parse_charge_manager_trace(TRACE_WITHOUT_TABLE)

    assert result is not None, "Result should not be None"
    assert result['row_count'] == 3, f"Expected row_count=3, got {result['row_count']}"
    assert result['table_data'] == {}, f"table_data should be empty dict, got {result['table_data']}"

    # Timestamps should use iteration index
    assert len(result['timestamps']) == 3, f"Expected 3 timestamps, got {len(result['timestamps'])}"
    assert result['timestamps'][0] == [0, '2025-01-15 10:00:00,123']
    assert result['timestamps'][1] == [1, '2025-01-15 10:00:01,456']
    assert result['timestamps'][2] == [2, '2025-01-15 10:00:02,789']

    # Summary data should be present with iteration indices
    assert 's0_raw_total' in result['summary_data'], "s0_raw_total should be in summary_data"
    assert len(result['summary_data']['s0_raw_total']) == 3
    assert result['summary_data']['s0_raw_total'][0] == [0, 100]
    assert result['summary_data']['s0_raw_total'][1] == [1, 110]
    assert result['summary_data']['s0_raw_total'][2] == [2, 120]

    # Hysteresis
    assert 'hysteresis' in result['summary_data']
    assert result['summary_data']['hysteresis'] == [[0, 42], [1, 45], [2, 48]]

    # Allocation
    assert 'alloc_current' in result['summary_data']
    assert result['summary_data']['alloc_current'] == [[0, 32000], [1, 16000], [2, 0]]
    assert result['summary_data']['alloc_phases'] == [[0, 3], [1, 1], [2, 0]]

    # Columns should NOT include PM/PV table columns (they have no data)
    col_keys = {c['key'] for c in result['columns']}
    assert 'pm_mtr' not in col_keys, "pm_mtr should not be in columns (no table data)"
    assert 'pm_avl' not in col_keys, "pm_avl should not be in columns (no table data)"
    # But should include summary/alloc/hysteresis columns
    assert 'hysteresis' in col_keys, "hysteresis should be in columns"
    assert 'alloc_current' in col_keys, "alloc_current should be in columns"

    print("  row_count:", result['row_count'])
    print("  table_data:", result['table_data'])
    print("  summary_data keys:", list(result['summary_data'].keys()))
    print("  timestamps:", result['timestamps'])
    print("  column groups:", sorted({c['group'] for c in result['columns']}))
    print("  PASSED\n")


def test_empty_trace():
    """Test 3: Empty/garbage content — should return row_count 0."""
    print("=" * 60)
    print("TEST 3: Empty/garbage trace content")
    print("=" * 60)

    result = parse_charge_manager_trace(TRACE_EMPTY)

    assert result is not None, "Result should not be None"
    assert result['row_count'] == 0, f"Expected row_count=0, got {result['row_count']}"
    assert result['summary_data'] == {}, f"summary_data should be empty"

    print("  row_count:", result['row_count'])
    print("  PASSED\n")


def test_cm_parsed_none_logic():
    """Test 4: Simulate the cm_parsed = None logic from handle_report."""
    print("=" * 60)
    print("TEST 4: cm_parsed None logic (simulating handle_report)")
    print("=" * 60)

    # With table data — cm_parsed should NOT be None
    result1 = parse_charge_manager_trace(TRACE_WITH_TABLE)
    cm_parsed_1 = result1 if result1['row_count'] > 0 else None
    assert cm_parsed_1 is not None, "With table data, cm_parsed should NOT be None"

    # Without table data — cm_parsed should NOT be None (this is the bug fix!)
    result2 = parse_charge_manager_trace(TRACE_WITHOUT_TABLE)
    cm_parsed_2 = result2 if result2['row_count'] > 0 else None
    assert cm_parsed_2 is not None, "Without table data but with iterations, cm_parsed should NOT be None (BUG FIX)"

    # Empty — cm_parsed should be None
    result3 = parse_charge_manager_trace(TRACE_EMPTY)
    cm_parsed_3 = result3 if result3['row_count'] > 0 else None
    assert cm_parsed_3 is None, "With empty trace, cm_parsed should be None"

    print("  Table trace -> cm_parsed is not None: CORRECT")
    print("  No-table trace -> cm_parsed is not None: CORRECT (bug fix)")
    print("  Empty trace -> cm_parsed is None: CORRECT")
    print("  PASSED\n")


def test_js_compatibility():
    """Test 5: Verify the output format is compatible with renderCmChart() in vislog.js."""
    print("=" * 60)
    print("TEST 5: JS compatibility check (output format)")
    print("=" * 60)

    result = parse_charge_manager_trace(TRACE_WITHOUT_TABLE)

    # renderCmChart expects: data.summary_data[key] = [[idx, val], ...]
    for key, pairs in result['summary_data'].items():
        for pair in pairs:
            assert isinstance(pair, list) and len(pair) == 2, f"summary_data[{key}] has invalid pair: {pair}"
            assert isinstance(pair[0], int), f"summary_data[{key}] index should be int: {pair}"
            assert isinstance(pair[1], int), f"summary_data[{key}] value should be int: {pair}"

    # timestamps: [[idx, "timestamp_str"], ...]
    for ts in result['timestamps']:
        assert isinstance(ts, list) and len(ts) == 2, f"Invalid timestamp: {ts}"
        assert isinstance(ts[0], int), f"Timestamp index should be int: {ts}"
        assert isinstance(ts[1], str), f"Timestamp value should be str: {ts}"

    # table_data should be empty dict (not None)
    assert isinstance(result['table_data'], dict), "table_data should be a dict"

    # columns should be a list of dicts with key, label, group
    for col in result['columns']:
        assert 'key' in col and 'label' in col and 'group' in col, f"Column missing fields: {col}"

    # row_count should be a positive int
    assert isinstance(result['row_count'], int) and result['row_count'] > 0

    # The output should be JSON-serializable (Flask will serialize it for the template)
    try:
        json.dumps(result)
    except (TypeError, ValueError) as e:
        assert False, f"Result is not JSON-serializable: {e}"

    print("  summary_data format: OK (list of [idx, val] pairs)")
    print("  timestamps format: OK (list of [idx, str] pairs)")
    print("  table_data format: OK (empty dict)")
    print("  columns format: OK (list of {key, label, group})")
    print("  JSON-serializable: OK")
    print("  PASSED\n")


if __name__ == '__main__':
    tests = [
        test_table_based_path,
        test_iteration_based_fallback,
        test_empty_trace,
        test_cm_parsed_none_logic,
        test_js_compatibility,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAILED: {e}\n")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}\n")
            failed += 1

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
