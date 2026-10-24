"""Captured timing-oriented mapping recipe for the pinned ABC toolchain.

Adapted from OpenROAD-flow-scripts abc_speed.script at
eaba6576441bf7c1743ea56ecdb1904210ec02c2. Copyright (c) 2018-2023,
The Regents of the University of California. BSD-3-Clause; see
licenses/OpenROAD-flow-scripts-BSD-3-Clause.txt for conditions and disclaimer.
Studio additionally passes its explicit delay target to mapping and sizing.
"""

SOURCE = ('https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/'
          'eaba6576441bf7c1743ea56ecdb1904210ec02c2/flow/scripts/abc_speed.script')

SPEED = '''&get -n
&st
&dch
&nf
&st
&syn2
&if -g -K 6
&synch2
&nf
&st
&syn2
&if -g -K 6
&synch2
&nf
&st
&syn2
&if -g -K 6
&synch2
&nf
&st
&syn2
&if -g -K 6
&synch2
&nf
&st
&syn2
&if -g -K 6
&synch2
&nf
&put
buffer -c
topo
stime -c
upsize -c
dnsize -c
'''


def speed_script(delay_ns=None):
    text=SPEED
    if delay_ns is not None:
        target=' -D '+format(delay_ns*1000,'.15g')
        for command in ('&nf','upsize -c','dnsize -c'):
            text=text.replace(command+'\n',command+target+'\n')
    return text
