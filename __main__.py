import sys
import time
from collections import OrderedDict
import datetime

from flask import Flask, request, session, g, redirect, url_for, render_template, flash, jsonify

from db import connect_db, init_db, display_time, current_interval, add_credits, time_fmt, add_temporary, deduct, \
    clear_temporary
from orm.model import User, PEEWEE, setup
from orm.server import PowerServer




# configuration

DEBUG = True
SECRET_KEY = 'a;lfsh92why'
USERNAME = 'admin'
PASSWORD = 'default'
from datetime import timedelta

app = Flask(__name__)
app.config.from_object(__name__)
app.permanent_session_lifetime = timedelta(hours=5)
from  power import PowerManager

manager = None

# TEST CODE
setup()
sysad = User.create(name='system', password='system', is_admin=True)
sysad.save()
al = User.create(name='al', password='test', picture='stud')
al.save()

server = PowerServer(PEEWEE)


def check_sys_password(request):
    pwd = request.form['password']
    return server.validate_user('system', pwd)


@app.before_request
def before_request():
    PEEWEE.connect()
    _user_query = User.select().order_by(User.name)
    _user_pics = [(u.name, u.picture) for u in _user_query]
    g.logins = OrderedDict(_user_pics)
    server.poll()  ##>>>> TEST CODE REMOVE

    g.server_status = server.status
    g.minutes_remaining = server.status.time_left.seconds / 60.0
    g.shutdown_time = server.status.off_time.strftime("%I:%M %p")

    g.active_user = None
    if server.active_user is not None:
        g.active_user = server.active_user.name

    g.g_time = time.strftime("%I:%M %p")


@app.teardown_request
def teardown_request(exception):
    PEEWEE.close()



@app.route('/')
def front_page():
    news = []

    user = g.active_user or "logged out"
    state = "ON" if g.server_status.on  else "OFF"
    remaining = format_remaining_time(g.minutes_remaining)
    off_time = g.server_status.off_time

    clock = time.strftime("%I:%M %p")
    news = OrderedDict(user=user, state=state, remaining=remaining, time=clock, off_time = off_time)
    if state == "ON":
        flash("tv is on")
    return render_template('main.html', news=news)


@app.route('/history')
def show_history():
    entries = server.history()
    return render_template('history.html', entries=entries)


@app.route('/users')
def users():

    entries = server.users()
    return render_template('users.html', kids=entries)


@app.route('/extend', methods=['GET', 'POST'])
def extend():
    error = None
    if request.method == 'GET':
        return render_template('extend.html', error=error)
    if request.method == 'POST':

        valid, reason = check_sys_password(request)
        if not valid:
            error = reason
            return render_template('extend.html', error=error)

        extra_minutes = int(request.form['amount'])
        server.add_temporary(extra_minutes)
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


'''
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
'''


@app.route('/direct/')
@app.route('/direct/<username>', methods=['GET', 'POST'])
def direct(username=None):
    error = None
    if request.method == 'POST':
        name = username
        pwd = request.form['password']

        valid, reason = server.validate_user(name, pwd)

        if valid:
            server.set_user(name)
            session['logged_in'] = True
            session['username'] = name
            manager.set_user(name)
            flash('%s logged in', name)
            return redirect(url_for('front_page'))
        else:
            error = reason
    return render_template('login_direct.html', error=error, username=username)


@app.route('/change_password/')
@app.route('/change_password/<username>', methods=['GET', 'POST'])
def change_pwd(username):
    error = None
    if request.method == 'POST':
        name = username
        pwd = request.form.get('old_password', 'no old password')
        new_1 = request.form.get('new_password_1', 'no new pwd1')
        new_2 = request.form.get('new_password_2', 'no new pwd2')

        if new_1 != new_2:
            error = "New passwords do not match"
            return render_template('change_password.html', error=error, username=name)

        with connect_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name, password FROM kids WHERE name = ?", (name,))
            msg = username
            results = cur.fetchall()
            if results[0][1] != pwd:
                cur.execute("SELECT name, password FROM kids WHERE name = 'System'", tuple())
                results = cur.fetchall()
                if results[0][1] != pwd:
                    error = "Invalid password"
                    return render_template('change_password.html', error=error, username=username)
                else:
                    msg = 'System user '

            cur.execute('UPDATE kids set password = ? WHERE name = ?', (new_1, username))
            cur.execute("INSERT INTO history (kids_name, event) VALUES (?,?)",
                        (msg, 'password changed for %s' % username))
            flash('password changed for %s' % username)
            return redirect(url_for('get_schedule', username=username))

    return render_template('change_password.html', error=error, username=username)


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
    return render_template('schedule.html', cap=cap, entries=entries, debit=debit, username=username, credits=repl,
                           balance=current.balance)


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
    remaining = g.minutes_remaining
    display = format_remaining_time(remaining)
    clock = time.strftime("%I:%M %p")
    return jsonify(user=user, state=state, remaining=display, time=clock, minutes=remaining)


def format_remaining_time(remaining):
    if remaining > 60:
        display = "{} hours {} minutes".format(int(remaining / 60.0), remaining % 60)
    else:
        display = "{} minutes".format(remaining)
    return display


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username')
    server.unset_user('logged out by user')
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
        app.run(host=('0.0.0.0'), port=5005, use_reloader=False)
