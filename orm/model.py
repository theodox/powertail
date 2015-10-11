from datetime import datetime, time

from peewee import Model, CharField, FloatField, DateTimeField, BooleanField, ForeignKeyField, IntegerField, Check, \
    TimeField, TextField, SqliteDatabase

__author__ = 'stevet'

CASCADE = 'cascade'
PEEWEE = SqliteDatabase('powertail_2.db')

import logging

LOGGING = logging.getLogger('powertail')


class PowertailMeta(Model):
    class Meta:
        database = PEEWEE


class User(PowertailMeta):
    name = CharField(unique=True)
    password = CharField(null=False)
    balance = FloatField(default=10.0)
    cap = FloatField(default=60, constraints=[Check('cap >= 0')])
    is_admin = BooleanField(default=False)
    last_login = DateTimeField(default=datetime.now)
    picture = CharField(default="porp")

    def __hash__(self):
        return hash(self.name)


class Replenish(PowertailMeta):
    user = ForeignKeyField(User, related_name='updates', on_delete=CASCADE)
    upcoming = DateTimeField(null=False)  # time of next refill
    rollover = IntegerField(default=7)  # time in days between refills
    amount = FloatField()


class Interval(PowertailMeta):
    user = ForeignKeyField(User, related_name='intervals', on_delete=CASCADE)
    day = IntegerField(constraints=[Check('day >= 0 and day < 7')])
    start = TimeField()
    end = TimeField(constraints=[Check('end > start')])
    expires = DateTimeField(null=True)


class Lockout(PowertailMeta):
    day = IntegerField(constraints=[Check('day >= 0 and day < 7')], null=False)
    start = TimeField()
    end = TimeField(constraints=[Check('end > start')])
    expires = DateTimeField(default=datetime(2099, 12, 31))


class Borrowed(PowertailMeta):
    user = ForeignKeyField(User, related_name='borrowings', on_delete=CASCADE)
    expires = DateTimeField(default=datetime(2000, 01, 01))


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

    sysad = User.create(name='system', password='1ipschitz', is_admin=True)
    sysad.save()

    helen = User.create(name='helen', password='helent2', picture='flower')
    helen.save()

    al = User.create(name='al', password='alt2', cap=120, picture='stud')
    al.save()

    nicky = User.create(name='nicky', password='nickyt2', picture='swimmer')
    nicky.save()

    daddy = User.create(name='daddy', password='mommy', cap=180, picture='goggles', isadmin=True)
    daddy.save()

    for r in range(7):

        for u in (helen, daddy, al, nicky):
            new_interval = Interval.create(user=u, day=r, start=time(9, 0), end=time(20, 0))
            new_interval.save()

    backdate = datetime.now()
    backdate = backdate.replace(hour=0, minute=1)

    for u in (helen, nicky):
        repl = Replenish.create(user=u, upcoming=backdate, amount=30, rollover=1)
        repl.save()

    for u in (al, daddy):
        repl = Replenish.create(user=u, upcoming=backdate, amount=60, rollover=1)
        repl.save()

    print "setup completed"
