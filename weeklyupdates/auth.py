import cherrypy

SESSION_KEY = 'weeklyupdates_loginid'

def require_login(f):
    if not hasattr(f, '_cp_config'):
        f._cp_config = dict()
    f._cp_config['weeklyupdates.require_login'] = True
    return f

def logged_in(loginid):
    cherrypy.session[SESSION_KEY] = loginid
    cherrypy.request.loginid = loginid

def logged_out():
    cherrypy.session[SESSION_KEY] = None
    cherrypy.lib.sessions.expire()

def check_login():
    cherrypy.request.loginid = cherrypy.session.get(SESSION_KEY)
    if cherrypy.request.config.get('weeklyupdates.require_login', False) and \
            cherrypy.request.loginid is None:
        raise cherrypy.HTTPRedirect("%s/login" % cherrypy.request.app.script_name)

cherrypy.tools.weeklyauth = cherrypy.Tool('before_handler', check_login)
