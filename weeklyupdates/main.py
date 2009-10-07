import cherrypy, os
from genshi.template import TemplateLoader
import util
from auth import require_login, logged_in, logged_out
from post import Post
import model, mail

thisdir = os.path.abspath(os.path.dirname(__file__))

def init_threadlocal_db(thread_index):
    cherrypy.thread_data.weeklydb = None

cherrypy.engine.subscribe('start_thread', init_threadlocal_db)

class CursorWrapper(object):
    def __init__(self, parent):
        self.parent = parent

    def execute(self, q, *args):
        q = q.replace('?', '%s')
        self.parent.execute(q, *args)

    def executemany(self, q, *args):
        q = q.replace('?', '%s')
        self.parent.executemany(q, *args)

    def fetchone(self):
        return self.parent.fetchone()

    def fetchall(self):
        return self.parent.fetchall()

    def close(self):
        self.parent.close()
        self.parent = None

    @property
    def rowcount(self):
        return self.parent.rowcount

def get_cursor(app=None):
    if app is None:
        app = cherrypy.request.app
    if cherrypy.thread_data.weeklydb is None:
        type = app.config['weeklyupdates']['database.type']
        if type == 'sqlite3':
            import sqlite3
            db = sqlite3.connect(app.config['weeklyupdates']['database.file'])
            cherrypy.thread_data.weeklydb_wrap = False
        elif type == 'MySQLdb':
            import MySQLdb
            db = MySQLdb.connect(**app.config['weeklyupdates']['database.connect.args'])
            cherrypy.thread_data.weeklydb_wrap = True
        else:
            raise Exception("Unrecognized database.type")

        cherrypy.thread_data.weeklydb = db

    db = cherrypy.thread_data.weeklydb
    cur = db.cursor()
    if cherrypy.thread_data.weeklydb_wrap:
        cur = CursorWrapper(cur)
    return db, cur

loader = TemplateLoader(os.path.join(thisdir, 'templates'), auto_reload=True)
def render(name, **kwargs):
    t = loader.load(name)
    return t.generate(loginname=cherrypy.request.loginname,
                      **kwargs).render('html')

def renderatom(**kwargs):
    t = loader.load('feed.xml')
    cherrypy.response.headers['Content-Type'] = 'application/atom+xml'
    return t.generate(loginname=cherrypy.request.loginname,
                      feedtag=cherrypy.request.app.config['weeklyupdates']['feed.tag.domain'],
                      **kwargs).render('xml')

class Root(object):
    def index(self):
        username = cherrypy.request.loginname

        db, cur = get_cursor()
        projects = model.get_projects(cur)
        users = model.get_users(cur)
        recent = model.get_recentposts(cur)

        if username is None:
            teamposts = None
            userposts = None
            todaypost = None
        else:
            teamposts = model.get_teamposts(cur, username)
            userposts, todaypost = model.get_user_posts(cur, username)

        cur.close()
        return render('index.xhtml', projects=projects, users=users, recent=recent,
                      teamposts=teamposts, userposts=userposts, todaypost=todaypost)

    def feed(self):
        db, cur = get_cursor()

        feedposts = model.get_feedposts(cur)

        cur.close()
        return renderatom(feedposts=feedposts,
                          feedurl=cherrypy.url('/feed'),
                          title="Mozilla Status Board Updates: All Users")

    def signup(self, **kwargs):
        db, cur = get_cursor()

        if cherrypy.request.method.upper() == 'POST':
            username = kwargs.pop('username')
            if username == '':
                raise cherrypy.HTTPError(409, "Cannot have an empty username")

            if username.startswith('!'):
                raise cherrypy.HTTPError(409, "Username must not start with !")

            cur.execute('SELECT username FROM users WHERE username = ?',
                        (username,))
            if cur.fetchone() is not None:
                raise cherrypy.HTTPError(409, "There is already a user of that name")

            email = kwargs.pop('email')
            email = (None, email)[email is not None]

            reminderday = kwargs.pop('reminderday')
            if reminderday == '-':
                reminderday = None
            else:
                reminderday = int(reminderday)

            sendemail = kwargs.pop('sendemail')
            if sendemail == '-':
                sendemail = None
            else:
                sendemail = int(sendemail)

            password = kwargs.pop('password1')
            password2 = kwargs.pop('password2')
            if password != password2:
                raise cherrypy.HTTPError(409, "The passwords didn't match")

            if kwargs.pop('globalpass') != cherrypy.request.app.config['weeklyupdates']['globalpass']:
                raise cherrypy.HTTPError(409, "The global password is incorrect")

            projects = []
            for k, v in kwargs.iteritems():
                if k.startswith('project_') and v == '1':
                    project = k[8:]
                    projects.append(project)

            cur.execute('''INSERT INTO users (username, email, password, reminderday, sendemail)
                        VALUES (?, ?, ?, ?, ?)''',
                        (username, email, password, reminderday, sendemail))
            cur.executemany('''INSERT INTO userprojects
                               (projectname, username)
                               SELECT projectname, ? FROM projects
                               WHERE projectname = ?''',
                            [(username, project) for project in projects])
            db.commit()

            raise cherrypy.HTTPRedirect(cherrypy.url('/login'))

        projects = model.get_projects(cur)

        cur.close()
        return render('signup.xhtml', projects=projects)

    def login(self, **kwargs):
        db, cur = get_cursor()
        if cherrypy.request.method.upper() == 'POST':
            username = kwargs.pop('username')
            password = kwargs.pop('password1')
            cur.execute('''SELECT username FROM users
                           WHERE username = ? AND password = ?''',
                        (username, password))
            if cur.fetchone() is not None:
                logged_in(username)
            else:
                raise cherrypy.HTTPError(409, "Invalid username/password")

        if cherrypy.request.loginname is not None:
            raise cherrypy.HTTPRedirect(cherrypy.url('/'))

        cur.close()
        return render('login.xhtml')

    def logout(self, **kwargs):
        logged_out()
        raise cherrypy.HTTPRedirect(cherrypy.url('/'))

    def user(self, username):
        db, cur = get_cursor()
        cur.execute('''SELECT username FROM users WHERE username = ?''',
                    (username,))
        if cur.fetchone() is None:
            raise cherrypy.HTTPError(404, "User not found")

        userposts, thispost = model.get_user_posts(cur, username)

        projects = model.get_userprojects(cur, username)
        teamposts = model.get_teamposts(cur, username)

        cur.close()
        return render('user.xhtml', username=username, projects=projects,
                      teamposts=teamposts, userposts=userposts)

    def userposts(self, username):
        db, cur = get_cursor()

        posts = model.get_all_userposts(cur, username)
        if not len(posts):
            raise cherry.HTTPError(404, "No posts found")

        cur.close()
        return render('userposts.xhtml', username=username, posts=posts)

    def userpostsfeed(self, username):
        db, cur = get_cursor()

        feedposts, thispost = model.get_user_posts(cur, username)

        cur.close()
        return renderatom(feedposts=feedposts,
                          feedurl=cherrypy.url('/feed/%s' % username),
                          title="Mozilla Status Board Updates: user %s" % username)

    def userteamposts(self, username):
        db, cur = get_cursor()

        teamposts = model.get_teamposts(cur, username)
        team = model.get_userteam(cur, username)

        cur.close()
        return render('teamposts.xhtml', username=username,
                      teamposts=teamposts, team=team)

    def userteampostsfeed(self, username):
        db, cur = get_cursor()

        teamposts = model.get_teamposts(cur, username)

        cur.close()
        return renderatom(feedposts=teamposts,
                          feedurl=cherrypy.url('/user/%s/teamposts/feed' % username),
                          title="Mozilla Status Board Updates: User Team: %s" % username)

    @require_login
    def preferences(self, **kwargs):
        user = cherrypy.request.loginname

        db, cur = get_cursor()
        cur.execute('''SELECT email, reminderday, sendemail
                       FROM users WHERE username = ?''',
                    (user,))
        r = cur.fetchone()
        if r is None:
            raise cherrypy.HTTPError(404, "User not found")

        email, reminderday, sendemail = r

        if cherrypy.request.method.upper() == 'POST':
            oldpassword = kwargs.pop('oldpassword')

            if oldpassword != '':
                cur.execute('''SELECT username FROM users
                               WHERE username = ? AND password = ?''',
                            (user, oldpassword))
                if cur.fetchone() is None:
                    raise cherrypy.HTTPError(409, "Invalid username/password")

                password = kwargs.pop('newpassword1')
                password2 = kwargs.pop('newpassword2')
                if password != password2:
                    raise cherrypy.HTTPError(409, "The passwords don't match")

                if password != '':
                    cur.execute('''UPDATE users
                                   SET password = ?
                                   WHERE username = ?''', (password, user))

            email = kwargs.pop('email')
            email = (None, email)[email is not None]

            reminderday = kwargs.pop('reminderday')
            if reminderday == '-':
                reminderday = None
            else:
                reminderday = int(reminderday)

            sendemail = kwargs.pop('sendemail')
            if sendemail == '-':
                sendemail = None
            else:
                sendemail = int(sendemail)

            cur.execute('''UPDATE users
                           SET email = ?, reminderday = ?, sendemail = ?
                           WHERE username = ?''',
                        (email, reminderday, sendemail, user))

            projectdata = []
            for k, v in kwargs.iteritems():
                if k.startswith('updateproject_') and v == '1':
                    project = k[14:]
                    if kwargs.get('project_%s' % project, False) == '1':
                        projectdata.append((user, project))

            cur.execute('''DELETE FROM userprojects WHERE username = ?''', (user,))
            cur.executemany('''INSERT INTO userprojects (username, projectname) VALUES (?, ?)''', projectdata)
            db.commit()


        cur.execute('''SELECT projectname,
                         EXISTS(SELECT * FROM userprojects
                                WHERE username = ?
                                  AND userprojects.projectname = projects.projectname)
                       FROM projects ORDER BY projectname''',
                    (user,))
        projects = cur.fetchall()


        cur.close()
        return render('me.xhtml', email=email, reminderday=reminderday,
                      sendemail=sendemail, projects=projects)

    @require_login
    def post(self, completed, planned, tags, isedit=False):
        user = cherrypy.request.loginname

        db, cur = get_cursor()

        assert cherrypy.request.method.upper() == 'POST'

        cur.execute('''SELECT email
                       FROM users
                       WHERE username = ?''',
                    (user,))
        email, = cur.fetchone()

        completed = completed or None
        planned = planned or None
        tags = tags or None

        today = util.today().toordinal()
        now = util.now()

        if isedit:
            cur.execute('''UPDATE posts
                           SET completed = ?, planned = ?, tags = ?, posttime = ?
                           WHERE username = ?
                             AND postdate = (
                               SELECT lastpostdate FROM (
                                 SELECT MAX(postdate) AS lastpostdate
                                 FROM posts AS p2
                                 WHERE p2.username = ?
                               ) AS maxq
                             )''',
                        (completed, planned, tags, now, user, user))
            print "Rows updated: %s" % cur.rowcount
        else:
            cur.execute('''INSERT INTO posts
                           (username, postdate, posttime, completed, planned, tags)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (user, today, now, completed, planned, tags))

        db.commit()

        allteam, sendnow = model.get_userteam_emails(cur, user)
        if len(sendnow):
            mail.sendpost(email, allteam, sendnow,
                          Post((user, today, now, completed, planned, tags)))

        raise cherrypy.HTTPRedirect(cherrypy.url('/'))

    @require_login
    def createproject(self, projectname):
        username = cherrypy.request.loginname

        if len(projectname) < 3:
            raise cherrypy.HTTPError(409, "Project name is not long enough")

        db, cur = get_cursor()

        cur.execute('''INSERT INTO projects (projectname, createdby)
                       VALUES (?, ?)''',
                    (projectname, username))
        cur.execute('''INSERT INTO userprojects (username, projectname)
                       VALUES (?, ?)''',
                    (username, projectname))
        db.commit()

        cur.close()
        raise cherrypy.HTTPRedirect(cherrypy.url('/project/%s' % projectname))

    def project(self, projectname):
        db, cur = get_cursor()

        cur.execute('''SELECT projectname FROM projects WHERE projectname = ?''',
                    (projectname,))
        if cur.fetchone() is None:
            raise cherrypy.HTTPError(404, "Project not found")

        users = model.get_project_users(cur, projectname)
        posts = model.get_project_posts(cur, projectname)
        late = model.get_project_late(cur, projectname)

        cur.close()
        return render('project.xhtml', projectname=projectname, users=users,
                      posts=posts, late=late)

    def projectfeed(self, projectname):
        db, cur = get_cursor()

        posts = model.get_project_posts(cur, projectname)

        cur.close()
        return renderatom(feedposts=posts,
                          feedurl=cherrypy.url('/project/%s' % projectname),
                          title="Mozilla Status Board Updates: Project %s" % projectname)

dispatcher = cherrypy.dispatch.RoutesDispatcher()
dispatcher.controllers['root'] = Root()

def connect(route, action, methods=('GET'), **kwargs):
    c = kwargs.pop('conditions', {})
    c['method'] = methods
    dispatcher.mapper.connect(route, controller='root', action=action, conditions=c, **kwargs)

connect('/', 'index')
connect('/signup', 'signup', methods=('GET', 'POST'))
connect('/login', 'login', methods=('GET', 'POST'))
connect('/logout', 'logout', methods=('POST',))
connect('/post', 'post', methods=('POST',))
connect('/preferences', 'preferences', methods=('GET', 'POST'))
connect('/feed', 'feed')
connect('/user/{username}', 'user')
connect('/user/{username}/posts', 'userposts')
connect('/user/{username}/posts/feed', 'userpostsfeed')
connect('/user/{username}/teamposts', 'userteamposts')
connect('/user/{username}/teamposts/feed', 'userteampostsfeed')
connect('/createproject', 'createproject', methods=('POST',))
connect('/project/{projectname}', 'project')
connect('/project/{projectname}/feed', 'projectfeed')

def render_error(**kwargs):
    return render('error.xhtml', **kwargs)

class Application(cherrypy.Application):
    def __init__(self, script_name='', config=None):
        cherrypy.Application.__init__(self, None, script_name, config)
        self.merge({
            'global': {
                'tools.encode.on': True,
                'tools.encode.encoding': 'utf-8',
                },
            '/static': {
                'tools.staticdir.on': True,
                'tools.staticdir.dir': 'static',
                'tools.staticdir.root': thisdir,
                },
            '/': {
                'tools.weeklyauth.on': True,
                'tools.sessions.on': True,
                'error_page.default': render_error,
                'request.dispatch': dispatcher,
                }
            })
