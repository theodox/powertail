import sys
import time
from collections import OrderedDict
import datetime

from flask import Flask, request, session, g, redirect, url_for, render_template, flash, jsonify

from orm.model import User, PEEWEE, setup, Interval
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

manager = None

# TEST CODE
try:
    server = PowerServer(PEEWEE, 10)
except:
    setup()
    server = PowerServer(PEEWEE, 10)
server.start()


def check_sys_password(request):
    pwd = request.form['password']
    return server.validate_user('system', pwd)


def interpret_html_time(time_str):
    return datetime.datetime.strptime(time_str, "%H:%M").time()


day_names = "Monday Tuesday Wednesday Thursday Friday Saturday Sunday "
DAY_NUMS = OrderedDict()
for num, day in enumerate(day_names.split()):
    DAY_NUMS[day] = num

DAY_NAMES = OrderedDict()
for num, day in enumerate(day_names.split()):
    DAY_NAMES[num] = day


@app.before_request
def before_request():
    PEEWEE.connect()
    _user_query = User.select().where(User.name != 'system').order_by(User.name)
    _user_pics = [(u.name, u.picture) for u in _user_query]
    g.logins = OrderedDict(_user_pics)
    g.server_status = server.status
    g.minutes_remaining = server.status.time_left.seconds / 60.0
    g.shutdown_time = server.status.off_time.strftime("%I:%M %p")
    g.active_user = None
    g.is_admin = False
    if server.active_user is not None:
        g.active_user = server.active_user.name
        g.is_admin = server.active_user.is_admin
    g.g_time = time.strftime("%I:%M %p")


@app.teardown_request
def teardown_request(exception):
    if exception:
        server.log(exception)
    PEEWEE.close()

@app.route('/update')
def update():
    """
    Live update loop
    """
    return jsonify(user=g.active_user,
                   state=g.server_status.on,
                   time=g.g_time,
                   minutes=round(g.minutes_remaining, 0),
                   shutoff=g.server_status.off_time)


@app.route('/')
def front_page():
    return render_template('main.html')


@app.route('/history')
def show_history():
    entries = server.history()
    return render_template('history.html', entries=entries)


@app.route('/users')
def users():
    entries = server.users()
    return render_template('users.html', users=entries)


@app.route('/extend', methods=['GET', 'POST'])
def extend():
    error = None
    if request.method == 'GET':
        return render_template('extend.html', error=error)
    if request.method == 'POST':

        if not check_sys_password(request)[0]:
            error = "Incorrect password"
            return render_template('extend.html', error=error)

        extra_minutes = int(request.form['amount'])
        server.add_temporary(extra_minutes)
        flash("TV will stay on for %s minutes" % extra_minutes)
        server.refresh()
        return redirect(url_for('front_page'))


@app.route('/today')
def today():
    day_num = datetime.datetime.now().weekday()
    intervals = server.day_schedule(day_num)
    return render_template('today.html', entries=intervals)


@app.route('/direct/<username>', methods=['GET', 'POST'])
def direct(username=None):
    error = None
    if request.method == 'GET':
        return render_template('login_direct.html',
                               error=error,
                               username=username)
    if request.method == 'POST':
        name = username
        pwd = request.form['password']

        valid, reason = server.validate_user(name, pwd)

        if not valid:
            error = reason
            return render_template('login_direct.html',
                                   error=error,
                                   username=username)
        else:
            server.set_user(name)
            session['logged_in'] = True
            session['username'] = name
            flash('%s logged in' % name)
            server.refresh()
            return redirect(url_for('front_page'))


@app.route('/change_password/')
@app.route('/change_password/<username>', methods=['GET', 'POST'])
def change_pwd(username):
    error = None
    if request.method == 'POST':
        pwd = request.form.get('old_password', 'no old password')
        new_1 = request.form.get('new_password_1', 'no new pwd1')
        new_2 = request.form.get('new_password_2', 'no new pwd2')

        if new_1 != new_2:
            error = "mismatched"
            return render_template('change_password.html', error=error, username=username)

        user = User.select().where(User.name == username).get()

        if pwd != user.password:
            error = "incorrect"
            return render_template('change_password.html', error=error, username=username)

        user.password = new_1
        user.save()
        flash('password changed for %s' % username)
        return redirect(url_for('get_schedule', username=username))

    return render_template('change_password.html', error=error, username=username)


@app.route('/donate/<username>', methods=['GET', 'POST'])
def donate(username=None):
    error = None

    if request.method == 'GET':
        return render_template('donate.html', error=error, user=username)

    elif request.method == 'POST':

        if not check_sys_password(request)[0]:
            error = "Incorrect password"
            return render_template('donate.html',
                                   error=error,
                                   user=username)

        extra = int(request.form['amount'])
        user = request.form['user']
        server.gift_time(user, extra)
        flash("added %s to %s" % (extra, user))
        server.refresh()
        return redirect(url_for('today'))


@app.route('/debit/<username>', methods=['GET', 'POST'])
def debit(username=None):
    error = None
    if request.method == 'GET':
        return render_template('debit.html', error=error, user=username)

    elif request.method == 'POST':
        if not check_sys_password(request)[0]:
            error = "Incorrect password"
            return render_template('debit.html',
                                   error=error,
                                   user=username)

        deduction = int(request.form['amount'])
        user = request.form['user']
        server.gift_time(user, -1 * deduction)
        flash("deducted %s from %s" % (deduction, user))
        server.refresh()
        return redirect(url_for('today'))


@app.route('/off')
def shutdown():
    server.clear_free_time()
    flash('tv shut down')
    server.refresh()
    if g.active_user:
        return logout()
    else:
        return redirect(url_for('front_page'))


@app.route('/overview')
def overview():
    _users = User.select().order_by(User.name)

    results = OrderedDict([(u, server.user_schedule(u.name)) for u in _users])
    return render_template('overview.html', entries=results)


@app.route('/schedule/<username>')
def get_schedule(username):
    entries = server.user_schedule(username)
    replenish = server.user_replenish(username)
    user = User.select().where((User.name == username)).get()

    return render_template('schedule.html',
                           cap=user.cap,
                           entries=entries,
                           username=username,
                           balance=user.balance,
                           replenish=replenish,
                           daynumbers=DAY_NUMS,
                           daynames=DAY_NAMES,
                           )


@app.route('/create_interval/<username>', methods=['GET', 'POST'])
def create_interval(username):
    error = None

    if request.method == 'GET':
        dayname = request.args.get('dayname')
        daynum = request.args.get('daynum')
        return render_template('add_interval.html',
                               username=username,
                               dayname=dayname,
                               daynum=daynum,
                               start_time="15:00",
                               end_time="18:00",
                               expires=datetime.date.today() + datetime.timedelta(days=1),
                               is_temp=False
                               )
    else:
        username = request.form['username']
        daynum = request.form['daynum']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        expires = request.form['expires']
        is_temp = request.form.get('is_temp') is not None

        if  not check_sys_password(request)[0]:
            error = "password"
            return render_template('add_interval.html',
                                   username=username,
                                   error=error, dayname=request.form['dayname'],
                                   daynum=daynum,
                                   start_time=start_time,
                                   end_time=end_time,
                                   expires=expires,
                                   is_temp=is_temp)

        start_time_obj = interpret_html_time(start_time)
        end_time_obj = interpret_html_time(end_time)

        if end_time_obj <= start_time_obj:
            error = "too_early"
            return render_template('add_interval.html',
                                   username=username,
                                   error=error, dayname=request.form['dayname'],
                                   daynum=daynum,
                                   start_time=start_time,
                                   end_time=end_time,
                                   expires=expires,
                                   is_temp=is_temp)

        exp = None
        if is_temp:
            exp = datetime.datetime.strptime(expires, "%Y-%m-%d").date()

        server.add_interval(username,
                            daynum,
                            start_time_obj,
                            end_time_obj,
                            expires=exp
                            )

        flash('added interval')
        return redirect(url_for('get_schedule', username=username))


@app.route('/remove_interval/<interval>', methods=['GET', 'POST'])
def delete_interval(interval):
    Interval.delete().where(Interval.id == interval).execute()
    user = request.args.get('username')
    return redirect(url_for('get_schedule', username=user))


@app.route('/add_replenish/<username>', methods=['GET', 'POST'])
def add_replenish(username):
    if request.method == 'GET':
        return render_template('add_replenish.html', username=username)

    if not check_sys_password(request)[0]:
        error = "password"
        return render_template('add_replenish.html',
                               username=username,
                               error=error)

    user = request.form['username']
    amount = int(request.form['amount'])
    rollover = int(request.form['update_frequency'])
    day = int(request.form['update_day'])
    server.add_replenish(user, day=day, frequency=rollover, amount=amount)
    flash('updated schedule')
    return redirect(url_for('get_schedule', username=user))


@app.route('/remove_replenish/<repl>', methods=['GET', 'POST'])
def delete_replenish(repl='repl'):
    replenish_object = server.get_replenish(repl)
    user = replenish_object.user.name

    if request.method == 'GET':
        return render_template('remove_replenish.html',
                               user=user,
                               next_day=DAY_NAMES[replenish_object.upcoming.weekday()],
                               repl=repl)

    if not check_sys_password(request)[0]:
        error = "password"
        return render_template('remove_replenish.html',
                               user=user,
                               next_day=DAY_NAMES[replenish_object.upcoming.weekday()],
                               repl=repl,
                               error=error)

    server.delete_replenish(int(repl))
    flash('deleted replenish')
    return redirect(url_for('get_schedule', username=user))

@app.route('/edit_cap/<username>' , methods=['GET', 'POST'])
def edit_cap(username):
    if request.method == 'GET':
        return render_template('edit_cap.html', username=username)

    if  not check_sys_password(request)[0]:
        error = "password"
        return render_template('edit_cap.html',
                               username=username,
                               error=error)
    user = request.form['user']
    amount = int(request.form['new_cap'])
    server.set_cap(user, amount)
    return redirect(url_for('get_schedule', username=user))


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username')
    server.unset_user('logged out by user')
    flash('You were logged out')
    server.refresh()

    return redirect(url_for('front_page'))

# @TODO
# - add/remove/edit user
# - weekday/weekend time add
# -


if __name__ == '__main__':
    if sys.argv[-1] == '--setup':
        setup()
        raise SystemExit(0)
    else:
        print "starting"
        app.run(host=('0.0.0.0'), port=5000, use_reloader=False)
