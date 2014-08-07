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
                                                charset='utf8',
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
        except cherrypy.HTTPRedirect:
            db.commit()
            raise
        except:
            db.rollback()
            raise
        finally:
            cherrypy.request.app.connectionpool().done(db)
    return _innerf

def get_cursor():
    return cherrypy.request.weeklycur

def get_projects():
    cur = get_cursor()
    cur.execute('''SELECT projectname FROM projects ORDER BY projectname''')
    return [project for project, in cur.fetchall()]

def get_user_posts(userid):
    """
    Get the 10 most recent posts by this username, and get today's post if there is one today.
    @returns posts, thispost
    """
    cur = get_cursor()
    cur.execute('''SELECT userid, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE userid = ?
                   ORDER BY postdate DESC, posttime DESC LIMIT 10''', (userid,))
    posts = [Post(r) for r in cur.fetchall()]
    if not len(posts):
        posts.append(Post(None))
        thispost = Post(None)
    elif posts[0].postdate == util.today():
        thispost = posts[0]
    else:
        thispost = Post(None)

    return posts, thispost

def get_user_feedposts(userid):
    cur = get_cursor()
    cur.execute('''SELECT userid, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE userid = ?
                     AND postdate >= ?
                   ORDER BY postdate DESC, posttime DESC''',
                (userid, util.today().toordinal() - 15))
    return [Post(d) for d in cur.fetchall()]

def get_all_userposts(userid):
    cur = get_cursor()
    cur.execute('''SELECT userid, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE userid = ?
                   ORDER BY postdate DESC, posttime DESC''', (userid,))
    return [Post(r) for r in cur.fetchall()]

def get_teamposts(userid):
    cur = get_cursor()
    cur.execute('''SELECT userid, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE postdate = (SELECT MAX(postdate)
                                     FROM posts AS p2
                                     WHERE p2.userid = posts.userid)
                     AND EXISTS(SELECT * FROM userprojects AS u1, userprojects AS u2
                                WHERE u1.projectname = u2.projectname
                                  AND u1.userid = posts.userid
                                  AND u2.userid = ?)
                     ORDER BY postdate DESC, posttime DESC''', (userid,))
    return [Post(d) for d in cur.fetchall()]

def get_feedposts():
    cur = get_cursor()
    cur.execute('''SELECT userid, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE postdate > ?
                   ORDER BY postdate DESC, posttime DESC''',
                (util.today().toordinal() - 15,))
    return [Post(d) for d in cur.fetchall()]

def get_recentposts():
    cur = get_cursor()
    cur.execute('''SELECT userid, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE postdate = (SELECT MAX(postdate)
                                     FROM posts AS p2
                                     WHERE p2.userid = posts.userid)
                     AND postdate > ?
                   ORDER BY postdate DESC, posttime DESC''',
                (util.today().toordinal() - 15,))
    return [Post(d) for d in cur.fetchall()]

def get_postbugs(post):
    cur = get_cursor()
    cur.execute('''SELECT titles.title, bug.bugid, bug.status
                   FROM bugtitles AS titles, bugs AS bug
                   WHERE bug.userid = ?
                     AND bug.postdate = ?
                     AND bug.bugid = titles.bugid''',
      (post.userid, post.postdate))
    post.populatebugs(cur.fetchall())

def get_userprojects(userid):
    cur = get_cursor()
    cur.execute('''SELECT projectname
                   FROM userprojects
                   WHERE userid = ?
                   ORDER BY projectname''',
                (userid,))
    return [project for project, in cur.fetchall()]

def get_userteam(userid):
    cur = get_cursor()
    cur.execute('''SELECT u2.userid, group_concat(u2.projectname)
                   FROM userprojects AS u1, userprojects AS u2
                   WHERE u1.userid = ?
                     AND u2.projectname = u1.projectname
                   GROUP BY u2.userid
                   ORDER BY u2.userid''',
                (userid,))

    return cur.fetchall()

def get_userteam_emails(userid):
    cur = get_cursor()
    cur.execute('''SELECT IFNULL(email, userid), sendemail
                   FROM users
                   WHERE EXISTS(SELECT *
                                FROM userprojects AS u1, userprojects AS u2
                                WHERE u1.userid = ?
                                  AND u2.projectname = u1.projectname
                                  AND u2.userid = users.userid)''',
                (userid,))
    r = cur.fetchall()
    return ([email for email, sendemail in r], [email for email, sendemail in r if sendemail == 0])

def get_project_users(projectname):
    cur = get_cursor()
    cur.execute('''SELECT userid FROM userprojects
                   WHERE projectname = ?
                   ORDER BY userid ASC''', (projectname,))
    return [userid for userid, in cur.fetchall()]

def get_project_late(projectname):
    cur = get_cursor()
    cur.execute('''SELECT userprojects.userid, MAX(postdate) AS lastpostdate
                   FROM userprojects LEFT OUTER JOIN posts ON posts.userid = userprojects.userid
                   WHERE projectname = ?
                   GROUP BY userprojects.userid
                   HAVING lastpostdate IS NULL OR lastpostdate < ?
                   ORDER BY lastpostdate ASC''',
                (projectname, util.today().toordinal() - 6))
    return [(userid, lastpostdate is not None and datetime.date.fromordinal(lastpostdate) or None)
            for userid, lastpostdate in cur.fetchall()]

def get_project_posts(projectname):
    cur = get_cursor()
    cur.execute('''SELECT userid, postdate, posttime, completed, planned, tags
                   FROM posts
                   WHERE postdate = (SELECT MAX(postdate)
                                     FROM posts AS p2
                                     WHERE p2.userid = posts.userid)
                     AND exists (SELECT * from userprojects
                                 WHERE userprojects.userid = posts.userid
                                 AND userprojects.projectname = ?)
                   ORDER BY postdate DESC, posttime DESC''', (projectname,))
    return [Post(d) for d in cur.fetchall()]

def get_naglist(cur):
    cur.execute('''SELECT users.userid, IFNULL(email, users.userid), MAX(postdate) AS lastpostdate
                   FROM users LEFT OUTER JOIN posts ON posts.userid = users.userid
                   WHERE reminderday = ? AND email IS NOT NULL
                   GROUP BY users.userid
                   HAVING lastpostdate IS NULL or lastpostdate < ?''',
                (util.today().weekday(), util.today().toordinal() - 6))
    return [(userid, email, lastpostdate is not None and datetime.date.fromordinal(lastpostdate) or None)
            for userid, email, lastpostdate in cur.fetchall()]

def iter_daily(cur, day):
    cur.execute('''SELECT userid, IFNULL(email, userid)
                   FROM users
                   WHERE sendemail = 1''')
    for userid, email in cur.fetchall():
        cur.execute('''SELECT userid, postdate, posttime, completed, planned, tags
                       FROM posts
                       WHERE postdate = ?
                         AND EXISTS(SELECT * FROM userprojects AS u1, userprojects AS u2
                                    WHERE u1.projectname = u2.projectname
                                    AND u1.userid = posts.userid
                                    AND u2.userid = ?)
                       ORDER BY postdate ASC, posttime ASC''',
                    (day.toordinal(), userid))
        yield userid, email, [Post(r) for r in cur.fetchall()]

def iter_weekly(cur, start, end):
    cur.execute('''SELECT userid, IFNULL(email, userid)
                   FROM users
                   WHERE sendemail = 2''')
    for userid, email in cur.fetchall():
        cur.execute('''SELECT userid, postdate, posttime, completed, planned, tags
                       FROM posts
                       WHERE postdate >= ? AND postdate <= ?
                         AND EXISTS(SELECT * FROM userprojects AS u1, userprojects AS u2
                                    WHERE u1.projectname = u2.projectname
                                    AND u1.userid = posts.userid
                                    AND u2.userid = ?)
                       ORDER BY postdate ASC, posttime ASC''',
                    (start.toordinal(), end.toordinal(), userid))
        yield userid, email, [Post(r) for r in cur.fetchall()]
