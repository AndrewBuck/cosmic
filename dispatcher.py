import os
import time
import django
import celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()


from cosmicapp.models import *
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
        pi = ProcessInput.objects.filter(completed=False)[:1][0]
    except IndexError:
        sleepTimeIndex += 1
        continue
    except:
        print("Unexpected error:", sys.exc_info()[0])
        raise

    if pi.process == 'imagestats':
        arg = pi.processargument_set.all()[0].arg
        imagestats.delay(arg)

    elif pi.process == 'generateThumbnails':
        arg = pi.processargument_set.all()[0].arg
        generateThumbnails.delay(arg)

    elif pi.process == 'sextractor':
        arg = pi.processargument_set.all()[0].arg
        sextractor.delay(arg)


    #TODO: This gets done right away, need to wait to set this to True until the celery task is actually finished, not just dispatched
    pi.completed = True
    pi.save()

    sleepTimeIndex = 0
    print("Task dispatched.")

