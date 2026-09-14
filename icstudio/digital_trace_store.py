"""Streaming VCD indexing with bounded-memory, paged transition access."""
from collections.abc import Sequence
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .digital_waveform import _read_tokens, read_vcd


def index_vcd(path, database):
    path = Path(path); database = Path(database)
    if path.stat().st_size > 2*1024**3: raise ValueError('Indexed VCD supports files up to 2 GiB. Reduce the dump scope.')
    if database.exists(): raise ValueError('Choose a new waveform index path.')
    counts = {}; pending = []
    try:
        with closing(sqlite3.connect(database)) as db:
            db.execute('CREATE TABLE events(code TEXT, ordinal INTEGER, tick INTEGER, value TEXT, PRIMARY KEY(code,ordinal)) WITHOUT ROWID')
            def flush():
                db.executemany('INSERT INTO events VALUES (?,?,?,?)', pending); pending.clear()
            def append(code, tick, value):
                if tick > 2**63-1: raise ValueError('Waveform tick exceeds the indexed 64-bit time range.')
                ordinal = counts.get(code,0); pending.append((code,ordinal,tick,value)); counts[code] = ordinal+1
                if len(pending)>=4096: flush()
            with path.open(encoding='ascii') as source:
                data = _read_tokens((word for line in source for word in line.split()), append)
            flush(); db.execute('CREATE INDEX event_time ON events(code,tick)'); db.commit()
        data.pop('changes'); data.update(storage='sqlite', counts=counts, database=database.name)
        return data
    except Exception:
        database.unlink(missing_ok=True)
        raise


class Events(Sequence):
    def __init__(self, database, code, count):
        self.database=database; self.code=code; self.count=count; self.page=-1; self.cache=[]

    def __len__(self): return self.count

    def __getitem__(self, index):
        if isinstance(index,slice): return [self[i] for i in range(*index.indices(self.count))]
        if index<0: index+=self.count
        if not 0<=index<self.count: raise IndexError(index)
        page=index//512
        if page!=self.page:
            with closing(sqlite3.connect(self.database.as_uri()+'?mode=ro',uri=True)) as db:
                self.cache=db.execute('SELECT tick,value FROM events WHERE code=? AND ordinal>=? AND ordinal<? ORDER BY ordinal',(self.code,page*512,(page+1)*512)).fetchall()
            self.page=page
        return self.cache[index%512]


def open_waveform(path):
    path=Path(path); data=json.loads(path.read_text())
    if data.get('storage')=='sqlite':
        from .digital import relative_path
        relative_path(data['database']); database=(path.parent/data['database']).resolve()
        if not database.is_relative_to(path.parent.resolve()): raise ValueError('Waveform database escaped its captured run.')
        if not database.is_file(): raise ValueError('The captured waveform index is missing.')
        data['changes']={code:Events(database,code,count) for code,count in data['counts'].items()}
        # Declarations without transitions retain an all-X value.
        for signal in data['signals']: data['changes'].setdefault(signal['code'],[])
    return data


def capture(path, root):
    if Path(path).stat().st_size <= 4*1024**2:
        try: return read_vcd(path)
        except ValueError as exc:
            if not any(word in str(exc) for word in ('limit','transitions','2,048 signals')): raise
    return index_vcd(path, Path(root)/'waveform.sqlite')


def next_event(events, tick, match='', reverse=False):
    """Search edges or exact four-state values strictly after/before a cursor."""
    from bisect import bisect_left, bisect_right
    if isinstance(events, Events):
        op,order=('<','DESC') if reverse else ('>','ASC')
        value='1' if match=='rising' else '0' if match=='falling' else match
        sql='SELECT tick FROM events WHERE code=? AND tick'+op+'?'+(' AND value=?' if value else '')+' ORDER BY tick '+order+' LIMIT 1'
        with closing(sqlite3.connect(events.database.as_uri()+'?mode=ro',uri=True)) as db:
            row=db.execute(sql,(events.code,tick,value) if value else (events.code,tick)).fetchone()
        return row[0] if row else None
    begin = bisect_left(events,tick,key=lambda e:e[0])-1 if reverse else bisect_right(events,tick,key=lambda e:e[0])
    indices = range(begin,-1,-1) if reverse else range(begin,len(events))
    for i in indices:
        t,value=events[i]
        if not match or value==match or match=='rising' and value=='1' or match=='falling' and value=='0': return t
    return None
