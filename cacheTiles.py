import sys
import time
import urllib.request

usage = "\n\n\n\tUSAGE: " + sys.argv[0] + " zoomLevel <optionalDelayBetweenRequests>\n\n\n"
if len(sys.argv) == 1:
    print(usage)
    sys.exit(1)

zoom = int(sys.argv[1])

print('Seeding cache for zoom level {}.  This is a total of {} tiles.'\
    .format(zoom, 2**(2*zoom)))

if len(sys.argv) > 2:
    delay = float(sys.argv[2])
else:
    delay = None

timeTakenArray = []
tileCounter = 0

for x in range(2**zoom):
    for y in range(2**zoom):
        tileCounter += 1
        reqStartTime = int(round(time.time() * 1000))
        response = urllib.request.urlopen('http://localhost:8080/map/sky/tiles/{}/{}/{}.png'.format(zoom, x, y))
        reqEndTime = int(round(time.time() * 1000))
        timeTaken = (reqEndTime - reqStartTime)/1000

        if response.getcode() == 200:
            actionString = 'cache hit'
        elif response.getcode() == 201:
            actionString = 'cache miss'
            #TODO: Also store which z, x, y this time is for so that for the slowest X percent of tiles we can also go a couple extra zoom levels down and pre-cache those as well since they are likely to be slower on average.
            timeTakenArray.append(timeTaken)
        elif response.getcode() == 302:
            actionString = 'all black tile redirect'
        else:
            actionString = 'code: ' + str(response.getcode())

        print('{:.2%} Zoom {}:   x: {}   y: {}      Request took {} seconds   {}'\
            .format(tileCounter/2**(2*zoom), zoom, x, y, round(timeTaken, 2), actionString))

        if delay is not None:
            time.sleep(delay)

if len(timeTakenArray) > 0:
    minTime = timeTakenArray[0]
    maxTime = timeTakenArray[0]
    sumTime = 0
    for time in timeTakenArray:
        sumTime += time
        minTime = min(time, minTime)
        maxTime = max(time, maxTime)

    print('\n\n-------------------------------------\n\nFinished.')
    print('Min time taken for a single request: {}'.format(minTime))
    print('Max time taken for a single request: {}'.format(maxTime))
    print('Average time taken for a single request: {}'.format(sumTime/len(timeTakenArray)))
else:
    print('\n\n-------------------------------------\n\nFinished.')
    print('All tiles were already cached.')
