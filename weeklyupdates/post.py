import datetime
from genshi.filters import HTMLSanitizer
from genshi.input import HTML

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
        return HTML(self.completed) | HTMLSanitizer()

    def getplanned(self):
        if self.planned is None:
            return None
        return HTML(self.planned) | HTMLSanitizer()

    def gettags(self):
        if self.tags is None:
            return None
        return HTML(self.tags) | HTMLSanitizer()

