from datetime import date

class Post(object):
    username = None
    postdate = None
    completed = None
    planned = None
    tags = None

    def __init__(self, record):
        if record is not None:
            self.username, self.postdate, self.completed, self.planned, self.tags = record
            self.postdate = date.fromordinal(self.postdate)
