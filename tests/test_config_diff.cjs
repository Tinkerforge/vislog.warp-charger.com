// Run with: node --test tests/test_config_diff.cjs
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
const diff = (before, after) => JSON.parse(JSON.stringify(context.configDiff(before, after)));

test('compares nested values without depending on object key order', () => {
    assert.deepEqual(diff({a: {b: 1, c: [null, false, 'text', {}]}},
        {a: {c: [null, false, 'text', {}], b: 1}}), []);
    assert.deepEqual(diff({'evse/config': {current: 6000}}, {'evse/config': {current: 16000}}), [
        {path: '$["evse/config"]["current"]', status: 'changed', before: 6000, after: 16000},
    ]);
});

test('distinguishes absent values from null and preserves added/removed subtrees', () => {
    assert.deepEqual(diff({removed: {enabled: true}, nullable: null}, {added: null, nullable: false}), [
        {path: '$["added"]', status: 'added', after: null},
        {path: '$["nullable"]', status: 'changed', before: null, after: false},
        {path: '$["removed"]', status: 'removed', before: {enabled: true}},
    ]);
    assert.deepEqual(diff({}, {empty: {}}), [{path: '$["empty"]', status: 'added', after: {}}]);
});

test('compares arrays by index including growth and shrinkage', () => {
    assert.deepEqual(diff({slots: [1, {active: false}]}, {slots: [1, {active: true}, null]}), [
        {path: '$["slots"][1]["active"]', status: 'changed', before: false, after: true},
        {path: '$["slots"][2]', status: 'added', after: null},
    ]);
    assert.deepEqual(diff([1, 2], [1]), [{path: '$[1]', status: 'removed', before: 2}]);
});

test('reports type changes, including empty containers and falsy values', () => {
    for (const [before, after] of [[{}, []], [[], null], [0, false], [1, '1'], ['', null]]) {
        assert.deepEqual(diff({value: before}, {value: after}), [
            {path: '$["value"]', status: 'changed', before, after},
        ]);
    }
});

test('keeps special keys unambiguous and treats prototype names as ordinary data', () => {
    const before = JSON.parse('{"__proto__":1,"a.b":1,"a":{"b":1},"quote\\\"":1}');
    const after = JSON.parse('{"__proto__":2,"a.b":2,"a":{"b":2},"quote\\\"":2,"constructor":null}');
    const rows = diff(before, after);
    assert.deepEqual(rows.map(row => row.path), [
        '$["__proto__"]', '$["a"]["b"]', '$["a.b"]', '$["constructor"]', '$["quote\\\""]',
    ]);
    assert.equal(rows[3].status, 'added');
    assert.deepEqual(before, JSON.parse('{"__proto__":1,"a.b":1,"a":{"b":1},"quote\\\"":1}'));
});
