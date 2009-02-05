#!/usr/bin/env python

"""
make.py

A drop-in or mostly drop-in replacement for GNU make.
"""

import os, subprocess, sys
from optparse import OptionParser
from pymake.data import Makefile, DataError
from pymake.parser import parsestream, parsecommandlineargs, SyntaxError

op = OptionParser()
op.add_option('-f', '--file', '--makefile',
              action='append',
              dest='makefiles',
              default=[])

options, arguments = op.parse_args()

m = Makefile()
if len(options.makefiles) == 0:
    if os.path.exists('Makefile'):
        options.makefiles.append('Makefile')
    else:
        raise Error("No makefile found")

try:
    targets = parsecommandlineargs(m, arguments)

    for f in options.makefiles:
        parsestream(open(f), f, m)

    m.finishparsing()

    if len(targets) == 0:
        if m.defaulttarget is None:
            raise Error("No target specified and no default target found.")
        targets = [m.defaulttarget]

    tlist = [m.gettarget(t) for t in targets]
    for t in tlist:
        t.resolvedeps(m, [], [])
    for t in tlist:
        t.make(m)
except (DataError, SyntaxError, subprocess.CalledProcessError), e:
    print e
    sys.exit(2)
