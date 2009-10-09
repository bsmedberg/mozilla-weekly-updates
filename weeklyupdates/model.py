import threading
import cherrypy
import datetime
import util
from post import Post

_anhour = datetime.timedelta(hours=1)

class ConnectionPool(object):
    """A basic database connection pool."""

    def __init__(self, config):
        type = config['weeklyupdates']['database.type']
        connectargs = config['weeklyupdates']['database.connect.args']
        if type == 'sqlite3':
            import sqlite3
            connectfn = lambda: sqlite3.connect(**connectargs)
        elif type == 'MySQLdb':
            import MySQLdb, MySQLdb.cursors

            class MySQLCursorWrapper(MySQLdb.cursors.Cursor):
                def execute(self, q, *args):
                    q = q.replace('?', '%s')
                    return MySQLdb.cursors.Cursor.execute(self, q, *args)

                def executemany(self, q, *args):
                    q = q.replace('?', '%s')
                    return MySQLdb.cursors.Cursor.executemany(self, q, *args)

            connectfn = lambda: MySQLdb.connect(cursorclass=MySQLCursorWrapper,
                                                **connectargs)

        self.connectfn = connectfn
        self.connectpool = []
        self.lock = threading.Lock()

    def get(self):
        self.lock.acquire()
        try:
            db = None
            while len(self.connectpool):
                db, lastused = self.connectpool.pop()
                if lastused > datetime.datetime.now() - _anhour:
                    break

                db.close()
                db = None
        finally:
            self.lock.release()

        if db is None:
            db = self.connectfn()

        return db

    def done(self, db):
        self.lock.acquire()
        try:
            self.connectpool.append((db, datetime.datetime.now()))
        finally:
            self.lock.release()

def requires_db(f):
    def _innerf(*args, **kwargs):
        db = cherrypy.request.app.connectionpool().get()
        try:
            cherrypy.request.weeklycur = db.cursor()
            result = f(*args, **kwargs)
            cherrypy.request.weeklycur.close()
            db.commit()
            return result
        except:
            db.rollback()
            raise
        finally:
            cherrypy.request.app.connectionpool().done(db)
    return _innerf

def get_cursor():
    return cherrypy.request.weeklycur

def get_users():
    cur = get_cursor()
    cur.execute('''SELECT username FROM users ORDER BY username''')
    return [user for user, in cur.fetchall()]

def get_projects():
    cur = get_cursor()
    cur.execute('''SELECT projectname FROM projects ORDER BY projectname''')
    return [project for project, in cur.fetchall()]

def get_user_posts(username):
    """
    Get the 10 most recent posts by this username, and get today's post if there is one today.
    @returns posts, thispost
    """
    cur = get_cursor()
    cur.execute('''SELECT username, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE username = ?
                   ORDER BY postdate DESC, posttime DESC LIMIT 10''', (username,))
    posts = [Post(r) for r in cur.fetchall()]
    if not len(posts):
        posts.append(Post(None))
        thispost = Post(None)
    elif posts[0].postdate == util.today():
        thispost = posts[0]
    else:
        thispost = Post(None)

    return posts, thispost

def get_user_feedposts(username):
    cur = get_cursor()
    cur.execute('''SELECT username, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE username = ?
                     AND postdate >= ?
                   ORDER BY postdate DESC, posttime DESC''',
                (username, util.today().toordinal() - 15))
    return [Post(d) for d in cur.fetchall()]

def get_all_userposts(username):
    cur = get_cursor()
    cur.execute('''SELECT username, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE username = ?
                   ORDER BY postdate DESC, posttime DESC''', (username,))
    return [Post(r) for r in cur.fetchall()]

def get_teamposts(username):
    cur = get_cursor()
    cur.execute('''SELECT username, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE postdate = (SELECT MAX(postdate)
                                     FROM posts AS p2
                                     WHERE p2.username = posts.username)
                     AND EXISTS(SELECT * FROM userprojects AS u1, userprojects AS u2
                                WHERE u1.projectname = u2.projectname
                                  AND u1.username = posts.username
                                  AND u2.username = ?)
                     ORDER BY postdate DESC, posttime DESC''', (username,))
    return [Post(d) for d in cur.fetchall()]

def get_feedposts():
    cur = get_cursor()
    cur.execute('''SELECT username, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE postdate > ?
                   ORDER BY postdate DESC, posttime DESC''',
                (util.today().toordinal() - 15,))
    return [Post(d) for d in cur.fetchall()]

def get_recentposts():
    cur = get_cursor()
    cur.execute('''SELECT username, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE postdate = (SELECT MAX(postdate)
                                     FROM posts AS p2
                                     WHERE p2.username = posts.username)
                     AND postdate > ?
                   ORDER BY postdate DESC, posttime DESC''',
                (util.today().toordinal() - 15,))
    return [Post(d) for d in cur.fetchall()]

def get_userprojects(username):
    cur = get_cursor()
    cur.execute('''SELECT projectname
                   FROM userprojects
                   WHERE username = ?
                   ORDER BY projectname''',
                (username,))
    return [username for username, in cur.fetchall()]

def get_userteam(username):
    cur = get_cursor()
    cur.execute('''SELECT u2.username, group_concat(u2.projectname)
                   FROM userprojects AS u1, userprojects AS u2
                   WHERE u1.username = ?
                     AND u2.projectname = u1.projectname
                   GROUP BY u2.username
                   ORDER BY u2.username''',
                (username,))

    return cur.fetchall()

def get_userteam_emails(username):
    cur = get_cursor()
    cur.execute('''SELECT email, sendemail
                   FROM users
                   WHERE EXISTS(SELECT *
                                FROM userprojects AS u1, userprojects AS u2
                                WHERE u1.username = ?
                                  AND u2.projectname = u1.projectname
                                  AND u2.username = users.username)
                     AND email IS NOT NULL''',
                (username,))
    r = cur.fetchall()
    return ([email for email, sendemail in r], [email for email, sendemail in r if sendemail == 0])

def get_project_users(projectname):
    cur = get_cursor()
    cur.execute('''SELECT username FROM userprojects
                   WHERE projectname = ?
                   ORDER BY username ASC''', (projectname,))
    return [projectname for projectname, in cur.fetchall()]

def get_project_late(projectname):
    cur = get_cursor()
    cur.execute('''SELECT userprojects.username, MAX(postdate) AS lastpostdate
                   FROM userprojects LEFT OUTER JOIN posts ON posts.username = userprojects.username
                   WHERE projectname = ?
                   GROUP BY userprojects.username
                   HAVING lastpostdate IS NULL OR lastpostdate < ?''',
                (projectname, util.today().toordinal() - 6))
    return [(username, lastpostdate is not None and datetime.date.fromordinal(lastpostdate) or None)
            for username, lastpostdate in cur.fetchall()]

def get_project_posts(projectname):
    cur = get_cursor()
    cur.execute('''SELECT username, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE postdate = (SELECT MAX(postdate)
                                     FROM posts AS p2
                                     WHERE p2.username = posts.username)
                     AND exists (SELECT * from userprojects
                                 WHERE userprojects.username = posts.username
                                 AND userprojects.projectname = ?)
                   ORDER BY postdate DESC, posttime DESC''', (projectname,))
    return [Post(d) for d in cur.fetchall()]

def get_naglist(cur):
    cur.execute('''SELECT users.username, email, MAX(postdate) AS lastpostdate
                   FROM users LEFT OUTER JOIN posts ON posts.username = users.username
                   WHERE reminderday = ? AND email IS NOT NULL
                   GROUP BY users.username
                   HAVING lastpostdate IS NULL or lastpostdate < ?''',
                (util.today().weekday(), util.today().toordinal() - 6))
    return [(username, email, lastpostdate is not None and datetime.date.fromordinal(lastpostdate) or None)
            for username, email, lastpostdate in cur.fetchall()]

def iter_daily(cur, day):
    cur.execute('''SELECT username, email
                   FROM users
                   WHERE sendemail = 1''')
    for username, email in cur.fetchall():
        cur.execute('''SELECT username, postdate, posttime, completed, planned, tags
                       FROM posts
                       WHERE postdate = ?
                         AND EXISTS(SELECT * FROM userprojects AS u1, userprojects AS u2
                                    WHERE u1.projectname = u2.projectname
                                    AND u1.username = posts.username
                                    AND u2.username = ?)
                       ORDER BY postdate ASC, posttime ASC''',
                    (day.toordinal(), username))
        yield username, email, [Post(r) for r in cur.fetchall()]

def iter_weekly(cur, start, end):
    cur.execute('''SELECT username, email
                   FROM users
                   WHERE sendemail = 2''')
    for username, email in cur.fetchall():
        cur.execute('''SELECT username, postdate, posttime, completed, planned, tags
                       FROM posts
                       WHERE postdate >= ? AND postdate <= ?
                         AND EXISTS(SELECT * FROM userprojects AS u1, userprojects AS u2
                                    WHERE u1.projectname = u2.projectname
                                    AND u1.username = posts.username
                                    AND u2.username = ?)
                       ORDER BY postdate ASC, posttime ASC''',
                    (start.toordinal(), end.toordinal(), username))
        yield username, email, [Post(r) for r in cur.fetchall()]
