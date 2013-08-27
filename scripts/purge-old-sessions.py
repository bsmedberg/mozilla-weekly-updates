import sys, os, time

sessiondir, days = sys.argv[1:]

days = int(days)

cutoff = time.time() - 24 * 60 * 60 * days
print "Finding files older than %s" % (time.ctime(cutoff),)

for leaf in os.listdir(sessiondir):
    sessionfile = os.path.join(sessiondir, leaf)
    if os.path.isfile(sessionfile):
        mtime = os.path.getmtime(sessionfile)
        if mtime < cutoff:
            os.unlink(sessionfile)

