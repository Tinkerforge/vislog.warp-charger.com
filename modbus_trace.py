"""Reconstruct Modbus ADUs from socket traces; all capture framing is synthetic."""

from collections import deque
import ipaddress
import re
import struct


def checksum(data):
    data += b'\0' * (len(data) % 2)
    total = sum(struct.unpack(f'!{len(data) // 2}H', data))
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return ~total & 0xffff


def parse_endpoint(value):
    address, port = value.rsplit(':', 1)
    ipaddress.ip_address(address.strip('[]'))
    if not port.isdecimal() or not 0 < int(port) <= 65535:
        raise ValueError('Invalid port')
    return address, int(port)


def modbus_register_info(packet):
    """Summarize Wireshark's decoded register values from a PDML packet.

    Read responses without a matching request have no known register address.
    Write-multiple acknowledgements contain no values and get no annotation.
    """
    entries = []
    for proto in packet.findall("proto[@name='modbus']"):
        fields = {field.get('name'): field for field in proto.findall('field')}
        if 'modbus.exception_code' in fields:
            continue
        function = fields.get('modbus.func_code')
        if function is None:
            continue
        code = function.get('show')
        address_known = (code not in ('3', '4', '23') or 'modbus.request_frame' in fields
                         or 'modbus.write_reference_num' in fields)
        for group in proto.iter('field'):
            number = next((field for field in group if field.get('name') in
                           ('modbus.regnum16', 'modbus.regnum32')), None)
            value = next((field for field in group if
                          field.get('name', '').startswith('modbus.regval_')), None)
            if number is not None and value is not None:
                label = f"Register {number.get('show')}" if address_known else 'Value'
                entries.append(f"{label} = {value.get('show')} (0x{value.get('value')})")
        # Wireshark exposes function 6 as raw modbus.data instead of regval_*.
        if code == '6' and 'modbus.reference_num' in fields and 'modbus.data' in fields:
            raw = fields['modbus.data'].get('value', '')
            if re.fullmatch('[0-9a-fA-F]{4}', raw):
                address = fields['modbus.reference_num'].get('show')
                entries.append(f'Register {address} = {int(raw, 16)} (0x{raw})')
    return '; '.join(entries)


def reconstruct_modbus_trace(content):
    """Return (pcap, metadata). Line references are 1-based within content.

    Each complete MBAP-framed ADU becomes one packet. Partial/malformed input
    remains visible as diagnostic events and is never guessed into a message.
    IPv6 embeds a connection instance and the full firmware uint64 client ID.
    Port 502 is used for automatic decoding even if the real server uses a
    different port. Capture timestamps only encode message order.
    """
    pcap = bytearray(struct.pack('<IHHiIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
    connections, active, events = [], {}, []
    frame_count = 0

    def connection(client):
        if client not in active:
            instance = len(connections) + 1
            address = ipaddress.IPv6Address((int(ipaddress.IPv6Address('2001:db8::'))
                                            + (instance << 64) + int(client)))
            info = {'client': client, 'connection': instance, 'endpoint': None,
                    'ip': str(address), 'port': 0}
            connections.append(info)
            active[client] = {'info': info, 'seq': [1, 1], 'buffers': [bytearray(), bytearray()],
                              'sources': [deque(), deque()], 'broken': [False, False]}
        return active[client]

    def event(state, kind, lines, **extra):
        item = {'kind': kind, 'client': state['info']['client'],
                'connection': state['info']['connection'], 'lines': lines, **extra}
        events.append(item)
        return item

    def flush(state, directions=(0, 1)):
        for direction in directions:
            if state['buffers'][direction]:
                event(state, 'incomplete', [line for line, _ in state['sources'][direction]],
                      direction='R' if direction == 0 else 'S',
                      data=state['buffers'][direction].hex())
                state['buffers'][direction].clear()
                state['sources'][direction].clear()

    def packet(state, direction, payload):
        nonlocal frame_count
        frame_count += 1
        info = state['info']
        client_ip = ipaddress.IPv6Address(info['ip']).packed
        server_ip = ipaddress.IPv6Address('2001:db8:ffff:ffff:ffff:ffff:ffff:ffff').packed
        client_mac = b'\x02\x00' + struct.pack('!I', info['connection'])
        server_mac = b'\x02\xff\xff\xff\xff\xff'
        # Both ports being 502 makes request/response direction ambiguous to
        # Wireshark. The logged endpoint remains available in metadata.
        client_port = info['port'] if info['port'] not in (0, 502) else 49152
        src, dst, smac, dmac, sport, dport = (
            (client_ip, server_ip, client_mac, server_mac, client_port, 502) if direction == 0 else
            (server_ip, client_ip, server_mac, client_mac, 502, client_port))
        seq = state['seq']
        tcp = struct.pack('!HHIIBBHHH', sport, dport, seq[direction], seq[1 - direction],
                          0x50, 0x18, 65535, 0, 0)
        pseudo = src + dst + struct.pack('!I3xB', len(tcp) + len(payload), 6)
        tcp = tcp[:16] + struct.pack('!H', checksum(pseudo + tcp + payload)) + tcp[18:]
        ip = struct.pack('!IHBB', 6 << 28, len(tcp) + len(payload), 6, 64) + src + dst
        frame = dmac + smac + b'\x86\xdd' + ip + tcp + payload
        # One millisecond per generated packet; these are not measured times.
        ticks = frame_count - 1
        pcap.extend(struct.pack('<IIII', ticks // 1000, ticks % 1000 * 1000, len(frame), len(frame)))
        pcap.extend(frame)
        seq[direction] = (seq[direction] + len(payload)) & 0xffffffff
        return frame_count

    for line_number, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r'([0-9]{1,20})([CDSR])(.*)', line.strip())
        if not match or int(match[1]) > 0xffffffffffffffff:
            # An unidentifiable missing chunk makes all current streams unsafe.
            for state in active.values():
                flush(state)
                state['broken'] = [True, True]
            events.append({'kind': 'invalid_line', 'lines': [line_number], 'data': line})
            continue
        client, kind, value = str(int(match[1])), match[2], match[3]
        if kind == 'C' and client in active:
            flush(active.pop(client))
        state = connection(client)
        if kind in 'CD':
            try:
                _, port = parse_endpoint(value)
                state['info'].update(endpoint=value, port=port)
                event(state, kind, [line_number], endpoint=value)
            except ValueError:
                event(state, 'invalid_endpoint', [line_number], data=value)
            if kind == 'D':
                flush(state)
                active.pop(client)
            continue
        direction = 0 if kind == 'R' else 1
        if not value or not re.fullmatch(r'(?:[0-9a-fA-F]{2})+', value):
            flush(state, (direction,))
            state['broken'][direction] = True
            event(state, 'invalid_hex', [line_number], direction=kind, data=value)
            continue
        if state['broken'][direction]:
            event(state, 'unframed', [line_number], direction=kind, data=value)
            continue
        buffer, sources = state['buffers'][direction], state['sources'][direction]
        chunk = bytes.fromhex(value)
        buffer.extend(chunk)
        sources.append([line_number, len(chunk)])
        while len(buffer) >= 6:
            protocol, length = struct.unpack_from('!HH', buffer, 2)
            if protocol != 0 or not 2 <= length <= 254:
                event(state, 'malformed', [number for number, _ in sources],
                      direction=kind, data=buffer.hex())
                buffer.clear()
                sources.clear()
                state['broken'][direction] = True
                break
            size = 6 + length
            if len(buffer) < size:
                break
            payload = bytes(buffer[:size])
            del buffer[:size]
            lines, remaining = [], size
            while remaining:
                number, count = sources[0]
                lines.append(number)
                consumed = min(remaining, count)
                remaining -= consumed
                if consumed == count:
                    sources.popleft()
                else:
                    sources[0][1] -= consumed
            event(state, 'message', lines, direction=kind, data=payload.hex(),
                  frame=packet(state, direction, payload))

    for state in active.values():
        flush(state)
    events.sort(key=lambda item: max(item['lines']))
    return bytes(pcap), {'events': events, 'connections': connections, 'synthetic': True}
