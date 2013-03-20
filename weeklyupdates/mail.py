import sys, cherrypy, datetime, smtplib, email.mime.multipart, email.mime.text
import main, model, util

_genericfrom = 'Mozilla Status Updates <noreply@smedbergs.us>'

def rendermail(template, subject, **kwargs):
    t = main.loader.load(template)
    htmlBody = t.generate(loginname=None, subject=subject, **kwargs)
    textBody = t.generate(loginname=None, subject=subject, **kwargs)
    return htmlBody.render('html'), textBody.render('text')

def sendmails(messages, fromaddress=None, recipientlist=None, app=None):
    if app is None:
        app = cherrypy.request.app
    smtpserver = app.config['weeklyupdates']['smtp.server']
    smtpuser = app.config['weeklyupdates'].get('smtp.username', None)
    smtppass = app.config['weeklyupdates'].get('smtp.password', None)

    session = smtplib.SMTP(smtpserver)
    if smtpuser is not None:
        session.login(smtpuser, smtppass)

    for message in messages:
        if fromaddress is not None:
            messagefrom = fromaddress
        else:
            messagefrom = message['From']

        if recipientlist is not None:
            messageto = recipientlist
        else:
            messageto = [message['To']]

        try:
            session.sendmail(messagefrom, messageto, message.as_string())
        except AttributeError, e:
            cherrypy.log.error("Exception sending mail from %r to %r: %s" % (fromaddress, recipientlist, e))
        except smtplib.SMTPException, e:
            cherrypy.log.error("Exception sending mail from %r to %r: %s" % (fromaddress, recipientlist, e))
    try:
        session.quit()
    except smtplib.SMTPException:
        pass

def sendpost(fromaddress, tolist, recipientlist, post):
    subject = "Status Update: %s on %s" % (post.username, post.postdate.isoformat())

    message = email.mime.multipart.MIMEMultipart('alternative')
    message['To'] = ', '.join(tolist)
    message['From'] = fromaddress
    message['Sender'] = 'weekly-updates@smedbergs.us'
    message['Subject'] = subject
    message['List-Id'] = '<weekly-updates.mozilla.com>'

    html, text = rendermail('message.xhtml', subject, post=post)
    message.attach(email.mime.text.MIMEText(text, 'plain', 'UTF-8'))
    message.attach(email.mime.text.MIMEText(html, 'html', 'UTF-8'))

    sendmails([message], fromaddress, recipientlist)

def getdigest(to, subject, posts):
    message = email.mime.multipart.MIMEMultipart('alternative')
    message['To'] = to
    message['From'] = _genericfrom
    message['Sender'] = 'weekly-updates@smedbergs.us'
    message['Subject'] = subject
    message['List-Id'] = '<weekly-updates.mozilla.com>'

    html, text = rendermail('messagedigest.xhtml', subject, posts=posts)
    message.attach(email.mime.text.MIMEText(text, 'plain', 'UTF-8'))
    message.attach(email.mime.text.MIMEText(html, 'html', 'UTF-8'))

    return message

def getnags(cur):
    for username, usermail, lastpostdate in model.get_naglist(cur):
        nag = """This is a friendly reminder from the Mozilla Status Board. """
        if lastpostdate is None:
            nag += "You have never made a post! "
        else:
            nag += "Your last post was %s. " % lastpostdate.isoformat()

        nag += "Please try to post weekly to keep other informed of your work."

        nag += "\n\nhttp://benjamin.smedbergs.us/weekly-updates.fcgi/"

        print "Sending nag to %s <%s>" % (username, usermail)

        message = email.mime.text.MIMEText(nag, 'plain', 'UTF-8')
        message['To'] = usermail
        message['From'] = _genericfrom
        message['Sender'] = 'weekly-updates@smedbergs.us'
        message['Subject'] = "Please post a status report"
        message['List-Id'] = '<weekly-updates.mozilla.com>'
        yield message

def getdaily(cur):
    yesterday = util.today() - datetime.timedelta(1)

    for username, email, posts in model.iter_daily(cur, yesterday):
        if len(posts):
            print "Sending daily update to %s <%s>" % (username, email)
            yield getdigest(email,
                            "Status Updates for %s" % yesterday.isoformat(),
                            posts)

def getweekly(cur):
    yesterday = util.today() - datetime.timedelta(1)
    lastweek = util.today() - datetime.timedelta(7)

    for username, email, posts in model.iter_weekly(cur, lastweek, yesterday):
        if len(posts):
            print "Sending weekly update to %s <%s>" % (username, email)

            subject = "Status Updates for %s through %s" % \
                (lastweek.isoformat(), yesterday.isoformat()),
            yield getdigest(email, subject, posts)

def sendtodaysmail(app):
    db = app.connectionpool().connectfn()
    cur = db.cursor()

    messages = [m for m in getnags(cur)]
    messages += [m for m in getdaily(cur)]

    if util.today().weekday() == 1:
        messages += [m for m in getweekly(cur)]

    sendmails(messages, app=app)

if __name__ == '__main__':
    app = main.Application()
    cherrypy.tree.apps[''] = app
    for c in sys.argv[1:]:
        app.merge(c)

    sendtodaysmail(app)
