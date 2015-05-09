__author__ = 'stevet'

from threading import Lock


class PowerTail(object):


    def __init__(self):

        self._state = False
        self._internal_state = self._state
        self.lock = Lock(False)

    def state(self):
        with self.lock:
            return _state

    def on(self):
        with self.lock:
            self._state = True
            self.enact()

    def off(self):
        with self.lock:
            self.state = False
            self.enact()

    def enact(self):
        if self._state != self._internal_state:
            print "changing to", self._state
            self._internal_state = self._state
