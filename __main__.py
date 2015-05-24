import power
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
import sys
from db import connect_db, init_db, display_time, allowed_now

# configuration

DEBUG = True
SECRET_KEY = 'development key'
USERNAME = 'admin'
PASSWORD = 'default'

app = Flask(__name__)
app.config.from_object(__name__)
# todo: the above can be a separate file: see  http://flask.pocoo.org/docs/0.10/tutorial/setup/#tutorial-setup

from  power import  PowerManager
manager = None

@app.before_request
def before_request():
    g.db = connect_db()


@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

@app.route('/')
def temp():
    news = []
    while not manager.queue.empty():
        news.append(str(manager.queue.get()))

    news.append("loaded")
    news.append(manager._kid or "logged out")
    news.append(str(manager.state()))
    news.append("%i minutes" % int(manager.get_remaining() * 60))
    return render_template('main.html', news = news)
    return "<br/>".join(news)

@app.route('/kids')
def show_kids():
    cur = g.db.execute('select name, balance from kids')
    entries = [dict(kid=row[0], balance=row[1]) for row in cur.fetchall()]
    return render_template('show_kids.html', kids=entries)


@app.route('/intervals')
def show_intervals():
    cur = g.db.execute('select kids_name, day, turn_on, turn_off from intervals order by kids_name, day')
    def row_fmt (row):
        return {
            'kid': row[0],
            'day': row[1],
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
            cur.execute("SELECT name, password FROM kids WHERE name like ?", (name ,))
            results = cur.fetchall()
            if len(results) == 0:
                error = "Invalid username"
            elif results[0][1] != pwd:
                error = "Invalid password"
            else:
                session['logged_in'] = True
                manager.set_user (name)
                flash('You were logged in')
                return redirect(url_for('temp'))
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    manager.set_user(None)
    flash('You were logged out')
    return redirect(url_for('temp'))


@app.route('/check')
def check():
    results = [allowed_now(k) for k in ('Nicky', 'Helen', 'Daddy', 'Al')]
    return "<br/>".join([str(r) for r in results])


if __name__ == '__main__':
    if sys.argv[-1] == '--setup':
        init_db(app)
        raise SystemExit(0)
    else:
        print "starting"
        manager = PowerManager.manager(app)
        manager.monitor()
        app.run()
