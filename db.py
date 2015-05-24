__author__ = 'stevet'
from flask import app
from contextlib import closing
import sqlite3
import datetime


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
    print "new database created"


def connect_db():
    return sqlite3.connect(DATABASE)


def deduct(kid, amount):
    if kid is None:
        return
    with connect_db() as db:
        cur = db.cursor()
        cur.execute("SELECT balance FROM kids WHERE name = ?", (kid,))
        balance = cur.fetchone()[0]
        balance = max(balance - amount, 0)
        cur.execute("UPDATE kids SET balance = ? WHERE name = ?", (balance, kid))


def remaining(kid):
    if kid is None:
        return 0

    with connect_db() as db:
        cur = db.execute("SELECT balance FROM kids WHERE name LIKE ?", (kid,))
        results = cur.fetchall()
        if not results:
            return 0
        row = results[0]
        if row[0] <= 0:
            return 0

        cur.execute("SELECT balance FROM kids WHERE name = ?", (kid,))
        balance = cur.fetchone()[0]

        today = datetime.date.isoweekday(datetime.date.today())
        intervals = cur.execute("SELECT turn_on, turn_off FROM intervals WHERE kids_name = ? AND day =?", (kid, today))
        now = datetime.datetime.now()
        test = now.hour + (now.minute / 60.0)
        results = intervals.fetchall()
        if not results:
            return 0
        start, end = results[0]
        if test < start or test > end:
            return 0
        return min(balance, end - test)


def allowed_now(kid):
    if kid is None:
        return False, "logged out"

    with connect_db() as db:
        cur = db.execute("SELECT balance FROM kids WHERE name LIKE ?", (kid,))
        results = cur.fetchall()
        if not results:
            return False, "no user"
        row = results[0]
        if row[0] <= 0:
            return False, "no balance"

        today = datetime.date.isoweekday(datetime.date.today())
        intervals = cur.execute("SELECT turn_on, turn_off FROM intervals WHERE kids_name = ? AND day =?", (kid, today))
        now = datetime.datetime.now()
        test = now.hour + (now.minute / 60.0)
        results = intervals.fetchall()
        if not results:
            return False, "no interval"
        start, end = results[0]
        if test < start or test > end:
            return False, "outside time"
        return True, "OK"
