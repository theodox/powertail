__author__ = 'stevet'

from threading import Lock
import sqlite3
import time
from threading import Thread, current_thread, RLock
import  db

class gpio_proxy(object):
    OUT = 1

    def setup(self, pin, val ):
        print 'pretending to set pin %i to %s' % (pin, val)

    def output(self, pin, val):
        print 'pretending to set pin %i to %s' % (pin, val)

try:
    import RPi.GPIO as gpio
except ImportError:
    gpio = gpio_proxy()


gpio.setup(12, gpio.OUT)


class PowerTail(object):


    def __init__(self):

        self._state = False
        self._internal_state = self._state
        self.lock = Lock()

    def state(self):
        with self.lock:
            return self._state

    def on(self):
        with self.lock:
            self._state = True
            return self.enact()

    def off(self):
        with self.lock:
            self._state = False
            return self.enact()

    def enact(self):
        if self._state != self._internal_state:
            self._internal_state = self._state
            with db.connect_db() as conn:
                db.log(conn, "System", "POWER SET %s" % self._state)
                gpio.output(12, self._internal_state)
            return self._internal_state
        return None


class PowerManager(object):
    DATABASE = '/tmp/flaskr.db'
    INSTANCE = None

    def __init__(self, app, interval = 1.5):
        self.db = self.DATABASE
        self.tail = PowerTail()
        self.stop = False
        self.lock = RLock()
        self._kid = None
        self.interval = interval
        self.app = app
        self.started  = False
        self._remaining = 0

    def get_remaining(self):
        with self.lock:
            return self._remaining

    def set_remaining(self, r):
        with self.lock:
            self._remaining = r

    def state(self):
        return self.tail.state()

    def set_user(self, kid):
        with self.lock:
            self._kid = kid
        self.app.logger.critical("logged in %s", str(kid))
        with db.connect_db() as conn:
            if kid:
                db.log(conn, kid, "logged in")
            else:
                db.log(conn, "System", "logged out")

    def get_user(self):
        with self.lock:
            return self._kid




    def check(self):
        while not self.stop:
            self.app.logger.debug("(%s): being %s", current_thread(), self.get_user())
            user = self.get_user()
            db.replenish(user)
            interval = db.current_interval(user)

            ok = interval.balance > 0 and interval.remaining > 0
            msg = None
            with db.connect_db() as conn:
                if ok:
                    fraction = self.interval / 60.0
                    db.deduct(user, fraction)
                    msg  = self.tail.on()

                else:
                    msg = self.tail.off()

            time.sleep(self.interval)

        self.tail.off()
        with db.connect_db() as conn:
            conn.log("System", "shutting down")
        self.app.logger.critical("monitor thread stopping")

    def monitor(self):
        if self.started is False:
            self.stop = False
            self.started = True

            ts = Thread(None, self.check)
            ts.setDaemon(True)
            ts.start()
            self.app.logger.critical("(%s) starting monitor thread" % current_thread())
        else:
            self.app.logger.critical("(%s) already running" % current_thread())

    def shutdown(self):
        self.stop = True

    @classmethod
    def manager(cls, app):
        if not cls.INSTANCE:
            cls.INSTANCE = PowerManager(app)
        else:
            cls.INSTANCE.shutdown()
            time.sleep(1)
            print "restarting manager"
            cls.INSTANCE = PowerManager(app)

        return cls.INSTANCE
