import datetime
from genshi.filters import HTMLSanitizer
from genshi.input import HTML
import markdown2
import re

link_patterns = (
    (re.compile(r'(https?://.*\b)'), r'\1'),
    (re.compile(r'bug[\s:#]+(\d{3,7})\b'), r'https://bugzilla.mozilla.org/show_bug?id=\1'),
)

md = markdown2.Markdown(html4tags=True, tab_width=2, extras=['link-patterns'],
                        link_patterns=link_patterns)

class Post(object):
    username = None
    postdate = None
    posttime = None
    completed = None
    planned = None
    tags = None

    def __init__(self, record):
        if record is not None:
            self.username, self.postdate, self.posttime, self.completed, self.planned, self.tags = record
            self.postdate = datetime.date.fromordinal(self.postdate)
            self.posttime = datetime.datetime.fromtimestamp(self.posttime)

    def getcompleted(self):
        if self.completed is None:
            return None
        return HTML(md.convert(self.completed)) | HTMLSanitizer()

    def getplanned(self):
        if self.planned is None:
            return None
        return HTML(md.convert(self.planned)) | HTMLSanitizer()

    def gettags(self):
        if self.tags is None:
            return None
        return HTML(md.convert(self.tags)) | HTMLSanitizer()

