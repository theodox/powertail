__author__ = 'stevet'

from threading import Lock
import sqlite3
import time
from threading import Thread, current_thread, RLock
from Queue import Queue
import  db

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
            print "changing to", self._state
            self._internal_state = self._state
            return self._internal_state
        return None


class PowerManager(object):
    DATABASE = '/tmp/flaskr.db'
    INSTANCE = None

    def __init__(self, app, interval = 10):
        self.db = self.DATABASE
        self.tail = PowerTail()
        self.stop = False
        self.queue = Queue()
        self.lock = RLock()
        self._kid = None
        self.interval = interval
        self.app = app
        self.started  = False
        self._remaining = 0
        print "manager created"

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


    def get_user(self):
        with self.lock:
            return self._kid



    def check(self):
        while not self.stop:
            self.app.logger.critical("(%s): being %s", current_thread(), self.get_user())
            user = self.get_user()
            ok, reason = db.allowed_now(user)
            result = None

            if ok:

                fraction = self.interval / 60.0
                db.deduct(user, fraction)
                self.set_remaining(db.remaining(user))
                result = self.tail.on()
            else:
                result = self.tail.off()

            if result is not None:
                self.queue.put(result, reason)
                self.app.logger.critical("(%s) %s: %s (%s remaining)" % (current_thread(), result, reason, self.get_remaining()))


            time.sleep(self.interval)

        self.tail.off()
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
