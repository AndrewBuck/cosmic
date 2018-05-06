from django.contrib.gis.geos import GEOSGeometry, Point
import sqlparse
import ephem

from cosmicapp import models
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
        result = models.GeoLiteBlock.objects.get(startIp__lte=integerIp, endIp__gte=integerIp)
        return (result.location.lat, result.location.lon)
    except models.GeoLiteBlock.DoesNotExist:
        return (0, 0)

def getAsteroidsAroundGeometry(geometry, bufferSize, targetTime, limitingMag, limit):
    if targetTime == None:
        return []

    geometry = GEOSGeometry(geometry)

    tolerance = models.CosmicVariable.getVariable('asteroidEphemerideTolerance')
    if bufferSize < tolerance:
        largeBufferSize = tolerance
    else:
        largeBufferSize = bufferSize

    # We use a larger limit here since some will be discarded.
    #TODO: Need to refine this method and/or come up with some better system.
    fakeLimit = max(limit*1.3, limit+500)

    # Start by performing a query which returns all asteroids that pass within the
    # bufferDistance around the targetTime.
    asteroidsApprox = models.AstorbEphemeris.objects.filter(
        geometry__dwithin=(geometry, largeBufferSize),
        startTime__lte=targetTime,
        endTime__gte=targetTime,
        brightMag__lt=limitingMag
        ).order_by('astorbRecord_id').distinct('astorbRecord_id')[:fakeLimit]

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
            'ephem': ephemeris,
            'separation': separation
            })

    asteroids.sort(key=lambda x: x['separation'])
    return asteroids[:limit]

def formulateObservingPlan(user, observatory, targets, includeOtherTargets, startTime, endTime, minTimeBetween, maxTimeBetween, limitingMag, minimumScore):
    def addCalibrationTarget(calibrationType, numExposures, exposureTime, startTime):
        #TODO: Accept an instrument configuration as a parameter and use the readout time of the instrument.
        readoutTime = 2

        d = {}
        d['identifier'] = calibrationType
        d['divID'] = 'calibration_' + str(random.Random().randint(0, 1e9))
        d['type'] = 'Calibration Image'
        d['score'] = 0.1
        d['peakScore'] = 0.1
        d['peakScoreTime'] = str(startTime)
        d['ra'] = None
        d['dec'] = None
        d['mag'] = None
        d['nextRising'] = None
        d['nextTransit'] = None
        d['nextSetting'] = None
        d['startTime'] = str(startTime)
        d['startTimeDatetime'] = startTime
        d['numExposures'] = numExposures
        d['exposureTime'] = exposureTime
        d['defaultSelected'] = "checked"
        d['timeNeeded'] = timedelta(seconds=numExposures*(exposureTime + readoutTime))

        endTime = startTime + d['timeNeeded']

        return d, endTime

    minTimeBetweenTimedelta = timedelta(minutes=minTimeBetween)
    maxTimeBetweenTimedelta = timedelta(minutes=maxTimeBetween)

    observingPlan = []

    # Beginning of session calibration.
    #TODO: We should add one set of dark exposures for each duration of image we are likely to take (including for flat images).
    d, calFinishTime = addCalibrationTarget('Flat', 10, 5, startTime)
    observingPlan.append(d)
    d, calFinishTime = addCalibrationTarget('Bias', 25, 0.001, calFinishTime + minTimeBetweenTimedelta)
    observingPlan.append(d)
    d, calFinishTime = addCalibrationTarget('Dark', 10, 30, calFinishTime + minTimeBetweenTimedelta) #To match light frames.
    observingPlan.append(d)
    d, calFinishTime = addCalibrationTarget('Dark', 10, 5, calFinishTime + minTimeBetweenTimedelta) #To match flat frames.
    observingPlan.append(d)
    d, calFinishTime = addCalibrationTarget('Allsky', 1, 1, calFinishTime + minTimeBetweenTimedelta) #Cell phone camera of sky conditions right around sunset.
    observingPlan.append(d)
    calFinishTime += minTimeBetweenTimedelta

    # End of session calibration.
    d, tempTime = addCalibrationTarget('Bias', 25, 0.001, endTime + timedelta(seconds=2))
    observingPlan.append(d)
    d, tempTime = addCalibrationTarget('Dark', 10, 30, tempTime + minTimeBetweenTimedelta) #To match light frames.
    observingPlan.append(d)

    for target in targets:
        d = {}
        d['target'] = target
        ra, dec = (None, None)
        mag = 0.0
        defaultSelected = True

        if isinstance(target, models.Bookmark):
            d['divID'] = target.getObjectTypeString + '_' + str(target.object_id)
            d['type'] = target.getObjectTypeCommonName
            d['typeInternal'] = target.getObjectTypeString
            d['id'] = str(target.object_id)
            d['identifier'] = target.content_object.getDisplayName

            if isinstance(target.content_object, models.ScorableObject):
                peakScoreTuple = target.content_object.getPeakScoreForInterval(calFinishTime, endTime, user, observatory)
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
                d['peakScoreTime'] = str(calFinishTime)

            if isinstance(target.content_object, models.SkyObject):
                if d['peakScore'] != 'None':
                    ra, dec = target.content_object.getSkyCoords(peakScoreTuple[1])
                    mag = target.content_object.getMag(peakScoreTuple[1])
                else:
                    ra, dec = target.content_object.getSkyCoords(calFinishTime)
                    mag = target.content_object.getMag(calFinishTime)

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
                observer.date = calFinishTime

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
        #TODO: Decide what filter(s) to use as part of the observing program for each object.
        d['numExposures'] = 1
        d['exposureTime'] = 30
        d['timeNeeded'] = timedelta(seconds=d['numExposures'] * d['exposureTime'])

        if defaultSelected:
            d['defaultSelected'] = "checked"
        else:
            d['defaultSelected'] = ""

        observingPlan.append(d)

    observingPlan.sort(key=lambda x: x['startTimeDatetime'])

    observationsToRemove = []
    for observation in observingPlan:
        observingTime = observation['timeNeeded']

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

            otherObservingTime = otherObservation['timeNeeded']
            t1 = observation['startTimeDatetime']
            t2 = otherObservation['startTimeDatetime']
            deltaT = t2 - t1

            #TODO: Need to take into account the order of the two observations and compare deltaT to the correct observing time.
            if (t2 <= t1 and deltaT < otherObservingTime) or (t1 <= t2 and deltaT < observingTime):
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

    obs = {}
    obs['identifier'] = "Start of Observing"
    obs['startTime'] = str(startTime-timedelta(seconds=1))
    obs['startTimeDatetime'] = dateparser.parse(obs['startTime'])
    obs['timeNeeded'] = timedelta(seconds=0)
    observingPlan.append(obs)

    obs = {}
    obs['identifier'] = "End of Observing"
    obs['startTime'] = str(endTime+timedelta(seconds=1))
    obs['startTimeDatetime'] = dateparser.parse(obs['startTime'])
    obs['timeNeeded'] = timedelta(seconds=0)
    observingPlan.append(obs)

    observingPlan.sort(key=lambda x: x['startTimeDatetime'])

    observationsAddedSinceCalibration = 0
    for observation in removedObservations:
        observingTime = observation['timeNeeded']
        observingTimeTimedelta = observingTime + minTimeBetweenTimedelta

        for i1, i2 in zip(observingPlan[0:], observingPlan[1:]):
            i1ObservingTime = i1['timeNeeded']
            if 'timeNeeded' in i1:
                openTimeWindow = i2['startTimeDatetime'] - i1['startTimeDatetime'] - i1['timeNeeded']
            else:
                print('Warning: No timeNeeded in observation: ', i1)
                openTimeWindow = i2['startTimeDatetime'] - i1['startTimeDatetime']

            if openTimeWindow > observingTimeTimedelta:
                observation['startTime'] = str(i1['startTimeDatetime'] + i1ObservingTime + minTimeBetweenTimedelta)
                observation['startTimeDatetime'] = dateparser.parse(observation['startTime'])

                if isinstance(target.content_object, models.ScorableObject) and 'target' in observation:
                    observation['score'] = observation['target'].content_object.getScoreForTime(observation['startTimeDatetime'], user, observatory)

                observingPlan.append(observation)
                if observation['defaultSelected'] == 'checked':
                    observationsAddedSinceCalibration += 1

                # Check to see if we should acquire more calibration frames.
                if observationsAddedSinceCalibration > 5:
                    observationsAddedSinceCalibration = 0
                    calStartTime = observation['startTimeDatetime'] + observation['timeNeeded'] + minTimeBetweenTimedelta
                    d, tempTime = addCalibrationTarget('Bias', 10, 0.001, calStartTime)
                    observingPlan.append(d)
                    d, tempTime = addCalibrationTarget('Dark', 5, 30, tempTime + minTimeBetweenTimedelta) #To match light frames.
                    observingPlan.append(d)

                observingPlan.sort(key=lambda x: x['startTimeDatetime'])
                break

    for observation in observingPlan:
        observation.pop('target', None)
        observation.pop('startTimeDatetime', None)
        observation.pop('timeNeeded', None)

    return observingPlan

def createTasksForNewImage(fileRecord, user):
    with transaction.atomic():
        imageRecord = models.Image(
            fileRecord = fileRecord
            )

        imageRecord.save()

        piImagestats = models.ProcessInput(
            process = "imagestats",
            requestor = user,
            priority = models.ProcessPriority.getPriorityForProcess("imagestats", "batch"),
            estCostCPU = fileRecord.uploadSize / 1e6,
            estCostBandwidth = 0,
            estCostStorage = 1000,
            estCostIO = fileRecord.uploadSize
            )

        piImagestats.save()
        piImagestats.addArguments([fileRecord.onDiskFileName])

        piThumbnails = models.ProcessInput(
            process = "generateThumbnails",
            requestor = user,
            priority = models.ProcessPriority.getPriorityForProcess("generateThumbnails", "batch"),
            estCostCPU = fileRecord.uploadSize / 1e6,
            estCostBandwidth = 0,
            estCostStorage = fileRecord.uploadSize / 10,
            estCostIO = 1.5 * fileRecord.uploadSize
            )

        piThumbnails.save()
        piThumbnails.addArguments([fileRecord.onDiskFileName])

        piSextractor = models.ProcessInput(
            process = "sextractor",
            requestor = user,
            priority = models.ProcessPriority.getPriorityForProcess("sextractor", "batch"),
            estCostCPU = 0.5 * fileRecord.uploadSize / 1e6,
            estCostBandwidth = 0,
            estCostStorage = 3000,
            estCostIO = fileRecord.uploadSize
            )

        piSextractor.save()
        piSextractor.addArguments([fileRecord.onDiskFileName])

        piImage2xy = models.ProcessInput(
            process = "image2xy",
            requestor = user,
            priority = models.ProcessPriority.getPriorityForProcess("image2xy", "batch"),
            estCostCPU = 0.5 * fileRecord.uploadSize / 1e6,
            estCostBandwidth = 0,
            estCostStorage = 3000,
            estCostIO = fileRecord.uploadSize
            )

        piImage2xy.save()
        piImage2xy.addArguments([fileRecord.onDiskFileName])

        piDaofind = models.ProcessInput(
            process = "daofind",
            requestor = user,
            priority = models.ProcessPriority.getPriorityForProcess("daofind", "batch"),
            estCostCPU = 0.5 * fileRecord.uploadSize / 1e6,
            estCostBandwidth = 0,
            estCostStorage = 3000,
            estCostIO = fileRecord.uploadSize
            )

        piDaofind.save()
        piDaofind.addArguments([fileRecord.onDiskFileName])

        piStarfind = models.ProcessInput(
            process = "starfind",
            requestor = user,
            priority = models.ProcessPriority.getPriorityForProcess("starfind", "batch"),
            estCostCPU = 0.5 * fileRecord.uploadSize / 1e6,
            estCostBandwidth = 0,
            estCostStorage = 3000,
            estCostIO = fileRecord.uploadSize
            )

        piStarfind.save()
        piStarfind.addArguments([fileRecord.onDiskFileName])

        piFlagSources = models.ProcessInput(
            process = "flagSources",
            requestor = user,
            priority = models.ProcessPriority.getPriorityForProcess("flagSources", "batch"),
            estCostCPU = 10,
            estCostBandwidth = 0,
            estCostStorage = 3000,
            estCostIO = 10000
            )

        piFlagSources.save()
        piFlagSources.addArguments([imageRecord.pk])

        piStarmatch = models.ProcessInput(
            process = "starmatch",
            requestor = user,
            priority = models.ProcessPriority.getPriorityForProcess("starmatch", "batch"),
            estCostCPU = 10,
            estCostBandwidth = 0,
            estCostStorage = 3000,
            estCostIO = 10000
            )

        piStarmatch.save()
        piStarmatch.addArguments([fileRecord.onDiskFileName])
        piStarmatch.prerequisites.add(piSextractor)
        piStarmatch.prerequisites.add(piDaofind)
        piStarmatch.prerequisites.add(piStarfind)
        piStarmatch.prerequisites.add(piFlagSources)

        piAstrometryNet = models.ProcessInput(
            process = "astrometryNet",
            requestor = user,
            priority = models.ProcessPriority.getPriorityForProcess("astrometryNet", "batch"),
            estCostCPU = 100,
            estCostBandwidth = 3000,
            estCostStorage = 3000,
            estCostIO = 10000000000
            )

        piAstrometryNet.save()
        #TODO: Add additional arguments for depth, cpu timeout, postion guess, etc.
        piAstrometryNet.addArguments([fileRecord.onDiskFileName])
        piAstrometryNet.prerequisites.add(piImagestats)
        piAstrometryNet.prerequisites.add(piStarmatch)

        piHeaders = models.ProcessInput(
            process = "parseHeaders",
            requestor = user,
            priority = models.ProcessPriority.getPriorityForProcess("parseHeaders", "batch"),
            estCostCPU = .1,
            estCostBandwidth = 0,
            estCostStorage = 1000,
            estCostIO = 2000,
            )

        piHeaders.save()
        piHeaders.addArguments([imageRecord.pk])
        piHeaders.prerequisites.add(piImagestats)

    return imageRecord

def computeSingleEphemeris(asteroid, ephemTime):
    ephemTimeObject = ephem.Date(ephemTime)

    body = ephem.EllipticalBody()

    body._inc = asteroid.inclination
    body._Om = asteroid.lonAscendingNode
    body._om = asteroid.argPerihelion
    body._a = asteroid.semiMajorAxis
    body._M = asteroid.meanAnomaly
    body._epoch_M = asteroid.epoch
    body._epoch = asteroid.epoch
    body._e = asteroid.eccentricity
    body._H = asteroid.absMag
    body._G = asteroid.slopeParam

    #TODO: The computed RA/DEC are off slightly, fix this.  I think it is due the +0.5 day issue in the epoch time in the import script.
    body.compute(ephemTimeObject)

    return body

def computeSingleEphemerisRange(asteroid, ephemTimeStart, ephemTimeEnd, tolerance, timeTolerance, startEphemeris, endEphemeris):
    if startEphemeris == None and endEphemeris == None:
        firstCall = True
    else:
        firstCall = False

    ephemerideList = []

    if startEphemeris == None:
        startEphemeris = computeSingleEphemeris(asteroid, ephemTimeStart)

    if endEphemeris == None:
        endEphemeris = computeSingleEphemeris(asteroid, ephemTimeEnd)

    if firstCall:
        ephemerideList.append( (ephemTimeStart, startEphemeris) )

    positionDelta = (180/math.pi)*ephem.separation(startEphemeris, endEphemeris)
    if positionDelta > tolerance:
        steps = math.ceil(positionDelta/tolerance)
        timeDelta = (ephemTimeEnd - ephemTimeStart) / steps

        if timeDelta > timeTolerance:
            timeDelta = timeTolerance
            steps = math.ceil((ephemTimeEnd - ephemTimeStart) / timeDelta)

        s = startEphemeris
        for i in range(steps-1):
            ephemTimeMid = ephemTimeStart + timeDelta
            tempList = computeSingleEphemerisRange(asteroid, ephemTimeStart, ephemTimeMid, tolerance, timeTolerance, s, None)

            #TODO: Add a check here and perform a linear interpolation between the s and m ephemeride positions.  If
            # the interpolated position differs by more than some smaller tolerance, then compute an extra step in the
            # middle.  This should mostly catch the special case where the asteroid undergoes retrograde motion and
            # moves back to nearly the same spot, even though it was quite a bit farther away in between those two
            # points.  This will not be a perfect solution but should be so close to perfect as to not matter.

            ephemerideList.extend(tempList)
            ephemTimeStart = ephemTimeMid
            s = tempList[-1][1]

    ephemerideList.append( (ephemTimeEnd, endEphemeris) )

    return ephemerideList

def computeAsteroidEphemerides(ephemTimeStart, ephemTimeEnd, clearFirst):
    tolerance = models.CosmicVariable.getVariable('asteroidEphemerideTolerance')
    timeTolerance = timedelta(days=models.CosmicVariable.getVariable('asteroidEphemerideTimeTolerance'))
    maxAngularDistance = models.CosmicVariable.getVariable('asteroidEphemerideMaxAngularDistance')

    def writeAstorbEphemerisToDB(astorbRecord, startTime, endTime, dimMag, brightMag, geometry):
        #print("saving " + str(startTime) + "       " + str(endTime) + "     " + geometry)
        record = models.AstorbEphemeris(
            astorbRecord = asteroid,
            startTime = startTime,
            endTime = endTime,
            dimMag = dimMag,
            brightMag = brightMag,
            geometry = geometry
            )

        record.save()

    offset = 0
    pagesize = 25000

    numAsteroids = models.AstorbRecord.objects.count()
    print('Num asteroids to compute: {}'.format(numAsteroids))
    sys.stdout.flush()

    with transaction.atomic():
        if clearFirst:
            models.AstorbEphemeris.objects.all().delete()

        while offset < numAsteroids:
            asteroids = models.AstorbRecord.objects.all()[offset : offset+pagesize]

            for asteroid in asteroids:
                #TODO: Add a check to see if there is already an ephemeris calculated near the start/end time and if so
                # pass it along to this function (remember to change the time to match the ephemeris we are passing).
                ephemerideList = computeSingleEphemerisRange(asteroid, ephemTimeStart, ephemTimeEnd, tolerance, timeTolerance, None, None)

                startingElement = ephemerideList[0]
                previousElement = ephemerideList[0]
                brightMag = startingElement[1].mag
                dimMag = startingElement[1].mag
                geometryString = 'LINESTRING(' + str(startingElement[1].ra*180/math.pi) + " " + str(startingElement[1].dec*180/math.pi)
                angularDistance = 0.0
                resultsWritten = False
                for element in ephemerideList[1:]:
                    resultsWritten = False
                    #print(element[0], element[1].ra*180/math.pi, element[1].dec*180/math.pi, element[1].mag)
                    if element[1].mag < brightMag:
                        brightMag = element[1].mag

                    if element[1].mag > dimMag:
                        dimMag = element[1].mag

                    # Check to see if the asteroid crosses the meridian
                    dRA = element[1].ra - previousElement[1].ra
                    dDec = element[1].dec - previousElement[1].dec
                    meridianCrossDistance = (180/math.pi)*math.sqrt(dRA*dRA + dDec*dDec)
                    if meridianCrossDistance < 180:    # Does not cross the meridian, handle normally.
                        meridianCross = False
                        geometryString += "," + str(element[1].ra*180/math.pi) + " " + str(element[1].dec*180/math.pi)
                    else:    # Does cross the meridian, end the line 1 segment early and start a new segment
                        meridianCross = True

                        # Check to see which direction we are crossing the meridian in and set up variables for later use.
                        if element[1].ra > math.pi and previousElement[1].ra < math.pi:
                            highRAElement = element
                            lowRAElement = previousElement
                            firstEdgeRA = 0
                            secondEdgeRA = 360
                        elif element[1].ra < math.pi and previousElement[1].ra > math.pi:
                            highRAElement = previousElement
                            lowRAElement = element
                            firstEdgeRA = 360
                            secondEdgeRA = 0
                        else:
                            print("ERROR: Got confused in meridian cross of asteroid.")
                            print("asteroid:", asteroid.number, "\t", asteroid.name, "\telement: ",
                                element[1].ra*(180/math.pi), element[1].dec*(180/math.pi),
                                "\tprev element: ", previousElement[1].ra*(180/math.pi), previousElement[1].dec*(180/math.pi))

                        # Calculate the edgeDec which is the declination at which the line segment crosses the
                        # meridian.  We do this by simple linear interpolation.
                        deltaRA = (180/math.pi)*(lowRAElement[1].ra + (2*math.pi-highRAElement[1].ra))
                        deltaDec =  (180/math.pi)*(lowRAElement[1].dec - highRAElement[1].dec)
                        deltaRAToEdge = (180/math.pi)*((2*math.pi-highRAElement[1].ra))
                        edgeDec = highRAElement[1].dec*(180/math.pi) + deltaDec*(deltaRAToEdge/deltaRA)

                        geometryString += "," + str(firstEdgeRA) + " " + str(edgeDec)

                    # TODO: Consider adding a constraint that dimMag-brightMag must be less than some value to handle highly
                    # eccentric objects whose brightness might change rapidly as it moves radially inward.  It also
                    # would handle objects passing very close to the earth as well.  Not sure if this would make sense or not.
                    # The only code change required to implement this is adding an 'or' statement to the 'if' statement below.
                    angularDistance += (180/math.pi)*ephem.separation(previousElement[1], element[1])
                    if angularDistance > maxAngularDistance or meridianCross:
                        geometryString += ')'

                        #TODO: When there is a meridian cross the start and end times of the two line segments are
                        # slightly different than what is recorded.  We can probably just ignore this but there may be
                        # some minor issues with doing so.
                        writeAstorbEphemerisToDB(asteroid, startingElement[0], element[0], dimMag, brightMag, geometryString)
                        startingElement = element
                        brightMag = startingElement[1].mag
                        dimMag = startingElement[1].mag
                        angularDistance = 0.0
                        resultsWritten = True

                        if meridianCross:
                            geometryString = 'LINESTRING(' + str(secondEdgeRA) + " " + str(edgeDec) + ","
                        else:
                            geometryString = 'LINESTRING('

                        geometryString += str(startingElement[1].ra*180/math.pi) + " " + str(startingElement[1].dec*180/math.pi)

                    previousElement = element

                if not resultsWritten:
                    geometryString += ")"
                    writeAstorbEphemerisToDB(asteroid, startingElement[0], element[0], dimMag, brightMag, geometryString)

            offset += pagesize
            print('Processed {} asteroids - {}% complete.'.format(offset, round(100*offset/numAsteroids,0)))
            sys.stdout.flush()

    return True

