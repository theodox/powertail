__author__ = 'stevet'

from threading import Lock
PIN = 16   #pin number for the GPIO board

class gpio_proxy(object):
    OUT = 1
    BOARD = 'board'

    def setup(self, pin, val):
        print 'pretending to set pin %i to %s' % (pin, val)

    def output(self, pin, val):
        print 'pretending to set pin %i to %s' % (pin, val)

    def setmode(self, mode):
        print 'pretending to set mode to "%s"' % mode


try:
    import RPi.GPIO as gpio
except ImportError:
    gpio = gpio_proxy()

# --- initializer ------
gpio.setmode(gpio.BOARD)
gpio.setup(PIN, gpio.OUT)
# ----------------------


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
            gpio.output(PIN, self._internal_state)
        return self._internal_state
