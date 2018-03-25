from django.contrib.gis.geos import GEOSGeometry, Point
import sqlparse
import ephem

from .models import *
from .tasks import *
from .templatetags.cosmicapp_extras import formatRA, formatDec

def formatSqlQuery(query):
    s = query.query.__str__()
    return sqlparse.format(s, reindent=True, keyword_case='upper')

def getClientIp(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def getLocationForIp(ip):
    (o1, o2, o3, o4) = ip.split('.')
    o1 = int(o1)
    o2 = int(o2)
    o3 = int(o3)
    o4 = int(o4)
    integerIp = (16777216*o1) + (65536*o2) + (256*o3 ) + o4

    try:
        result = GeoLiteBlock.objects.get(startIp__lte=integerIp, endIp__gte=integerIp)
        return (result.location.lat, result.location.lon)
    except GeoLiteBlock.DoesNotExist:
        return (0, 0)

def getAsteroidsAroundGeometry(geometry, bufferSize, targetTime, limitingMag, limit):
    if targetTime == None:
        return []

    geometry = GEOSGeometry(geometry)

    #TODO: Move this '10' into a global variable or something to force it to be the same as what is used in the compute ephemerides routines.
    if bufferSize < 10:
        largeBufferSize = 10
    else:
        largeBufferSize = bufferSize

    # We use a larger limit here since some will be discarded.
    fakeLimit = min(limit*10, 100)

    # Start by performing a query which returns all asteroids that pass within the bufferDistance within a few months
    # of the targetTime
    asteroidsApprox = AstorbEphemeris.objects.filter(
        geometry__dwithin=(geometry, largeBufferSize),
        startTime__lte=targetTime,
        endTime__gte=targetTime,
        brightMag__lt=limitingMag
        ).order_by('-astorbRecord__astrometryNeededCode', '-astorbRecord__ceu', 'astorbRecord_id').distinct('astorbRecord__astrometryNeededCode', 'astorbRecord__ceu', 'astorbRecord_id')[:fakeLimit]

    # Now that we have narrowed it down to a list of candidates, check through that list and calculate the exact
    # ephemeris at the desired targetTime for each candidate and discard any which don't actually fall within the
    # desired distance.
    asteroids = []
    for asteroid in asteroidsApprox:
        ephemeris = computeSingleEphemeris(asteroid.astorbRecord, targetTime)

        ephemPoint = Point(ephemeris.ra*(180/math.pi), ephemeris.dec*(180/math.pi))
        separation = geometry.distance(ephemPoint)
        if separation > bufferSize or ephemeris.mag > limitingMag:
            continue

        # Update the CEU on the record to the correct value for the time the query was
        # for.  This should be close to the original value, but in some cases can get be different
        asteroid.astorbRecord.ceu = asteroid.astorbRecord.getCeuForTime(targetTime)

        asteroids.append({
            'record': asteroid.astorbRecord,
            'ephem': ephemeris
            })

    return asteroids

def formulateObservingPlan(user, observatory, targets, includeOtherTargets, startTime, endTime, minTimeBetween, maxTimeBetween, limitingMag, minimumScore):
    #TODO: Also include calibration images at the beginning, middle, and end of the observing session.
    minTimeBetweenTimedelta = timedelta(minutes=minTimeBetween)
    maxTimeBetweenTimedelta = timedelta(minutes=maxTimeBetween)

    observingPlan = []
    for target in targets:
        d = {}
        d['target'] = target
        ra, dec = (None, None)
        mag = 0.0
        defaultSelected = True

        if isinstance(target, Bookmark):
            d['divID'] = target.getObjectTypeString + '_' + str(target.object_id)
            d['type'] = target.getObjectTypeCommonName
            d['typeInternal'] = target.getObjectTypeString
            d['id'] = str(target.object_id)
            d['identifier'] = target.content_object.getDisplayName

            if isinstance(target.content_object, ScorableObject):
                peakScoreTuple = target.content_object.getPeakScoreForInterval(startTime, endTime, user, observatory)
                d['peakScore'] = round(peakScoreTuple[0], 2)
                d['peakScoreTime'] = str(peakScoreTuple[1])

                score = d['peakScore']
                d['score'] = round(score, 2)

                if score < minimumScore:
                    defaultSelected = False
            else:
                d['score'] = "None"
                defaultSelected = False
                d['peakScore'] = 'None'
                d['peakScoreTime'] = str(startTime)

            if isinstance(target.content_object, SkyObject):
                if d['peakScore'] != 'None':
                    ra, dec = target.content_object.getSkyCoords(peakScoreTuple[1])
                    mag = target.content_object.getMag(peakScoreTuple[1])
                else:
                    ra, dec = target.content_object.getSkyCoords(startTime)
                    mag = target.content_object.getMag(startTime)

                if mag != None:
                    if mag > limitingMag:
                        defaultSelected = False

        d['ra'] = formatRA(ra)
        d['dec'] = formatDec(dec)
        d['mag'] = str(mag)

        d['startTime'] = d['peakScoreTime']
        d['startTimeDatetime'] = dateparser.parse(d['startTime'])

        if ra != None and dec != None:
            body = ephem.FixedBody()
            body._ra = ra
            body._dec = dec
            body._epoch = '2000'   #TODO: Set epoch properly based on which catalog we are reading.
                                   # Do this by adding a 'getEpoch' method to each class that comes from a catalog and return a suitable value.

            observer = ephem.Observer()
            observer.lat = observatory.lat
            observer.lon = observatory.lon
            observer.elevation = observatory.elevation
            if d['peakScore'] != 'None':
                observer.date = peakScoreTuple[1]
            else:
                observer.date = startTime

            #TODO: There should be a UI interface to disable this day/night check or set a specific behaviour, etc.
            # If the sun is above -6 degrees from the horizon (twighlight) then do not select it by default.
            v = ephem.Sun(observer)
            if v.alt >= 1:
                defaultSelected = False

            # Compute the next transit and determine if it happens at a specfic time or if it never happens (and if so, why)
            d['nextTransit'] = str(observer.next_transit(body))
            try:
                d['nextRising'] = str(observer.next_rising(body))
                d['nextSetting'] = str(observer.next_setting(body))
            except ephem.AlwaysUpError:
                d['nextRising'] = "Circumpolar"
                d['nextSetting'] = "Circumpolar"
            except ephem.NeverUpError:
                d['nextRising'] = "Never visible"
                d['nextSetting'] = "Never visible"
                defaultSelected = False

        #TODO: Add a function to models.py to compute an observing program for each object.
        d['numExposures'] = 1
        d['exposureTime'] = 30

        if defaultSelected:
            d['defaultSelected'] = "checked"
        else:
            d['defaultSelected'] = ""

        observingPlan.append(d)

    observingPlan.sort(key=lambda x: x['startTime'])

    observationsToRemove = []
    for observation in observingPlan:
        observingTime = timedelta(seconds=observation['numExposures'] * observation['exposureTime'])

        #TODO: This whole loop can be gotten rid of and replaced by a one liner that does the same thing.
        skip = True
        for otherObservation in observingPlan:
            # Skip over all the ones until we get 1 past the 'observation' from the outer loop and then start the
            # actual loop proceessing on the remaining items.
            if skip:
                if observation == otherObservation:
                    skip = False
                    continue
                continue

            otherObservingTime = timedelta(seconds=otherObservation['numExposures'] * otherObservation['exposureTime'])
            t1 = dateparser.parse(observation['startTime'])
            t2 = dateparser.parse(otherObservation['startTime'])
            deltaT = t2 - t1
            #TODO: Need to take into account the order of the two observations and compare deltaT to the correct observing time.
            if deltaT < otherObservingTime or deltaT < observingTime:
                if observation['score'] < otherObservation['score']:
                    observationsToRemove.append(observation)
                else:
                    observationsToRemove.append(otherObservation)

    removedObservations = []
    for observation in observationsToRemove:
        if observation in observingPlan:
            observingPlan.remove(observation)
            removedObservations.append(observation)

    def observationSortKey(x):
        if x['defaultSelected'] == 'checked':
            return x['score']
        else:
            return 0

    removedObservations.sort(key=lambda x: observationSortKey(x), reverse=True)

    # If there are 0 or 1 entries in the observingPlan the next loop will exit without doing anything so we pad out the
    # list before we start that loop to ensure this does not happen.
    obs = {}
    obs['identifier'] = "Start of Observing"
    obs['startTime'] = str(startTime-timedelta(seconds=1))
    obs['startTimeDatetime'] = dateparser.parse(obs['startTime'])
    observingPlan.append(obs)
    obs = {}
    obs['identifier'] = "End of Observing"
    obs['startTime'] = str(endTime+timedelta(seconds=1))
    obs['startTimeDatetime'] = dateparser.parse(obs['startTime'])
    observingPlan.append(obs)
    observingPlan.sort(key=lambda x: x['startTime'])

    for observation in removedObservations:
        observingTime = observation['numExposures'] * observation['exposureTime']
        observingTimeTimedelta = timedelta(seconds=observingTime) + minTimeBetweenTimedelta

        for i1, i2 in zip(observingPlan[0:], observingPlan[1:]):
            i1ObservingTime = timedelta(seconds=observation['numExposures'] * observation['exposureTime'])
            openTimeWindow = i2['startTimeDatetime'] - i1['startTimeDatetime']

            if openTimeWindow > observingTimeTimedelta:
                observation['startTime'] = str(i1['startTimeDatetime'] + i1ObservingTime + minTimeBetweenTimedelta)
                observation['startTimeDatetime'] = dateparser.parse(observation['startTime'])

                if isinstance(target.content_object, ScorableObject):
                    observation['score'] = observation['target'].content_object.getScoreForTime(observation['startTimeDatetime'], user, observatory)

                observingPlan.append(observation)
                observingPlan.sort(key=lambda x: x['startTime'])
                break

    for observation in observingPlan:
        observation.pop('target', None)
        observation.pop('startTimeDatetime', None)

    return observingPlan

