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
    return "Hello world"

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
        if request.form['username'] != app.config['USERNAME']:
            error = 'Invalid username'
        elif request.form['password'] != app.config['PASSWORD']:
            error = 'Invalid password'
        else:
            session['logged_in'] = True
            flash('You were logged in')
            return redirect(url_for('show_entries'))
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out')
    return redirect(url_for('show_entries'))


@app.route('/check')
def check():
    results = [allowed_now(k) for k in ('Nicky', 'Helen', 'Daddy', 'Al')]
    return "<br/>".join([str(r) for r in results])


if __name__ == '__main__':
    if sys.argv[-1] == '--setup':
        init_db(app)
        raise SystemExit(0)

    app.run()
