// Run with: node --test tests/test_timeline.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

const context = vm.createContext({
    localStorage: {getItem: () => null},
    document: {
        documentElement: {setAttribute() {}},
        readyState: 'loading', addEventListener() {},
    },
});
vm.runInContext(fs.readFileSync(__dirname + '/../static/vislog.js', 'utf8'), context);
const evaluate = code => vm.runInContext(code, context);

test('state bands follow irregular sample times and stop at the final sample', () => {
    const segments = evaluate('protoStateSegments([1000, 1500, 3100, 4000], [0, 0, 1, 2])');
    assert.deepEqual(JSON.parse(JSON.stringify(segments)), [
        {start: 1000, end: 3100, value: 0},
        {start: 3100, end: 4000, value: 1},
        {start: 4000, end: 4000, value: 2},
    ]);
});

test('missing state samples form unknown intervals rather than extending the previous state', () => {
    const segments = evaluate('protoStateSegments([0, 1, 2, 3, 4], [2, null, NaN, -1, 2])');
    assert.deepEqual(JSON.parse(JSON.stringify(segments)), [
        {start: 0, end: 1, value: 2}, {start: 1, end: 4, value: null}, {start: 4, end: 4, value: 2},
    ]);
    assert.equal(evaluate('protoStateSegments([], []).length'), 0);
});

test('state lanes use sample indices on invalid clocks and only include available signals', () => {
    const lanes = evaluate(`protoBuildStateLanes({numeric_time_axis: false,
        labels: ['a', 'b', 'c'], sample_times_ms: [100, 200, 10],
        after_protocol_json: {'info/name': {type: 'warp3'}},
        all_column_data: {iec61851_state: [0, 1, 2], contactor_error: [null, null, null], power: [0, 0, 0]}})`);
    assert.equal(lanes.length, 1);
    assert.equal(lanes[0].hw, 4);
    assert.equal(lanes[0].segments[2].start, 2);
});

test('contactor decoding distinguishes monitoring bits across hardware generations', () => {
    evaluate(`var T = {state_unknown: 'Unknown', state_open: 'Open', state_error: 'Error',
        state_monitor_1: 'Input live', state_ok: 'OK'};`);
    assert.equal(evaluate(`protoStateDescription('contactor_state', 1, 1).label`), 'Input live');
    assert.equal(evaluate(`protoStateDescription('contactor_state', 1, 4).label`), 'L1+N');
    assert.equal(evaluate(`protoStateDescription('contactor_state', 31, 32).color`), 'error');
    assert.equal(evaluate(`protoStateDescription('contactor_state', 1, -1).color`), 'unknown');
    assert.equal(evaluate(`protoStateDescription('contactor_error', 0, -1).color`), 'idle');
    assert.equal(evaluate(`protoStateDescription('error_state', 2, -1).color`), 'error');
});

test('nearby packets cluster by lane and split as time scale expands', () => {
    evaluate(`
        var packets = ['HomePlug AV', 'HomePlug AV', 'TCP', 'V2GMSG (ISO-2)', 'ICMPv6']
            .map((proto, i) => [i + 1, 0, '', '', proto]);
        var times = [1000, 1051, 1051, 1051, 9000];
    `);
    assert.equal(evaluate('protoIsoClusters(times, packets, 1000, 9000, 800).length'), 4);
    assert.equal(evaluate('protoIsoClusters(times, packets, 1000, 1100, 800).length'), 4);
    assert.equal(evaluate('protoIsoClusters(times, packets, 1100, 8999, 800).length'), 0);
    assert.equal(evaluate('protoIsoClusters(times, packets, 1000, 9000, 800)[0].indices.length'), 2);
    assert.equal(evaluate('protoIsoClusters(times, packets, 1000, 1100, 800)[0].indices.length'), 1);
});

test('cluster boundaries leave enough space for count labels', () => {
    evaluate(`var closePackets = Array.from({length: 5}, () => [0, 0, '', '', 'TCP']);`);
    const spacing = evaluate(`protoIsoClusters([19, 21, 39, 41, 80], closePackets, 0, 100, 100)
        .map(c => c.pixel)`);
    assert.deepEqual(Array.from(spacing), [19, 80]);
});

test('wall time and uptime keep milliseconds without wrapping uptime at 24 hours', () => {
    evaluate('protoData = {time_offset_ms: null}');
    assert.equal(evaluate('protoFormatTime(90061051)'), '25:01:01.051');
    evaluate('protoData.time_offset_ms = Date.UTC(2026, 0, 1, 23, 59, 59)');
    assert.equal(evaluate('protoFormatTime(1051)'), '00:00:00.051');
    assert.equal(evaluate('protoFormatTime(1051, false)'), '00:00:00');
});
