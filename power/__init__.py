__author__ = 'stevet'

from threading import Lock


class gpio_proxy(object):
    OUT = 1

    def setup(self, pin, val):
        print 'pretending to set pin %i to %s' % (pin, val)

    def output(self, pin, val):
        print 'pretending to set pin %i to %s' % (pin, val)


try:
    import RPi.GPIO as gpio
except ImportError:
    gpio = gpio_proxy()

gpio.setmode(gpio.BOARD)
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
            gpio.output(12, self._internal_state)
        return self._internal_state
