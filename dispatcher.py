import os
import sys
import time
import django
from django.utils import timezone
import celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()


from cosmicapp.models import *
from cosmicapp.tasks import *

quit = False

# The time to wait between successive checks to the DB for tasks in the queue.  The first value is the time to wait
# between tasks when there is more than one in the queue, subsequent values are used for a "backoff timer".
#TODO: The 10 second sleep between task submissions is a hack to workaround the sqlite db limitation.  Set to a small value for production use.
sleepTimes = [1, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15,
15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 60]
sleepTimeIndex = 0

def getFirstPrerequisite(pi):
    prerequisites = pi.prerequisites.all()
    unmet = []
    for prerequisite in prerequisites:
        if prerequisite.completed == None:
            unmet.append(getFirstPrerequisite(prerequisite))
        elif prerequisite.completed == 'failure':
            return None
        elif prerequisite.completed == 'success':
            continue

    if None in unmet:
        return none
    elif len(unmet) > 0:
        return unmet[0]
    else:
        return pi

while not quit:
    if sleepTimeIndex > len(sleepTimes) - 1:
        sleepTimeIndex = len(sleepTimes) - 1

    sleepTime = sleepTimes[sleepTimeIndex]
    print("Sleeping for " + str(sleepTime) + " seconds.")
    sys.stdout.flush()
    time.sleep(sleepTime)
    print("Checking queue.")
    sys.stdout.flush()

    try:
        pi = ProcessInput.objects.filter(completed=None)[:1][0]
    except IndexError:
        sleepTimeIndex += 1
        continue
    except:
        print("Unexpected error:", sys.exc_info()[0])
        raise

    print("checking prerequisistes for:  ", pi.process)
    pi = getFirstPrerequisite(pi)
    print("prerequisiste is:  ", pi.process)
    if pi == None:
        pi.completed = 'failed_prerequisite'
        pi.save()
        continue

    if pi.process == 'imagestats':
        arg = pi.processargument_set.all()[0].arg
        celeryResult = imagestats.delay(arg)

    elif pi.process == 'generateThumbnails':
        arg = pi.processargument_set.all()[0].arg
        celeryResult = generateThumbnails.delay(arg)

    elif pi.process == 'sextractor':
        arg = pi.processargument_set.all()[0].arg
        celeryResult = sextractor.delay(arg)

    elif pi.process == 'daofind':
        arg = pi.processargument_set.all()[0].arg
        celeryResult = daofind.delay(arg)

    elif pi.process == 'starfind':
        arg = pi.processargument_set.all()[0].arg
        celeryResult = starfind.delay(arg)

    elif pi.process == 'parseheaders':
        arg = pi.processargument_set.all()[0].arg
        celeryResult = parseHeaders.delay(arg)

    else:
        print("Skipping unknown task type: " + pi.process)
        sys.stdout.flush()
        continue

    pi.startedDateTime = timezone.now()
    print("Task dispatched.")
    sys.stdout.flush()

    #TODO: This forces the task to complete before the next task is submitted to celery.  In the future when we have
    # multiple celery workers this should be expanded to pass out several jobs at a time and replace any completed
    # ones in order to keep the various celery nodes busy.
    waitTime = 0.5
    while not celeryResult.ready():
        print("   Task running, waiting " + str(waitTime) + " seconds.")
        sys.stdout.flush()
        time.sleep(waitTime)
        waitTime += 1

    # Write the result of the returned value back to the database, either success, failure, or error (early exit).
    if celeryResult.info == True:
        pi.completed = 'success'
    elif celeryResult.info == False:
        pi.completed = 'failure'
    else:
        pi.completed = str(celeryResult.info)

    pi.save()

    print("Task completed with result:  " + pi.completed)
    sys.stdout.flush()

    sleepTimeIndex = 0

