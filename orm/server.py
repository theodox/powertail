__author__ = 'stevet'
from time import sleep
from datetime import timedelta
from collections import namedtuple, OrderedDict
import threading

from power import PowerTail
from orm.model import *

PowerCheck = namedtuple('powercheck', 'on message balance time_left off_time')

from peewee import SqliteDatabase

CASCADE = 'cascade'
PEEWEE = SqliteDatabase('powertail_2.db')


def time_difference(time1, time2):
    first = datetime.combine(datetime.today(), time1)
    second = datetime.combine(datetime.today(), time2)
    return first - second

_DAY_NAMES =  dict(enumerate('Mon. Tue. Wed. Th. Fri. Sat. Sun.'.split()))

class PowerServer(object):
    def __init__(self, peewee_db, interval=12.0):
        self.interval = interval
        self.database = peewee_db
        self._power = PowerTail()
        self._alive = False
        self._system = User.select().where(User.name % "system" and User.is_admin == True).get()
        self._user = None
        self._last_check = None
        self._status = PowerCheck(0, 'starting', -1, timedelta(), datetime.now())
        self._lock = threading.RLock()

    @property
    def status(self):
        with self._lock:
            return self._status

    @property
    def active_user(self):
        with self._lock:
            return self._user

    def set_user(self, user_name):
        with self._lock:
            if self._user is not None:
                self.unset_user()
            with self.database.atomic():
                try:
                    self._user = User.select().where(User.name % user_name).get()
                    self.log('logged in', user=self._user)
                    return 1
                except:
                    self.log('unable to log in %s' % user_name)
                    return 0

    def unset_user(self, message="logged out"):
        with self._lock:
            self.log(message, user=self._user)
            self._user = None

    @PEEWEE.atomic()
    def set_cap(self, user, amount):
        user_object = User.select().where((User.name == user)).get()
        user_object.cap = amount
        user_object.save()


    @PEEWEE.atomic()
    def log(self, message, user=None):
        user = user or self._system
        msg = History.create(user=user, message=message)
        msg.save()
        LOGGING.info(message)

    @PEEWEE.atomic()
    def validate_user(self, user, password):
        """
        return a tuple True/False, message.  True is a valid login, false is not, message explains why
        """
        try:
            user_object = User.select().where((User.name == user)).get()
            if password == user_object.password:
                return True, ""
            return False, "incorrect password"
        except User.DoesNotExist:
            return False, "incorrect user name %s" % user

    def check(self):
        """
        check the database for the to see if the status is on and if so, how much time is left
        """
        # replenish if needed
        self.replenish()


        # delete any expired temporary lockouts or intervals
        self.clear_old_lockouts()
        self.clear_old_intervals()

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
            return -1, "Not logged in", 0, timedelta(seconds=0), self._last_check

        # re-get the user in case server balance was edited
        with PEEWEE.atomic():
            self._user = User.select().where(User.name == self._user.name).get()

        # locked out?
        lockouts = self.get_current_lockouts(current_time, today)
        if lockouts:
            self.unset_user("logged off: locked out")
            return lockouts

        # no allowed block for this user?
        intervals = self.get_current_intervals(current_time, today)
        if not intervals:
            self.unset_user("logged off: no interval")
            return 0, "no interval", 0, timedelta(seconds=0), self._last_check

        # update balance, calculate shut down time
        balance = self.update_balance(elapsed)

        if balance < 0:
            self.unset_user("logged off: out of time")
            return 0, "out of time", 0, timedelta(seconds=0), self._last_check

        time_to_shutdown = self.get_remaining_time(current_time, intervals, today)
        shutdown_delta = min(balance, time_to_shutdown)
        shutdown_delta = timedelta(seconds=shutdown_delta * 60.0)
        shutdown_time = now_dt + shutdown_delta

        return 1, "logged in", balance, shutdown_delta, shutdown_time

    @PEEWEE.atomic()
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

    @PEEWEE.atomic()
    def clear_old_lockouts(self):
        grace = timedelta(minutes=5)
        expiration = datetime.now() - grace
        old_lockouts = Lockout.delete().where((Lockout.expires < expiration))
        old_lockouts.execute()

    @PEEWEE.atomic()
    def clear_old_intervals(self):
        grace = timedelta(minutes=5)
        expiration = datetime.now() - grace
        expiration = Interval.delete().where((Lockout.expires >> None) & (Lockout.expires < expiration))
        expiration.execute()

    @PEEWEE.atomic()
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
        remaining_in_interval = round(.5 + time_difference(current_interval.end, current_time).seconds / 60.0, 0)
        return remaining_in_interval

    @PEEWEE.atomic()
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
        remaining = time_difference(active_lockout.end, current_time)
        return 0, "locked out", -1, remaining, active_lockout.end

    @PEEWEE.atomic()
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

    @PEEWEE.atomic()
    def update_balance(self, elapsed):
        """
        update the user's balance to reflect elapsed time
        """
        balance = self._user.balance - elapsed
        balance = round(balance, 2)
        balance = max(balance, -1) # runtime deduction won't go below -1
        self._user.balance = balance
        self._user.save()
        return balance

    @PEEWEE.atomic()
    def replenish(self):
        tonight = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0)
        to_be_replenished = Replenish.select().where(Replenish.upcoming < tonight).join(User)

        for r in to_be_replenished:
            # if there are bonus minutes, don't drop to cap
            # but don't go past either
            if r.user.balance < r.user.cap:
                r.user.balance += r.amount
                r.user.balance = min(r.user.balance, r.user.cap)
                r.user.save()
            r.upcoming = r.upcoming + timedelta(days=r.rollover)
            r.save()

    @PEEWEE.atomic()
    def gift_time(self, user, amount):
        _u = User.select().where(User.name == user).get()
        _u.balance = _u.balance + amount
        _u.save()
        if amount > 0:
            self.log("added %s minutes to %s" % (amount, user))
        else:
            self.log("deducted %s minutes from %s" % (amount, user))

    @PEEWEE.atomic()
    def add_temporary(self, minutes):
        now = datetime.now()
        expires = now + timedelta(minutes=minutes)
        new_time = FreeTime.create(expires=expires)
        new_time.save()
        self.log('free time until {0}:{1}'.format(expires.hour, expires.minute))
        return new_time

    @PEEWEE.atomic()
    def history(self, limit=100):
        return History.select().limit(limit).order_by(History.time.desc())

    @PEEWEE.atomic()
    def users(self):
        user_data = tuple(User.select().order_by(User.name))
        results = OrderedDict()
        for u in user_data:
            results[u] = self.user_replenish(u.name)
        return results

    @PEEWEE.atomic()
    def user_schedule(self, user_name):
        u = User.select().where(User.name == user_name).get()
        intervals = Interval.select().where(Interval.user == u).order_by(Interval.day, Interval.start)
        return tuple(intervals)

    @PEEWEE.atomic()
    def user_replenish(self, user_name):
        u = User.select().where(User.name == user_name).get()
        updates = Replenish.select().where(Replenish.user == u)
        return tuple(i for i in updates)

    @PEEWEE.atomic()
    def day_schedule(self, daynumber):
        active_intervals = Interval.select().where((Interval.day == daynumber)).order_by(Interval.user, Interval.start)
        result = OrderedDict((i.user, []) for i in active_intervals)
        for k in active_intervals:
            result[k.user].append(k)
        return result

    @PEEWEE.atomic()
    def refresh(self):
        self._status = PowerCheck(*self.check())

    @PEEWEE.atomic()
    def add_interval(self, user_name, day, start, end, expires=None):
        u = User.select().where(User.name == user_name).get()
        i = Interval.create(user=u, start=start, end=end, day=day, expires=expires)
        i.save()
        self.refresh()
        self.log("Added new interval for {0}: day {1}, start {2}, end {3}".format(user_name, day, start, end))

    @PEEWEE.atomic()
    def clear_free_time(self):
        FreeTime.delete().execute()
        self.log("Free time cleared")

    @PEEWEE.atomic()
    def remove_interval(self, interval):
        interval.delete()
        self.log("Interval deleted for %s " % interval.user.name)

    @PEEWEE.atomic()
    def edit_interval(self, interval, new_start, new_end):
        interval.update(start=new_start, end=new_end)
        interval.save()

    @PEEWEE.atomic()
    def add_replenish(self, user_name, day=0, frequency=7, amount=60):
        u = User.select().where(User.name == user_name).get()
        r = Replenish.create(user=u, upcoming=datetime.now(),
                             amount=amount, rollover=frequency)
        today = datetime.today().weekday()
        if day < today:
            day += 7
        day_delta = (day - today) * 24
        r.upcoming = r.upcoming + timedelta(hours=day_delta)
        r.save()
        self.log("Will replenish %s every % days starting %s" %
                 (user_name, frequency, _DAY_NAMES[day % 7]))

    @PEEWEE.atomic()
    def get_replenish(self, id):
        return Replenish.select().where(Replenish.id == id).get()

    @PEEWEE.atomic()
    def delete_replenish(self, id):
        Replenish.delete().where(Replenish.id == id).execute()
        self.log("replenish %i deleted" % id)

    def poll(self):
        """
        Update loop
        """
        while self._alive:
            self._status = PowerCheck(*self.check())
            if self._status.on > 0:
                self._power.on()
            else:
                self._power.off()

            LOGGING.info(self._status)
            sleep(self.interval)
        self.log("server shutdown")

    def start(self):
        self._alive = True
        worker_thread = threading.Thread(None, target=self.poll)
        worker_thread.daemon = True
        worker_thread.start()

    def stop(self):
        self._alive = False
