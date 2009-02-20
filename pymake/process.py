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

def getcontext(jcount):
    assert jcount > 0
    if jcount == 1:
        return _serialsingleton

    return ParallelContext(jcount)

class SerialContext(object):
    """
    Manages the serial execution of processes.
    """

    jcount = 1

    def call(self, argv, shell, env, cwd, cb, echo):
        if echo is not None:
            print echo
        p = subprocess.Popen(argv, shell=shell, env=env, cwd=cwd)
        cb(p.wait())

    def finish(self):
        pass

_serialsingleton = SerialContext()

class ParallelContext(object):
    """
    Manages the parallel execution of processes.
    """

    _allcontexts = set()

    def __init__(self, jcount):
        self.jcount = jcount
        self.exit = False

        self.pending = [] # list of (argv, shell, env, cwd, cb, echo)
        self.running = [] # list of (subprocess, cb)

        self._allcontexts.add(self)

    def finish(self):
        assert len(self.pending) == 0 and len(self.running) == 0, "pending: %i running: %i" % (len(self.pending), len(self.running))
        self._allcontexts.remove(self)

    def run(self):
        while (len(self.running) < self.jcount) and len(self.pending):
            _log.debug("context<%s>: pending: %i running: %i jcount: %i running a command" % (id(self), len(self.pending), len(self.running),
                                                                                              self.jcount))

            argv, shell, env, cwd, cb, echo = self.pending.pop(0)

            if echo is not None:
                print echo
            p = subprocess.Popen(argv, shell=shell, env=env, cwd=cwd)
            self.running.append((p, cb))

    def call(self, argv, shell, env, cwd, cb, echo):
        """
        Asynchronously call the process
        """

        self.pending.append((argv, shell, env, cwd, cb, echo))
        self.run()

    @staticmethod
    def spin():
        """
        Spin the 'event loop', and return only when it is empty.
        """

        while True:
            for c in ParallelContext._allcontexts:
                c.run()

            pid, status = os.waitpid(-1, 0)
            result = statustoresult(status)

            found = False

            for c in ParallelContext._allcontexts:
                for i in xrange(0, len(c.running)):
                    p, cb = c.running[i]
                    if p.pid == pid:
                        del c.running[i]
                        cb(result)
                        found = True
                        break

                if found: break
