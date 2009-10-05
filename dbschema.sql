CREATE TABLE IF NOT EXISTS projects
(
  projectname VARCHAR(255) NOT NULL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS users
(
  username VARCHAR(255) NOT NULL PRIMARY KEY,
  email VARCHAR(255),
  password VARCHAR(255) NULL
);

CREATE TABLE IF NOT EXISTS userprojects
(
  projectname VARCHAR(255) NOT NULL,
  username VARCHAR(255) NOT NULL,
  CONSTRAINT userprojects_pkey PRIMARY KEY (projectname, username)
);

CREATE TABLE IF NOT EXISTS posts
(
  username VARCHAR(255) NOT NULL,
  postdate DATETIME NOT NULL,
  completed TEXT,
  planned TEXT,
  tags TEXT,
  CONSTRAINT posts_pkey PRIMARY KEY (username, postdate)
);
