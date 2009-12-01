import cherrypy, os
import MySQLdb
from genshi.template import TemplateLoader
import util
from auth import require_login, logged_in, logged_out
from post import Post
import model, mail

thisdir = os.path.abspath(os.path.dirname(__file__))

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
    @model.requires_db
    def index(self):
        username = cherrypy.request.loginname

        projects = model.get_projects()
        users = model.get_users()

        if username is None:
            teamposts = None
            userposts = None
            todaypost = None
            recent = model.get_recentposts()
        else:
            teamposts = model.get_teamposts(username)
            userposts, todaypost = model.get_user_posts(username)
            recent = None

        return render('index.xhtml', projects=projects, users=users, recent=recent,
                      teamposts=teamposts, userposts=userposts, todaypost=todaypost)

    @model.requires_db
    def posts(self):
        recent = model.get_recentposts()
        return render('posts.xhtml', recent=recent)

    @model.requires_db
    def feed(self):
        feedposts = model.get_feedposts()

        return renderatom(feedposts=feedposts,
                          feedurl=cherrypy.url('/feed'),
                          title="Mozilla Status Board Updates: All Users")

    @model.requires_db
    def signup(self, **kwargs):
        if cherrypy.request.method.upper() == 'POST':
            cur = model.get_cursor()

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

            raise cherrypy.HTTPRedirect(cherrypy.url('/login'))

        projects = model.get_projects()

        return render('signup.xhtml', projects=projects)

    @model.requires_db
    def login(self, **kwargs):
        if cherrypy.request.method.upper() == 'POST':
            cur = model.get_cursor()

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

        return render('login.xhtml')

    def logout(self, **kwargs):
        logged_out()
        raise cherrypy.HTTPRedirect(cherrypy.url('/'))

    @model.requires_db
    def user(self, username):
        cur = model.get_cursor()

        cur.execute('''SELECT username FROM users WHERE username = ?''',
                    (username,))
        if cur.fetchone() is None:
            raise cherrypy.HTTPError(404, "User not found")

        userposts, thispost = model.get_user_posts(username)

        projects = model.get_userprojects(username)
        teamposts = model.get_teamposts(username)

        return render('user.xhtml', username=username, projects=projects,
                      teamposts=teamposts, userposts=userposts)

    @model.requires_db
    def userposts(self, username):
        posts = model.get_all_userposts(username)
        if not len(posts):
            raise cherrypy.HTTPError(404, "No posts found")

        return render('userposts.xhtml', username=username, posts=posts)

    @model.requires_db
    def userpostsfeed(self, username):
        feedposts = model.get_user_feedposts(username)

        return renderatom(feedposts=feedposts,
                          feedurl=cherrypy.url('/feed/%s' % username),
                          title="Mozilla Status Board Updates: user %s" % username)

    @model.requires_db
    def userteamposts(self, username):
        teamposts = model.get_teamposts(username)
        team = model.get_userteam(username)

        return render('teamposts.xhtml', username=username,
                      teamposts=teamposts, team=team)

    @model.requires_db
    def userteampostsfeed(self, username):
        teamposts = model.get_teamposts(username)

        return renderatom(feedposts=teamposts,
                          feedurl=cherrypy.url('/user/%s/teamposts/feed' % username),
                          title="Mozilla Status Board Updates: User Team: %s" % username)

    @require_login
    @model.requires_db
    def preferences(self, **kwargs):
        user = cherrypy.request.loginname

        cur = model.get_cursor()

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


        cur.execute('''SELECT projectname,
                         EXISTS(SELECT * FROM userprojects
                                WHERE username = ?
                                  AND userprojects.projectname = projects.projectname)
                       FROM projects ORDER BY projectname''',
                    (user,))
        projects = cur.fetchall()

        return render('me.xhtml', email=email, reminderday=reminderday,
                      sendemail=sendemail, projects=projects)

    @require_login
    @model.requires_db
    def post(self, completed, planned, tags, isedit=False):
        user = cherrypy.request.loginname

        assert cherrypy.request.method.upper() == 'POST'

        cur = model.get_cursor()
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
        else:
            cur.execute('''INSERT INTO posts
                           (username, postdate, posttime, completed, planned, tags)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (user, today, now, completed, planned, tags))

        allteam, sendnow = model.get_userteam_emails(user)
        if len(sendnow):
            mail.sendpost(email, allteam, sendnow,
                          Post((user, today, now, completed, planned, tags)))

        raise cherrypy.HTTPRedirect(cherrypy.url('/'))

    @require_login
    @model.requires_db
    def createproject(self, projectname):
        username = cherrypy.request.loginname

        if len(projectname) < 3:
            raise cherrypy.HTTPError(409, "Project name is not long enough")

        cur = model.get_cursor()
        cur.execute('''INSERT INTO projects (projectname, createdby)
                       VALUES (?, ?)''',
                    (projectname, username))
        cur.execute('''INSERT INTO userprojects (username, projectname)
                       VALUES (?, ?)''',
                    (username, projectname))

        raise cherrypy.HTTPRedirect(cherrypy.url('/project/%s' % projectname))

    @model.requires_db
    def project(self, projectname):
        cur = model.get_cursor()
        cur.execute('''SELECT projectname FROM projects WHERE projectname = ?''',
                    (projectname,))
        if cur.fetchone() is None:
            raise cherrypy.HTTPError(404, "Project not found")

        users = model.get_project_users(projectname)
        posts = model.get_project_posts(projectname)
        late = model.get_project_late(projectname)

        return render('project.xhtml', projectname=projectname, users=users,
                      posts=posts, late=late)

    @model.requires_db
    def projectfeed(self, projectname):
        posts = model.get_project_posts(projectname)

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
connect('/posts', 'posts')
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
    _pool = None

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

    def connectionpool(self):
        if self._pool is None:
            self._pool = model.ConnectionPool(self.config)
        return self._pool
