import power
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
import sys
from db import connect_db, init_db, display_time, current_interval, add_credits
import time

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
    remaining = int(min(interval.balance, interval.remaining))
    clock = time.strftime("%I:%M %p")
    news = dict(user=user, state=state, remaining=remaining, time=clock)
    if state == "ON":
        flash("tv is on")
    return render_template('main.html', news=news)


@app.route('/history')
def show_history():
    cur = g.db.execute('SELECT time, kids_name, event FROM history ORDER BY time DESC LIMIT 100')
    entries = [dict(time=row[0][5:-3], kid=row[1], msg=row[2]) for row in cur.fetchall()]
    return render_template('history.html', entries=entries)


@app.route('/kids')
def show_kids():
    cur = g.db.execute('select name, balance, cap, replenished from kids')
    entries = [dict(kid=row[0], balance=row[1], cap=row[2], replenished=row[3]) for row in cur.fetchall()]
    return render_template('show_kids.html', kids=entries)


@app.route('/intervals')
def show_intervals():
    cur = g.db.execute('select kids_name, day, turn_on, turn_off from intervals order by kids_name, day')
    day_names = 'Sun Mon Tues Weds Thur Fr Sat'.split()

    def row_fmt(row):
        return {
            'kid': row[0],
            'day': day_names[row[1] - 1],
            'on': display_time(row[2]),
            'off': display_time(row[3])
        }

    entries = [row_fmt(row) for row in cur.fetchall()]
    return render_template('show_intervals.html', entries=entries)


@app.route('/add', methods=['POST'])
def add_entry():
    if not session.get('logged_in'):
        abort(401)
    g.db.execute('insert into entries (title, text) values (?, ?)',
                 [request.form['title'], request.form['text']])
    g.db.commit()
    flash('New entry was successfully posted')
    return redirect(url_for('show_entries'))


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
        pass
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


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    manager.set_user(None)
    flash('You were logged out')
    return redirect(url_for('front_page'))


@app.route('/check')
def check():
    results = dict()
    for k in ('Nicky', 'Helen', 'Daddy', 'Al'):
        interval = current_interval(k)
        results[k] = interval
    return render_template('checks.html', entries=results)


if __name__ == '__main__':
    if sys.argv[-1] == '--setup':
        init_db(app)
        raise SystemExit(0)
    else:
        print "starting"
        manager = PowerManager.manager(app)
        manager.monitor()
        app.run(host=('0.0.0.0'))
