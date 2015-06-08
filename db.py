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
    am = "<sup>am</sup>"
    if time >= 12:
        am = "<sup>pm</sup>"
    minutes = int((time - int(time)) * 60)
    return "{}:{:02d}{}".format(hrs, minutes, am)


def init_db(app):
    with closing(connect_db()) as db:
        with app.open_resource('table.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
        print "new database created"
        log(db, 'System', 'database created')


def hournumber(dt):
    try:
       dt =  datetime.datetime.strptime(str(dt), "%Y-%m-%d %H:%M:%S.%f")
    except Exception as e:
        pass
    return dt.hour + (dt.minute / 60.0)

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


from collections import namedtuple

interval = namedtuple('interval', 'start end balance remaining')



def current_interval(kid):

    now = datetime.datetime.now()
    now_num = hournumber(now)
    end_time = -1

    default = interval(now_num, -1, 0, 0)

    with connect_db() as db:

        cur = db.execute('DELETE FROM temporaries WHERE ends < ?', (now, ))
        temps = db.execute("SELECT ends FROM temporaries ORDER BY ends DESC LIMIT 1")
        temporaries = temps.fetchone()
        if temporaries:
            rest = hournumber(temporaries[0])

            default = interval(now_num, rest, (rest-now_num) * 60, (rest-now_num) * 60)
            print "auto-interval", default

        if kid is None:
            return default

        cur = db.execute("SELECT balance FROM kids WHERE name LIKE ?", (kid,))
        results = cur.fetchone()
        balance = results[0]

        today = datetime.date.isoweekday(datetime.date.today())
        intervals = cur.execute("SELECT turn_on, turn_off FROM intervals WHERE kids_name LIKE ? AND day =?",
                                (kid, today))
        now = datetime.datetime.now()
        time_as_number = now.hour + (now.minute / 60.0)
        results = intervals.fetchall()
        for r in results:
            on, off = r
            if on <= time_as_number <= off:
                if default.remaining > balance:
                    return default
                return interval(on, off, balance, (off - time_as_number) * 60)
        return interval(now_num, -1, balance, 0)


def replenish(kid):
    if kid is None:
        return False

    with connect_db() as db:
        repl = db.execute("SELECT replenished FROM kids WHERE name LIKE ? AND DATE (replenished) <  DATE ('now')",
                          (kid,))
        recent = repl.fetchone()

        if recent:
            daynum = db.execute("SELECT strftime ('%w', 'now')").fetchone()[0]
            daynum = int(daynum)
            repl_amount = db.execute(
                "SELECT sun, mon, tues, weds, thurs, fri, sat FROM replenish WHERE kids_name LIKE ?", ( kid,))
            refresh = repl_amount.fetchone()[daynum]
            cap_amount = db.execute("SELECT cap, balance FROM kids WHERE name LIKE ?", (kid,))
            cap, balance = cap_amount.fetchone()
            new_balance = min(cap, refresh + balance)

            db.execute("UPDATE kids SET balance = ? , replenished = DATE('now') WHERE name LIKE ?", (new_balance, kid))
            log(db, kid, "replenished with %i credits" % new_balance)


def add_credits(kid, amount):
    if kid is None:
        return False

    with connect_db() as db:
        cap_amount = db.execute("SELECT cap, balance FROM kids WHERE name LIKE ?", (kid,))
        cap, balance = cap_amount.fetchone()
        new_balance = min(cap, amount + balance)

        db.execute("UPDATE kids SET balance = ? WHERE name LIKE ?", (new_balance, kid))
        log(db, kid, "added %i credits" % amount)


def add_temporary(minutes):
    now = datetime.datetime.now()
    then = datetime.timedelta(minutes=minutes)
    ends = now + then
    with connect_db() as db:
        db.execute("INSERT  INTO temporaries (ends) VALUES (?)", (ends,));
        log(db, "System", "extended until %s" % ends)


def log(connection, kid, message):
    if not kid:
        return
    connection.execute("INSERT INTO history (kids_name, event) VALUES (?,?)", (kid, message))


def time_fmt(mins):
    if mins > 60:
        hrs = mins / 60.0
        return "{:.1f} hrs".format(hrs)
    return "{} mins".format(int(mins))