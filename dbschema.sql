CREATE TABLE IF NOT EXISTS users
(
  userid VARCHAR(80) NOT NULL PRIMARY KEY,
  email VARCHAR(255),
  password VARCHAR(80) NULL,
  reminderday TINYINT NULL,
  sendemail TINYINT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS projects
(
  projectname VARCHAR(80) NOT NULL PRIMARY KEY,
  createdby VARCHAR(80) NOT NULL,
  CONSTRAINT projects_createdby_fkey FOREIGN KEY (createdby) REFERENCES users (userid)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS userprojects
(
  projectname VARCHAR(80) NOT NULL,
  userid VARCHAR(80) NOT NULL,
  CONSTRAINT userprojects_pkey PRIMARY KEY (projectname, userid),
  CONSTRAINT userprojects_projectname_fkey FOREIGN KEY (projectname) REFERENCES projects (projectname),
  CONSTRAINT userprojects_userid_fkey FOREIGN KEY (userid) REFERENCES users (userid)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS posts
(
  userid VARCHAR(80) NOT NULL,
  postdate INTEGER NOT NULL,
  posttime INTEGER NOT NULL,
  completed TEXT,
  planned TEXT,
  tags TEXT,
  CONSTRAINT posts_pkey PRIMARY KEY (userid, postdate),
  CONSTRAINT posts_userid_fkey FOREIGN KEY (userid) REFERENCES users (userid)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bugs
(
  bugid INTEGER NOT NULL,
  userid VARCHAR(80) NOT NULL,
  postdate INTEGER NOT NULL,
  status TINYINT NULL,
  CONSTRAINT bugs_pkey PRIMARY KEY (bugid, postdate),
  CONSTRAINT bugs_userid_fkey FOREIGN KEY (userid) REFERENCES posts (userid)
  -- CONSTRAINT bugs_bugid_fkey FOREIGN KEY (bugid) REFERENCES bugtitles (bugid)
  -- CONSTRAINT bugs_postdate_fkey FOREIGN KEY (postdate) REFERENCES posts (postdate)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bugtitles
(
  bugid INTEGER NOT NULL,
  title TEXT,
  CONSTRAINT bugtitles_pkey PRIMARY KEY (bugid),
  CONSTRAINT bugtitles_bugid_fkey FOREIGN KEY (bugid) REFERENCES bugs (bugid)
) ENGINE=InnoDB;
