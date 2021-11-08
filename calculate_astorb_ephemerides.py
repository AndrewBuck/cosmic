from django.conf import settings
from datetime import datetime, timedelta, timezone

import django
import os
import sys
import pytz

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from django.utils import timezone

from cosmicapp.models import *
from cosmicapp.tasks import *

currentTime = timezone.now()
startTime = dateparser.parse(str(currentTime.year) + "-01-01")
endTime = dateparser.parse(str(currentTime.year+1) + "-01-01")
timeTolerance = CosmicVariable.getVariable('asteroidEphemerideTimeTolerance')
tolerance = CosmicVariable.getVariable('asteroidEphemerideTolerance')
clearTable = True

if len(sys.argv) > 1:
    startTime = dateparser.parse(sys.argv[1] + 'UTC')

if len(sys.argv) > 2:
    endTime = dateparser.parse(sys.argv[2] + 'UTC')

if len(sys.argv) > 3:
    timeTolerance = float(sys.argv[3])

if len(sys.argv) > 4:
    tolerance = float(sys.argv[4])

if len(sys.argv) > 5:
    if sys.argv[5].lower() == 'true':
        clearTable = True
    else:
        clearTable = False

print('\nCalculating asteroid ephemerides from {} to {}\nwith a max time step of {} days\nand a max position step of {} degrees.\n\nClear table: {}\n\n'.format(startTime, endTime, timeTolerance, tolerance, clearTable))
sys.stdout.flush()

#TODO: Take arguments for dates, etc, from command line.
result = computeAsteroidEphemerides(startTime, endTime, clearTable)

print("Result is " + str(result))

