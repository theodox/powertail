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
        log(db, 'System', 'database created')


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
        return True, min (end-test, row[0])


def replenish(kid):

    if kid is None:
        return False

    with connect_db() as db:
        repl = db.execute("SELECT replenished from kids WHERE name LIKE ? and DATE (replenished) <  DATE ('now')", (kid,))
        recent = repl.fetchone()

        if recent:
            daynum = db.execute("SELECT strftime ('%w', 'now')").fetchone()[0]
            daynum = int(daynum)
            repl_amount = db.execute("SELECT sun, mon, tues, weds, thurs, fri, sat FROM replenish WHERE kids_name like ?", ( kid,))
            refresh = repl_amount.fetchone()[daynum]
            cap_amount = db.execute("SELECT cap, balance FROM kids WHERE name LIKE ?", (kid,))
            cap, balance = cap_amount.fetchone()
            new_balance = min(cap,refresh + balance )

            db.execute("UPDATE kids SET balance = ? , replenished = DATE('now') WHERE name LIKE ?", (new_balance, kid))
            log(db, kid, "replenished with %i credits" % new_balance)


def log(connection, kid, message):
    if not kid:
        return
    print "logging"
    print connection.execute("INSERT INTO history (kids_name, event) VALUES (?,?)", (kid, message))