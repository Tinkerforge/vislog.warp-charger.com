// Run with: node --test tests/test_event_log.cjs
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
const merge = (before, after) => JSON.parse(JSON.stringify(context.mergeEventLogs(before, after)));

test('appended entries appear once after the complete before log', () => {
    assert.deepEqual(merge('1 start\n2 ready', '1 start\n2 ready\n3 charging'), {
        before: ['1 start', '2 ready'], after: ['3 charging'], overlap: 2,
    });
});

test('ring-buffer truncation keeps older entries and removes the overlapping suffix', () => {
    assert.deepEqual(merge('1 start\n2 ready\n3 charging', '2 ready\n3 charging\n4 stopped'), {
        before: ['1 start', '2 ready', '3 charging'], after: ['4 stopped'], overlap: 2,
    });
});

test('identical logs and shorter suffixes contain no new entries', () => {
    assert.deepEqual(merge('a\nb', 'a\nb'), {before: ['a', 'b'], after: [], overlap: 2});
    assert.deepEqual(merge('a\nb', 'b'), {before: ['a', 'b'], after: [], overlap: 1});
});

test('nonoverlapping and missing snapshots preserve all available text', () => {
    assert.deepEqual(merge('before', 'after'), {before: ['before'], after: ['after'], overlap: 0});
    assert.deepEqual(merge('', 'after'), {before: [], after: ['after'], overlap: 0});
    assert.deepEqual(merge('before', ''), {before: ['before'], after: [], overlap: 0});
    assert.deepEqual(merge('', ''), {before: [], after: [], overlap: 0});
});

test('repeated messages only deduplicate the longest boundary overlap', () => {
    assert.deepEqual(merge('a\nb\na\nb', 'a\nb\nc\na'), {
        before: ['a', 'b', 'a', 'b'], after: ['c', 'a'], overlap: 2,
    });
    assert.equal(merge('a\nb\nc', 'a\nb').overlap, 0);
});

test('normalizes line endings while preserving indentation and interior blank lines', () => {
    assert.deepEqual(merge('\r\n  1 startup\r\n\r\n  2 ready\r\n', '  1 startup\n\n  2 ready\n  3 next'), {
        before: ['  1 startup', '', '  2 ready'], after: ['  3 next'], overlap: 3,
    });
    assert.equal(merge('a\n ', ' \nb').overlap, 0);
});
