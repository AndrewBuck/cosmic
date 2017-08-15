import os
import time
import django
import celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()


from cosmicapp.models import ProcessInput, ProcessOutput, ProcessArgument, ProcessOutputFile
from cosmicapp.tasks import *

quit = False

sleepTimes = [0, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15,
15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 60]
sleepTimeIndex = 0

while not quit:
    if sleepTimeIndex > len(sleepTimes) - 1:
        sleepTimeIndex = len(sleepTimes) - 1

    sleepTime = sleepTimes[sleepTimeIndex]
    print("Sleeping for " + str(sleepTime) + " seconds.")
    time.sleep(sleepTime)
    print("Checking queue.")
    try:
        pi = ProcessInput.objects.filter(completed=False).order_by('-priority', 'submittedDateTime')[:1][0]
    except IndexError:
        sleepTimeIndex += 1
        continue
    except:
        print("Unexpected error:", sys.exc_info()[0])
        raise

    if pi.process == 'imagestats':
        arg = pi.processargument_set.all()[0].arg
        imagestats.delay(arg)

    pi.completed = True
    pi.save()

    sleepTimeIndex = 0

