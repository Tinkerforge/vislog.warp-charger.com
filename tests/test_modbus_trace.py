"""Socket reconstruction and built-in Wireshark Modbus decoding regression tests."""

import gzip
import ipaddress
import os
import struct
import tempfile
import unittest
from unittest.mock import patch

from modbus_trace import reconstruct_modbus_trace, checksum, parse_endpoint, modbus_register_info
from tests.test_input_formats import main, snapshot_fixture, UUID


QUERY = '000100000009011003e80001020001'
REPLY = '000100000006011003e80001'


def frames(pcap):
    offset = 24
    while offset < len(pcap):
        seconds, micros, length, original = struct.unpack_from('<IIII', pcap, offset)
        assert length == original
        yield seconds + micros / 1e6, pcap[offset + 16:offset + 16 + length]
        offset += 16 + length


def snapshot(trace):
    result = snapshot_fixture('modbus')
    result['trace_log'] = f'__begin_modbus_tcp_srvr__\n{trace}\n__end_modbus_tcp_srvr__'
    return result


class ModbusReconstructionTests(unittest.TestCase):
    def test_split_coalesced_and_interleaved_directions(self):
        trace = '\n'.join((
            '0C10.2.4.11:43046', '1C2001:db8::1:50000',
            '0R' + QUERY[:14], '1R' + QUERY, '0R' + QUERY[14:] + QUERY,
            '0S' + REPLY[:8], '1S' + REPLY, '0S' + REPLY[8:],
        ))
        pcap, metadata = reconstruct_modbus_trace(trace)
        messages = [event for event in metadata['events'] if event['kind'] == 'message']
        self.assertEqual([event['lines'] for event in messages], [[4], [3, 5], [5], [7], [6, 8]])
        self.assertEqual([event['client'] for event in messages], ['1', '0', '0', '1', '0'])
        packets = list(frames(pcap))
        self.assertEqual([frame[74:].hex() for _, frame in packets], [QUERY, QUERY, QUERY, REPLY, REPLY])
        self.assertEqual([time for time, _ in packets], [0, .001, .002, .003, .004])
        for _, frame in packets:
            self.assertEqual(frame[12:14], b'\x86\xdd')
            tcp = frame[54:]
            pseudo = frame[22:54] + struct.pack('!I3xB', len(tcp), 6)
            self.assertEqual(checksum(pseudo + tcp), 0)
        # Client 0's sequence advances for its second query, independent of client 1.
        self.assertEqual(struct.unpack_from('!I', packets[2][1], 58)[0], 1 + len(bytes.fromhex(QUERY)))
        self.assertEqual(struct.unpack_from('!I', packets[4][1], 62)[0], 1 + 2 * len(bytes.fromhex(QUERY)))

    def test_uint64_ids_ipv6_and_reused_connections(self):
        client = '18446744073709551615'
        trace = '\n'.join((f'{client}C[2001:db8::12]:55000', f'{client}R{QUERY}',
                           f'{client}D[2001:db8::12]:55000', f'{client}C::ffff:192.0.2.1:55000',
                           f'{client}R{QUERY}'))
        pcap, metadata = reconstruct_modbus_trace(trace)
        a, b = metadata['connections']
        self.assertEqual(a['client'], client)
        self.assertNotEqual(a['ip'], b['ip'])
        self.assertEqual(int(ipaddress.IPv6Address(a['ip'])) & ((1 << 64) - 1), int(client))
        self.assertNotEqual(list(frames(pcap))[0][1][22:38], list(frames(pcap))[1][1][22:38])
        self.assertEqual(parse_endpoint('::ffff:192.0.2.1:55000'), ('::ffff:192.0.2.1', 55000))

    def test_incomplete_and_malformed_streams_remain_visible(self):
        for ending in ('', '\n0D192.0.2.1:1234', '\n0C192.0.2.2:1234'):
            _, metadata = reconstruct_modbus_trace('0R' + QUERY[:14] + ending)
            self.assertTrue(any(event['kind'] == 'incomplete' for event in metadata['events']))
            self.assertFalse(any(event['kind'] == 'message' for event in metadata['events']))
        pcap, metadata = reconstruct_modbus_trace('\n'.join((
            '0R000100000001', '0R' + QUERY, '0S' + REPLY,
            '0C192.0.2.1:1234', '0R' + QUERY)))
        self.assertEqual([frame[74:].hex() for _, frame in frames(pcap)], [REPLY, QUERY])
        self.assertIn('malformed', [event['kind'] for event in metadata['events']])
        self.assertIn('unframed', [event['kind'] for event in metadata['events']])

    def test_invalid_hex_does_not_discard_other_direction(self):
        pcap, metadata = reconstruct_modbus_trace('\n'.join((
            '0S' + REPLY[:10], '0Rabc', '0S' + REPLY[10:], '0R' + QUERY)))
        self.assertEqual([frame[74:].hex() for _, frame in frames(pcap)], [REPLY])
        self.assertIn('invalid_hex', [event['kind'] for event in metadata['events']])
        self.assertIn('unframed', [event['kind'] for event in metadata['events']])

    def test_unknown_line_stops_active_streams_and_invalid_endpoint_is_visible(self):
        pcap, metadata = reconstruct_modbus_trace('\n'.join((
            '0Cbad:999999', '0R' + QUERY[:10], 'dropped lines', '0R' + QUERY,
            '0C192.0.2.1:1234', '0R' + QUERY)))
        self.assertEqual(len(list(frames(pcap))), 1)
        kinds = [event['kind'] for event in metadata['events']]
        for kind in ('invalid_endpoint', 'incomplete', 'invalid_line', 'unframed'):
            self.assertIn(kind, kinds)

    @unittest.skipUnless(main.TSHARK_PATH, 'tshark unavailable')
    def test_real_dissector_decodes_requests_responses_and_registers(self):
        pcap, _ = reconstruct_modbus_trace('\n'.join((
            '0C192.0.2.1:43046', '0R' + QUERY[:14], '0R' + QUERY[14:], '0S' + REPLY,
            '1C2001:db8::1:50000', '1R' + QUERY, '1S' + REPLY)))
        packets = main.dissect_pcap(pcap, ['-n', '-d', 'tcp.port==502,mbtcp', '-o', 'tcp.check_checksum:TRUE'])
        self.assertEqual(len(packets), 4)
        for index, packet in enumerate(packets):
            self.assertEqual(packet[4], 'Modbus/TCP')
            self.assertIn('Query' if index % 2 == 0 else 'Response', packet[6])
            self.assertIn('Write Multiple Registers', packet[6])
            self.assertIn('1000', str(packet[7]))

    @unittest.skipUnless(main.TSHARK_PATH, 'tshark unavailable')
    def test_reused_endpoint_and_server_port_as_client_port(self):
        pcap, _ = reconstruct_modbus_trace('\n'.join((
            '0C::1:502', '0R' + QUERY, '0S' + REPLY, '0D::1:502',
            '0C::1:502', '0R' + QUERY, '0S' + REPLY)))
        packets = main.dissect_pcap(pcap)
        self.assertEqual(len(packets), 4)
        self.assertTrue(all(packet[4] == 'Modbus/TCP' for packet in packets))
        self.assertIn('Query', packets[2][6])
        self.assertIn('Response', packets[3][6])

    @unittest.skipUnless(main.TSHARK_PATH, 'tshark unavailable')
    def test_register_overview_values_for_writes_reads_and_exceptions(self):
        pcap, _ = reconstruct_modbus_trace('\n'.join((
            '0R' + QUERY, '0S' + REPLY,
            '0R000200000006010300640002', '0S0002000000070103041234abcd',
            '0R000300000006010600650009', '0S000300000006010600650009',
            '0R000400000006010400640001', '0S000400000003018402',
            # No request for this connection: show values without invented addresses.
            '1S0002000000070103041234abcd')))
        packets = main.dissect_pcap(pcap, ['-n', '-d', 'tcp.port==502,mbtcp'],
                                    summary_annotation=modbus_register_info)
        self.assertEqual(len(packets), 9)
        self.assertIn('Register 1000 = 1 (0x0001)', packets[0][6])
        self.assertNotIn(' | ', packets[1][6])
        self.assertNotIn(' | ', packets[2][6])
        self.assertIn('Register 100 = 4660 (0x1234); Register 101 = 43981 (0xabcd)', packets[3][6])
        for index in (4, 5):
            self.assertIn('Register 101 = 9 (0x0009)', packets[index][6])
        self.assertNotIn(' | ', packets[7][6])
        self.assertIn('Value = 4660 (0x1234)', packets[8][6])
        self.assertNotIn('Register 0 =', packets[8][6])


class ModbusEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()
        directory = self.enterContext(tempfile.TemporaryDirectory(prefix='modbus-', dir='/tmp/opencode'))
        self.enterContext(patch.object(main, 'PROTOCOL_DIR', directory))
        exists = os.path.exists
        self.enterContext(patch.object(main.os.path, 'exists', side_effect=lambda path:
                                     path == os.path.join(directory, UUID) or exists(path)))
        self.document = {'is_protocol': True, 'snapshots': {
            'pre': snapshot('0R' + QUERY), 'post': snapshot('1R' + QUERY + '\n1S' + REPLY)}}
        self.enterContext(patch.object(main, 'read_and_preprocess_protocol', side_effect=lambda _: self.document))
        self.enterContext(patch.object(main, 'check_firmware_version', return_value=None))

    def test_snapshot_download_and_cache_isolation(self):
        with patch.object(main, 'TSHARK_PATH', '/synthetic/tshark'), patch.object(
                main, 'dissect_pcap', return_value=[[1, 0, '', '', 'Modbus/TCP', 88, 'Query', []]]) as dissect:
            for query, count in (('?snapshot=pre', 1), ('?snapshot=post', 2), ('', 2)):
                response = self.client.get(f'/en/{UUID}/modbus.pcap{query}')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(list(frames(response.data))), count)
                self.assertIn('reconstructed', response.headers['Content-Disposition'])
                response = self.client.get(f'/en/{UUID}/modbus.json{query}', headers={'Accept-Encoding': 'gzip'})
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'"synthetic":true', gzip.decompress(response.data))
            self.assertEqual(dissect.call_count, 2)

    def test_validation_empty_and_standalone(self):
        for suffix in ('json', 'pcap'):
            for query, expected in (('?snapshot=bad', 400), ('?snapshot=', 400), ('?snapshot=standalone', 404)):
                self.assertEqual(self.client.get(f'/en/{UUID}/modbus.{suffix}{query}').status_code, expected)
            self.assertEqual(self.client.get(f'/xx/{UUID}/modbus.{suffix}').status_code, 404)
            self.assertEqual(self.client.get(f'/en/Unknown/modbus.{suffix}').status_code, 404)
        self.document = {'is_protocol': False, 'snapshots': {'standalone': snapshot('0R' + QUERY)}}
        self.assertEqual(self.client.get(f'/en/{UUID}/modbus.pcap?snapshot=pre').status_code, 200)
        self.document['snapshots']['standalone'] = snapshot('')
        self.assertEqual(self.client.get(f'/en/{UUID}/modbus.pcap').status_code, 404)

    def test_no_tshark_and_failed_dissection_keep_events_and_retry(self):
        with patch.object(main, 'TSHARK_PATH', None):
            response = self.client.get(f'/en/{UUID}/modbus.json')
            self.assertEqual(response.json['dissection_error'], 'tshark-unavailable')
            self.assertEqual(len(response.json['events']), 2)
            self.assertEqual(self.client.get(f'/en/{UUID}/modbus.pcap').status_code, 200)
        with patch.object(main, 'TSHARK_PATH', '/synthetic/tshark'), patch.object(main, 'dissect_pcap', return_value=None) as dissect:
            self.assertEqual(self.client.get(f'/en/{UUID}/modbus.json').json['dissection_error'], 'dissection-failed')
            self.client.get(f'/en/{UUID}/modbus.json')
            self.assertEqual(dissect.call_count, 2)

    def test_connection_only_and_repeated_modules(self):
        snap = snapshot('0C::1:4000\n0D::1:4000')
        snap['trace_log'] += '\n' + snapshot('1R' + QUERY)['trace_log']
        pcap, metadata = main.extract_modbus_capture(snap)
        self.assertEqual(len(list(frames(pcap))), 1)
        self.assertEqual(metadata['events'][-1]['lines'], [3])
        self.document['snapshots']['post'] = snapshot('0C::1:4000\n0D::1:4000')
        with patch.object(main, 'dissect_pcap') as dissect:
            data = self.client.get(f'/en/{UUID}/modbus.json').json
            self.assertEqual([event['kind'] for event in data['events']], ['C', 'D'])
            dissect.assert_not_called()

    def test_viewer_render_and_raw_fallback(self):
        snap = snapshot('0C::1:4000\n0R' + QUERY)
        with main.app.test_request_context(f'/en/{UUID}'), patch.object(main, 'TSHARK_PATH', None):
            data = main.prepare_report(snap, 'en')
            self.assertTrue(data['modbus_tcp_available'])
            data.update(has_embedded_reports=True, snapshot='pre')
            html = main.render_template('report.html', data=data, t=main.get_translations('en'), lang='en')
            self.assertIn('id="modbus-tbody"', html)
            self.assertIn('modbus.pcap?snapshot=pre', html)
            self.assertIn('id="trace-modbus_tcp_srvr-text"', html)
            self.assertIn('Reconstructed TCP/IP trace', html)


if __name__ == '__main__':
    unittest.main()
