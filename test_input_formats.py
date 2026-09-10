"""Production input/render tests using only synthetic diagnostic data."""

import base64
import datetime
import gzip
import json
import os
import re
import tempfile
import unittest
from unittest.mock import mock_open, patch

from input_parser import parse_document

# Import the application without creating or configuring its debug log.
with patch('logging.basicConfig'):
    import main


CSV = 'millis,allowed_charging_current,power\n1000,6000,1200\n2000,16000,3600'
UUID = 'SyntheticInput123'


def section(name, body):
    return f'___{name}_START___\n{body}\n___{name}_END___'


def snapshot_fixture(label, day=1):
    report = {
        'fixture': label,
        'uptime': day * 1250,
        'rtc/time': {
            'year': 2026, 'month': 1, 'day': day,
            'hour': 12, 'minute': 0, 'second': 0,
        },
        'ntp/config': {'timezone': 'UTC' if day == 1 else 'Europe/Berlin'},
    }
    # A minimal synthetic ELF prefix and TF metadata, not a real crash dump.
    dump = base64.b64encode(
        b'\x7fELF' + b'___tf_coredump_info_start___'
        + json.dumps({'firmware_file_name': f'{label}-synthetic.bin'}).encode()
        + b'___tf_coredump_info_end___'
    ).decode('ascii')
    return {
        'report_json': report,
        'event_log': f'{label}-event-one\n\n{label}-event-two',
        'trace_log': (
            f'{label}-trace-outside\n\n'
            f'__begin_diagnostic__\n{label}-module-one\n\n{label}-module-two\n'
            '__end_diagnostic__\n'
            f'__begin_iso15118_ll__\n{day * 1000} 02000000000{day}\n'
            '__end_iso15118_ll__'
        ),
        'coredump': dump,
    }


def marked_snapshot(snapshot, prefix=''):
    return '\n\n'.join(
        section(prefix + name, body) for name, body in (
            ('DEBUG_REPORT', json.dumps(snapshot['report_json'], indent=2)),
            ('EVENT_LOG', snapshot['event_log']),
            ('TRACE_LOG', snapshot['trace_log']),
            ('CORE_DUMP', snapshot['coredump']),
        )
    )


def combined_fixture():
    return '\n\n'.join((
        marked_snapshot(snapshot_fixture('before'), 'PRE_'),
        section('DEBUG_PROTOCOL', CSV),
        marked_snapshot(snapshot_fixture('after', 2), 'POST_'),
    ))


def legacy_report_fixture():
    snapshot = snapshot_fixture('legacy')
    return '\n\n'.join((
        'Scroll down for event log!',
        json.dumps(snapshot['report_json']),
        'legacy-event',
        '___TRACE_LOG_START___',
        snapshot['trace_log'],
        '___CORE_DUMP_START___',
        snapshot['coredump'],
    ))


def legacy_protocol_fixture():
    return '\n\n'.join((
        '{"fixture": "legacy-before"}', 'legacy-before-event', CSV,
        '{"fixture": "legacy-after"}', 'legacy-after-event',
    ))


class InputParserTests(unittest.TestCase):
    def test_marked_standalone(self):
        snapshot = snapshot_fixture('standalone')
        document = parse_document(marked_snapshot(snapshot))
        self.assertFalse(document['is_protocol'])
        self.assertFalse(document['has_embedded_reports'])
        self.assertEqual(document['snapshots'], {'standalone': snapshot})
        self.assertEqual(document['protocol_csv'], '')
        self.assertIsNone(document['dropped_lines_count'])
        self.assertEqual(document['warnings'], [])

    def test_marked_combined_isolates_all_snapshot_sections(self):
        document = parse_document(combined_fixture())
        self.assertTrue(document['is_protocol'])
        self.assertTrue(document['has_embedded_reports'])
        self.assertEqual(document['snapshots'], {
            'pre': snapshot_fixture('before'),
            'post': snapshot_fixture('after', 2),
        })
        self.assertEqual(document['protocol_csv'], CSV)
        self.assertEqual(document['warnings'], [])

    def test_marked_blank_lines_crlf_and_bom(self):
        for content in (marked_snapshot(snapshot_fixture('standalone')), combined_fixture()):
            expected = parse_document(content)
            for newline in ('\n', '\r\n', '\r'):
                with self.subTest(protocol=expected['is_protocol'], newline=repr(newline)):
                    padded = '\n\n' + content.replace('___\n', '___\n\n\n') + '\n\n'
                    self.assertEqual(
                        parse_document('\ufeff' + padded.replace('\n', newline)), expected,
                    )

    def test_accidental_coredump_spelling_remains_supported(self):
        for content in (marked_snapshot(snapshot_fixture('standalone')), combined_fixture()):
            with self.subTest(protocol='DEBUG_PROTOCOL' in content):
                self.assertEqual(parse_document(content.replace('CORE_DUMP', 'COREDUMP')),
                                 parse_document(content))

    def test_coredump_only_sections(self):
        for name in ('CORE_DUMP', 'COREDUMP'):
            for snapshot, prefix in (('standalone', ''), ('pre', 'PRE_'), ('post', 'POST_')):
                with self.subTest(name=name, snapshot=snapshot):
                    document = parse_document(section(prefix + name, 'synthetic-dump'))
                    self.assertEqual(document['snapshots'][snapshot]['coredump'], 'synthetic-dump')
                    self.assertFalse(any('Unknown section' in warning for warning in document['warnings']))

    def test_legacy_report_with_start_only_trace_and_coredump(self):
        expected = snapshot_fixture('legacy')
        expected['event_log'] = 'legacy-event'
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)):
                document = parse_document('\ufeff' + legacy_report_fixture().replace('\n', newline))
                self.assertFalse(document['is_protocol'])
                self.assertFalse(document['has_embedded_reports'])
                self.assertEqual(document['snapshots'], {'standalone': expected})
                self.assertEqual(document['warnings'], [])

    def test_event_log_preserves_timestamp_indentation(self):
        log = '                  0,015 | startup\n\n\t                 0,016 | next  '
        for snapshot, prefix in (('standalone', ''), ('pre', 'PRE_'), ('post', 'POST_')):
            for newline in ('\n', '\r\n'):
                with self.subTest(snapshot=snapshot, newline=repr(newline)):
                    content = section(prefix + 'EVENT_LOG', '\n' + log + '\n')
                    document = parse_document(content.replace('\n', newline))
                    self.assertEqual(document['snapshots'][snapshot]['event_log'], log)

    def test_legacy_protocol(self):
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)):
                document = parse_document('\ufeff' + legacy_protocol_fixture().replace('\n', newline))
                self.assertTrue(document['is_protocol'])
                self.assertFalse(document['has_embedded_reports'])
                self.assertEqual(document['protocol_csv'], CSV)
                for key, label in (('pre', 'before'), ('post', 'after')):
                    self.assertEqual(document['snapshots'][key], {
                        'report_json': {'fixture': f'legacy-{label}'},
                        'event_log': f'legacy-{label}-event',
                        'trace_log': '', 'coredump': None,
                    })
                self.assertEqual(document['warnings'], [])

    def test_dropped_notice_is_removed_without_shifting_sections(self):
        for content in (combined_fixture(), legacy_protocol_fixture()):
            for spacing in ('\n', '\n\n'):
                with self.subTest(marked=content.startswith('___'), spacing=spacing):
                    notice = '12345 lines have been dropped from the following table.' + spacing
                    expected = parse_document(content)
                    expected['dropped_lines_count'] = 12345
                    actual = parse_document(content.replace(CSV, notice + CSV).replace('\n', '\r\n'))
                    self.assertEqual(actual, expected)

    def test_unknown_section_warns_and_is_not_displayed(self):
        content = '\n'.join((
            section('DEBUG_REPORT', '{"fixture": "known"}'),
            section('FUTURE_DATA', 'unknown-private-looking-but-synthetic-payload'),
            section('EVENT_LOG', 'known-event'),
        ))
        document = parse_document(content)
        self.assertEqual(document['warnings'], ['Unknown section FUTURE_DATA; not displayed.'])
        self.assertEqual(document['snapshots']['standalone']['event_log'], 'known-event')
        self.assertNotIn('unknown-private-looking-but-synthetic-payload', json.dumps(document))

    def test_duplicate_sections_keep_first_and_warn(self):
        first = snapshot_fixture('first')
        document = parse_document(marked_snapshot(first) + '\n' + marked_snapshot(snapshot_fixture('second')))
        self.assertEqual(document['snapshots'], {'standalone': first})
        self.assertCountEqual(document['warnings'], [
            f'Duplicate section {name}; using the first occurrence.'
            for name in ('DEBUG_REPORT', 'EVENT_LOG', 'TRACE_LOG', 'CORE_DUMP')
        ])

    def test_missing_end_recovers_at_next_start_and_eof(self):
        content = '\n'.join((
            '___DEBUG_REPORT_START___', '{"fixture": "recovered"}',
            section('EVENT_LOG', 'event-after-truncated-report'),
            '___TRACE_LOG_START___', 'trace-at-eof',
        ))
        document = parse_document(content)
        self.assertEqual(document['snapshots']['standalone'], {
            'report_json': {'fixture': 'recovered'},
            'event_log': 'event-after-truncated-report',
            'trace_log': 'trace-at-eof', 'coredump': None,
        })
        self.assertEqual(document['warnings'], [
            'Missing end marker for DEBUG_REPORT.', 'Missing end marker for TRACE_LOG.',
        ])

    def test_missing_start_and_mismatched_end_warn_without_losing_active_section(self):
        content = '\n'.join((
            '___DEBUG_REPORT_START___', '{"fixture": "recovered"}',
            '___FUTURE_DATA_END___', '___DEBUG_REPORT_END___',
            '___EVENT_LOG_END___', section('TRACE_LOG', 'surviving-trace'),
        ))
        document = parse_document(content)
        self.assertEqual(document['snapshots']['standalone']['report_json'], {'fixture': 'recovered'})
        self.assertEqual(document['snapshots']['standalone']['trace_log'], 'surviving-trace')
        self.assertIn('Unexpected end marker for FUTURE_DATA.', document['warnings'])
        self.assertIn('Unexpected end marker for EVENT_LOG.', document['warnings'])

    def test_missing_report_data_recovers_other_sections(self):
        document = parse_document(section('PRE_EVENT_LOG', 'surviving-event'))
        self.assertEqual(document['snapshots']['pre']['report_json'], {})
        self.assertEqual(document['snapshots']['pre']['event_log'], 'surviving-event')
        self.assertCountEqual(document['warnings'], [
            'Missing PRE_DEBUG_REPORT data.', 'Missing charge table or millis column.',
        ])

    def test_invalid_json_recovers_event_trace_or_coredump(self):
        for raw_json in ('{broken', '[]', 'null', '42', '"not an object"'):
            for name, key in (('EVENT_LOG', 'event_log'), ('TRACE_LOG', 'trace_log'), ('CORE_DUMP', 'coredump')):
                with self.subTest(raw_json=raw_json, section=name):
                    document = parse_document(section('DEBUG_REPORT', raw_json) + '\n' + section(name, 'survives'))
                    self.assertEqual(document['snapshots']['standalone']['report_json'], {})
                    self.assertEqual(document['snapshots']['standalone'][key], 'survives')
                    self.assertEqual(document['warnings'], ['Invalid JSON in DEBUG_REPORT.'])

    def test_invalid_json_does_not_discard_charge_table(self):
        document = parse_document('\n'.join((
            section('PRE_DEBUG_REPORT', '{broken'),
            section('DEBUG_PROTOCOL', CSV),
            section('POST_DEBUG_REPORT', '{"fixture": "valid-after"}'),
        )))
        self.assertEqual(document['protocol_csv'], CSV)
        self.assertEqual(document['snapshots']['pre']['report_json'], {})
        self.assertEqual(document['snapshots']['post']['report_json'], {'fixture': 'valid-after'})
        self.assertEqual(document['warnings'], ['Invalid JSON in PRE_DEBUG_REPORT.'])

    def test_historical_empty_json_value_repair(self):
        raw = '{"missing": , "fixture": "repaired"}'
        for content in (section('DEBUG_REPORT', raw), 'Scroll down for event log!\n\n' + raw):
            with self.subTest(marked=content.startswith('___')):
                document = parse_document(content)
                self.assertEqual(document['snapshots']['standalone']['report_json'], {
                    'missing': {}, 'fixture': 'repaired',
                })
                self.assertEqual(document['warnings'], [])

    def test_no_usable_data_is_rejected(self):
        for content in (
            '', '\ufeff\r\n\r\n', 'unrecognized text',
            section('DEBUG_REPORT', '{broken'), section('DEBUG_REPORT', '[]'),
            section('DEBUG_REPORT', '{}'), section('DEBUG_PROTOCOL', 'power\n1200'),
            section('PRE_TRACE_LOG', ''), '___DEBUG_REPORT_END___',
        ):
            with self.subTest(content=content):
                with self.assertRaisesRegex(ValueError, 'No usable diagnostic data found'):
                    parse_document(content)

    def test_standalone_logs_survive_missing_or_invalid_json(self):
        for content in (
            section('EVENT_LOG', 'surviving-event') + '\n' + section('TRACE_LOG', 'surviving-trace'),
            'Scroll down for event log!\n\n{broken\n\nsurviving-event',
        ):
            document = parse_document(content)
            self.assertFalse(document['is_protocol'])
            self.assertEqual(document['snapshots']['standalone']['event_log'], 'surviving-event')
            self.assertTrue(document['warnings'])

    def test_unknown_prefixed_section_does_not_change_document_type(self):
        document = parse_document(marked_snapshot(snapshot_fixture('standalone')) + '\n' +
                                  section('PRE_FUTURE_DATA', 'ignored'))
        self.assertFalse(document['is_protocol'])
        self.assertFalse(document['has_embedded_reports'])

    def test_ambiguous_trace_coredump_boundary_does_not_leak_dump(self):
        for name in ('CORE_DUMP', 'COREDUMP'):
            for snapshot, prefix in (('standalone', ''), ('pre', 'PRE_'), ('post', 'POST_')):
                with self.subTest(name=name, snapshot=snapshot):
                    document = parse_document(section(prefix + 'DEBUG_REPORT', '{"uptime": 123}') + '\n' +
                                              f'___{prefix}TRACE_LOG_START___\ntrace\nsecret-dump\n___{prefix}{name}_END___')
                    self.assertEqual(document['snapshots'][snapshot]['trace_log'], '')
                    self.assertNotIn('secret-dump', json.dumps(document))

    def test_file_loader_uses_utf8_sig_and_production_parser(self):
        content = '\ufeff' + combined_fixture().replace('\n', '\r\n')
        with patch('builtins.open', mock_open(read_data=content)) as opened:
            document = main.read_and_preprocess_protocol('synthetic-input')
        opened.assert_called_once_with('synthetic-input', 'r', encoding='utf-8-sig')
        self.assertEqual(document, parse_document(combined_fixture()))


class FlaskInputFormatTests(unittest.TestCase):
    def setUp(self):
        self.content = combined_fixture()
        self.client = main.app.test_client()
        self.enterContext(patch.dict(main.app.config, TESTING=True))
        directory = self.enterContext(tempfile.TemporaryDirectory(prefix='input-formats-', dir='/tmp/opencode'))
        self.enterContext(patch.object(main, 'PROTOCOL_DIR', directory))
        self.file_path = os.path.join(directory, UUID)
        exists = os.path.exists
        self.enterContext(patch.object(main.os.path, 'exists', side_effect=lambda path: path == self.file_path or exists(path)))
        self.loader = self.enterContext(patch.object(
            main, 'read_and_preprocess_protocol', side_effect=lambda path: parse_document(self.content),
        ))
        self.firmware = self.enterContext(patch.object(main, 'check_firmware_version', return_value=None))
        self.enterContext(patch.object(main, 'TSHARK_PATH', '/synthetic/tshark'))

    def render(self, query=''):
        response = self.client.get(f'/en/{UUID}{query}')
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        html = response.get_data(as_text=True)
        match = re.search(r'\blet data = (.+);', html)
        self.assertIsNotNone(match, 'Rendered template must include its JSON data')
        return html, json.loads(match[1])

    def test_combined_before_post_and_default_render_selected_trace_and_dump(self):
        for query, selected, label, other in (
            ('?snapshot=pre', 'pre', 'before', 'after'),
            ('?snapshot=post', 'post', 'after', 'before'),
            ('', 'post', 'after', 'before'),
        ):
            with self.subTest(query=query):
                html, data = self.render(query)
                self.assertEqual(data['snapshot'], selected)
                self.assertEqual(data['report_snapshots'], ['pre', 'post'])
                self.assertEqual(data['report_json']['fixture'], label)
                self.assertEqual(data['report_log'], f'{label}-event-one\n\n{label}-event-two')
                self.assertIn('id="config-tab"', html)
                self.assertIn('id="log-tab"', html)
                self.assertIn('id="report-json"', html)
                self.assertIn('id="report-log-text"', html)
                for old_tab in ('before-json-tab', 'after-json-tab', 'before-log-tab', 'after-log-tab'):
                    self.assertNotIn(f'id="{old_tab}"', html)
                self.assertEqual(data['report_trace'], f'{label}-trace-outside')
                self.assertEqual(data['trace_modules']['diagnostic'], f'{label}-module-one\n\n{label}-module-two')
                self.assertEqual(data['coredump_info']['firmware_name'], f'{label}-synthetic.bin')
                self.assertTrue(data['coredump_info']['has_coredump'])
                self.assertNotIn(f'{other}-module-one', html)
                self.assertNotIn(f'{other}-trace-outside', html)
                self.assertNotIn(f'{other}-synthetic.bin', html)
                other_snapshot = snapshot_fixture(other, 2 if other == 'after' else 1)
                self.assertNotIn(other_snapshot['coredump'], html)
                self.assertIn(f'<option value="{selected}" selected>', html)
                self.assertLess(html.index('role="tablist"'), html.index('id="report-snapshot"'))
                self.assertLess(html.index('id="chart-tab"'), html.index('id="report-snapshot"'))
                self.assertLess(html.index('id="report-snapshot"'), html.index('id="config-tab"'))
                self.assertNotIn('report-snapshot-hint', html)
                self.assertNotIn('<label for="report-snapshot"', html)
                self.assertIn(f'/{UUID}/iso15118.pcap?snapshot={selected}', html)
                self.assertTrue(data['iso15118_ll_available'])
                self.assertEqual(data['trace_modules']['iso15118_ll'], '')
                self.assertEqual(data['all_column_data']['allowed_charging_current'], [6000, 16000])
                self.assertEqual(data['before_protocol_json']['fixture'], 'before')
                self.assertEqual(data['after_protocol_json']['fixture'], 'after')
                self.firmware.assert_called_with(data['report_json'])

    def test_standalone_marked_and_legacy_render(self):
        for content, label in (
            (marked_snapshot(snapshot_fixture('standalone')), 'standalone'),
            (legacy_report_fixture(), 'legacy'),
        ):
            with self.subTest(label=label):
                self.content = content
                html, data = self.render()
                self.assertEqual(data['snapshot'], 'standalone')
                self.assertEqual(data['report_json']['fixture'], label)
                self.assertIn(f'{label}-module-one', data['trace_modules']['diagnostic'])
                self.assertEqual(data['coredump_info']['firmware_name'], f'{label}-synthetic.bin')
                self.assertIn('id="trace-diagnostic-tab"', html)
                self.assertNotIn('id="report-snapshot"', html)

    def test_legacy_protocol_renders_chart_and_before_after_without_report_features(self):
        self.content = legacy_protocol_fixture()
        html, data = self.render('?configuration=power&selected=power')
        self.assertFalse(data['has_embedded_reports'])
        self.assertEqual(data['before_protocol_json'], {'fixture': 'legacy-before'})
        self.assertEqual(data['after_protocol_json'], {'fixture': 'legacy-after'})
        self.assertEqual(data['before_protocol_log'], 'legacy-before-event')
        self.assertEqual(data['after_protocol_log'], 'legacy-after-event')
        self.assertEqual(data['all_column_data']['power'], [1200, 3600])
        self.assertEqual(len(data['labels']), 2)
        self.assertEqual(data['legacy_config'], 'power')
        self.assertEqual(data['legacy_selected'], 'power')
        self.assertIn('id="proto-chart"', html)
        self.assertNotIn('id="report-snapshot"', html)
        self.assertNotIn('id="dump-tab"', html)
        for old_tab in ('before-json-tab', 'after-json-tab', 'before-log-tab', 'after-log-tab'):
            self.assertIn(f'id="{old_tab}"', html)
        self.firmware.assert_not_called()

    def test_default_falls_back_to_only_pre_snapshot(self):
        self.content = marked_snapshot(snapshot_fixture('before'), 'PRE_') + '\n' + section('DEBUG_PROTOCOL', CSV)
        html, data = self.render()
        self.assertEqual(data['snapshot'], 'pre')
        self.assertEqual(data['report_snapshots'], ['pre'])
        self.assertIn('before-module-one', html)

    def test_invalid_and_unavailable_snapshot_statuses(self):
        for suffix in ('', '/iso15118.pcap', '/iso15118.json'):
            for snapshot, status in (('invalid', 400), ('before', 400), ('', 400), ('standalone', 404)):
                with self.subTest(suffix=suffix, snapshot=snapshot):
                    response = self.client.get(f'/en/{UUID}{suffix}?snapshot={snapshot}')
                    self.assertEqual(response.status_code, status)
        self.content = marked_snapshot(snapshot_fixture('standalone'))
        self.assertEqual(self.client.get(f'/en/{UUID}?snapshot=pre').status_code, 200)

    def test_standalone_ignores_before_after_selection(self):
        for content in (marked_snapshot(snapshot_fixture('standalone')), legacy_report_fixture()):
            self.content = content
            for selection in ('pre', 'post'):
                with self.subTest(legacy=content.startswith('Scroll'), selection=selection):
                    html, data = self.render(f'?snapshot={selection}')
                    self.assertEqual(data['snapshot'], 'standalone')
                    self.assertFalse(data['has_embedded_reports'])
                    self.assertEqual(data['report_snapshots'], [])
                    self.assertNotIn('id="report-snapshot"', html)
                    self.assertIn('id="report-json"', html)
                    self.assertIn('id="report-log-text"', html)
                    snapshot = parse_document(content)['snapshots']['standalone']
                    with patch.object(main, 'extract_iso15118_pcap', return_value=(b'pcap', 0)) as extract, patch.object(
                        main, 'dissect_iso15118_pcap', return_value=[{'fixture': 'standalone'}],
                    ):
                        for suffix in ('pcap', 'json'):
                            response = self.client.get(f'/en/{UUID}/iso15118.{suffix}?snapshot={selection}')
                            self.assertEqual(response.status_code, 200)
                        extract.assert_called_with(snapshot)

    def test_render_recovery_and_dropped_warnings(self):
        self.content = '\n'.join((
            section('PRE_DEBUG_REPORT', '{broken'),
            section('PRE_TRACE_LOG', 'recovered-trace'),
            section('DEBUG_PROTOCOL', '12345 lines have been dropped from the following table.\n' + CSV),
        ))
        html, data = self.render()
        self.assertEqual(data['report_json'], {})
        self.assertEqual(data['report_trace'], 'recovered-trace')
        self.assertFalse(data['coredump_info']['has_coredump'])
        self.assertEqual(data['dropped_lines_count'], 12345)
        self.assertIn('Invalid JSON in PRE_DEBUG_REPORT.', html)
        self.assertIn('12345', html)
        self.assertEqual(data['all_column_data']['power'], [1200, 3600])

    def test_no_usable_input_returns_400(self):
        self.content = section('DEBUG_REPORT', '{broken')
        response = self.client.get(f'/en/{UUID}')
        self.assertEqual(response.status_code, 400)
        self.assertIn('No usable diagnostic data found.', response.get_data(as_text=True))

    def test_prepare_report_combines_repeated_modules_without_coredump_leakage(self):
        snapshot = snapshot_fixture('repeat')
        snapshot['trace_log'] = '\n'.join((
            'outside-start', '__begin_diagnostic__\nfirst\n__end_diagnostic__',
            'outside-middle', '__begin_diagnostic__\nsecond\n__end_diagnostic__',
            'outside-end',
        ))
        data = main.prepare_report(snapshot, 'en')
        self.assertEqual(data['trace_modules'], {'diagnostic': 'first\nsecond'})
        self.assertEqual(data['report_trace'], 'outside-start\n\noutside-middle\n\noutside-end')
        self.assertEqual(data['coredump_info']['raw_dump'], snapshot['coredump'])
        self.assertNotIn(snapshot['coredump'], data['report_trace'])

    def test_extract_pcap_and_download_use_selected_snapshot_clock(self):
        document = parse_document(self.content)
        for query, key, day in (('?snapshot=pre', 'pre', 1), ('?snapshot=post', 'post', 2), ('', 'post', 2)):
            with self.subTest(query=query):
                epoch = datetime.datetime(2026, 1, day, 12, tzinfo=datetime.timezone.utc).timestamp() - day * 1.25
                trace = f'\n{day * 1000} 02000000000{day}\n'
                with patch.object(main, 'iso15118_ll_to_pcap', return_value=b'synthetic-pcap') as convert:
                    self.assertEqual(main.extract_iso15118_pcap(document['snapshots'][key]), (b'synthetic-pcap', epoch))
                    convert.assert_called_once_with(trace, epoch)
                    convert.reset_mock()
                    response = self.client.get(f'/en/{UUID}/iso15118.pcap{query}')
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data, b'synthetic-pcap')
                    self.assertEqual(response.mimetype, 'application/vnd.tcpdump.pcap')
                    convert.assert_called_once_with(trace, epoch)

    def test_extract_pcap_missing_or_invalid_clock_uses_relative_time(self):
        for report in ({}, {'uptime': 1000}, {'uptime': 'invalid', 'rtc/time': snapshot_fixture('clock')['report_json']['rtc/time']},
                       {'uptime': 1000, 'rtc/time': {'year': 1970}},
                       {'uptime': 1000, 'rtc/time': dict(snapshot_fixture('clock')['report_json']['rtc/time'], year=1970)},
                       {'uptime': 1000, 'rtc/time': 'invalid'}):
            with self.subTest(report=report):
                snapshot = snapshot_fixture('relative')
                snapshot['report_json'] = report
                with patch.object(main, 'iso15118_ll_to_pcap', return_value=b'relative') as convert:
                    self.assertEqual(main.extract_iso15118_pcap(snapshot), (b'relative', 0))
                    convert.assert_called_once_with('\n1000 020000000001\n', 0)

    def test_extract_pcap_does_not_use_trace_from_event_log_or_coredump(self):
        snapshot = snapshot_fixture('no-trace')
        snapshot['event_log'] = snapshot['trace_log']
        snapshot['coredump'] = snapshot['trace_log']
        snapshot['trace_log'] = 'no iso15118 module here'
        with patch.object(main, 'iso15118_ll_to_pcap') as convert:
            self.assertEqual(main.extract_iso15118_pcap(snapshot), (None, 0))
            convert.assert_not_called()

    def test_extract_pcap_includes_repeated_modules(self):
        snapshot = snapshot_fixture('repeat')
        snapshot['trace_log'] += '\n__begin_iso15118_ll__\n2000 020000000002\n__end_iso15118_ll__'
        with patch.object(main, 'iso15118_ll_to_pcap', return_value=b'pcap') as convert:
            main.extract_iso15118_pcap(snapshot)
        self.assertEqual(convert.call_args.args[0], '\n1000 020000000001\n\n\n2000 020000000002\n')

    def test_json_cache_isolated_by_selection_and_reused(self):
        def convert(trace, epoch):
            return b'pre-pcap' if '020000000001' in trace else b'post-pcap'

        with patch.object(main, 'iso15118_ll_to_pcap', side_effect=convert) as converter, patch.object(
            main, 'dissect_iso15118_pcap', side_effect=lambda pcap: [{'fixture': pcap.decode()}],
        ) as dissect:
            for repeat in range(2):
                for query, expected, offset in (
                    ('?snapshot=pre', 'pre-pcap', 0),
                    ('?snapshot=post', 'post-pcap', 3600),
                    ('', 'post-pcap', 3600),
                ):
                    with self.subTest(repeat=repeat, query=query):
                        headers = {'Accept-Encoding': 'gzip'} if repeat else {}
                        response = self.client.get(f'/en/{UUID}/iso15118.json{query}', headers=headers)
                        self.assertEqual(response.status_code, 200)
                        payload = json.loads(gzip.decompress(response.data)) if repeat else response.get_json()
                        self.assertEqual(payload, {
                            'has_boot_epoch': True, 'tz_offset': offset,
                            'packets': [{'fixture': expected}],
                        })
                        if repeat:
                            self.assertEqual(response.headers['Content-Encoding'], 'gzip')
                if not repeat:
                    calls = dissect.call_count
                    self.assertGreaterEqual(calls, 2)
                    converter_calls = converter.call_count
                    loader_calls = self.loader.call_count
            self.assertEqual(dissect.call_count, calls)
            self.assertEqual(converter.call_count, converter_calls)
            self.assertEqual(self.loader.call_count, loader_calls)

    def test_json_invalid_default_selector_rejected_on_cold_and_warm_cache(self):
        with patch.object(main, 'iso15118_ll_to_pcap', return_value=b'post-pcap'), patch.object(
            main, 'dissect_iso15118_pcap', return_value=[{'fixture': 'post'}],
        ):
            explicit = self.client.get(f'/en/{UUID}/iso15118.json?snapshot=default')
            implicit = self.client.get(f'/en/{UUID}/iso15118.json')
            warm_explicit = self.client.get(f'/en/{UUID}/iso15118.json?snapshot=default')
        self.assertEqual(implicit.status_code, 200)
        self.assertEqual(warm_explicit.status_code, 400)
        self.assertEqual(explicit.status_code, 400)


if __name__ == '__main__':
    unittest.main()
