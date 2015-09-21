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


def same_day_delta(time1, time2):
    first = datetime.combine(datetime.today(), time1)
    second = datetime.combine(datetime.today(), time2)
    return first - second


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
    expires = DateTimeField(default=datetime(2099, 12, 31))


class FreeTime(PowertailMeta):
    expires = DateTimeField(null=True)


class History(PowertailMeta):
    user = ForeignKeyField(User, related_name='actions', on_delete=CASCADE, index=True)
    time = DateTimeField(default=datetime.now)
    message = TextField()


_TABLES = [User, Replenish, Interval, Lockout, History, FreeTime]


def setup():
    PEEWEE.connect()
    for t in _TABLES:
        try:
            PEEWEE.drop_table(t)
        except:
            pass
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
        # delete any expired temporary lockouts
        self.clear_old_lockouts()

        now_dt = datetime.now()
        if self._last_check is None:
            self._last_check = datetime.now()
            elapsed = 0.0
        else:
            elapsed = (now_dt - self._last_check).seconds / 60.0
            self._last_check = datetime.now()
        today = now_dt.weekday()
        current_time = now_dt.time()

        # in a temporary interval? return remaining time
        temp = self.free_time()
        if temp:
            return temp

        # not logged in?
        if self._user is None:
            return -1, "Not logged in", -1, -1, -1

        # locked out?
        lockouts = self.get_current_lockouts(current_time, today)
        if lockouts:
            self.logout("logged off: locked out")
            return lockouts

        # no allowed block for this user?
        intervals = self.get_current_intervals(current_time, today)
        if not intervals:
            self.logout("logged off: no interval")
            return 0, "no interval", -1, -1, -1

        # update balance, calculate shut down time
        balance = self.update_balance(elapsed)
        time_to_shutdown = self.get_remaining_time(current_time, intervals, today)
        shutdown_delta = min(balance, time_to_shutdown)
        shutdown_delta = timedelta(seconds=shutdown_delta * 60.0)
        shutdown_time = now_dt + shutdown_delta

        return 1, "logged in", balance, shutdown_delta, shutdown_time

    def free_time(self):
        """
        delete expired free time, return a free time result if there is an active free time block
        """
        grace = timedelta(seconds=10)
        expiration = datetime.now() - grace
        delete_expired = FreeTime.delete().where((FreeTime.expires < expiration))
        delete_expired.execute()
        try:
            override = FreeTime.select().get()
            time_left = override.expires - datetime.now()
            return 1, "temporary", -1, time_left, override.expires
        except:
            return None

    def clear_old_lockouts(self):
        grace = timedelta(minutes=5)
        expiration = datetime.now() - grace
        old_lockouts = Lockout.delete().where((Lockout.expires < expiration))
        old_lockouts.execute()

    def get_remaining_time(self, current_time, intervals, today):
        """
        return the number of minutes left in the current interval.  If there's a lockout coming before the end of the interval, return the time until then
        """
        current_interval = intervals[0]
        try:
            possible_lockouts = Lockout.select().where(
                (Lockout.day == today) & (Lockout.start < current_interval.end)).get()
            current_interval.end = possible_lockouts.start
            # this model data is NOT SAVED, it's just used to calculate remaining time
        except:
            # no intervening lockouts
            pass
        remaining_in_interval = round(.5 + same_day_delta(current_interval.end, current_time).seconds / 60.0, 0)
        return remaining_in_interval

    def get_current_lockouts(self, current_time, today):
        """
        return the latest of any active lockouts
        """
        lockout_query = Lockout.select().where(
            (Lockout.day == today) &
            (Lockout.start < current_time) &
            (Lockout.end > current_time)).order_by(Lockout.end.desc())
        lockouts = tuple((i for i in lockout_query))
        if not lockouts:
            return False

        active_lockout = lockouts[0]
        remaining = same_day_delta(active_lockout.end, current_time)
        return 0, "locked out", -1, remaining, active_lockout.end

    def get_current_intervals(self, current_time, today):
        """
        Get any intervals for the current user which include today
        """
        intervals_query = self._user.intervals.select().where(
            (Interval.day == today) &
            (Interval.start < current_time) &
            (Interval.end > current_time))
        intervals = tuple((i for i in intervals_query))
        return intervals

    def update_balance(self, elapsed):
        """
        update the user's balance to reflect elapsed time
        """
        balance = self._user.balance - elapsed
        balance = round(balance, 2)
        balance = max(balance, 0)
        self._user.balance = balance
        self._user.save()
        return balance

    def poll(self):
        """
        Update loop
        """
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


from unittest import TestCase


class TestORM(TestCase):
    TEST_USER = 'al'

    def test_login(self):
        start_time = datetime.now() - timedelta(minutes=1)
        end_time = datetime.now() + timedelta(minutes=6)
        test = Interval.create(user=self.test_user,
                               start=time(start_time.hour, start_time.minute),
                               end=time(end_time.hour, end_time.minute),
                               day=start_time.weekday())
        test.save()
        self.server.login('al')

        result = PowerCheck(*self.server.check())
        assert result.on == 1
        assert result.off_time.hour == end_time.hour and result.off_time.minute == end_time.minute
        assert result.balance == 10.0
        assert round((result.time_left.seconds / 60.0), 2) == 6.0

    def test_no_login(self):
        self.server.login('nicky')
        result = PowerCheck(*self.server.check())
        assert result.on == -1
        assert result.balance == -1
        assert result.off_time == -1
        assert result.time_left == -1

    def test_temporary(self):
        self.server.logout()
        tmp = FreeTime.create(expires=datetime.now() + timedelta(minutes=7))
        tmp.save()
        result = PowerCheck(*self.server.check())
        assert result.on == 1
        assert result.balance == -1
        assert result.off_time == tmp.expires
        assert 420 >= result.time_left.seconds >= 418

        FreeTime.delete().execute()
        assert PowerCheck(*self.server.check()).on == -1

    def test_lockout(self):
        start_time = datetime.now() - timedelta(minutes=1)
        end_time = datetime.now() + timedelta(minutes=6)
        test = Interval.create(user=self.test_user,
                               start=time(start_time.hour, start_time.minute),
                               end=time(end_time.hour, end_time.minute),
                               day=start_time.weekday())
        test.save()
        self.server.login('al')

        result = PowerCheck(*self.server.check())
        assert result.on == 1
        ll = Lockout.create(start=time(start_time.hour, start_time.minute),
                            end=time(end_time.hour, end_time.minute),
                            day=start_time.weekday())
        ll.save()
        result = PowerCheck(*self.server.check())
        assert result.on == 0
        assert result.balance == -1
        # the time left in this calculation is going to vary between 5 and 6 minutes due to rounding.
        assert 359 >= result.time_left.seconds >= 299

    def test_multiple_lockouts(self):
        start_time = datetime.now() - timedelta(minutes=1)
        end_time = datetime.now() + timedelta(minutes=6)
        end_time2 = datetime.now() + timedelta(minutes=2)

        test = Interval.create(user=self.test_user,
                               start=start_time.time(),
                               end=end_time.time(),
                               day=start_time.weekday())
        test.save()
        self.server.login('al')

        result = PowerCheck(*self.server.check())
        assert result.on == 1

        early = Lockout.create(start=start_time.time(),
                               end=end_time2.time(),
                               day=start_time.weekday()
                               )
        early.save()

        ll = Lockout.create(start=start_time.time(),
                            end=end_time.time(),
                            day=start_time.weekday())
        ll.save()
        result = PowerCheck(*self.server.check())
        assert result.on == 0
        assert result.balance == -1
        # should still report the end of the last lockout
        assert 359 >= result.time_left.seconds >= 299

    def test_lockout_clear(self):
        backdate = datetime.now() - timedelta(days=1)
        ll = Lockout.create(day = 1, start = time(0,1), end = time(2,3), expires = backdate)
        ll.save()
        self.server.clear_old_lockouts()
        remainder = [i for i in Lockout.select()]
        assert len(remainder) == 0





    def setUp(self):
        setup()
        PEEWEE.connect()
        system = User.create(name='system', password='unset', is_admin=True)
        self.test_user = User.create(name=self.TEST_USER, password='al', balance=10.0)
        system.save()
        self.test_user.save()
        self.server = PowerServer(PEEWEE)
