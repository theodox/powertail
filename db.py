__author__ = 'stevet'
from flask import app
from contextlib import closing
import sqlite3
import  datetime


DATABASE = '/tmp/flaskr.db'


def display_time(time):
    if time >= 24:
        return "midnight"
    hrs = int(time) % 12
    am = "AM"
    if time >= 12:
        am = "PM"
    minutes = int((time - int(time)) * 60)
    return "{}:{:02d} {}".format(hrs, minutes, am)


def init_db(app):
    with closing(connect_db()) as db:
        with app.open_resource('table.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
    print "new databse created"


def connect_db():
    return sqlite3.connect(DATABASE)


def allowed_now(kid):
    db = connect_db()
    cur = db.execute("SELECT balance FROM kids WHERE name like ?", (kid,))
    row = cur.fetchall()[0]
    if row[0] <= 0:
        return False, "no balance"

    today = datetime.date.isoweekday(datetime.date.today())
    intervals = db.execute("SELECT turn_on, turn_off FROM intervals WHERE kids_name = ? and day =?", (kid, today))
    now = datetime.datetime.now()
    test = now.hour + (now.minute / 60.0)
    start, end = intervals.fetchall()[0]
    if test < start or test > end:
        return False, "outside time", test, now
    return True, "OK"
