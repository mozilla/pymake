"""
Run the test(s) listed on the command line. If a directory is listed,
we'll recursively walk the directory for files named .mk and run each.

For each test, we simply run gmake -f test.mk. By default, make must exit
with an exit code of 0, and must print 'TEST-PASS'.
"""

from subprocess import Popen, PIPE, STDOUT
from optparse import OptionParser
import os

o = OptionParser()
opts, args = o.parse_args()

if len(args) == 0:
    args = ['.']

makefiles = []
for a in args:
    if os.path.isfile(a):
        makefiles.append(a)
    elif os.path.isdir(a):
        for path, dirnames, filenames in os.walk(a):
            for f in filenames:
                if f.endswith('.mk'):
                    makefiles.append('%s/%s' % (path, f))
    else:
        print >>sys.stderr, "Error: Unknown file on command line"
        sys.exit(1)

for makefile in makefiles:
    print "Running: %s" % makefile,

    p = Popen(['gmake', '-f', makefile], stdout=PIPE, stderr=STDOUT)
    stdout, d = p.communicate()
    if p.returncode != 0:
        print "FAIL"
        print stdout
    if stdout.find('TEST-FAIL') != -1:
        print "FAIL"
        print stdout
    elif stdout.find('TEST-PASS') != -1:
        print "PASS"
    else:
        print "FAIL (no passing output)"
        print stdout
