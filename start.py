import sys
import cherrypy
from main import Application
from optparse import OptionParser

o = OptionParser()
o.add_option('-s', '--site-config', help='Global (site-wide) configuration',
             default=[], dest='siteconfigs', action='append', type='string')
o.add_option('-a', '--app-config', help='App configuration',
             default=[], dest='appconfigs', action='append', type='string')
options, args = o.parse_args()
if len(args):
    o.print_help()
    sys.exit(2)

for c in options.siteconfigs:
    cherrypy.config.update(c)

app = Application()
cherrypy.tree.apps[''] = app
for c in options.appconfigs:
    app.merge(c)

cherrypy.engine.start()
