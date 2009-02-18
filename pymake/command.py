"""
Logic to execute a command
"""

import os, subprocess, sys, logging, time
from optparse import OptionParser
import pymake.data, pymake.parser

def parsemakeflags(env):
    makeflags = env.get('MAKEFLAGS', '')
    makeflags = makeflags.strip()

    if makeflags == '':
        return []

    if makeflags[0] not in ('-', ' '):
        makeflags = '-' + makeflags

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
                raise pymake.data.DataError("MAKEFLAGS has trailing backslash")
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

log = logging.getLogger('pymake.execution')

op = OptionParser()
op.add_option('-f', '--file', '--makefile',
              action='append',
              dest='makefiles',
              default=[])
op.add_option('-d',
              action="store_true",
              dest="verbose", default=False)
op.add_option('--debug-log',
              dest="debuglog", default=None)
op.add_option('-C', '--directory',
              dest="directory", default=None)
op.add_option('-v', '--version', action="store_true",
              dest="printversion", default=False)
op.add_option('-j', '--jobs', type="int",
              dest="jobcount", default=1)
op.add_option('--parse-profile',
              dest="parseprofile", default=None)
op.add_option('--no-print-directory', action="store_false",
              dest="printdir", default=True)

def main(args, env, cwd):
    makelevel = int(env.get('MAKELEVEL', '0'))
    arglist = args + parsemakeflags(env)

    options, arguments = op.parse_args(arglist)

    if options.printversion:
        version()
        return 0

    shortflags = []
    longflags = []

    loglevel = logging.WARNING
    if options.verbose:
        loglevel = logging.DEBUG
        shortflags.append('d')

    logkwargs = {}
    if options.debuglog:
        logkwargs['filename'] = options.debuglog
        longflags.append('--debug-log=%s' % options.debuglog)

    if options.jobcount:
        log.info("pymake doesn't implement -j yet. ignoring")
        shortflags.append('j%i' % options.jobcount)

    if options.directory is None:
        workdir = cwd
    else:
        workdir = os.path.join(cwd, options.directory)

    makeflags = ''.join(shortflags) + ' ' + ' '.join(longflags)

    logging.basicConfig(level=loglevel, **logkwargs)

    if options.printdir:
        print "make.py[%i]: Entering directory '%s'" % (makelevel, workdir)
        sys.stdout.flush()

    if len(options.makefiles) == 0:
        if os.path.exists(os.path.join(workdir, 'Makefile')):
            options.makefiles.append('Makefile')
        else:
            print "No makefile found"
            return 2

    try:
        def parse():
            i = 0

            while True:
                m = pymake.data.Makefile(restarts=i, make='%s %s' % (sys.executable, sys.argv[0]),
                                         makeflags=makeflags, makelevel=makelevel, workdir=workdir)

                starttime = time.time()
                targets = pymake.parser.parsecommandlineargs(m, arguments)
                for f in options.makefiles:
                    m.include(f)

                log.info("Parsing[%i] took %f seconds" % (i, time.time() - starttime,))

                m.finishparsing()
                if m.remakemakefiles():
                    log.info("restarting makefile parsing")
                    i += 1
                    continue

                return m, targets

        if options.parseprofile is None:
            m, targets = parse()
        else:
            import cProfile
            cProfile.run("m, targets = parse()", options.parseprofile)

        if len(targets) == 0:
            if m.defaulttarget is None:
                print "No target specified and no default target found."
                return 2
            targets = [m.defaulttarget]
            tstack = ['<default-target>']
        else:
            tstack = ['<command-line>']

        starttime = time.time()
        for t in targets:
            m.gettarget(t).make(m, ['<command-line>'], [])
        log.info("Execution took %f seconds" % (time.time() - starttime,))

    except (pymake.data.DataError, pymake.parser.SyntaxError), e:
        print e
        if options.printdir:
            print "make.py[%i]: Leaving directory '%s'" % (makelevel, workdir)
        sys.stdout.flush()
        return 2

    if options.printdir:
        print "make.py[%i]: Leaving directory '%s'" % (makelevel, workdir)

    sys.stdout.flush()
