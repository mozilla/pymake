#!/usr/bin/env python

"""
make.py

A drop-in or mostly drop-in replacement for GNU make.
"""

import os, subprocess, sys, logging
from optparse import OptionParser
from pymake.data import Makefile, DataError
from pymake.parser import parsestream, parsecommandlineargs, SyntaxError

def parsemakeflags():
    makeflags = os.environ.get('MAKEFLAGS', '')
    makeflags.strip()

    opts = []
    curopt = ''

    i = 0
    while i < len(makeflags):
        c = makeflags[i]
        if c.isspace():
            opts.append(curopt)
            curopt = ''
            i += 1
            while i < len(makeflags) and makeflags[i].isspace():
                i += 1
            continue

        if c == '\\':
            i += 1
            if i == len(makeflags):
                raise DataError("MAKEFLAGS has trailing backslash")
            c = makeflags[i]
            
        curopt += c
        i += 1

    if curopt != '':
        opts.append(curopt)

    return opts

log = logging.getLogger('pymake.execution')

op = OptionParser()
op.add_option('-f', '--file', '--makefile',
              action='append',
              dest='makefiles',
              default=[])
op.add_option('-v', '--verbose',
              action="store_true",
              dest="verbose", default=True)
op.add_option('-C', '--directory',
              dest="directory", default=None)

arglist = sys.argv[1:] + parsemakeflags()

options, arguments = op.parse_args(arglist)

makeflags = ''

if options.verbose:
    logging.basicConfig(level=logging.DEBUG)
    makeflags += 'v'

if options.directory:
    log.info("Switching to directory: %s" % options.directory)
    os.chdir(options.directory)

if len(options.makefiles) == 0:
    if os.path.exists('Makefile'):
        options.makefiles.append('Makefile')
    else:
        print "No makefile found"
        sys.exit(2)

makelevel = int(os.environ.get('MAKELEVEL', '0'))

try:
    i = 0
    while True:
        m = Makefile(restarts=i, make='%s %s' % (sys.executable, sys.argv[0]),
                     makeflags=makeflags, makelevel=makelevel)
        targets = parsecommandlineargs(m, arguments)

        for f in options.makefiles:
            m.include(f)

        m.finishparsing()
        if m.remakemakefiles():
            log.info("restarting makefile parsing")
            i += 1
            continue

        break

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
