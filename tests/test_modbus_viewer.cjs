// Run with: node --test tests/test_modbus_viewer.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

const context = vm.createContext({
    localStorage: {getItem: () => null},
    document: {documentElement: {setAttribute() {}}, readyState: 'loading', addEventListener() {}},
});
vm.runInContext(fs.readFileSync(__dirname + '/../static/vislog.js', 'utf8'), context);
vm.runInContext(`var T = {modbus_client: 'Client', modbus_server: 'Charger', modbus_lines: 'Lines',
    modbus_connection: 'Connection', modbus_endpoint: 'Endpoint', modbus_frame: 'Frame',
    modbus_C: 'Connected', modbus_D: 'Disconnected', modbus_incomplete: 'Incomplete',
    modbus_message: 'Message', modbus_payload: 'Payload', modbus_raw_trace: 'Raw'};`, context);

function rows(data, serverName) {
    context.fixture = data;
    context.serverName = serverName;
    return JSON.parse(JSON.stringify(vm.runInContext('modbusViewerRows(fixture, serverName)', context)));
}

test('frame numbers map to messages despite intervening connection events', () => {
    const result = rows({
        connections: [{connection: 1, client: '18446744073709551615', endpoint: '::1:50000', ip: '2001:db8::1'}],
        events: [
            {kind: 'C', client: '18446744073709551615', connection: 1, lines: [1]},
            {kind: 'message', client: '18446744073709551615', connection: 1, lines: [2, 3], direction: 'R', frame: 1, data: '000100000006010300000001'},
            {kind: 'message', client: '18446744073709551615', connection: 1, lines: [4], direction: 'S', frame: 2, data: '0001000000050103021234'},
            {kind: 'D', client: '18446744073709551615', connection: 1, lines: [5]},
        ],
        packets: [[1, 0, '', '', 'Modbus/TCP', 86, 'Query', ['Decoded query']],
                  [2, .001, '', '', 'Modbus/TCP', 84, 'Response', ['Decoded response']]],
    }, 'warp3-2dkh');
    assert.equal(result[0].info, 'Connected');
    assert.deepEqual(result[1].cells, [2, 'Client 18446744073709551615', 'warp3-2dkh', 'Modbus/TCP', 12, 'Query']);
    assert.equal(result[2].cells[1], 'warp3-2dkh');
    assert.equal(result[2].cells[2], 'Client 18446744073709551615');
    assert.ok(result[1].tree.includes('Frame: 1'));
    assert.ok(result[2].tree.includes('Decoded response'));
    assert.equal(result[3].info, 'Disconnected');
    assert.equal(result[1].endpoint, '::1:50000');
});

test('missing dissection preserves payloads, incomplete messages and unrecognized lines', () => {
    const result = rows({connections: [], packets: [], events: [
        {kind: 'message', client: '0', lines: [1], direction: 'R', frame: 1, data: '0102'},
        {kind: 'incomplete', client: '0', lines: [2], direction: 'S', data: '0001'},
        {kind: 'invalid_line', lines: [3], data: '<script>not markup</script>'},
    ]});
    assert.equal(result[0].cells[3], 'Modbus/TCP');
    assert.deepEqual(result[0].tree.at(-1), ['Payload', ['0102']]);
    assert.equal(result[1].info, 'Incomplete');
    assert.deepEqual(result[2].tree.at(-1), ['Raw', ['<script>not markup</script>']]);
    assert.equal(result[2].cells[4], '—');
});
