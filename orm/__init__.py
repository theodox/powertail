__author__ = 'stevet'
import logging
LOGGING = logging.getLogger('powertail')
LOGGING.addHandler(logging.StreamHandler())
LOGGING.setLevel(1)