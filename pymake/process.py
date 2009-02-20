"""
Skipping shell invocations is good, when possible. This wrapper around subprocess does dirty work of
parsing command lines into argv and making sure that no shell magic is being used.
"""

import subprocess, shlex, re, logging, sys, threading, traceback
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

class ParallelContext(object):
    """
    Manages the parallel execution of processes.
    """

    def __init__(self, jcount):
        self.jcount = jcount
        self.exit = False

        self.lock = threading.Lock()
        self.threadcount = 0

        self.notifypending = threading.Condition(self.lock)
        self.pending = []
        self.running = 0

        self.notifyresult = threading.Condition(self.lock)
        self.results = []

    def _run(self):
        self.notifypending.acquire()
        try:
            while True:
                if len(self.pending) == 0:
                    self.notifypending.wait()
                    continue

                argv, shell, env, cwd, cb, echo, idx = self.pending.pop(0)
                self.running += 1

                _log.debug("running <%i>: pending: %i running %i threads: %i: results: %i" % (idx,
                                                                                              len(self.pending),
                                                                                              self.running,
                                                                                              self.threadcount,
                                                                                              len(self.results)))

                self.notifypending.release()
                if echo is not None:
                    print echo
                res = subprocess.call(argv, shell=shell, env=env, cwd=cwd)
                self.notifypending.acquire()

                self.running -= 1
                self.results.append((cb, res, idx))
                self.notifyresult.notify()

                continue
        finally:
            self.notifypending.release()

    counter = 0

    def call(self, argv, shell, env, cwd, cb, echo):
        """
        Asynchronously call the process
        """
        self.notifypending.acquire()
        try:
            idx = ParallelContext.counter
            ParallelContext.counter += 1

            _log.debug("call <%i>: pending: %i running %i threads: %i: results: %i: %r" % (idx,
                                                                                           len(self.pending),
                                                                                           self.running,
                                                                                           self.threadcount,
                                                                                           len(self.results), argv))

            self.pending.append((argv, shell, env, cwd, cb, echo, idx))
            self.notifypending.notify()
            if len(self.pending) and self.threadcount < self.jcount:
                _log.debug("Creating a new thread for process execution")
                self.threadcount += 1
                t = threading.Thread(target=self._run)
                t.setDaemon(True)
                t.start()
        finally:
            self.notifypending.release()

    def spin(self):
        """
        Spin the 'event loop', and return only when it is empty.
        """
        self.notifyresult.acquire()
        while True:
            _log.debug("spin: pending: %i running %i threads: %i results: %i" % (len(self.pending),
                                                                                 self.running,
                                                                                 self.threadcount,
                                                                                 len(self.results)))
            if len(self.results) > 0:
                lresults = self.results
                self.results = []
                self.notifyresult.release()
                try:
                    for cb, res, idx in lresults:
                        _log.debug("results of <%i>: %s" % (idx, res))
                        try:
                            cb(res)
                        except Exception, e:
                            _log.debug("Exception throwing during callback: %s" % (e,))
                            raise
                finally:
                    self.notifyresult.acquire()

            if len(self.pending) == 0 and self.running == 0 and len(self.results) == 0:
                _log.debug("exiting spin")
                self.notifyresult.release()
                return

            self.notifyresult.wait(20)
            if len(self.results) == 0:
                raise Exception("wait timeout")
