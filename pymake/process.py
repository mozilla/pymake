"""
Skipping shell invocations is good, when possible. This wrapper around subprocess does dirty work of
parsing command lines into argv and making sure that no shell magic is being used.
"""

import subprocess, shlex, re, logging, sys, traceback, os
import command

_log = logging.getLogger('pymake.process')

blacklist = re.compile(r'[=\\$><;*?[{~`|&]')
def clinetoargv(cline):
    """
    If this command line can safely skip the shell, return an argv array.
    """

    if blacklist.search(cline) is not None:
        return None

    return shlex.split(cline, comments=True)

shellwords = (':', '.', 'break', 'cd', 'continue', 'exec', 'exit', 'export',
              'getopts', 'hash', 'pwd', 'readonly', 'return', 'shift', 
              'test', 'times', 'trap', 'umask', 'unset', 'alias',
              'set', 'bind', 'builtin', 'caller', 'command', 'declare',
              'echo', 'enable', 'help', 'let', 'local', 'logout', 
              'printf', 'read', 'shopt', 'source', 'type', 'typeset',
              'ulimit', 'unalias', 'set')

def call(cline, env, cwd, loc, cb, context, echo):
    argv = clinetoargv(cline)
    if argv is None or (len(argv) and argv[0] in shellwords):
        _log.debug("%s: Running command through shell because of shell metacharacters" % (loc,))
        context.call(cline, shell=True, env=env, cwd=cwd, cb=cb, echo=echo)
        return

    if not len(argv):
        cb(res=0)
        return

    if argv[0] == command.makepypath:
        command.main(argv[1:], env, cwd, context, cb)
        return

    if argv[0:2] == [sys.executable, command.makepypath]:
        command.main(argv[2:], env, cwd, context, cb)
        return

    _log.debug("%s: skipping shell, no metacharacters found" % (loc,))
    context.call(argv, shell=False, env=env, cwd=cwd, cb=cb, echo=echo)

def statustoresult(status):
    """
    Convert the status returned from waitpid into a prettier numeric result.
    """
    sig = status & 0xFF
    if sig:
        return -sig

    return status >>8

class ParallelContext(object):
    """
    Manages the parallel execution of processes.
    """

    def __init__(self, jcount):
        self.jcount = jcount
        self.exit = False

        self.pending = [] # list of (argv, shell, env, cwd, cb, echo)
        self.running = [] # list of (subprocess, cb)

    def run(self):
        while len(self.running) < self.jcount and len(self.pending):
            argv, shell, env, cwd, cb, echo = self.pending.pop(0)

            if echo is not None:
                print echo
            p = subprocess.Popen(argv, shell=shell, env=env, cwd=cwd)
            self.running.append((p, cb))

    counter = 0

    def call(self, argv, shell, env, cwd, cb, echo):
        """
        Asynchronously call the process
        """

        self.pending.append((argv, shell, env, cwd, cb, echo))
        self.run()

    def spin(self):
        """
        Spin the 'event loop', and return only when it is empty.
        """

        while len(self.pending) or len(self.running):
            self.run()
            assert len(self.running)

            _log.debug("spin: pending: %i running %i" % (len(self.pending),
                                                         len(self.running)))
            
            pid, status = os.waitpid(-1, 0)
            result = statustoresult(status)

            for i in xrange(0, len(self.running)):
                p, cb = self.running[i]
                if p.pid == pid:
                    cb(result)
                    del self.running[i]
                    break

        _log.debug("exiting spin")
