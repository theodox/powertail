
drop table if exists kids;
create table kids (
  name text PRIMARY KEY not null,
  password text not null,
  balance real not null
);

INSERT INTO kids ('name', 'password', 'balance') VALUES
  ('Nicky', 'nicky', 0),
  ('Helen', 'helen', 0),
  ('Al', 'al', 5),
  ('Daddy', 'dad', 999);

drop table if EXISTS intervals;
create table intervals (
  id integer primary key autoincrement,
  day integer NOT NULL,
  turn_on real not NULL,
  turn_off real not NULL,
  kids_name text,
  FOREIGN KEY (kids_name) REFERENCES kids(name)
);

INSERT  into intervals('day','turn_on', 'turn_off', 'kids_name') VALUES
  (7, 11.0, 24.0, 'Daddy'),
  (6, 9.0, 21.0, 'Daddy'),
  (1, 18.0, 20.0, 'Daddy'),
  (6, 8, 14, 'Al'),
  (7, 8, 19, 'Al');

