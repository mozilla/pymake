"""
Run the test(s) listed on the command line. If a directory is listed, the script will recursively
walk the directory for files named .mk and run each.

For each test, we run gmake -f test.mk. By default, make must exit with an exit code of 0, and must print 'TEST-PASS'.

The test file may contain lines at the beginning to alter the default behavior. These are all evaluated as python:

#T commandline: ['extra', 'params', 'here']
#T returncode: 2
"""

from subprocess import Popen, PIPE, STDOUT
from optparse import OptionParser
import os, re, sys

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

tre = re.compile('^#T ([a-z]+): (.*)$')

for makefile in makefiles:
    print "Testing: %s" % makefile,

    cline = ['gmake', '-f', makefile]
    returncode = 0

    mdata = open(makefile)
    for line in mdata:
        m = tre.search(line)
        if m is None:
            break
        key, data = m.group(1, 2)
        data = eval(data)
        if key == 'commandline':
            cline.extend(data)
        elif key == 'returncode':
            returncode = data
        else:
            print >>sys.stderr, "Unexpected #T key: %s" % key
            sys.exit(1)

    mdata.close()

    p = Popen(cline, stdout=PIPE, stderr=STDOUT)
    stdout, d = p.communicate()
    if p.returncode != returncode:
        print "FAIL"
        print stdout
    elif stdout.find('TEST-FAIL') != -1:
        print "FAIL"
        print stdout
    elif stdout.find('TEST-PASS') != -1:
        print "PASS"
    else:
        print "FAIL (no passing output)"
        print stdout
