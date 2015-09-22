__author__ = 'stevet'

from unittest import TestCase
from datetime import timedelta, date

from orm.server import PowerCheck, PowerServer
from orm.model import *


class TestORM(TestCase):
    TEST_USER = 'al'
    TEST_PWD = 'la'

    def test_login(self):
        start_time = datetime.now() - timedelta(minutes=1)
        end_time = datetime.now() + timedelta(minutes=6)
        test = Interval.create(user=self.test_user,
                               start=time(start_time.hour, start_time.minute),
                               end=time(end_time.hour, end_time.minute),
                               day=start_time.weekday())
        test.save()
        self.server.set_user('al')

        result = PowerCheck(*self.server.check())
        assert result.on == 1
        assert result.off_time.hour == end_time.hour and result.off_time.minute == end_time.minute
        assert result.balance == 10.0
        assert round((result.time_left.seconds / 60.0), 2) == 6.0

    def test_no_login(self):
        self.server.set_user('nicky')
        result = PowerCheck(*self.server.check())
        assert result.on == -1
        assert result.balance == -1
        assert result.off_time == -1
        assert result.time_left == -1

    def test_temporary(self):
        self.server.unset_user()
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
        self.server.set_user('al')

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
        self.server.set_user('al')

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
        ll = Lockout.create(day=1, start=time(0, 1), end=time(2, 3), expires=backdate)
        ll.save()
        self.server.clear_old_lockouts()
        remainder = [i for i in Lockout.select()]
        assert len(remainder) == 0

    def test_replenish_weekly(self):
        test_day = date.today()
        test_hr = time(01, 01)
        test_rollover = datetime.combine(test_day, test_hr)
        al = User.select().where(User.name == 'system').get()
        original_balance = al.balance
        test_repl = Replenish.create(user=al, amount=9, upcoming=test_rollover)
        test_repl.save()
        self.server.replenish()
        repl = Replenish.select().get()
        assert repl.upcoming == test_rollover + timedelta(days=7)
        assert repl.user.balance == original_balance + 9

    def test_replenish_daily(self):
        test_day = date.today()
        test_hr = time(01, 01)
        test_rollover = datetime.combine(test_day, test_hr)
        al = User.select().where(User.name == 'system').get()
        original_balance = al.balance
        test_repl = Replenish.create(user=al, amount=9, upcoming=test_rollover, rollover = 1)
        test_repl.save()
        self.server.replenish()
        repl = Replenish.select().get()
        assert repl.upcoming == test_rollover + timedelta(days=1)
        assert repl.user.balance == original_balance + 9

    def test_validate_user(self):
        test_valid_ok = self.server.validate_user(self.TEST_USER, self.TEST_PWD)
        assert test_valid_ok[0]

    def test_validate_bad_user(self):
        test_valid_ok = self.server.validate_user('ssdsdsfefg', self.TEST_PWD)
        assert not test_valid_ok[0]

    def test_validate_bad_pwd(self):
        test_valid_ok = self.server.validate_user(self.TEST_USER, 'sdsf123')
        assert not test_valid_ok[0]


    def setUp(self):
        setup()
        PEEWEE.connect()
        system = User.create(name='system', password='unset', is_admin=True)
        self.test_user = User.create(name=self.TEST_USER, password=self.TEST_PWD, balance=10.0)
        system.save()
        self.test_user.save()
        self.server = PowerServer(PEEWEE)
