import sys
import time
from collections import OrderedDict
import datetime

from flask import Flask, request, session, g, redirect, url_for, render_template, flash, jsonify

from db import connect_db, init_db, display_time, current_interval, add_credits, time_fmt, add_temporary, deduct, \
    clear_temporary












# configuration

DEBUG = True
SECRET_KEY = 'a;lfsh92why'
USERNAME = 'admin'
PASSWORD = 'default'

app = Flask(__name__)
app.config.from_object(__name__)
# todo: the above can be a separate file: see  http://flask.pocoo.org/docs/0.10/tutorial/setup/#tutorial-setup

from  power import PowerManager

manager = None


def check_sys_password(request):
    with connect_db() as conn:
        cur = conn.cursor()
        pwd = request.form['password']
        pwd_check = cur.execute("SELECT password FROM kids WHERE name = 'System'")
        return pwd_check.fetchone()[0] == pwd


@app.before_request
def before_request():
    g.db = connect_db()
    g.g_time = time.strftime("%I:%M %p")
    known_logins = g.db.execute('SELECT name, pic FROM kids WHERE name  != "System" ORDER BY NAME ').fetchall()
    g.logins = OrderedDict(known_logins)
    g.active_user = manager._kid


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
        remaining = "{} hours {} minutes".format(int(remaining / 60.0), remaining % 60)
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
    cur = g.db.execute('select name, balance, cap, replenished, debit from kids WHERE name NOT  like "System"')
    entries = [dict(kid=row[0], balance=row[1], cap=row[2], replenished=row[3], debit=-1 * row[4]) for row in
               cur.fetchall()]
    return render_template('users.html', kids=entries)


@app.route('/extend', methods=['GET', 'POST'])
def extend():
    error = None
    if request.method == 'GET':
        return render_template('extend.html', error=error)
    if request.method == 'POST':

        if not check_sys_password(request):
            error = "Incorrect password"
            return render_template('extend.html', error=error)

        with connect_db() as conn:
            extra_minutes = int(request.form['amount'])
            add_temporary(extra_minutes)
            flash("TV will stay on for %s minutes" % extra_minutes)
            return redirect(url_for('front_page'))


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
        cap, entries, debit = get_schedule_for_user(u)
        today = [e for e in entries if e['day_num'] == day_num]
        for e in today:
            e['valid'] = e['off_num'] > test
        if today:
            results[u] = time_fmt(cap), time_fmt(interval.balance), today, time_fmt(-1 * debit)

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
            return render_template('donate.html', error=error, children=(username,))
        else:
            return render_template('donate.html', error=error, children=all_kids)

    elif request.method == 'POST':

        if not check_sys_password(request):
            error = "Incorrect password"
            return render_template('donate.html', error=error, children=(request.form['child'],),
                                   username=request.form['child'])

        extra = int(request.form['amount'])
        kid = request.form['child']
        add_credits(kid, extra)
        flash("added %s to %s" % (extra, kid))
        return redirect(url_for('today'))


@app.route('/debit/<username>', methods=['GET', 'POST'])
def apply_debit(username=None):
    error = None
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM kids")
        all_kids = [i[0] for i in cur.fetchall()]
    if request.method == 'GET':
        if username:
            return render_template('debit.html', error=error, children=(username,))
        else:
            return render_template('debit.html', error=error, children=all_kids)

    elif request.method == 'POST':

        if not check_sys_password(request):
            error = "Incorrect password"
            return render_template('debit.html', error=error, children=(request.form['child'],),
                                   username=request.form['child'])

        deduction = int(request.form['amount'])
        kid = request.form['child']
        deduct(kid, deduction)
        flash("deducted %s from %s" % (deduction, kid))

        return redirect(url_for('today'))


def get_schedule_for_user(username):
    cap, debit = g.db.execute('select cap, debit from kids WHERE name LIKE ?', (username,)).fetchone()
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

    return cap, entries, debit


@app.route('/off')
def shutdown():
    try:
        logout()
    except:
        pass

    clear_temporary()
    flash('tv shut down')

    return redirect(url_for('front_page'))


@app.route('/overview')
def overall_schedule():
    results = dict()
    users = g.db.execute("SELECT name FROM kids WHERE NAME NOT LIKE 'System'").fetchall()
    for k in users:
        results[k[0]] = get_schedule_for_user(k[0])
    return render_template('overall_schedule.html', entries=results)


@app.route('/schedule/<username>')
def get_schedule(username):
    cap, entries, debit = get_schedule_for_user(username)
    repl = {}
    for e in entries:
        repl[e['day']] = e['add']
    current = current_interval(username)
    return render_template('schedule.html', cap=cap, entries=entries, debit=debit, username=username, credits = repl, balance = current.balance)


@app.route('/create_interval/<username>', methods=['GET', 'POST'])
def create_interval(username):
    error = None

    if request.method == 'GET':
        dayname = request.args.get('dayname')
        daynum = request.args.get('daynum')
        return render_template('add_interval.html', username=username, dayname=dayname, daynum=daynum)
    else:
        username = request.form['username']
        daynum = request.form['daynum']
        if not check_sys_password(request):
            error = "Incorrect password"
            return render_template('add_interval.html', username=username,
                                   error=error, dayname=request.form['dayname'],
                                   daynum=daynum)
        start_hr, start_min = request.form['start_time'].split(":")
        end_hr, end_min = request.form['end_time'].split(":")
        start_num = int(start_hr) + int(start_min) / 60.0
        end_num = int(end_hr) + int(end_min) / 60.0
        if start_num >= end_num:
            error = "End time must be later than start time"
            return render_template('add_interval.html', username=username,
                                   error=error, dayname=request.form['dayname'],
                                   daynum=daynum)
        with connect_db() as db:
            cursor = db.cursor()
            cursor.execute("INSERT INTO intervals ('day', 'turn_on', 'turn_off', 'kids_name') VALUES (?, ?, ?, ?)",
                           (daynum, start_num, end_num, username))

            flash('added interval')
            return redirect(url_for('get_schedule', username=username))


@app.route('/remove_interval/<username>', methods=['GET', 'POST'])
def delete_interval(username):
    error = None
    if request.method == 'GET':
        dayname = request.args.get('dayname')
        daynum = request.args.get('daynum')
        start_num = float(request.args.get('start_num'))
        end_num = float(request.args.get('end_num'))
        start_time = display_time(start_num)
        end_time = display_time(end_num)
        return render_template('delete_interval.html', username=username, start_time=start_time, start_num=start_num,
                               end_time=end_time, end_num=end_num, dayname=dayname, daynum=daynum, error=None)
    else:
        username = request.form.get('username')
        dayname = request.form.get('dayname')
        daynum = request.form.get('daynum')
        start_num = float(request.form.get('start_num'))
        end_num = float(request.form.get('end_num'))
        start_time = display_time(start_num)
        end_time = display_time(end_num)

        if not check_sys_password(request):
            return render_template('delete_interval.html', username=username, start_time=start_time,
                                   start_num=start_num,
                                   end_time=end_time, end_num=end_num, dayname=dayname, daynum=daynum,
                                   error="Incorrect password")
        with connect_db() as conn:
            real_day_num = int(daynum)
            print "SELECT * FROM intervals WHERE (kids_name like %s AND day=%s AND turn_on=%s AND turn_off=%s)" % (
            username, real_day_num, start_num, end_num)

            print conn.cursor().execute(
                "SELECT * FROM intervals WHERE (kids_name like ? AND day=? AND ABS (turn_on - ?) < .05  AND ABS (turn_off-?) < .05)",
                (username, real_day_num, start_num, end_num)).fetchall()

            conn.cursor().execute(
                "DELETE FROM intervals WHERE (kids_name like ? AND day=? AND ABS (turn_on - ?) < .05  AND ABS (turn_off-?) < .05)",
                (username, real_day_num, start_num, end_num))

        flash('removed interval for %s' % username)
        return redirect(url_for('get_schedule', username=username))


@app.route('/update')
def update():
    user = manager._kid or "logged out"
    state = "ON" if manager.state() else "OFF"
    interval = current_interval(manager._kid)
    remaining = int(min(interval.balance, interval.remaining) + .5)
    if remaining > 60:
        display = "{} hours {} minutes".format(int(remaining / 60.0), remaining % 60)
    else:
        display = "{} minutes".format(remaining)
    clock = time.strftime("%I:%M %p")
    return jsonify(user=user, state=state, remaining=display, time=clock, minutes=remaining)


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
        app.run(host=('0.0.0.0'), use_reloader=False)
