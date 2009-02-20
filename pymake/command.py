"""
Logic to execute a command
"""

import os, subprocess, sys, logging, time, traceback
from optparse import OptionParser
import data, parser, process, util

# TODO: If this ever goes from relocatable package to system-installed, this may need to be
# a configured-in path.

makepypath = os.path.normpath(os.path.join(os.path.dirname(__file__), '../make.py'))

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
                raise data.DataError("MAKEFLAGS has trailing backslash")
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

def main(args, env, cwd, context, cb):
    try:
        makelevel = int(env.get('MAKELEVEL', '0'))

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
        op.add_option('--no-print-directory', action="store_false",
                      dest="printdir", default=True)

        options, arguments1 = op.parse_args(parsemakeflags(env))
        options, arguments2 = op.parse_args(args, values=options)

        arguments = arguments1 + arguments2

        if options.printversion:
            version()
            cb(0)
            return

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

        if options.directory is None:
            workdir = cwd
        else:
            workdir = os.path.join(cwd, options.directory)

        shortflags.append('j%i' % (options.jobcount,))

        makeflags = ''.join(shortflags) + ' ' + ' '.join(longflags)

        logging.basicConfig(level=loglevel, **logkwargs)

        if context is not None and context.jcount > 1 and options.jobcount == 1:
            log.debug("-j1 specified, creating new serial execution context")
            context = process.getcontext(options.jobcount)
            subcontext = True
        elif context is None:
            log.debug("Creating new execution context, jobcount %s" % options.jobcount)
            context = process.getcontext(options.jobcount)
            subcontext = True
        else:
            log.debug("Using parent execution context")
            subcontext = False

        if options.printdir:
            print "make.py[%i]: Entering directory '%s'" % (makelevel, workdir)
            sys.stdout.flush()

        if len(options.makefiles) == 0:
            if os.path.exists(os.path.join(workdir, 'Makefile')):
                options.makefiles.append('Makefile')
            else:
                print "No makefile found"
                cb(2)
                return

        # subvert python readonly closures
        o = util.makeobject(('restarts', 'm', 'targets', 'remade', 'error'),
                            restarts=-1)

        def remakecb(remade):
            if remade:
                o.restarts += 1
                if o.restarts > 0:
                    log.info("make.py[%i]: Restarting makefile parsing" % (makelevel,))
                o.m = data.Makefile(restarts=o.restarts, make='%s %s' % (sys.executable, makepypath),
                                    makeflags=makeflags, makelevel=makelevel, workdir=workdir,
                                    context=context, env=env)

                o.targets = parser.parsecommandlineargs(o.m, arguments)
                for f in options.makefiles:
                    o.m.include(f)

                o.m.finishparsing()
                o.m.remakemakefiles(remakecb)
                return

            if len(o.targets) == 0:
                if o.m.defaulttarget is None:
                    print "No target specified and no default target found."
                    cb(2)
                    return
                o.targets = [o.m.defaulttarget]
                tstack = ['<default-target>']
            else:
                tstack = ['<command-line>']

            def makecb(error, didanything):
                o.remade += 1

                log.debug("makecb[%i]: remade %i targets" % (makelevel, o.remade))

                if error is not None:
                    print error
                    o.error = True

                if o.remade == len(o.targets):
                    if subcontext:
                        context.finish()

                    if options.printdir:
                        print "make.py[%i]: Leaving directory '%s'" % (makelevel, workdir)
                    sys.stdout.flush()

                    cb(o.error and 2 or 0)

            o.remade = 0
            o.error = False

            for t in o.targets:
                o.m.gettarget(t).make(o.m, ['<command-line>'], [], cb=makecb)

        remakecb(True)

    except (util.MakeError), e:
        print e
        if options.printdir:
            print "make.py[%i]: Leaving directory '%s'" % (makelevel, workdir)
        sys.stdout.flush()
        cb(2)
        return
