import os
import sys
import time
import django
from django.utils import timezone
import threading
import celery
from django.db.models import ExpressionWrapper, F, Q

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()


from cosmicapp.models import *
from cosmicapp.tasks import *

quit = False
dispatchSemaphore = threading.Semaphore(value=3)
astrometryNetSemaphore = threading.Semaphore(value=1)

# The time to wait between successive checks to the DB for tasks in the queue.  The first value is the time to wait
# between tasks when there is more than one in the queue, subsequent values are used for a "backoff timer".
sleepTimes = [0.3, 0.5, 1.5, 3, 3, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8,
    10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 15]
sleepTimeIndex = 0

def getFirstPrerequisite(pi):
    prerequisites = pi.prerequisites.all().order_by('-priority', 'submittedDateTime')
    unmet = []
    for prerequisite in prerequisites:
        if prerequisite.completed == None:
            unmet.append(getFirstPrerequisite(prerequisite))
        elif prerequisite.completed == 'failure':
            return None, 'failed_prerequisite'
        elif prerequisite.completed == 'success':
            continue

    for prereq, status in unmet:
        if prereq is None:
            if status == 'failed_prerequisite':
                return None, 'failed_prerequisite'
            else:
                continue

        if prereq.startedDateTime is None:
            return prereq, 'prereq_found'

    if len(unmet) == 0:
        return pi, 'no_umnet_ok_to_proceed'
    else:
        return None, 'prerequisite_running'

def dispatchProcessInput(pi):
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
        return

    waitTime = 0.25
    while not celeryResult.ready():
        print("   Task running, waiting " + str(waitTime) + " seconds.")
        sys.stdout.flush()
        time.sleep(waitTime)
        waitTime = waitTime*1.5 + 0.1
        waitTime = min(waitTime, 5)

    if pi.process == 'astrometryNet':
        astrometryNetSemaphore.release()

    # Write the result of the returned value back to the database, either success, failure, or error (early exit).
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
            dateTime = timezone.now(),
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

    dispatchSemaphore.release()

# Begin program exectution.

# Clear previously dispatched runs that crashed or were killed before they were finished.
#NOTE: Having this line means it is only safe to run a single instance of the dispatcher, starting up a second
# dispatcher will kill the startedDateTime entries currently running on the first and they will all get run again.
ProcessInput.objects.filter(completed=None).update(startedDateTime=None)

while not quit:
    dispatchSemaphore.acquire()

    astrometryNetTasksAllowed = astrometryNetSemaphore.acquire(False)

    if sleepTimeIndex > len(sleepTimes) - 1:
        sleepTimeIndex = len(sleepTimes) - 1

    sleepTime = sleepTimes[sleepTimeIndex]
    print("Sleeping for " + str(sleepTime) + " seconds.")
    sys.stdout.flush()
    time.sleep(sleepTime)
    print("Checking queue.")
    sys.stdout.flush()

    try:
        index = random.Random().randint(0, 5)
        inputQuery = ProcessInput.objects.filter(completed=None, startedDateTime__isnull=True).order_by('-priority', 'submittedDateTime')

        if not astrometryNetTasksAllowed:
            print('Not allowing astrometryNet tasks since one is already dispatched.')
            sys.stdout.flush()
            inputQuery = inputQuery.filter(~Q(process='astrometryNet'))
        else:
            print('Allowing astrometryNet tasks.')
            sys.stdout.flush()

        pi = inputQuery[index:index+1][0]

    except IndexError:
        if len(inputQuery) == 0:
            sleepTimeIndex += 1
            dispatchSemaphore.release()
            if astrometryNetTasksAllowed:
                astrometryNetSemaphore.release()
            continue
        else:
            pi = inputQuery[0]
    except:
        print("Unexpected error:", sys.exc_info()[0])
        sys.stdout.flush()
        dispatchSemaphore.release()
        if astrometryNetTasksAllowed:
            astrometryNetSemaphore.release()
        raise

    print("checking prerequisistes for:  ", pi.process)
    sys.stdout.flush()
    prerequisite, status = getFirstPrerequisite(pi)

    print(status)
    sys.stdout.flush()

    if status == 'failed_prerequisite':
        pi.startedDateTime = timezone.now()
        pi.completed = 'failed_prerequisite'
        pi.save()
        dispatchSemaphore.release()
        if astrometryNetTasksAllowed:
            astrometryNetSemaphore.release()
        continue

    elif status == 'prerequisite_running':
        print("waiting on already running prerequisite.  Sleeping 2 seconds.")
        sys.stdout.flush()
        time.sleep(2)
        dispatchSemaphore.release()
        if astrometryNetTasksAllowed:
            astrometryNetSemaphore.release()
        continue

    pi = prerequisite

    # If we successfully acquired the astrometryNetSemaphore but then didn't end up using it to dispatch a task we
    # return it to the pool.  If we did acquire it, but the task is an astrometryNet task, then it will be released
    # when the task is completed.
    if astrometryNetTasksAllowed and pi.process != 'astrometryNet':
        astrometryNetSemaphore.release()

    argList = ''
    for arg in pi.arguments.all():
        argList += ' "{}"'.format(arg.arg)
    print("prerequisiste is:  {} {}".format(pi.process, argList))
    sys.stdout.flush()

    pi.startedDateTime = timezone.now()
    pi.save()
    print("Task dispatched.")
    sys.stdout.flush()

    t = threading.Thread(target=dispatchProcessInput, args=(pi,))
    t.start()
    time.sleep(0.1)
    sleepTimeIndex = 0

