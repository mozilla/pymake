"""
Skipping shell invocations is good, when possible. This wrapper around subprocess does dirty work of
parsing command lines into argv and making sure that no shell magic is being used.
"""

import subprocess, shlex, re, logging, sys, traceback, os
import command, util
if sys.platform=='win32':
    import ctypes
    SYNCHRONIZE = 0x00100000
    INFINITE = -1

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
    #TODO: call this once up-front somewhere and save the result?
    shell, prependshell = util.checkmsyscompat()
    if argv is None or (len(argv) and argv[0] in shellwords):
        _log.debug("%s: Running command through shell because of shell metacharacters" % (loc,))
        if prependshell:
            cline = [shell, "-c", cline]
        context.call(cline, shell=not prependshell, env=env, cwd=cwd, cb=cb, echo=echo)
        return

    if not len(argv):
        cb(res=0)
        return

    if argv[0] == command.makepypath:
        command.main(argv[1:], env, cwd, context, cb)
        return

    if argv[0:2] == [sys.executable.replace('\\', '/'),
                     command.makepypath.replace('\\', '/')]:
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
    return ParallelContext(jcount)

class ParallelContext(object):
    """
    Manages the parallel execution of processes.
    """

    _allcontexts = set()

    # For Windows, we need to keep track of process handles
    # so we can wait on them.
    _handles = {}

    def __init__(self, jcount):
        self.jcount = jcount
        self.exit = False

        self.pending = [] # list of (cb, args, kwargs)
        self.running = [] # list of (subprocess, cb)

        self._allcontexts.add(self)

    def finish(self):
        assert len(self.pending) == 0 and len(self.running) == 0, "pending: %i running: %i" % (len(self.pending), len(self.running))
        self._allcontexts.remove(self)

    def run(self):
        while len(self.pending) and len(self.running) < self.jcount:
            cb, args, kwargs = self.pending.pop(0)
            _log.debug("Running callback %r with args %r kwargs %r" % (cb, args, kwargs))
            cb(*args, **kwargs)

    def defer(self, cb, *args, **kwargs):
        self.pending.append((cb, args, kwargs))

    def _docall(self, argv, shell, env, cwd, cb, echo):
            if echo is not None:
                print echo
            p = ParallelContext._popen(argv, shell=shell, env=env, cwd=cwd)
            self.running.append((p, cb))

    def call(self, argv, shell, env, cwd, cb, echo):
        """
        Asynchronously call the process
        """

        self.defer(self._docall, argv, shell, env, cwd, cb, echo)

    @staticmethod
    def _popen(argv, **kwargs):
        p = subprocess.Popen(argv, **kwargs)
        if sys.platform=='win32':
            # we need a handle so we can wait on it
            h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, p.pid)
            ParallelContext._handles[h] = p.pid
        return p

    @staticmethod
    def _waitanypid():
        if sys.platform != 'win32':
            pid, status = os.waitpid(-1, 0)
        else:
            arrtype = ctypes.c_long * len(ParallelContext._handles)
            handle_array = arrtype(*ParallelContext._handles.keys())
            ret = ctypes.windll.kernel32.WaitForMultipleObjects(len(handle_array), handle_array, False, INFINITE)
            h = handle_array[ret]
            exitcode = ctypes.c_long()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exitcode))
            ctypes.windll.kernel32.CloseHandle(h)
            pid = ParallelContext._handles[h]
            status = exitcode.value <<8
            del ParallelContext._handles[h]
        return (pid, status)

    @staticmethod
    def spin():
        """
        Spin the 'event loop', and never return.
        """

        _log.debug("Spinning the event loop")

        while True:
            clist = list(ParallelContext._allcontexts)
            for c in clist:
                c.run()

            dowait = any((len(c.running) for c in ParallelContext._allcontexts))

            if dowait:
                pid, status = ParallelContext._waitanypid()
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

def makedeferrable(usercb, **userkwargs):
    def cb(*args, **kwargs):
        kwargs.update(userkwargs)
        return usercb(*args, **kwargs)

    return cb
