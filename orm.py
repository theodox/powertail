__author__ = 'stevet'
from time import sleep
from datetime import datetime, time, timedelta
import logging
from collections import namedtuple
import threading


PowerCheck = namedtuple('powercheck', 'on message balance time_left off_time')

from peewee import Model, CharField, TimeField, IntegerField, FloatField, DateTimeField, ForeignKeyField, \
    SqliteDatabase, BooleanField, TextField, Check

CASCADE = 'cascade'
PEEWEE = SqliteDatabase('powertail_2.db')
LOGGING = logging.getLogger('powertail')
LOGGING.addHandler(logging.StreamHandler())
LOGGING.setLevel(1)


class PowertailMeta(Model):
    class Meta:
        database = PEEWEE


class User(PowertailMeta):
    name = CharField(unique=True)
    password = CharField(null=False)
    balance = FloatField(default=10.0)
    last_login = DateTimeField(default=datetime.now)
    daily_cap = FloatField(default=60)
    weekly_cap = FloatField(default=-1)
    is_admin = BooleanField(default=False)


class Replenish(PowertailMeta):
    user = ForeignKeyField(User, related_name='updates', on_delete=CASCADE, index=True)
    day = IntegerField()
    amount = FloatField()


class Interval(PowertailMeta):
    user = ForeignKeyField(User, related_name='intervals', on_delete=CASCADE, index=True)
    day = IntegerField(constraints=[Check('day > 0 and day < 7')])
    start = TimeField()
    end = TimeField(constraints=[Check('end > start')])


class Lockout(PowertailMeta):
    day = IntegerField(constraints=[Check('day > 0 and day < 7')], null=False)
    start = TimeField()
    end = TimeField(constraints=[Check('end > start')])


class History(PowertailMeta):
    user = ForeignKeyField(User, related_name='actions', on_delete=CASCADE, index=True)
    time = DateTimeField(default=datetime.now)
    message = TextField()


_TABLES = [User, Replenish, Interval, Lockout, History]


def setup():
    PEEWEE.connect()
    for t in _TABLES:
        PEEWEE.drop_table(t)
        PEEWEE.create_table(t)






class PowerServer(object):
    def __init__(self, peewee_db, interval=30.0):
        self.interval = interval
        self.database = peewee_db
        self._alive = False
        self._system = User.select().where(User.name % "system" and User.is_admin == True).get()
        self._user = None
        self._last_check = None
        self._status = PowerCheck(0, 'starting', -1, timedelta(), datetime.now())

    @property
    def status(self):
        with threading.Lock(self):
            return self._status

    def login(self, user_name):
        if self._user is not None:
            self.logout()
        with self.database.atomic():
            try:
                self._user = User.select().where(User.name % user_name).get()
                self.log('logged in', user=self._user)
                return 1
            except:
                self.log('unable to log in %s' % user_name)
                return 0

    def logout(self, message="logged out"):
        self.log(message, user=self._user)
        self._user = None

    def log(self, message, user=None):
        user = user or self._system
        with self.database.atomic():
            msg = History.create(user=user, message=message)
            msg.save()
            LOGGING.info(message)

    def check(self):
        """
        check the database for the to see if the status is on and if so, how much time is left
        """
        now_dt = datetime.now()
        if self._last_check is None:
            self._last_check = datetime.now()
            elapsed = 0.0
        else:
            elapsed = (now_dt - self._last_check).seconds / 60.0
            self._last_check = datetime.now()
        today = now_dt.weekday()
        current_time = now_dt.time()

        if self._user is None:
            return -1, "Not logged in", -1, -1, -1

        lockouts = self.get_current_lockouts(current_time, today)
        if lockouts:
            self.logout("logged off: locked out")
            return 0, "locked out", -1, -1, -1

        intervals = self.get_current_intervals(current_time, today)
        if not intervals:
            self.logout("logged off: no interval")
            return 0, "no interval", -1, -1, -1

        balance = self.update_balance(elapsed)
        time_to_shutdown = self.get_remaining_time(current_time, intervals, today)

        shutdown_delta = min(balance, time_to_shutdown)
        shutdown_delta = timedelta(minutes=shutdown_delta / 60.0)
        shutdown_time = now_dt + shutdown_delta

        return 1, "logged in", balance, shutdown_delta, shutdown_time

    def get_remaining_time(self, current_time, intervals, today):
        current_interval = intervals[0]
        try:
            possible_lockouts = Lockout.select().where(
                (Lockout.day == today) & (Lockout.start < current_interval.end)).get()
            current_interval.end = possible_lockouts.start
            # this model data is NOT SAVED, it's just used to calculate remaining time
        except:
            # no intervening lockouts
            pass
        remaining_in_interval = (current_interval.end.minute - current_time.minute) + \
                                ((current_interval.end.hour - current_time.hour) * 60)
        return remaining_in_interval

    def update_balance(self, elapsed):
        balance = self._user.balance - elapsed
        balance = round(balance, 2)
        balance = max(balance, 0)
        self._user.balance = balance
        self._user.save()
        return balance

    def get_current_lockouts(self, current_time, today):
        lockout_query = Lockout.select().where(
            (Lockout.day == today) &
            (Lockout.start < current_time) &
            (Lockout.end > current_time))
        lockouts = tuple((i for i in lockout_query))
        return lockouts

    def get_current_intervals(self, current_time, today):
        intervals_query = self._user.intervals.select().where(
            (Interval.day == today) &
            (Interval.start < current_time) &
            (Interval.end > current_time))
        intervals = tuple((i for i in intervals_query))
        return intervals

    def poll(self):
        while self._alive:
            self.check()
            sleep(self.interval)
            LOGGING.info(self._status)
        self.log("server shutdown")

    def start(self):
        self._alive = True
        worker_thread = threading.Thread(None, target=self.poll)
        worker_thread.daemon = True
        worker_thread.start()

    def stop(self):
        self._alive = False

setup()

PEEWEE.connect()
system = User.create(name='system', password='unset', is_admin=True)
al = User.create(name='al', password='al', balance=10.0)
system.save()
al.save()
test = Interval.create(user=al, start=time(17, 10), end=time(22, 15), day=5)
test.save()

test_lockout = Lockout.create(day=5, start=time(20, 20), end=time(21, 00))
test_lockout.save()

xxx = PowerServer(PEEWEE)
xxx.login('al')
for n in range(10):
    print PowerCheck(*xxx.check())
    sleep(5)
xxx.logout()
xxx.login('dummy')
print [(i.message, i.user.name) for i in History.select().order_by(History.time)]
print xxx.check()
