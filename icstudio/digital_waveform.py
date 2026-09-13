"""Bounded four-state VCD reader, using exact integer ticks and shared aliases."""
from __future__ import annotations

from bisect import bisect_right
from pathlib import Path
import re

MAX_VCD_BYTES = 32 * 1024 * 1024
MAX_EVENTS = 200000
MAX_SIGNALS = 2048
MAX_WIDTH = 4096
MAX_VALUE_BYTES = 64 * 1024 * 1024


def read_vcd(path):
    path = Path(path)
    if path.stat().st_size > MAX_VCD_BYTES:
        raise ValueError('VCD exceeds the 32 MiB preview limit. Reduce the dump scope or simulation duration.')
    # Own the file outside the lazy tokenizer so parse errors close it immediately,
    # even when a caller retains the exception traceback (and its generator).
    with path.open(encoding='ascii') as source:
        return _read_tokens(word for line in source for word in line.split())


def _read_tokens(stream):
    scopes = []; signals = []; changes = {}; widths = {}
    ticks = 0; count = 0; value_bytes = 0; enddefs = False; timescale = None
    def section():
        words = []
        for word in stream:
            if word == '$end':
                return words
            words.append(word)
        raise ValueError('Truncated VCD directive.')
    for word in stream:
        if word.startswith('$'):
            if word in ('$dumpvars', '$dumpall', '$dumpon', '$dumpoff', '$end'):
                continue
            body = section()
            if word == '$timescale':
                match = re.fullmatch(r'(1|10|100)(s|ms|us|ns|ps|fs)', ''.join(body))
                if not match:
                    raise ValueError('Unsupported VCD timescale.')
                timescale = ''.join(body)
            elif word == '$scope':
                if len(body) != 2: raise ValueError('Invalid VCD scope.')
                scopes.append(body[1])
            elif word == '$upscope':
                if not scopes: raise ValueError('Unbalanced VCD scope.')
                scopes.pop()
            elif word == '$var':
                if len(body) < 4: raise ValueError('Invalid VCD variable.')
                kind, size, code, name = body[:4]; width = int(size)
                if kind in ('real', 'realtime', 'string'):
                    raise ValueError('The digital viewer supports bit-vector VCD signals; remove real/string dumps.')
                if not 1 <= width <= MAX_WIDTH or len(signals) >= MAX_SIGNALS:
                    raise ValueError('VCD preview supports 2,048 signals of at most 4,096 bits. Reduce the dump scope.')
                if code in widths and widths[code] != width:
                    raise ValueError('VCD aliases disagree on signal width.')
                widths[code] = width; changes.setdefault(code, [])
                signals.append({'name': '.'.join(scopes + [name]) + ''.join(body[4:]), 'width': width, 'code': code})
            elif word == '$enddefinitions':
                enddefs = True
            continue
        if not enddefs:
            raise ValueError('VCD value before enddefinitions.')
        if word.startswith('#'):
            value = int(word[1:])
            if value < ticks: raise ValueError('VCD time moves backwards.')
            ticks = value
            continue
        if word[0] in 'bB':
            value = word[1:].lower()
            try: code = next(stream)
            except StopIteration: raise ValueError('Truncated VCD vector.') from None
        elif word[0] in '01xXzZ':
            value = word[0].lower(); code = word[1:]
        else:
            raise ValueError('Unsupported VCD value token: '+word[:60])
        if code not in widths or not re.fullmatch('[01xz]+', value) or len(value) > widths[code]:
            raise ValueError('Invalid VCD signal value.')
        value = value.rjust(widths[code], value[0] if value[0] in 'xz' else '0')
        if not changes[code] or changes[code][-1][1] != value:
            value_bytes += len(value)
            if value_bytes > MAX_VALUE_BYTES:
                raise ValueError('Decoded VCD values exceed the 64 MiB preview limit. Reduce the dump scope.')
            changes[code].append([ticks, value]); count += 1
            if count > MAX_EVENTS:
                raise ValueError('VCD exceeds 200,000 preview transitions. Reduce the dump scope or duration.')
    if not enddefs or not signals or not timescale:
        raise ValueError('VCD must contain timescale, signal declarations and enddefinitions.')
    return {'version': 1, 'timescale': timescale, 'end_tick': ticks,
            'signals': signals, 'changes': changes, 'event_count': count}


def value_at(events, tick, width):
    index = bisect_right(events, tick, key=lambda e: e[0]) - 1
    return events[index][1] if index >= 0 else 'x' * width


def format_value(bits, radix='hex'):
    if radix == 'binary' or any(c in bits for c in 'xz'):
        return bits
    return str(int(bits, 2)) if radix == 'unsigned' else format(int(bits, 2), '0'+str((len(bits)+3)//4)+'x')
