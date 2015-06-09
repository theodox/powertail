import sys
import time

from flask import Flask, request, session, g, redirect, url_for, render_template, flash, jsonify
from collections import OrderedDict
from db import connect_db, init_db, display_time, current_interval, add_credits, time_fmt, add_temporary
import datetime

# configuration

DEBUG = True
SECRET_KEY = 'development key'
USERNAME = 'admin'
PASSWORD = 'default'




app = Flask(__name__)
app.config.from_object(__name__)
# todo: the above can be a separate file: see  http://flask.pocoo.org/docs/0.10/tutorial/setup/#tutorial-setup

from  power import PowerManager

manager = None

@app.before_request
def before_request():
    g.db = connect_db()
    g.g_time = time.strftime("%I:%M %p")
    known_logins = g.db.execute('SELECT name, pic FROM kids WHERE name != "System" ORDER BY NAME ').fetchall()
    g.logins = OrderedDict(known_logins)


@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


@app.route('/')
def front_page():
    news = []

    user = manager._kid or "logged out"
    state = "ON" if manager.state() else "OFF"
    interval = current_interval(manager._kid)
    remaining = int(min(interval.balance, interval.remaining) + .5)
    if remaining > 60:
        remaining = "{} hours {} minutes".format( int(remaining/60.0),  remaining%60)
    else:
        remaining = "{} minutes".format(remaining)
    clock = time.strftime("%I:%M %p")
    news = OrderedDict(user=user, state=state, remaining=remaining, time=clock)
    if state == "ON":
        flash("tv is on")
    return render_template('main.html', news=news)


@app.route('/history')
def show_history():
    cur = g.db.execute('SELECT time, kids_name, event FROM history ORDER BY time DESC LIMIT 100')
    entries = [dict(time=row[0][5:-3], kid=row[1], msg=row[2]) for row in cur.fetchall()]
    return render_template('history.html', entries=entries)


@app.route('/users')
def users():
    cur = g.db.execute('select name, balance, cap, replenished from kids WHERE name NOT  like "System"')
    entries = [dict(kid=row[0], balance=row[1], cap=row[2], replenished=row[3]) for row in cur.fetchall()]
    return render_template('users.html', kids=entries)

@app.route('/extend', methods=['GET','POST'])
def extend():
    error = None
    if request.method == 'GET':
        return render_template('extend.html', error=error)
    if request.method == 'POST':
        with connect_db() as conn:
            cur = conn.cursor()
            pwd = request.form['password']
            pwd_check = cur.execute("SELECT password FROM kids WHERE name = 'System'")
            if pwd == pwd_check.fetchone()[0]:
                extra_minutes = int (request.form['amount'])
                add_temporary(extra_minutes)
                flash("TV will stay on for %s minutes" % extra_minutes)
                return redirect(url_for('front_page'))
            else:
                error = 'Invalid password'
            return render_template('extend.html', error=error)

@app.route('/today')
def today():

    day_num = int(time.strftime("%w"))
    now = datetime.datetime.now()
    test = now.hour + (now.minute / 60.0)
    results = dict()
    users = g.db.execute("SELECT name FROM kids WHERE NAME NOT LIKE 'System'").fetchall()
    users = [k[0] for k in users]
    for u in users:
        interval = current_interval(u)
        cap, entries = get_schedule_for_user(u)
        today = [e for e in entries if e['day_num'] == day_num]
        for e in today:
            e['valid'] = e['off_num'] > test
        if today:
            results[u] = time_fmt(cap), time_fmt(interval.balance), today

    return render_template('today.html', entries=results)




@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        name = request.form['username']
        pwd = request.form['password']

        with connect_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name, password FROM kids WHERE name like ?", (name,))
            results = cur.fetchall()
            if len(results) == 0:
                error = "Invalid username"
            elif results[0][1] != pwd:
                error = "Invalid password"
            else:
                session['logged_in'] = True
                session['username'] = name
                manager.set_user(name)
                flash('You were logged in')
                return redirect(url_for('front_page'))
    return render_template('login.html', error=error)


@app.route('/direct/')
@app.route('/direct/<username>', methods=['GET', 'POST'])
def direct(username):
    error = None
    if request.method == 'POST':
        name = username
        pwd = request.form['password']

        with connect_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name, password FROM kids WHERE name like ?", (name,))
            results = cur.fetchall()
            if len(results) == 0:
                error = "Invalid username"
            elif results[0][1] != pwd:
                error = "Invalid password"
            else:
                session['logged_in'] = True
                session['username'] = name
                manager.set_user(name)
                flash('You were logged in')
                return redirect(url_for('front_page'))

    return render_template('login_direct.html', error=error, username=username)


@app.route('/donate/')
@app.route('/donate/<username>', methods=['GET', 'POST'])
def donate(username=None):
    error = None
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM kids")
        all_kids = [i[0] for i in cur.fetchall()]
    if request.method == 'GET':
        if username:
            return render_template('donate.html', error=error, children=(username,) )
        else:
            return render_template('donate.html', error=error, children=all_kids)

    elif request.method == 'POST':
        with connect_db() as conn:
            cur = conn.cursor()
            pwd = request.form['password']
            pwd_check = cur.execute("SELECT password FROM kids WHERE name = 'System'")
            if pwd == pwd_check.fetchone()[0]:
                extra = int (request.form['amount'])
                kid = request.form['child']
                add_credits(kid, extra)
                flash("added %s to %s" % (extra, kid))
            else:
                error = 'Invalid password'

        return render_template('donate.html', error=error, children=all_kids)


def get_schedule_for_user(username):
    cap = g.db.execute('select cap from kids WHERE name LIKE ?', (username,)).fetchone()[0]
    replenish = g.db.execute('select * from replenish where kids_name LIKE ?', (username,))
    repl = replenish.fetchone()[1:-1]
    day_names = 'Sun Mon Tue Wed Thu Fri Sat'.split()
    schedule = g.db.execute('select  day, turn_on, turn_off from intervals WHERE kids_name LIKE ? order by day',
                            (username,))

    def row_fmt(row):
        day = row[0] - 1
        return {
            'day': day_names[day],
            'on': display_time(row[1]),
            'off': display_time(row[2]),
            'add': repl[day],
            'day_num': day,
            'on_num': row[1],
            'off_num': row[2]
        }

    entries = [row_fmt(row) for row in schedule.fetchall()]
    return cap, entries


@app.route('/schedule')
def overall_schedule():
    results = dict()
    users = g.db.execute("SELECT name FROM kids WHERE NAME NOT LIKE 'System'").fetchall()
    for k in users:
        results[k[0]] = get_schedule_for_user(k[0])
    return render_template('overall_schedule.html', entries=results)


@app.route('/schedule/<username>')
def get_schedule(username):

    cap, entries = get_schedule_for_user(username)
    return render_template('schedule.html', cap  = cap, entries=entries,username=username)


@app.route('/update')
def update():
    user = manager._kid or "logged out"
    state = "ON" if manager.state() else "OFF"
    interval = current_interval(manager._kid)
    remaining = int(min(interval.balance, interval.remaining) + .5)
    if remaining > 60:
        remaining = "{} hours {} minutes".format( int(remaining/60.0),  remaining%60)
    else:
        remaining = "{} minutes".format(remaining)
    clock = time.strftime("%I:%M %p")
    return jsonify(user=user, state=state, remaining=remaining, time=clock)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username')
    manager.set_user(None)
    flash('You were logged out')
    return redirect(url_for('front_page'))



if __name__ == '__main__':
    if sys.argv[-1] == '--setup':
        init_db(app)
        raise SystemExit(0)
    else:
        print "starting"

        manager = PowerManager.manager(app)
        manager.monitor()
        app.run(host=('0.0.0.0'))
