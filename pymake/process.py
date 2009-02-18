"""
Skipping shell invocations is good, when possible. This wrapper around subprocess does dirty work of
parsing command lines into argv and making sure that no shell magic is being used.
"""

import subprocess, shlex, re, logging

_log = logging.getLogger('pymake.execution')

blacklist = re.compile(r'[=\\$><;*?[{~`]')
def clinetoargv(cline):
    """
    If this command line can safely skip the shell, return an argv array.
    """

    if blacklist.search(cline) is not None:
        return None

    return shlex.split(cline, comments=True)

def call(cline, env, cwd, loc):
    argv = clinetoargv(cline)
    if argv is None:
        _log.debug("%s: Running command through shell because of shell metacharacters" % (loc,))
        return subprocess.call(cline, shell=True, env=env, cwd=cwd)

    _log.debug("%s: skipping shell, no metacharacters found" % (loc,))
    return subprocess.call(argv, shell=False, env=env, cwd=cwd)
