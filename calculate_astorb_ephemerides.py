from django.conf import settings
from datetime import datetime, timedelta, timezone

import django
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from django.utils import timezone

from cosmicapp.models import *
from cosmicapp.tasks import *

startYear = 2015
endYear = 2019
timeTolerance = 29
tolerance = 10

if len(sys.argv) > 1:
    startYear = int(sys.argv[1])

if len(sys.argv) > 2:
    endYear = int(sys.argv[2])

if len(sys.argv) > 3:
    timeTolerance = int(sys.argv[3])

if len(sys.argv) > 4:
    tolerance = int(sys.argv[4])

print('Calculating asteroid ephemerides from {} to {} with a max time step of {} days and a max position step of {} degrees.'.format(startYear, endYear, timeTolerance, tolerance))
sys.stdout.flush()

#TODO: Take arguments for dates, etc, from command line.
startTime = datetime(2015, 1, 1, tzinfo=timezone.utc)
endTime = datetime(2019, 1, 1, tzinfo=timezone.utc)
timeTolerance = timedelta(days=29)
result = computeAsteroidEphemerides(startTime, endTime, 10, timeTolerance, True)

print("Result is " + str(result))

