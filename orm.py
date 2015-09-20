__author__ = 'stevet'
from time import sleep
from datetime import datetime, time
import logging
from collections import namedtuple

PowerCheck = namedtuple('powercheck', 'on message remaining')

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
    end = TimeField()


class Lockout(PowertailMeta):
    day = IntegerField(constraints=[Check('day > 0 and day < 7')], null=False)
    start = DateTimeField()
    end = DateTimeField()


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

    system = User.create(name='system', password='unset', is_admin=True)
    al = User.create(name='al', password='al', balance=10.0)
    system.save()
    al.save()
    test = Interval.create(user=al, start=time(17, 10), end=time(19, 15), day=5)
    test.save()


setup()


class PowerServer(object):
    def __init__(self, peewee_db):
        self.database = peewee_db
        self._system = User.select().where(User.name % "system" and User.is_admin == True).get()
        self._user = None
        self._last_check = None

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

    def logout(self):
        self.log('logged out', user=self._user)
        self._user = None

    def log(self, message, user=None):
        user = user or self._system
        with self.database.atomic():
            msg = History.create(user=user, message=message)
            msg.save()
            LOGGING.info(message)

    def check(self):
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
            return -1, "Not logged in", -1

        lockouts = [i for i in Lockout.select().where(
            Lockout.day == today and Lockout.start < current_time and Lockout.end > current_time)]
        if lockouts:
            return 0, "Locked Out", -1

        intervals = [i for i in self._user.intervals.select().where(
            Interval.day == today and Interval.start < current_time and Interval.end > current_time)]
        if not intervals:
            self.logout()
            return 0, "No interval", -1

        balance = self._user.balance - elapsed
        balance = round(balance, 2)
        balance = max(balance, 0)
        self._user.balance = balance
        self._user.save()

        current_interval = intervals[0]
        remaining_in_interval = (current_interval.end.minute - current_time.minute) + \
                                ((current_interval.end.hour - current_time.hour) * 60)

        return 1, "logged in", min(balance, remaining_in_interval)


xxx = PowerServer(PEEWEE)
xxx.login('al')
for n in range(10):
    print xxx.check()
    sleep(5)
xxx.logout()
xxx.login('dummy')
print [(i.message, i.user.name) for i in History.select().order_by(History.time)]
print xxx.check()
