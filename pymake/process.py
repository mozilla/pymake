"""
Skipping shell invocations is good, when possible. This wrapper around subprocess does dirty work of
parsing command lines into argv and making sure that no shell magic is being used.
"""

import subprocess, shlex, re, logging

_log = logging.getLogger('pymake.execution')

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

def call(cline, env, cwd, loc):
    argv = clinetoargv(cline)
    if argv is None or (len(argv) and argv[0] in shellwords):
        _log.debug("%s: Running command through shell because of shell metacharacters" % (loc,))
        return subprocess.call(cline, shell=True, env=env, cwd=cwd)

    if not len(argv):
        return 0

    _log.debug("%s: skipping shell, no metacharacters found" % (loc,))
    return subprocess.call(argv, shell=False, env=env, cwd=cwd)
