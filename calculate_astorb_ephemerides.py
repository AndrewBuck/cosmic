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

startTime = dateparser.parse('2015 UTC')
endTime = dateparser.parse('2019 UTC')
timeTolerance = CosmicVariable.getVariable('asteroidEphemerideTimeTolerance')
tolerance = CosmicVariable.getVariable('asteroidEphemerideTolerance')
clearTable = True

if len(sys.argv) > 1:
    startTime = dateparser.parse(sys.argv[1] + 'UTC')

if len(sys.argv) > 2:
    endTime = dateparser.parse(sys.argv[2] + 'UTC')

if len(sys.argv) > 5:
    if sys.argv[5].lower() == 'true':
        clearTable = True
    else:
        clearTable = False

print('Calculating asteroid ephemerides from {} to {} with a max time step of {} days and a max position step of {} degrees.  Clear table: {}'.format(startTime, endTime, timeTolerance, tolerance, clearTable))
sys.stdout.flush()

#TODO: Take arguments for dates, etc, from command line.
result = computeAsteroidEphemerides(startTime, endTime, clearTable)

print("Result is " + str(result))

