import datetime
from genshi.filters import HTMLSanitizer
from genshi.input import HTML, ParseError
import markdown2
import re

link_patterns = (
    (re.compile(r'(?<![">])(https?://.*?(?=[\s\]\)\|]|$))', re.I | re.MULTILINE), r'\1'),
    (re.compile(r'bug[\s:#]+(\d{3,7})\b', re.I), r'https://bugzilla.mozilla.org/show_bug.cgi?id=\1'),
)

md = markdown2.Markdown(html4tags=True, tab_width=2,
                        extras=['link-patterns',
                                'cuddled-lists',
                                'code-friendly'],
                        link_patterns=link_patterns)

class Post(object):
    userid = None
    postdate = None
    posttime = None
    completed = None
    planned = None
    tags = None
    bugs = None

    def __init__(self, record):
        if record is not None:
            self.userid, self.postdate, self.posttime, self.completed, self.planned, self.tags = record
            self.postdate = datetime.date.fromordinal(self.postdate)
            self.posttime = datetime.datetime.fromtimestamp(self.posttime)

    def populatebugs(self, bugs):
        if bugs is not None:
            self.bugs = bugs

    def getcompleted(self):
        if self.completed is None:
            return None
        try:
            return HTML(md.convert(self.completed)) | HTMLSanitizer()
        except ParseError:
            return self.completed

    def getplanned(self):
        if self.planned is None:
            return None
        try:
            return HTML(md.convert(self.planned)) | HTMLSanitizer()
        except ParseError:
            return self.planned

    def gettags(self):
        if self.tags is None:
            return None
        try:
            return HTML(md.convert(self.tags)) | HTMLSanitizer()
        except ParseError:
            return self.tags

