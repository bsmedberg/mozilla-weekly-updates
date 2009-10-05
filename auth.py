import cherrypy

SESSION_KEY = 'weeklyupdates_username'

def require_login(f):
    if not hasattr(f, '_cp_config'):
        f._cp_config = dict()
    f._cp_config['weeklyupdates.require_login'] = True
    return f

def logged_in(username):
    cherrypy.session[SESSION_KEY] = username
    cherrypy.request.loginname = username

def logged_out():
    cherrypy.session[SESSION_KEY] = None
    cherrypy.lib.sessions.expire()

def check_login():
    cherrypy.request.loginname = cherrypy.session.get(SESSION_KEY)
    if cherrypy.request.config.get('weeklyupdates.require_login', False) and \
            cherrypy.request.loginname is None:
        raise cherrypy.HTTPRedirect("%s/login" % cherrypy.request.app.script_name)

cherrypy.tools.weeklyauth = cherrypy.Tool('before_handler', check_login)
