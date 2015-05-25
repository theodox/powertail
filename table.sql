DROP TABLE IF EXISTS kids;
CREATE TABLE kids (
  name     TEXT PRIMARY KEY NOT NULL,
  password TEXT             NOT NULL,
  balance  REAL             NOT NULL,
  cap      INTEGER          NOT NULL DEFAULT 60,
  replenished  TEXT NOT NULL DEFAULT '2015-01-01'
);


DROP TABLE IF EXISTS intervals;
CREATE TABLE intervals (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  day       INTEGER NOT NULL,
  turn_on   REAL    NOT NULL,
  turn_off  REAL    NOT NULL,
  kids_name TEXT,
  FOREIGN KEY (kids_name) REFERENCES kids (name)
);

DROP TABLE IF EXISTS replenish;
CREATE TABLE replenish
(
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  sun       INTEGER NOT NULL DEFAULT 0,
  mon       INTEGER NOT NULL DEFAULT 0,
  tues      INTEGER NOT NULL DEFAULT 0,
  weds      INTEGER NOT NULL DEFAULT 0,
  thurs     INTEGER NOT NULL DEFAULT 0,
  fri       INTEGER NOT NULL DEFAULT 0,
  sat       INTEGER NOT NULL DEFAULT 0,
  kids_name TEXT,
  FOREIGN KEY (kids_name) REFERENCES kids (name)
);


DROP TABLE IF EXISTS history;
CREATE TABLE history
(
  id integer PRIMARY KEY AUTOINCREMENT ,
  time  DATETIME DEFAULT (datetime('now','localtime')),
  event TEXT NOT NULL,
  kids_name TEXT,
  FOREIGN KEY (kids_name) REFERENCES kids (name)
);

INSERT INTO kids ('name', 'password', 'balance', 'cap') VALUES
  ('Nicky', 'nicky', 0, 60),
  ('Helen', 'helen', 0, 60),
  ('Al', 'al', 0, 360),
  ('Daddy', 'dad', 0, 240),
  ('Guest', 'guest', 0, 60),
  ('System', 'system', 0,0);

INSERT INTO intervals ('day', 'turn_on', 'turn_off', 'kids_name') VALUES
  (1, 14.5, 16.5, 'Helen'),
  (2, 14.5, 16.5, 'Helen'),
  (3, 14.5, 16.5, 'Helen'),
  (4, 14.5, 16.5, 'Helen'),
  (5, 14.5, 16.5, 'Helen'),
  (6, 8, 21, 'Helen'),
  (7, 8, 21, 'Helen'),
  (1, 14.5, 16.5, 'Nicky'),
  (2, 14.5, 16.5, 'Nicky'),
  (3, 14.5, 16.5, 'Nicky'),
  (4, 14.5, 16.5, 'Nicky'),
  (5, 14.5, 16.5, 'Nicky'),
  (6, 8, 21, 'Nicky'),
  (7, 8, 21, 'Nicky'),
  (6, 14.5, 20, 'Al'),
  (7, 8, 21, 'Al'),
  (1, 8, 21, 'Al'),
  (1, 8, 24, 'Daddy'),
  (2, 8, 24, 'Daddy'),
  (3, 8, 24, 'Daddy'),
  (4, 8, 24, 'Daddy'),
  (5, 8, 24, 'Daddy'),
  (6, 8, 24, 'Daddy'),
  (7, 8, 24, 'Daddy');

INSERT INTO replenish (sun, mon, tues, weds, thurs, fri, sat, kids_name) VALUES
  (240, 240, 240, 240, 240, 240, 240, 'Daddy'),
  (30, 30, 30, 30, 30, 30, 30, 'Nicky'),
  (30, 30, 30, 30, 30, 30, 30, 'Helen'),
  (180, 0, 0, 0, 0, 180, 180, 'Al'),
  (60, 60, 60, 60, 60, 60, 60, 'guest');
  