import sys, cherrypy, datetime, email.mime.multipart, email.mime.text
import main, model, util

def rendermail(template, subject, **kwargs):
    t = main.loader.load(template)
    htmlBody = t.generate(loginid=None, subject=subject, **kwargs)
    textBody = t.generate(loginid=None, subject=subject, **kwargs)
    return htmlBody.render('html'), textBody.render('text').strip()

def sendmails_smtp(messages, fromaddress, app):
    import smtplib
    smtpserver = app.config['weeklyupdates']['smtp.server']
    smtpuser = app.config['weeklyupdates'].get('smtp.username', None)
    smtppass = app.config['weeklyupdates'].get('smtp.password', None)

    session = smtplib.SMTP(smtpserver)
    if smtpuser is not None:
        session.login(smtpuser, smtppass)

    for message in messages:
        recipient = message['To']

        messagestr = message.as_string()
        try:
            session.sendmail("", recipient, messagestr)
        except AttributeError, e:
            cherrypy.log.error("Exception sending mail from %r to %r: %s" % (fromaddress, recipient, e))
        except smtplib.SMTPException, e:
            cherrypy.log.error("Exception sending mail from %r to %r: %s" % (fromaddress, recipient, e))
    try:
        session.quit()
    except smtplib.SMTPException:
        pass

def sendmails_ses(messages, fromaddress, app):
    import boto3, botocore.exceptions
    session = boto3.client('ses')

    for message in messages:
        recipient = message['To']

        messagestr = message.as_string()
        try:
            msg = session.send_raw_email(
                Source=fromaddress,
                Destinations=[recipient],
                RawMessage={'Data': messagestr}
            )
            cherrypy.log.error_log.info("Sent email. %s %i %s", recipient, msg.get('HTTPStatusCode', 0), msg.get('MessageId', None))
        except botocore.exceptions.ClientError, e:
            cherrypy.log.error_log.error("Failed email. %s %s", recipient, e)

def sendmails(messages, app=None):
    if app is None:
        app = cherrypy.request.app

    fromaddress = app.config['weeklyupdates']['email.from']
    for message in messages:
        message['From'] = fromaddress

    if app.config['weeklyupdates'].get('email.use_ses', False):
        sendmails_ses(messages, fromaddress, app)
    else:
        sendmails_smtp(messages, fromaddress, app)

def sendpost(fromaddress, recipientlist, post):
    subject = "Status Update: %s on %s" % (post.userid, post.postdate.isoformat())

    messages = []

    for recipient in recipientlist:
        message = email.mime.multipart.MIMEMultipart('alternative')
        message['To'] = recipient
        message['Subject'] = subject
        message['List-Id'] = '<weekly-updates.mozilla.com>'

        html, text = rendermail('message.xhtml', subject, post=post)
        message.attach(email.mime.text.MIMEText(text, 'plain', 'UTF-8'))
        message.attach(email.mime.text.MIMEText(html, 'html', 'UTF-8'))
        messages.append(message)

    sendmails(messages)

def getdigest(to, subject, posts):
    message = email.mime.multipart.MIMEMultipart('alternative')
    message['To'] = to
    message['Subject'] = subject
    message['List-Id'] = '<weekly-updates.mozilla.com>'

    html, text = rendermail('messagedigest.xhtml', subject, posts=posts)
    message.attach(email.mime.text.MIMEText(text, 'plain', 'UTF-8'))
    message.attach(email.mime.text.MIMEText(html, 'html', 'UTF-8'))

    return message

def getnags(cur):
    for userid, usermail, lastpostdate in model.get_naglist(cur):
        nag = """This is a friendly reminder from the Mozilla Status Board. """
        if lastpostdate is None:
            nag += "You have never made a post! "
        else:
            nag += "Your last post was %s. " % lastpostdate.isoformat()

        nag += "Please try to post weekly to keep other informed of your work."

        nag += "\n\nhttp://statusupdates.dev.mozaws.net/"

        print "Sending nag to %s <%s>" % (userid, usermail)

        message = email.mime.text.MIMEText(nag, 'plain', 'UTF-8')
        message['To'] = usermail
        message['Subject'] = "Please post a status report"
        message['List-Id'] = '<weekly-updates.mozilla.com>'
        yield message

def getdaily(cur):
    yesterday = util.today() - datetime.timedelta(1)

    for userid, email, posts in model.iter_daily(cur, yesterday):
        if len(posts):
            print "Sending daily update to %s <%s>" % (userid, email)
            yield getdigest(email,
                            "Status Updates for %s" % yesterday.isoformat(),
                            posts)

def getweekly(cur):
    yesterday = util.today() - datetime.timedelta(1)
    lastweek = util.today() - datetime.timedelta(7)

    for userid, email, posts in model.iter_weekly(cur, lastweek, yesterday):
        if len(posts):
            print "Sending weekly update to %s <%s>" % (userid, email)

            subject = "Status Updates for %s through %s" % \
                (lastweek.isoformat(), yesterday.isoformat())
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
