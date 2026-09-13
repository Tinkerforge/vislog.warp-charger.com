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
