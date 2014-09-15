import cherrypy, os
import MySQLdb
from genshi.template import TemplateLoader
import re
import util
from auth import require_login, logged_in, logged_out
import model, mail
import browserid

thisdir = os.path.abspath(os.path.dirname(__file__))
bug_re = re.compile("^bug(\d+)$")

loader = TemplateLoader(os.path.join(thisdir, 'templates'), auto_reload=True)
def render(name, **kwargs):
    if not "team" in kwargs:
        kwargs["team"] = []
    if not "daysleft" in kwargs:
        kwargs["daysleft"] = "Unknown"
    if not "iteration" in kwargs:
        kwargs["iteration"] = "Unknown"
    t = loader.load(name)
    return t.generate(loginid=cherrypy.request.loginid,
                      **kwargs).render('html')

def renderatom(**kwargs):
    t = loader.load('feed.xml')
    cherrypy.response.headers['Content-Type'] = 'application/atom+xml'
    rv = t.generate(loginid=cherrypy.request.loginid,
                      feedtag=cherrypy.request.app.config['weeklyupdates']['feed.tag.domain'],
                      **kwargs).render('xml')
    if isinstance(rv, unicode):
      rv = rv.encode('utf-8')
    return rv

def kwargs_to_buglist(kwargs):
    bugs = []
    # kwargs will contain {"bugNNNNN": "newstatus", "bugMMMMMM": "otherstatus"}
    for key, value in kwargs.iteritems():
        bug_key = bug_re.match(key)
        if not bug_key:
            continue
        bugid = int(bug_key.group(1))
        summary = kwargs.get("bug%d.summary" % (bugid,), "Unknown bug")
        if isinstance(summary, str):
            summary = summary.decode("utf-8")
        statusnum = model.bugstatuses.get(value, 0)
        bug = model.Bug(summary, bugid, statusnum)
        bugs.append(bug)
    return bugs

class Root(object):
    @model.requires_db
    def index(self):
        loginid = cherrypy.request.loginid

        projects = model.get_projects()
        iteration, daysleft = model.get_current_iteration()

        if loginid is None:
            team = ()
            teamposts = None
            userposts = None
            todaypost = None
            bugs = None
            recent = model.get_recentposts()
        else:
            team = model.get_user_projects(loginid)
            teamposts = model.get_teamposts(loginid)
            userposts, todaypost = model.get_user_posts(loginid)
            bugs = model.get_currentbugs(loginid, iteration)
            recent = None

        return render('index.xhtml', projects=projects, recent=recent, team=team, bugs=bugs,
                      iteration=iteration, daysleft=daysleft, teamposts=teamposts, userposts=userposts,
                      todaypost=todaypost)

    @model.requires_db
    def posts(self):
        recent = model.get_recentposts()
        projects = model.get_projects()
        return render('posts.xhtml', recent=recent, team=[], projects=projects)

    @model.requires_db
    def feed(self):
        feedposts = model.get_feedposts()

        return renderatom(feedposts=feedposts,
                          feedurl=cherrypy.url('/feed'),
                          title="Mozilla Status Board Updates: All Users")

    @model.requires_db
    def login(self, **kwargs):
        if cherrypy.request.method.upper() == 'POST':
            cur = model.get_cursor()

            returnTo = kwargs.get('returnTo', cherrypy.url('/'))

            assertion = kwargs.pop('loginAssertion')
            if assertion == '':
                logged_out()
                raise cherrypy.HTTPRedirect(returnTo)

            try:
                result = browserid.verify(assertion, cherrypy.request.base)
            except browserid.ConnectionError:
                raise cherrypy.HTTPError(503, "Login connection error")
            except browserid.TrustError:
                raise cherrypy.HTTPError(409, "Invalid login")

            loginid = result['email']

            cur.execute('''SELECT userid FROM users
                           WHERE userid = ?''',
                        (loginid,))
            if cur.fetchone() is None:
                cur.execute('''INSERT INTO users
                               (userid) VALUES (?)''',
                            (loginid,))
                logged_in(loginid)
                raise cherrypy.HTTPRedirect(cherrypy.url('/preferences'))
            logged_in(loginid)
            raise cherrypy.HTTPRedirect(returnTo)

        if cherrypy.request.loginid is not None:
            raise cherrypy.HTTPRedirect(cherrypy.url('/'))

        return render('login.xhtml')

    @model.requires_db
    def user(self, userid):
        cur = model.get_cursor()

        cur.execute('''SELECT userid FROM users WHERE userid = ?''',
                    (userid,))
        if cur.fetchone() is None:
            raise cherrypy.HTTPError(404, "User not found")

        userposts, thispost = model.get_user_posts(userid)

        projects = model.get_userprojects(userid)
        teamposts = model.get_teamposts(userid)

        return render('user.xhtml', userid=userid, projects=projects,
                      teamposts=teamposts, userposts=userposts, team=[])

    @model.requires_db
    def userposts(self, userid):
        posts = model.get_all_userposts(userid)
        if not len(posts):
            raise cherrypy.HTTPError(404, "No posts found")

        projects = model.get_userprojects(userid)
        return render('userposts.xhtml', userid=userid, posts=posts, team=[], projects=projects)

    @model.requires_db
    def userpostsfeed(self, userid):
        feedposts = model.get_user_feedposts(userid)

        return renderatom(feedposts=feedposts,
                          feedurl=cherrypy.url('/feed/%s' % userid),
                          title="Mozilla Status Board Updates: user %s" % userid)

    @model.requires_db
    def userteamposts(self, userid):
        teamposts = model.get_teamposts(userid)
        team = model.get_userteam(userid)
        projects = model.get_projects()

        return render('teamposts.xhtml', userid=userid, team=team,
                      teamposts=teamposts, projects=projects)

    @model.requires_db
    def userteampostsfeed(self, userid):
        teamposts = model.get_teamposts(userid)

        return renderatom(feedposts=teamposts,
                          feedurl=cherrypy.url('/user/%s/teamposts/feed' % userid),
                          title="Mozilla Status Board Updates: User Team: %s" % userid)

    @require_login
    @model.requires_db
    def preferences(self, **kwargs):
        loginid = cherrypy.request.loginid

        cur = model.get_cursor()

        cur.execute('''SELECT bugmail, email, reminderday, sendemail
                       FROM users WHERE userid = ?''',
                    (loginid,))
        r = cur.fetchone()
        if r is None:
            raise cherrypy.HTTPError(404, "User not found")

        bugmail, email, reminderday, sendemail = r

        if cherrypy.request.method.upper() == 'POST':
            bugmail = kwargs.pop('bugmail')
            if bugmail == '' or bugmail == loginid:
                bugmail = None

            email = kwargs.pop('email')
            if email == '' or email == loginid:
                email = None

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
                           SET bugmail = ?, email = ?, reminderday = ?, sendemail = ?
                           WHERE userid = ?''',
                        (bugmail, email, reminderday, sendemail, loginid))

            projectdata = []
            for k, v in kwargs.iteritems():
                if k.startswith('updateproject_') and v == '1':
                    project = k[14:]
                    if kwargs.get('project_%s' % project, False) == '1':
                        projectdata.append((loginid, project))

            cur.execute('''DELETE FROM userprojects WHERE userid = ?''', (loginid,))
            cur.executemany('''INSERT INTO userprojects (userid, projectname) VALUES (?, ?)''', projectdata)


        cur.execute('''SELECT projectname,
                         EXISTS(SELECT * FROM userprojects
                                WHERE userid = ?
                                  AND userprojects.projectname = projects.projectname)
                       FROM projects ORDER BY projectname''',
                    (loginid,))
        projects = cur.fetchall()

        return render('me.xhtml', bugmail=bugmail, email=email,
                      reminderday=reminderday, sendemail=sendemail,
                      projects=projects, userid=loginid, team=[])

    def preview(self, completed, planned, tags, **kwargs):
        assert cherrypy.request.method.upper() == 'POST'

        today = util.today().toordinal()
        now = util.now()
        bugs = kwargs_to_buglist(kwargs)
        if isinstance(completed, str):
            completed = completed.decode("utf-8")
        if isinstance(planned, str):
            planned = planned.decode("utf-8")
        if isinstance(tags, str):
            tags = tags.decode("utf-8")
        post = model.create_post_with_bugs(('<preview>', today, now, completed, planned, tags), bugs)
        return render('preview.xhtml', post=post)

    @require_login
    @model.requires_db
    def post(self, completed, planned, tags, isedit=False, **kwargs):
        loginid = cherrypy.request.loginid

        assert cherrypy.request.method.upper() == 'POST'

        cur = model.get_cursor()

        cur.execute('''SELECT IFNULL(email, userid)
                       FROM users
                       WHERE userid = ?''',
                    (loginid,))
        email, = cur.fetchone()

        completed = completed or None
        planned = planned or None
        tags = tags or None

        today = util.today().toordinal()
        now = util.now()
        bugs = kwargs_to_buglist(kwargs)

        if isedit:
            cur.execute('''UPDATE posts
                           SET completed = ?, planned = ?, tags = ?, posttime = ?
                           WHERE userid = ?
                             AND postdate = (
                               SELECT lastpostdate FROM (
                                 SELECT MAX(postdate) AS lastpostdate
                                 FROM posts AS p2
                                 WHERE p2.userid = ?
                               ) AS maxq
                             )''',
                        (completed, planned, tags, now, loginid, loginid))
        else:
            cur.execute('''INSERT INTO posts
                           (userid, postdate, posttime, completed, planned, tags)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (loginid, today, now, completed, planned, tags))

        for bug in bugs:
            model.save_bugstatus(cur, loginid, bug, today)
        allteam, sendnow = model.get_userteam_emails(loginid)
        if isinstance(completed, str):
            completed = completed.decode("utf-8")
        if isinstance(planned, str):
            planned = planned.decode("utf-8")
        if isinstance(tags, str):
            tags = tags.decode("utf-8")
        if len(sendnow):
            mail.sendpost(email, allteam, sendnow,
                          model.create_post_with_bugs((loginid, today, now,
                                completed, planned, tags), bugs))

        raise cherrypy.HTTPRedirect(cherrypy.url('/'))

    @require_login
    @model.requires_db
    def createproject(self, projectname):
        loginid = cherrypy.request.loginid

        if len(projectname) < 3:
            raise cherrypy.HTTPError(409, "Project name is not long enough")

        cur = model.get_cursor()
        cur.execute('''INSERT INTO projects (projectname, createdby)
                       VALUES (?, ?)''',
                    (projectname, loginid))
        cur.execute('''INSERT INTO userprojects (userid, projectname)
                       VALUES (?, ?)''',
                    (loginid, projectname))

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
        iteration, daysleft = model.get_current_iteration()
        projects = model.get_projects()

        return render('project.xhtml', projectname=projectname, users=users,
                      posts=posts, late=late, team=[projectname], iteration=iteration,
                      daysleft=daysleft, projects=projects)

    @model.requires_db
    def projectfeed(self, projectname):
        posts = model.get_project_posts(projectname)

        return renderatom(feedposts=posts,
                          feedurl=cherrypy.url('/project/%s' % projectname),
                          title="Mozilla Status Board Updates: Project %s" % projectname)

    def markup(self):
        return render('markup.xhtml')

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
connect('/preview', 'preview', methods=('POST',))
connect('/post', 'post', methods=('POST',))
connect('/preferences', 'preferences', methods=('GET', 'POST'))
connect('/feed', 'feed')
connect('/user/{userid}', 'user')
connect('/user/{userid}/posts', 'userposts')
connect('/user/{userid}/posts/feed', 'userpostsfeed')
connect('/user/{userid}/teamposts', 'userteamposts')
connect('/user/{userid}/teamposts/feed', 'userteampostsfeed')
connect('/createproject', 'createproject', methods=('POST',))
connect('/project/{projectname}', 'project')
connect('/project/{projectname}/feed', 'projectfeed')
connect('/markup', 'markup')

def render_error(**kwargs):
    return render('error.xhtml', **kwargs)

class Application(cherrypy.Application):
    _pool = None

    def __init__(self, script_name='', config=None):
        cherrypy.Application.__init__(self, None, script_name, config)
        self.merge({
            '/static': {
                'tools.staticdir.on': True,
                'tools.staticdir.dir': 'static',
                'tools.staticdir.root': thisdir,
                },
            '/': {
                'tools.encode.on': True,
                'tools.encode.encoding': 'utf-8',
                'tools.encode.add_charset': True,
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
