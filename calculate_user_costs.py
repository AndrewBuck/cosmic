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

if len(sys.argv) > 1:
    startTime = dateparser.parse(sys.argv[1] + 'UTC')

if len(sys.argv) > 2:
    endTime = dateparser.parse(sys.argv[2] + 'UTC')

print('Calculating user costs {} to {}'.format(startTime, endTime))
sys.stdout.flush()

with transaction.atomic():
    processInput = ProcessInput(
        process = 'calculateUserCostTotals',
        requestor = None,
        priority = models.ProcessPriority.getPriorityForProcess("calculateUserCostTotals", "batch"),
        estCostCPU = 10,
        estCostBandwidth = 0,
        estCostStorage = 1000,
        estCostIO = 100000
        )

    processInput.save()
    processInput.addArguments([str(startTime), str(endTime)])

