from django.conf import settings
from datetime import datetime, timedelta, timezone

import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from django.utils import timezone

from cosmicapp.models import *
from cosmicapp.tasks import *

#TODO: Take arguments for dates, etc, from command line.
startTime = datetime(2015, 1, 1, tzinfo=timezone.utc)
endTime = datetime(2019, 1, 1, tzinfo=timezone.utc)
timeTolerance = timedelta(days=29)
result = computeAsteroidEphemerides(startTime, endTime, 10, timeTolerance, True)

print("Result is " + str(result))

