#!/usr/bin/env python3
"""Two-host SQLite lock/commit visibility probe for a campaign filesystem.

Run leader and follower on distinct hosts against the same absolute directory.
This probes the actual mount; it does not certify every network filesystem or
replace the separate concurrent-run/crash acceptance in the accompanying guide.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import sqlite3
import sys
import time
import uuid


def write(path,value):
    data=json.dumps(value,indent=2,allow_nan=False).encode();temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with open(temporary,'xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def wait(path,timeout):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if path.is_file():return json.loads(path.read_text())
        time.sleep(.1)
    raise TimeoutError('Peer evidence was not received: '+str(path))


def identity():
    return dict(hostname=socket.gethostname(),platform=platform.platform(),python=platform.python_version(),sqlite=sqlite3.sqlite_version,pid=os.getpid(),unix_time=time.time())


def leader(directory,timeout,smoke):
    directory.mkdir(parents=True,exist_ok=False);nonce=uuid.uuid4().hex;host=identity();database=directory/'probe.sqlite3'
    with sqlite3.connect(database,timeout=2) as db:
        db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE probe(value TEXT NOT NULL)');db.execute('INSERT INTO probe VALUES (?)',(nonce,));db.commit()
        db.execute('BEGIN IMMEDIATE');db.execute('UPDATE probe SET value=?',(nonce+'-leader',))
        write(directory/'ready.json',dict(nonce=nonce,host=host,directory=str(directory),status='write lock held'))
        blocked=wait(directory/'blocked.json',timeout)
        if blocked['nonce']!=nonce or not blocked.get('write_blocked'):raise ValueError('Peer did not observe the held write lock.')
        if blocked['host']['hostname']==host['hostname'] and not smoke:raise ValueError('Two-host acceptance requires distinct hosts; use --allow-same-host-smoke only for a local script check.')
        db.commit();write(directory/'released.json',dict(nonce=nonce,committed_value=nonce+'-leader'))
        committed=wait(directory/'committed.json',timeout)
        if committed['nonce']!=nonce or db.execute('SELECT value FROM probe').fetchone()[0]!=nonce+'-follower':raise ValueError('Peer commit is not visible on the leader.')
    distinct=blocked['host']['hostname']!=host['hostname']
    report=dict(schema=1,status='passed' if distinct else 'same_host_smoke_only',directory=str(directory),nonce=nonce,
                leader=host,follower=blocked['host'],peer_write_excluded=True,leader_commit_visible_to_peer=True,
                peer_commit_visible_to_leader=True,distinct_hostnames=distinct,
                qualification='Observed SQLite rollback-journal lock exclusion and synchronized commits on this exact mount. Physical host placement, clock synchronization and campaign crash recovery require separate recorded acceptance.')
    write(directory/'report.json',report);return report


def follower(directory,timeout,smoke):
    ready=wait(directory/'ready.json',timeout);host=identity();nonce=ready['nonce']
    if ready['directory']!=str(directory):raise ValueError('Mount the campaign filesystem at the identical absolute path on both hosts.')
    if host['hostname']==ready['host']['hostname'] and not smoke:raise ValueError('Follower is on the same host; this cannot qualify two-host operation.')
    database=directory/'probe.sqlite3';blocked=False;detail=''
    with sqlite3.connect(database,timeout=.25) as db:
        db.execute('PRAGMA synchronous=FULL')
        try:db.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError as exc:
            if 'locked' not in str(exc).lower():raise
            blocked=True;detail=str(exc)
        if not blocked:raise ValueError('Unsafe filesystem: peer acquired a write lock while the leader held it.')
        write(directory/'blocked.json',dict(nonce=nonce,host=host,write_blocked=blocked,sqlite_message=detail))
        released=wait(directory/'released.json',timeout)
        if released['nonce']!=nonce:raise ValueError('The probe session changed.')
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT value FROM probe').fetchone()[0]!=released['committed_value']:raise ValueError('The leader commit is not visible on the follower.')
        db.execute('UPDATE probe SET value=?',(nonce+'-follower',));db.commit()
        write(directory/'committed.json',dict(nonce=nonce,host=host,leader_commit_seen=True,peer_commit_written=True))
    return wait(directory/'report.json',timeout)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('role',choices=['leader','follower']);parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=60);parser.add_argument('--allow-same-host-smoke',action='store_true');args=parser.parse_args()
    if not 1<=args.timeout<=300:parser.error('Use a peer timeout of 1–300 seconds.')
    directory=args.directory.resolve()
    try:
        report=(leader if args.role=='leader' else follower)(directory,args.timeout,args.allow_same_host_smoke)
        print(json.dumps(report));return 0
    except Exception as exc:
        error=dict(status='failed',role=args.role,host=identity(),error=str(exc))
        if directory.exists():write(directory/(args.role+'-error.json'),error)
        print(json.dumps(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
