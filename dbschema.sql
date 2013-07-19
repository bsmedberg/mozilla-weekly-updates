CREATE TABLE IF NOT EXISTS users
(
  username VARCHAR(80) NOT NULL PRIMARY KEY,
  email VARCHAR(255),
  password VARCHAR(80) NULL,
  reminderday TINYINT NULL,
  sendemail TINYINT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS projects
(
  projectname VARCHAR(80) NOT NULL PRIMARY KEY,
  createdby VARCHAR(80) NOT NULL,
  CONSTRAINT projects_createdby_fkey FOREIGN KEY (createdby) REFERENCES users (username)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS userprojects
(
  projectname VARCHAR(80) NOT NULL,
  username VARCHAR(80) NOT NULL,
  CONSTRAINT userprojects_pkey PRIMARY KEY (projectname, username),
  CONSTRAINT userprojects_projectname_fkey FOREIGN KEY (projectname) REFERENCES projects (projectname),
  CONSTRAINT userprojects_username_fkey FOREIGN KEY (username) REFERENCES users (username)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS posts
(
  username VARCHAR(80) NOT NULL,
  postdate INTEGER NOT NULL,
  posttime INTEGER NOT NULL,
  completed TEXT,
  planned TEXT,
  tags TEXT,
  CONSTRAINT posts_pkey PRIMARY KEY (username, postdate),
  CONSTRAINT posts_username_fkey FOREIGN KEY (username) REFERENCES users (username)
) ENGINE=InnoDB;
