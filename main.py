import cherrypy, os, sqlite3
from genshi.template import TemplateLoader
from datetime import date
from auth import require_login, logged_in, logged_out
from post import Post

thisdir = os.path.abspath(os.path.dirname(__file__))

def init_threadlocal_db(thread_index):
    cherrypy.thread_data.weeklydb = None

cherrypy.engine.subscribe('start_thread', init_threadlocal_db)

def get_cursor():
    if cherrypy.thread_data.weeklydb is None:
        db = sqlite3.connect(cherrypy.request.app.config['weeklyupdates']['database.file'])
        cherrypy.thread_data.weeklydb = db
    return (cherrypy.thread_data.weeklydb,
            cherrypy.thread_data.weeklydb.cursor())

loader = TemplateLoader(os.path.join(thisdir, 'templates'), auto_reload=True)
def render(name, **kwargs):
    t = loader.load(name)
    return t.generate(baseurl=cherrypy.request.app.script_name, loginname=cherrypy.request.loginname,
                      **kwargs).render('html')

def get_projects(cur):
    cur.execute('''SELECT projectname FROM projects ORDER BY projectname''')
    return [project for project, in cur.fetchall()]

class Root(object):
    def index(self):
        db, cur = get_cursor()
        projects = get_projects(cur)

        cur.execute('''SELECT username FROM users ORDER BY username''')
        users = [user for user, in cur.fetchall()]

        # cur.execute('''SELECT username, postdate, completed, planned, tags
        #                FROM posts
        #                WHERE postdate = SELECT (MAX(postdate) FROM

        cur.close()
        return render('index.xhtml', projects=projects, users=users)

    def signup(self, **kwargs):
        db, cur = get_cursor()

        if cherrypy.request.method.upper() == 'POST':
            username = kwargs.pop('username')
            if username == '':
                raise cherrypy.HTTPError(409, "Cannot have an empty username")

            cur.execute('SELECT username FROM users WHERE username = ?',
                        (username,))
            if cur.fetchone() is not None:
                raise cherrypy.HTTPError(409, "There is already a user of that name")

            email = kwargs.pop('email') or None

            password = kwargs.pop('password1')
            password2 = kwargs.pop('password2')
            if password != password2:
                raise cherrypy.HTTPError(409, "The passwords didn't match")

            projects = []
            for k, v in kwargs.iteritems():
                if k.startswith('project_') and v == '1':
                    project = k[8:]
                    projects.append(project)

            cur.execute('''INSERT INTO users (username, email, password)
                        VALUES (?, ?, ?)''',
                        (username, email, password))
            cur.executemany('''INSERT INTO userprojects
                               (projectname, username)
                               SELECT projectname, projectname FROM projects
                               WHERE projectname = ?''',
                            [(project,) for project in projects])
            db.commit()

            raise cherrypy.HTTPRedirect("%s/login" % cherrypy.request.app.script_name)

        projects = get_projects(cur)

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
            raise cherrypy.HTTPRedirect("%s/me" % cherrypy.request.app.script_name)

        return render('login.xhtml')

    def logout(self, **kwargs):
        logged_out()
        raise cherrypy.HTTPRedirect("%s/" % cherrypy.request.app.script_name)

    def user(self, username):
        db, cur = get_cursor()
        cur.execute('''SELECT username FROM users WHERE username = ?''',
                    (username,))
        if cur.fetchone() is None:
            raise cherrypy.HTTPError(404, "User not found")

        cur.execute('''SELECT projectname FROM userprojects
                       WHERE username = ?''',
                    (username,))
        projects = [project for project, in cur.fetchall()]

        cur.close()
        return render('user.xhtml', projects=projects, username=username)

    @require_login
    def me(self, **kwargs):
        user = cherrypy.request.loginname

        db, cur = get_cursor()
        cur.execute('''SELECT email FROM users WHERE username = ?''',
                    (user,))
        r = cur.fetchone()
        if r is None:
            raise cherrypy.HTTPError(404, "User not found")

        email, = r

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
                    cur.execute('''UPDATE users SET password = ?''', (password,))

            email = kwargs.pop('email')
            cur.execute('''UPDATE users SET email = ?''', (email or None,))

            projectdata = []
            for k, v in kwargs.iteritems():
                if k.startswith('updateproject_') and v == '1':
                    project = k[14:]
                    if kwargs.get('project_%s' % project, False) == '1':
                        projectdata.append((user, project))

            cur.execute('''DELETE FROM userprojects WHERE username = ?''', (user,))
            cur.executemany('''INSERT INTO userprojects (username, projectname) VALUES (?, ?)''', projectdata)
            db.commit()

        cur.execute('''SELECT username, postdate, completed, planned, tags
                       FROM posts
                       WHERE username = ?
                       ORDER BY postdate DESC LIMIT 10''', (user,))
        posts = [Post(r) for r in cur.fetchall()]
        if not len(posts):
            posts.append(Post(None))
            thispost = Post(None)
        elif posts[0].postdate == date.today():
            thispost = posts[0]
        else:
            thispost = Post(None)

        cur.execute('''SELECT projectname,
                         EXISTS(SELECT * FROM userprojects
                                WHERE username = ?
                                  AND userprojects.projectname = projects.projectname)
                       FROM projects ORDER BY projectname''',
                    (user,))
        projects = cur.fetchall()

        cur.execute('''SELECT username, postdate, completed, planned, tags
                       FROM posts
                       WHERE postdate = (SELECT MAX(postdate)
                                         FROM posts AS p2
                                         WHERE p2.username = posts.username)
                         AND EXISTS(SELECT * FROM userprojects AS u1, userprojects AS u2
                                    WHERE u1.projectname = u2.projectname
                                      AND u1.username = posts.username
                                      AND u2.username = ?)
                         ORDER BY postdate DESC''', (user,))
        projectposts = [Post(d) for d in cur.fetchall()]

        cur.close()
        return render('me.xhtml', email=email or '', projects=projects, posts=posts, thispost=thispost, projectposts=projectposts)

    @require_login
    def post(self, postdate=None, **kwargs):
        user = cherrypy.request.loginname

        db, cur = get_cursor()

        if cherrypy.request.method.upper() == 'POST':
            completed = kwargs.get('completed') or None
            planned = kwargs.get('planned') or None
            tags = kwargs.get('tags') or None

            if postdate is None:
                cur.execute('''INSERT INTO posts
                               (username, postdate, completed, planned, tags)
                               VALUES (?, ?, ?, ?, ?)''',
                            (user, date.today().toordinal(), completed, planned, tags))
            else:
                cur.execute('''UPDATE posts
                               SET completed = ?, planned = ?, tags = ?
                               WHERE username = ? AND postdate = ?''',
                            (completed, planned, tags, user, postdate))
                if cur.rowcount == 0:
                    raise cherrypy.HTTPError(409, "A post never existed on this date")

            db.commit()
            raise cherrypy.HTTPRedirect("%s/me" % cherrypy.request.app.script_name)


        if postdate is None:
            thispost = Post(None)
            cur.execute('''SELECT username, postdate, completed, planned, tags
                           FROM posts
                           WHERE username = ?
                           ORDER BY postdate DESC LIMIT 1''', (user,))
            lastpost = Post(cur.fetchone())
            if lastpost.postdate == date.today():
                raise cherrypy.HTTPRedirect('%s/post/%i' % (cherrypy.request.app.script_name, lastpost.postdate.toordinal()))
        else:
            lastpost = Post(None)
            cur.execute('''SELECT username, postdate, completed, planned, tags
                           FROM posts
                           WHERE username = ?
                             AND postdate = ?''', (user, int(postdate)))
            thispost = Post(cur.fetchone())
            if thispost.postdate is None:
                raise cherrypy.HTTPError(404, "Post on %s not found" % date.fromordinal(int(postdate)).isoformat())

        cur.execute('''SELECT username, postdate, completed, planned, tags
                       FROM posts
                       WHERE EXISTS (SELECT *
                                     FROM userprojects AS u1, userprojects AS u2
                                     WHERE u1.projectname = u2.projectname
                                       AND u1.username = posts.username
                                       AND u2.username = ?)
                       AND posts.postdate = (SELECT max(p2.postdate)
                                             FROM posts AS p2
                                             WHERE p2.username = posts.username)
                       ORDER by postdate''', (user,))
        projectposts = [(username, date.fromordinal(postdate), completed, planned, tags)
                        for username, postdate, completed, planned, tags in cur.fetchall()]

        cur.close()
        return render('post.xhtml', thispost=thispost, lastpost=lastpost, projectposts=projectposts)

dispatcher = cherrypy.dispatch.RoutesDispatcher()
dispatcher.controllers['root'] = Root()

def connect(route, action, methods=('GET'), **kwargs):
    c = kwargs.pop('conditions', {})
    c['method'] = methods
    dispatcher.mapper.connect(route, controller='root', action=action, conditions=c, **kwargs)

connect('/', 'index')
connect('/signup', 'signup')
connect('/login', 'login', methods=('GET', 'POST'))
connect('/logout', 'logout', methods=('POST',))
connect('/user/{username}', 'user')
connect('/user/{username}/feed', 'userfeed')
connect('/user/{username}/project-feed', 'userprojectfeed')
connect('/projects/{projectname}', 'project')
connect('/projects/{projectname}/feed', 'projectfeed')

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
