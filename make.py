#!/usr/bin/env python

"""
make.py

A drop-in or mostly drop-in replacement for GNU make.
"""

import os, subprocess, sys, logging
from optparse import OptionParser
from pymake.data import Makefile, DataError
from pymake.parser import parsestream, parsecommandlineargs, SyntaxError

op = OptionParser()
op.add_option('-f', '--file', '--makefile',
              action='append',
              dest='makefiles',
              default=[])
op.add_option('-v', '--verbose',
              action="store_true",
              dest="verbose", default=True)

options, arguments = op.parse_args()

if options.verbose:
    logging.basicConfig(level=logging.DEBUG)

m = Makefile()
if len(options.makefiles) == 0:
    if os.path.exists('Makefile'):
        options.makefiles.append('Makefile')
    else:
        print "No makefile found"
        sys.exit(2)

try:
    targets = parsecommandlineargs(m, arguments)

    for f in options.makefiles:
        parsestream(open(f), f, m)

    m.finishparsing()

    if len(targets) == 0:
        if m.defaulttarget is None:
            print "No target specified and no default target found."
            sys.exit(2)
        targets = [m.defaulttarget]

    tlist = [m.gettarget(t) for t in targets]
    for t in tlist:
        t.resolvedeps(m, [], [])
    for t in tlist:
        t.make(m)
except (DataError, SyntaxError, subprocess.CalledProcessError), e:
    print e
    sys.exit(2)
