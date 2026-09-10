"""Read legacy and section-delimited WARP diagnostic files without Flask state."""

import json
import re


_MARKER = re.compile(r'^___([A-Z0-9_]+)_(START|END)___[ \t]*$', re.MULTILINE)
_REPORT_PARTS = ('DEBUG_REPORT', 'EVENT_LOG', 'TRACE_LOG', 'CORE_DUMP')
_SECTION_ALIASES = {prefix + 'COREDUMP': prefix + 'CORE_DUMP' for prefix in ('', 'PRE_', 'POST_')}


def parse_document(content):
    content = content.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    warnings = []
    dropped = re.search(r'^(\d+) lines have been dropped from the following table\.[ \t]*$',
                        content, re.MULTILINE)
    dropped_count = int(dropped[1]) if dropped else None
    content = re.sub(r'^\d+ lines have been dropped from the following table\.[ \t]*(?:\n\n|\n|$)',
                     '', content, flags=re.MULTILINE)
    markers = list(_MARKER.finditer(content))
    # Legacy reports have start-only TRACE_LOG and CORE_DUMP markers.
    marked = any(m[1] in ('DEBUG_REPORT', 'DEBUG_PROTOCOL', 'EVENT_LOG', 'COREDUMP') or
                 m[1].startswith(('PRE_', 'POST_')) or
                 (m[1] in ('TRACE_LOG', 'CORE_DUMP') and m[2] == 'END') for m in markers)
    sections = {}
    if marked:
        active = None
        start = 0

        def store(name, text):
            if name in sections:
                warnings.append(f'Duplicate section {name}; using the first occurrence.')
            else:
                # Only remove separator newlines: log timestamps are space-aligned.
                sections[name] = _MARKER.sub('', text).strip('\n')

        for marker in markers:
            name, boundary = _SECTION_ALIASES.get(marker[1], marker[1]), marker[2]
            if boundary == 'START':
                if active is not None:
                    warnings.append(f'Missing end marker for {active}.')
                    store(active, content[start:marker.start()])
                active, start = name, marker.end()
            elif active == name:
                store(active, content[start:marker.start()])
                active = None
            else:
                warnings.append(f'Unexpected end marker for {name}.')
                if active is not None and name.removeprefix('PRE_').removeprefix('POST_') in _REPORT_PARTS:
                    # The boundary is ambiguous: do not expose another section's
                    # payload (notably a coredump) as a trace or event log.
                    warnings.append(f'Missing end marker for {active}.')
                    active = None
        if active is not None:
            warnings.append(f'Missing end marker for {active}.')
            store(active, content[start:])

        known = {'DEBUG_PROTOCOL'} | {
            prefix + part for prefix in ('', 'PRE_', 'POST_') for part in _REPORT_PARTS
        }
        for name in sections.keys() - known:
            warnings.append(f'Unknown section {name}; not displayed.')
        is_protocol = ('DEBUG_PROTOCOL' in sections or
                       any(name.startswith(('PRE_', 'POST_')) for name in sections.keys() & known))
    else:
        blocks = content.split('\n\n')
        is_report = len(blocks[0]) < 100 and 'Scroll down for event log!' in blocks[0]
        is_protocol = not is_report
        if is_report:
            sections['DEBUG_REPORT'] = blocks[1] if len(blocks) > 1 else ''
            sections['EVENT_LOG'] = blocks[2] if len(blocks) > 2 else ''
            # Legacy trace/coredump sections have start markers, but no required ends.
            remainder = '\n\n'.join(blocks[3:])
            legacy_markers = list(_MARKER.finditer(remainder))
            for i, marker in enumerate(legacy_markers):
                if marker[2] != 'START':
                    continue
                end = legacy_markers[i + 1].start() if i + 1 < len(legacy_markers) else len(remainder)
                name = _SECTION_ALIASES.get(marker[1], marker[1])
                sections[name] = remainder[marker.end():end].strip()
        else:
            for index, name in enumerate(('PRE_DEBUG_REPORT', 'PRE_EVENT_LOG', 'DEBUG_PROTOCOL',
                                          'POST_DEBUG_REPORT', 'POST_EVENT_LOG')):
                if index < len(blocks):
                    sections[name] = blocks[index]

    snapshots = {}
    for snapshot, prefix in (('standalone', ''), ('pre', 'PRE_'), ('post', 'POST_')):
        if not any(prefix + part in sections for part in _REPORT_PARTS):
            continue
        raw_json = sections.get(prefix + 'DEBUG_REPORT', '')
        report_json = {}
        if raw_json:
            try:
                report_json = json.loads(raw_json.replace('": ,', '": {},'))
                if not isinstance(report_json, dict):
                    raise ValueError('Expected a JSON object')
            except (json.JSONDecodeError, ValueError):
                warnings.append(f'Invalid JSON in {prefix}DEBUG_REPORT.')
                report_json = {}
        else:
            warnings.append(f'Missing {prefix}DEBUG_REPORT data.')
        snapshots[snapshot] = {
            'report_json': report_json,
            'event_log': sections.get(prefix + 'EVENT_LOG', ''),
            'trace_log': sections.get(prefix + 'TRACE_LOG', ''),
            'coredump': sections.get(prefix + 'CORE_DUMP'),
        }

    csv = sections.get('DEBUG_PROTOCOL', '').strip()
    has_csv = bool(csv and 'millis' in csv.split('\n', 1)[0].split(','))
    if is_protocol and not has_csv:
        warnings.append('Missing charge table or millis column.')
    usable_reports = any(s['report_json'] or s['event_log'] or s['trace_log'] or s['coredump']
                         for s in snapshots.values())
    if not has_csv and not usable_reports:
        raise ValueError('No usable diagnostic data found.')
    return {
        'is_protocol': is_protocol,
        'has_embedded_reports': marked and is_protocol,
        'snapshots': snapshots,
        'protocol_csv': csv,
        'dropped_lines_count': dropped_count,
        'warnings': warnings,
    }
