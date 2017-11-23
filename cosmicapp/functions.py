from django.contrib.gis.geos import GEOSGeometry, Point
import sqlparse

from .models import *
from .tasks import *

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
    geometry = GEOSGeometry(geometry)

    #TODO: Move this '10' into a global variable or something to force it to be the same as what is used in the compute ephemerides routines.
    if bufferSize < 10:
        largeBufferSize = 10
    else:
        largeBufferSize = bufferSize

    # Start by performing a query which returns all asteroids that pass within the bufferDistance within a few months
    # of the targetTime
    asteroidsApprox = AstorbEphemeris.objects.filter(
        geometry__dwithin=(geometry, largeBufferSize),
        startTime__lte=targetTime,
        endTime__gte=targetTime,
        brightMag__lt=limitingMag
        ).distinct('astorbRecord_id')[:limit*10]   # We use a larger limit here since some will be discarded.

    # Now that we have narrowed it down to a list of candidates, check through that list and calculate the exact
    # ephemeris at the desired targetTime for each candidate and discard any which don't actually fall within the
    # desired distance.
    asteroids = []
    for asteroid in asteroidsApprox:
        ephemeris = computeSingleEphemeris(asteroid.astorbRecord, targetTime)

        ephemPoint = Point(ephemeris.ra*(180/math.pi), ephemeris.dec*(180/math.pi))
        separation = geometry.distance(ephemPoint)
        if separation > bufferSize:
            continue

        asteroids.append({
            'record': asteroid.astorbRecord,
            'ephem': ephemeris
            })

    return asteroids
