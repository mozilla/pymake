#!/usr/bin/env python

"""
make.py

A drop-in or mostly drop-in replacement for GNU make.
"""

import os, subprocess, sys, logging, time
from optparse import OptionParser
from pymake.data import Makefile, DataError
from pymake.parser import parsestream, parsecommandlineargs, SyntaxError

def parsemakeflags():
    makeflags = os.environ.get('MAKEFLAGS', '')
    makeflags = makeflags.strip()

    if makeflags == '':
        return []

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

def version(*args):
    print """pymake: GNU-compatible make program
Copyright (C) 2009 The Mozilla Foundation <http://www.mozilla.org/>
This is free software; see the source for copying conditions.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE."""
    sys.exit(0)

log = logging.getLogger('pymake.execution')

makelevel = int(os.environ.get('MAKELEVEL', '0'))

op = OptionParser()
op.add_option('-f', '--file', '--makefile',
              action='append',
              dest='makefiles',
              default=[])
op.add_option('-d',
              action="store_true",
              dest="verbose", default=False)
op.add_option('-C', '--directory',
              dest="directory", default=None)
op.add_option('-v', '--version',
              action="callback", callback=version)
op.add_option('-j', '--jobs', type="int",
              dest="jobcount", default=1)

arglist = sys.argv[1:] + parsemakeflags()

options, arguments = op.parse_args(arglist)

makeflags = ''

loglevel = logging.WARNING
if options.verbose:
    loglevel = logging.DEBUG
    makeflags += 'd'

if options.jobcount:
    log.info("pymake doesn't implement -j yet. ignoring")
    makeflags += 'j%i' % options.jobcount

logging.basicConfig(level=loglevel)


if options.directory:
    log.info("Switching to directory: %s" % options.directory)
    os.chdir(options.directory)
    
print "make.py[%i]: Entering directory '%s'" % (makelevel, os.getcwd())
sys.stdout.flush()

if len(options.makefiles) == 0:
    if os.path.exists('Makefile'):
        options.makefiles.append('Makefile')
    else:
        print "No makefile found"
        sys.exit(2)

try:
    i = 0
    while True:
        m = Makefile(restarts=i, make='%s %s' % (sys.executable, sys.argv[0]),
                     makeflags=makeflags, makelevel=makelevel)

        starttime = time.time()
        targets = parsecommandlineargs(m, arguments)
        for f in options.makefiles:
            m.include(f)

        log.info("Parsing[%i] took %f seconds" % (i, time.time() - starttime,))

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
        tstack = ['<default-target>']
    else:
        tstack = ['<command-line>']


    starttime = time.time()
    for t in targets:
        m.gettarget(t).make(m, ['<command-line>'], [])
    log.info("Execution took %f seconds" % (time.time() - starttime,))

except (DataError, SyntaxError, subprocess.CalledProcessError), e:
    print e
    print "make.py[%i]: Leaving directory '%s'" % (makelevel, os.getcwd())
    sys.stdout.flush()
    sys.exit(2)

print "make.py[%i]: Leaving directory '%s'" % (makelevel, os.getcwd())
