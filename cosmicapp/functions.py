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
        ).order_by('-astorbRecord__ceu', 'astorbRecord_id').distinct('astorbRecord__ceu', 'astorbRecord_id')[:fakeLimit]

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

        asteroids.append({
            'record': asteroid.astorbRecord,
            'ephem': ephemeris
            })

    return asteroids

def formulateObservingPlan(user, observatory, targets, includeOtherTargets, dateTime, minTimeBetween, maxTimeBetween):
    observingPlan = []
    for target in targets:
        d = {}
        ra, dec = (None, None)
        if isinstance(target, Bookmark):
            d['divID'] = target.getObjectTypeString + '_' + str(target.object_id)
            d['type'] = target.getObjectTypeCommonName
            d['typeInternal'] = target.getObjectTypeString
            d['id'] = str(target.object_id)
            d['identifier'] = target.content_object.getDisplayName

            if isinstance(target.content_object, SkyObject):
                ra, dec = target.content_object.getSkyCoords(dateTime)

        d['ra'] = formatRA(ra)
        d['dec'] = formatDec(dec)

        if ra != None and dec != None:
            body = ephem.FixedBody()
            body._ra = ra
            body._dec = dec
            body._epoch = '2000'   #TODO: Set epoch properly based on which catalog we are reading.

            observer = ephem.Observer()
            observer.lat = observatory.lat
            observer.lon = observatory.lon
            observer.elevation = observatory.elevation
            observer.date = dateTime

            d['startTime'] = str(observer.next_transit(body))
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

        d['numExposures'] = 1
        d['exposureTime'] = 30

        observingPlan.append(d)

    observingPlan.sort(key=lambda x: x['startTime'])
    return observingPlan

