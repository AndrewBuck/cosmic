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
sleepTimes = [0.1, 0.5, 1.5, 3, 3, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8,
    10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 15]
sleepTimeIndex = 0

def getFirstPrerequisite(pi):
    prerequisites = pi.prerequisites.all().order_by('-priority', 'submittedDateTime')
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
        pi = ProcessInput.objects.filter(completed=None).order_by('-priority', 'submittedDateTime')[:1][0]
    except IndexError:
        sleepTimeIndex += 1
        continue
    except:
        print("Unexpected error:", sys.exc_info()[0])
        raise

    print("checking prerequisistes for:  ", pi.process)
    pi = getFirstPrerequisite(pi)
    argList = ''
    for arg in pi.arguments.all():
        argList += ' "{}"'.format(arg.arg)
    print("prerequisiste is:  {} {}".format(pi.process, argList))
    if pi == None:
        pi.completed = 'failed_prerequisite'
        pi.save()
        continue

    if pi.process == 'imagestats':
        arg = pi.arguments.all()[0].arg
        celeryResult = imagestats.delay(arg, pi.pk)

    elif pi.process == 'generateThumbnails':
        arg = pi.arguments.all()[0].arg
        celeryResult = generateThumbnails.delay(arg, pi.pk)

    elif pi.process == 'sextractor':
        arg = pi.arguments.all()[0].arg
        celeryResult = sextractor.delay(arg, pi.pk)

    elif pi.process == 'image2xy':
        arg = pi.arguments.all()[0].arg
        celeryResult = image2xy.delay(arg, pi.pk)

    elif pi.process == 'daofind':
        arg = pi.arguments.all()[0].arg
        celeryResult = daofind.delay(arg, pi.pk)

    elif pi.process == 'starfind':
        arg = pi.arguments.all()[0].arg
        celeryResult = starfind.delay(arg, pi.pk)

    elif pi.process == 'starmatch':
        arg = pi.arguments.all()[0].arg
        celeryResult = starmatch.delay(arg, pi.pk)

    elif pi.process == 'astrometryNet':
        arg = pi.arguments.all()[0].arg
        celeryResult = astrometryNet.delay(arg, pi.pk)

    elif pi.process == 'parseHeaders':
        arg = pi.arguments.all()[0].arg
        celeryResult = parseHeaders.delay(arg, pi.pk)

    elif pi.process == 'flagSources':
        arg = pi.arguments.all()[0].arg
        celeryResult = flagSources.delay(arg, pi.pk)

    elif pi.process == 'imageCombine':
        argList = []
        for arg in pi.arguments.all():
            argList.append(arg.arg)

        celeryResult = imageCombine.delay(argList, pi.pk)

    elif pi.process == 'calculateUserCostTotals':
        arg0 = pi.arguments.all()[0].arg
        arg1 = pi.arguments.all()[1].arg

        celeryResult = calculateUserCostTotals.delay(arg0, arg1, pi.pk)

    else:
        print("Skipping unknown task type: " + pi.process)
        sys.stdout.flush()
        continue

    pi.startedDateTime = timezone.now()
    pi.save()
    print("Task dispatched.")
    sys.stdout.flush()

    #TODO: This forces the task to complete before the next task is submitted to celery.  In the future when we have
    # multiple celery workers this should be expanded to pass out several jobs at a time and replace any completed
    # ones in order to keep the various celery nodes busy.
    waitTime = 0.25
    while not celeryResult.ready():
        print("   Task running, waiting " + str(waitTime) + " seconds.")
        sys.stdout.flush()
        time.sleep(waitTime)
        waitTime = waitTime*1.5 + 0.1
        waitTime = min(waitTime, 5)

    # Write the result of the returned value back to the database, either success, failure, or error (early exit).
    #TODO: Pass the return result through directly as a string and modify the individual tasks to return more detailed strings.
    if isinstance(celeryResult.info, dict):
        cost = celeryResult.info['executionTime'] * CosmicVariable.getVariable('cpuCostPerSecond')
        processOutput = ProcessOutput(
            processInput = pi,
            outputText = celeryResult.info['outputText'],
            outputErrorText = celeryResult.info['outputErrorText'],
            actualCostCPU = celeryResult.info['executionTime'],
            actualCost = cost
            )

        processOutput.save()

        siteCost = SiteCost(
            user = pi.requestor,
            text = 'Process input ' + str(pi.pk),
            cost = cost
            )

        siteCost.save()

        pi.completed = 'success.'
    else:
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

