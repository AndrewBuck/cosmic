import hashlib
import os
import math
from datetime import datetime, timedelta
import dateparser

from django.middleware import csrf
from django.http import HttpResponse
from django.shortcuts import render
from django.template import loader
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.conf import settings
from django.db.models import Q, Max, Min, Avg, StdDev
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.contrib.gis.geos import GEOSGeometry, Point

from lxml import etree
import ephem
from astropy import wcs
from astropy.io import fits

from .models import *
from .forms import *
from .functions import *
from .tasks import *

#TODO: Replace all model.pk references with model.whatever_id as the second version does not fetch the joined model from the db.

def index(request):
    context = {"user" : request.user}
    return render(request, "cosmicapp/index.html", context)

def about(request):
    context = {"user" : request.user}
    return render(request, "cosmicapp/about.html", context)

def processes(request, process=None):
    context = {"user" : request.user}

    if process == None:
        return render(request, "cosmicapp/processes.html", context)

    validPages = ['astrometrynet', 'generatethumbnails', 'imagestats', 'parseheaders', 'sextractor', 'image2xy',
        'daofind', 'starfind', 'starmatch', 'flagsources']

    process = process.lower()
    if process in validPages:
        return render(request, "cosmicapp/" + process + ".html", context)

    else:
        return HttpResponse('Process "' + process + '" not found.', status=400, reason='Parameters missing.')
def createuser(request):
    context = {"user" : request.user}

    #TODO: Need a lot more validation here.
    #TODO: Also need to do something about people creating usernames as attempted SQL injection attacks.  The standard
    # username validation should take care of a lot of this but some extra precautions maybe should be taken.  We are
    # unlikely to actually be vulnerable to an SQL injection via this method, however we don't want the user table
    # polluted with attempted attacks.
    if request.method == 'POST':
        p = request.POST
        if p['password'] != p['repeatpassword']:
            context['usercreationerror'] = "Entered passwords do not match"
        else:
            User.objects.create_user(p['username'], p['email'], p['password'])
            return HttpResponseRedirect('/login/')

    return render(request, "cosmicapp/createuser.html", context)

def donate(request):
    context = {"user" : request.user}

    return render(request, "cosmicapp/donate.html", context)

@login_required
def upload(request):
    context = {"user" : request.user}
    context['supportedImageTypes'] = settings.SUPPORTED_IMAGE_TYPES

    if request.method == 'POST' and 'myfiles' in request.FILES:
        #TODO: Create a record for this upload session and link all the UploadedFileRecords to it.
        records = []
        for myfile in request.FILES.getlist('myfiles'):
            fs = FileSystemStorage()
            filename = fs.save(myfile.name, myfile)

            #TODO: Instead of replacing spaces we should rename the file to a hash name or something with no chance of
            # special characters that would break other processes.
            filenameNoSpaces = filename.replace(' ', '_')
            os.rename(settings.MEDIA_ROOT + filename, settings.MEDIA_ROOT + filenameNoSpaces)
            filename = filenameNoSpaces

            hashObject = hashlib.sha256()
            for chunk in myfile.chunks():
                hashObject.update(chunk)

            record = UploadedFileRecord(
                uploadingUser = User.objects.get(pk=request.user.pk),
                unpackedFromFile = None,
                originalFileName = myfile.name,
                onDiskFileName = filename,
                fileSha256 = hashObject.hexdigest(),
                uploadDateTime = timezone.now(),
                uploadSize = myfile.size
                )

            record.save()
            records.append(record)

            fileBase, fileExtension = os.path.splitext(record.onDiskFileName)

            if fileExtension.lower() in settings.SUPPORTED_IMAGE_TYPES:
                with transaction.atomic():
                    imageRecord = Image(
                        fileRecord = record
                        )

                    imageRecord.save()

                    piImagestats = ProcessInput(
                        process = "imagestats",
                        requestor = User.objects.get(pk=request.user.pk),
                        submittedDateTime = timezone.now(),
                        priority = ProcessPriority.getPriorityForProcess("imagestats", "batch"),
                        estCostCPU = record.uploadSize / 1e6,
                        estCostBandwidth = 0,
                        estCostStorage = 1000,
                        estCostIO = record.uploadSize
                        )

                    piImagestats.save()
                    piImagestats.addArguments([record.onDiskFileName])

                    piThumbnails = ProcessInput(
                        process = "generateThumbnails",
                        requestor = User.objects.get(pk=request.user.pk),
                        submittedDateTime = timezone.now(),
                        priority = ProcessPriority.getPriorityForProcess("generateThumbnails", "batch"),
                        estCostCPU = record.uploadSize / 1e6,
                        estCostBandwidth = 0,
                        estCostStorage = record.uploadSize / 10,
                        estCostIO = 1.5 * record.uploadSize
                        )

                    piThumbnails.save()
                    piThumbnails.addArguments([record.onDiskFileName])

                    piSextractor = ProcessInput(
                        process = "sextractor",
                        requestor = User.objects.get(pk=request.user.pk),
                        submittedDateTime = timezone.now(),
                        priority = ProcessPriority.getPriorityForProcess("sextractor", "batch"),
                        estCostCPU = 0.5 * record.uploadSize / 1e6,
                        estCostBandwidth = 0,
                        estCostStorage = 3000,
                        estCostIO = record.uploadSize
                        )

                    piSextractor.save()
                    piSextractor.addArguments([record.onDiskFileName])

                    piImage2xy = ProcessInput(
                        process = "image2xy",
                        requestor = User.objects.get(pk=request.user.pk),
                        submittedDateTime = timezone.now(),
                        priority = ProcessPriority.getPriorityForProcess("image2xy", "batch"),
                        estCostCPU = 0.5 * record.uploadSize / 1e6,
                        estCostBandwidth = 0,
                        estCostStorage = 3000,
                        estCostIO = record.uploadSize
                        )

                    piImage2xy.save()
                    piImage2xy.addArguments([record.onDiskFileName])

                    piDaofind = ProcessInput(
                        process = "daofind",
                        requestor = User.objects.get(pk=request.user.pk),
                        submittedDateTime = timezone.now(),
                        priority = ProcessPriority.getPriorityForProcess("daofind", "batch"),
                        estCostCPU = 0.5 * record.uploadSize / 1e6,
                        estCostBandwidth = 0,
                        estCostStorage = 3000,
                        estCostIO = record.uploadSize
                        )

                    piDaofind.save()
                    piDaofind.addArguments([record.onDiskFileName])

                    piStarfind = ProcessInput(
                        process = "starfind",
                        requestor = User.objects.get(pk=request.user.pk),
                        submittedDateTime = timezone.now(),
                        priority = ProcessPriority.getPriorityForProcess("starfind", "batch"),
                        estCostCPU = 0.5 * record.uploadSize / 1e6,
                        estCostBandwidth = 0,
                        estCostStorage = 3000,
                        estCostIO = record.uploadSize
                        )

                    piStarfind.save()
                    piStarfind.addArguments([record.onDiskFileName])

                    piStarmatch = ProcessInput(
                        process = "starmatch",
                        requestor = User.objects.get(pk=request.user.pk),
                        submittedDateTime = timezone.now(),
                        priority = ProcessPriority.getPriorityForProcess("starmatch", "batch"),
                        estCostCPU = 10,
                        estCostBandwidth = 0,
                        estCostStorage = 3000,
                        estCostIO = 10000
                        )

                    piStarmatch.save()
                    piStarmatch.addArguments([record.onDiskFileName])
                    piStarmatch.prerequisites.add(piSextractor)
                    piStarmatch.prerequisites.add(piDaofind)
                    piStarmatch.prerequisites.add(piStarfind)

                    piAstrometryNet = ProcessInput(
                        process = "astrometryNet",
                        requestor = User.objects.get(pk=request.user.pk),
                        submittedDateTime = timezone.now(),
                        priority = ProcessPriority.getPriorityForProcess("astrometryNet", "batch"),
                        estCostCPU = 100,
                        estCostBandwidth = 3000,
                        estCostStorage = 3000,
                        estCostIO = 10000000000
                        )

                    piAstrometryNet.save()
                    #TODO: Add additional arguments for depth, cpu timeout, postion guess, etc.
                    piAstrometryNet.addArguments([record.onDiskFileName])
                    piAstrometryNet.prerequisites.add(piImagestats)
                    piAstrometryNet.prerequisites.add(piStarmatch)

                    piHeaders = ProcessInput(
                        process = "parseHeaders",
                        requestor = User.objects.get(pk=request.user.pk),
                        submittedDateTime = timezone.now(),
                        priority = ProcessPriority.getPriorityForProcess("parseHeaders", "batch"),
                        estCostCPU = .1,
                        estCostBandwidth = 0,
                        estCostStorage = 1000,
                        estCostIO = 2000,
                        )

                    piHeaders.save()
                    piHeaders.addArguments([imageRecord.pk])
                    piHeaders.prerequisites.add(piImagestats)

        context['upload_successful'] = True
        context['records'] = records

    return render(request, "cosmicapp/upload.html", context)

def userpage(request, username):
    context = {"user" : request.user}

    try:
        foruser = User.objects.get(username = username)
    except User.DoesNotExist:
        context['foruser'] = username
        return render(request, "cosmicapp/usernotfound.html", context)

    foruserForm = ProfileForm(instance = foruser.profile)

    context['foruser'] = foruser
    context['foruserForm'] = foruserForm
    context['otherObservatories'] = Observatory.objects.filter(user=foruser).order_by('-pk')
    if foruser.profile.defaultObservatory != None:
        context['otherObservatories'] = context['otherObservatories'].exclude(pk=foruser.profile.defaultObservatory.pk)

    if request.method == 'POST':
        if 'edit' in request.POST:
            context['edit'] = request.POST['edit']
        else:
            profileForm = ProfileForm(request.POST)

            if request.user.username == foruser.username and profileForm.is_valid():
                foruser.profile.birthDate = profileForm.cleaned_data['birthDate']
                foruser.profile.save()

                return HttpResponseRedirect('/user/' + foruser.username + '/')

    return render(request, "cosmicapp/userpage.html", context)

def observatory(request, id):
    context = {"user" : request.user}

    if id.lower() == 'new':
        if request.method == 'POST' and request.user.is_authenticated:
            if not (request.POST['lat'] != "" and request.POST['lon'] != ""):
                context['defaultName'] = request.POST['name']
                context['defaultLat'] = request.POST['lat']
                context['defaultLon'] = request.POST['lon']
                context['defaultEle'] = request.POST['ele']
                context['defaultChecked'] = request.POST['makedefault']
                context['error'] = 'Error: Missing required fields'
                return render(request, "cosmicapp/observatorynew.html", context)

            lat = float(request.POST.get('lat', ''))
            lon = float(request.POST.get('lon', ''))
            name = request.POST.get('name', None)
            ele = float(request.POST.get('ele', ''))

            observatory = Observatory(
                user = request.user,
                name = name,
                lat = lat,
                lon = lon,
                elevation = ele
                )

            observatory.save()

            if request.POST.get('makedefault', '') == "checked":
                request.user.profile.defaultObservatory = observatory
                request.user.profile.save()

            return HttpResponseRedirect('/user/' + request.user.username + '/')
        else:
            if not request.user.is_authenticated:
                context['error'] = 'Error: You must be logged in to create an observatory.'

            return render(request, "cosmicapp/observatorynew.html", context)

    try:
        observatory = Observatory.objects.get(pk=id)
    except Observatory.DoesNotExist:
        context['id'] = id
        return render(request, "cosmicapp/observatorynotfound.html", context)

    context['observatory'] = observatory

    #TODO: For code clarity reasons, it might make sense to refactor this section to work it into the section up above.
    # Not sure about this yet.
    if request.method == 'POST' and request.user.is_authenticated and request.user == observatory.user:
        if request.POST['makedefault'] == 'true':
            request.user.profile.defaultObservatory = observatory

        if request.POST['makedefault'] == 'clear':
            request.user.profile.defaultObservatory = None

        request.user.profile.save()
        return HttpResponseRedirect('/user/' + request.user.username + '/')

    return render(request, "cosmicapp/observatory.html", context)

def processQueue(request):
    context = {"user" : request.user}

    processInputsUncompleted = ProcessInput.objects.filter(completed=None).order_by('-priority', 'submittedDateTime')[:50]
    processInputsCompleted = ProcessInput.objects.filter(~Q(completed=None)).order_by('-startedDateTime')[:50]
    context['processInputsUncompleted'] = processInputsUncompleted
    context['processInputsCompleted'] = processInputsCompleted

    return render(request, "cosmicapp/processqueue.html", context)

def processOutput(request, id):
    context = {"user" : request.user}

    processOutput = ProcessOutput.objects.filter(pk=id).first()

    if processOutput == None:
        return HttpResponse('Process Output Not Found: ' + str(id), status=400, reason='Process Output Not Found.')

    context['processOutput'] = processOutput

    return render(request, "cosmicapp/processOutput.html", context)

def catalogs(request):
    context = {"user" : request.user}
    context['catalogs'] = Catalog.objects.all()

    return render(request, "cosmicapp/catalogs.html", context)

def image(request, id):
    context = {"user" : request.user}
    context['id'] = id

    try:
        image = Image.objects.get(pk=id)
    except Image.DoesNotExist:
        return render(request, "cosmicapp/imagenotfound.html", context)

    context['image'] = image

    overlappingPlates = []
    plateSolution = image.getBestPlateSolution()
    imagePlateArea = None
    if plateSolution != None:
        imagePlateArea = plateSolution.geometry.area
        overlappingPlatesObjects = PlateSolution.objects.filter(geometry__overlaps=plateSolution.geometry).distinct('image').exclude(image_id=image.pk)
        for plate in overlappingPlatesObjects:
            overlappingRegion = plateSolution.geometry.intersection(plate.geometry)
            overlappingPlates.append({
                'plate': plate,
                'plateArea': plate.geometry.area,
                'overlapArea': overlappingRegion.area
                })

    context['overlappingPlates'] = overlappingPlates
    context['imagePlateArea'] = imagePlateArea

    numSextractorSources = SextractorResult.objects.filter(image_id=image.pk).count()
    context['numSextractorSources'] = numSextractorSources

    numImage2xySources = Image2xyResult.objects.filter(image_id=image.pk).count()
    context['numImage2xySources'] = numImage2xySources

    numDaofindSources = DaofindResult.objects.filter(image_id=image.pk).count()
    context['numDaofindSources'] = numDaofindSources

    numStarfindSources = StarfindResult.objects.filter(image_id=image.pk).count()
    context['numStarfindSources'] = numStarfindSources

    matches = SourceFindMatch.objects.filter(image_id=image.pk)
    context['numDaofindStarfindMatches'] = matches.filter(daofindResult__isnull=False, starfindResult__isnull=False).count()
    context['numImage2xyDaofindMatches'] = matches.filter(image2xyResult__isnull=False, daofindResult__isnull=False).count()
    context['numImage2xyStarfindMatches'] = matches.filter(image2xyResult__isnull=False, starfindResult__isnull=False).count()
    context['numSextractorDaofindMatches'] = matches.filter(sextractorResult__isnull=False, daofindResult__isnull=False).count()
    context['numSextractorImage2xyMatches'] = matches.filter(sextractorResult__isnull=False, image2xyResult__isnull=False).count()
    context['numSextractorStarfindMatches'] = matches.filter(sextractorResult__isnull=False, starfindResult__isnull=False).count()

    numProperties = ImageProperty.objects.filter(image_id=image.pk).count()
    context['numProperties'] = numProperties

    return render(request, "cosmicapp/image.html", context)

def imageSources(request, id):
    context = {"user" : request.user}
    context['id'] = id

    try:
        image = Image.objects.get(pk=id)
    except Image.DoesNotExist:
        return render(request, "cosmicapp/imagenotfound.html", context)

    context['image'] = image

    return render(request, "cosmicapp/imageSources.html", context)

def imageProperties(request, id):
    context = {"user" : request.user}
    context['id'] = id

    try:
        image = Image.objects.get(pk=id)
    except Image.DoesNotExist:
        return render(request, "cosmicapp/imagenotfound.html", context)

    context['image'] = image

    properties = ImageProperty.objects.filter(image_id=image.pk)
    context['properties'] = properties

    hduList = fits.open(settings.MEDIA_ROOT + image.fileRecord.onDiskFileName)

    fitsHeaderString = ''
    i = 0
    for hdu in hduList:
        fitsHeaderString += '=== HDU {} ===\n\n'.format(i)
        fitsHeaderString += hdu.header.tostring(sep='\n', endcard=False, padding=False)
        i += 1

    context['fitsHeaderString'] = fitsHeaderString

    return render(request, "cosmicapp/imageProperties.html", context)

#TODO: This can probably be removed.
"""
def imageThumbnailUrl(request, id, size):
    context = {"user" : request.user}

    try:
        image = Image.objects.get(pk=id)
    except Image.DoesNotExist:
        return render(request, "cosmicapp/imagenotfound.html", context)

    hintWidth = int(request.GET.get('hintWidth', -1))
    hintHeight = int(request.GET.get('hintHeight', -1))
    stretch = request.GET.get('stretch', 'false')

    return HttpResponse(image.getThumbnailUrl(size, hintWidth, hintHeight, stretch))
"""

def parseQueryOrderBy(request, mappingDict, fallbackEntry, fallbackAscDesc):
    if 'order' in request.GET:
        orderSplit = request.GET['order'].split('_', 1)
        orderField = orderSplit[0]
        if orderField in mappingDict:
            orderField = mappingDict[orderField]
        else:
            orderField = mappingDict[fallbackEntry]

        if len(orderSplit) > 1:
            ascDesc = orderSplit[1]
        else:
            ascDesc = ''

        if ascDesc == 'desc':
            ascDesc = '-'
        elif ascDesc == 'asc':
            ascDesc = ''
        else:
            ascDesc = fallbackAscDesc
    else:
        orderField = mappingDict[fallbackEntry]
        ascDesc = fallbackAscDesc

    return orderField, ascDesc

def cleanupQueryValues(valueString, parseAs):
    if parseAs in ('string', 'int', 'kvPairs'):
        values = valueString.split('|')
        values = map(str.strip, values)
        values = list(filter(len, values))

    if parseAs == 'int':
        intValues = []
        for value in values:
            try:
                i = int(value)
                intValues.append(i)
            except:
                pass

        values = intValues

    if parseAs == 'kvPairs':
        kvPairs = list()
        for value in values:
            split = value.split('=', 1)
            if(len(split) < 2):
                continue

            paramKey = split[0].strip()
            paramValue = split[1].strip()

            if paramKey == '' or paramValue == '':
                continue

            kvPairs.append( (paramKey, paramValue) )

        values = kvPairs

    return values

def query(request):
    root = etree.Element("queryresult")

    # Strip out "blank" query parameters such as 'id='.
    #NOTE: Modifying the request.GET datastructure is not standard, need to make sure this is safe.  Maybe better to
    # make a copy and query on that.
    request.GET._mutable = True
    for key in list(request.GET):
        items = list(filter(len, request.GET.getlist(key)))
        if len(items) == 0:
            request.GET.pop(key)
        elif len(items) == 1:
            request.GET[key] = items[0]
        elif len(items) > 1:
            request.GET.setlist(key, items)
    request.GET._mutable = False

    if not ('queryfor' in request.GET):
        #TODO: Convert this to xml.
        return HttpResponse("bad request: missing 'queryfor'")

    limit = 10    # Set a default limit in case the query did not specify one at all.
    if 'limit' in request.GET:
        try:
            limit = int(request.GET['limit'])
        except:
            pass

        if request.GET['queryfor'] in ['image', 'imageTransform']:
            if limit > 100:
                limit = 100
        elif request.GET['queryfor'] in ['sextractorResult', 'image2xyResult', 'daofindResult', 'starfindResult', 'sourceFindMatch', 'userSubmittedResult']:
            if limit > 10000:
                limit = 10000

    offset = 0
    if 'offset' in request.GET:
        try:
            offset = int(request.GET['offset'])
        except:
            pass

    if request.GET['queryfor'] == 'image':
        orderField, ascDesc = parseQueryOrderBy(request, {'time': 'fileRecord__uploadDateTime'}, 'time', '-')
        results = Image.objects

        if 'user' in request.GET:
            for valueString in request.GET.getlist('user'):
                values = cleanupQueryValues(valueString, 'string')
                if len(values) > 0:
                    results = results.filter(fileRecord__uploadingUser__username__in=values)

        if 'imageProperty' in request.GET:
            for valueString in request.GET.getlist('imageProperty'):
                values = cleanupQueryValues(valueString, 'kvPairs')
                queryQ = Q()
                for paramKey, paramValue in values:
                    subQuery = Q(properties__key=paramKey) & Q(properties__value=paramValue)
                    queryQ = queryQ | subQuery

                results = results.filter(queryQ)

        if 'questionAnswer' in request.GET:
            for valueString in request.GET.getlist('questionAnswer'):
                values = cleanupQueryValues(valueString, 'kvPairs')
                queryQ = Q()
                for paramKey, paramValue in values:
                    subQuery = Q(answers__kvs__key=paramKey) & Q(answers__kvs__value=paramValue)
                    queryQ = queryQ | subQuery

                results = results.filter(queryQ)

        if 'id' in request.GET:
            for valueString in request.GET.getlist('id'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(pk__in=values)

        #TODO: Allow querying by uploaded filename.

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            imageDict = {}
            imageDict['id'] = str(result.pk)
            imageDict['dimX'] = str(result.dimX)
            imageDict['dimY'] = str(result.dimY)
            imageDict['dimZ'] = str(result.dimZ)
            imageDict['bitDepth'] = str(result.bitDepth)
            imageDict['frameType'] = result.frameType
            imageDict['numPlateSolutions'] = str(result.plateSolutions.count())

            #TODO: These next lines can be replaced by a direct db query which is faster than calling this function which does more calculation than we need here.
            imageDict['thumbUrlSmall'] = result.getThumbnailUrlSmall()
            imageDict['thumbUrlMedium'] = result.getThumbnailUrlMedium()
            imageDict['thumbUrlLarge'] = result.getThumbnailUrlLarge()
            imageDict['thumbUrlFull'] = result.getThumbnailUrlFull()

            etree.SubElement(root, "Image", imageDict)

    if request.GET['queryfor'] == 'imageTransform':
        orderField, ascDesc = parseQueryOrderBy(request, {'referenceImage': 'referenceImage'}, 'referenceImage', '')
        results = ImageTransform.objects

        if 'bothId' in request.GET:
            for valueString in request.GET.getlist('bothId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(referenceImage__in=values)
                    results = results.filter(subjectImage__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            imageTransformDict = {}
            imageTransformDict['id'] = str(result.pk)
            imageTransformDict['userId'] = str(result.user.pk)
            imageTransformDict['userName'] = str(result.user.username)
            imageTransformDict['referenceId'] = str(result.referenceImage.pk)
            imageTransformDict['subjectId'] = str(result.subjectImage.pk)
            imageTransformDict['m00'] = str(result.m00)
            imageTransformDict['m01'] = str(result.m01)
            imageTransformDict['m02'] = str(result.m02)
            imageTransformDict['m10'] = str(result.m10)
            imageTransformDict['m11'] = str(result.m11)
            imageTransformDict['m12'] = str(result.m12)

            etree.SubElement(root, "ImageTransform", imageTransformDict)

    elif request.GET['queryfor'] == 'sextractorResult':
        orderField, ascDesc = parseQueryOrderBy(request, {'confidence': 'confidence'}, 'confidence', '-')
        results = SextractorResult.objects

        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(image__pk__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            sextractorDict = {}
            ra, dec = result.getRaDec()
            sextractorDict['ra'] = str(ra)
            sextractorDict['dec'] = str(dec)
            sextractorDict['id'] = str(result.pk)
            sextractorDict['confidence'] = str(result.confidence)
            sextractorDict['imageId'] = str(result.image.pk)
            sextractorDict['pixelX'] = str(result.pixelX)
            sextractorDict['pixelY'] = str(result.pixelY)
            sextractorDict['pixelZ'] = str(result.pixelZ)
            sextractorDict['fluxAuto'] = str(result.fluxAuto)
            sextractorDict['fluxAutoErr'] = str(result.fluxAutoErr)
            sextractorDict['flags'] = str(result.flags)
            sextractorDict['boxXMin'] = str(result.boxXMin)
            sextractorDict['boxYMin'] = str(result.boxYMin)
            sextractorDict['boxXMax'] = str(result.boxXMax)
            sextractorDict['boxYMax'] = str(result.boxYMax)

            etree.SubElement(root, "SextractorResult", sextractorDict)

    elif request.GET['queryfor'] == 'image2xyResult':
        orderField, ascDesc = parseQueryOrderBy(request, {'confidence': 'confidence'}, 'confidence', '-')
        results = Image2xyResult.objects

        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(image__pk__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            image2xyDict = {}
            ra, dec = result.getRaDec()
            image2xyDict['ra'] = str(ra)
            image2xyDict['dec'] = str(dec)
            image2xyDict['id'] = str(result.pk)
            image2xyDict['confidence'] = str(result.confidence)
            image2xyDict['imageId'] = str(result.image.pk)
            image2xyDict['pixelX'] = str(result.pixelX)
            image2xyDict['pixelY'] = str(result.pixelY)
            image2xyDict['pixelZ'] = str(result.pixelZ)
            image2xyDict['flux'] = str(result.flux)
            image2xyDict['background'] = str(result.background)

            etree.SubElement(root, "Image2xyResult", image2xyDict)

    elif request.GET['queryfor'] == 'daofindResult':
        orderField, ascDesc = parseQueryOrderBy(request, {'confidence': 'confidence'}, 'confidence', '-')
        results = DaofindResult.objects

        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(image__pk__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            daofindDict = {}
            ra, dec = result.getRaDec()
            daofindDict['ra'] = str(ra)
            daofindDict['dec'] = str(dec)
            daofindDict['id'] = str(result.pk)
            daofindDict['confidence'] = str(result.confidence)
            daofindDict['imageId'] = str(result.image.pk)
            daofindDict['pixelX'] = str(result.pixelX)
            daofindDict['pixelY'] = str(result.pixelY)
            daofindDict['pixelZ'] = str(result.pixelZ)
            daofindDict['mag'] = str(result.mag)
            daofindDict['flux'] = str(result.flux)
            daofindDict['peak'] = str(result.peak)
            daofindDict['sharpness'] = str(result.sharpness)
            daofindDict['sround'] = str(result.sround)
            daofindDict['ground'] = str(result.ground)

            etree.SubElement(root, "DaofindResult", daofindDict)

    elif request.GET['queryfor'] == 'starfindResult':
        orderField, ascDesc = parseQueryOrderBy(request, {'confidence': 'confidence'}, 'confidence', '-')
        results = StarfindResult.objects

        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(image__pk__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            starfindDict = {}
            ra, dec = result.getRaDec()
            starfindDict['ra'] = str(ra)
            starfindDict['dec'] = str(dec)
            starfindDict['id'] = str(result.pk)
            starfindDict['confidence'] = str(result.confidence)
            starfindDict['imageId'] = str(result.image.pk)
            starfindDict['pixelX'] = str(result.pixelX)
            starfindDict['pixelY'] = str(result.pixelY)
            starfindDict['pixelZ'] = str(result.pixelZ)
            starfindDict['mag'] = str(result.mag)
            starfindDict['peak'] = str(result.peak)
            starfindDict['flux'] = str(result.flux)
            starfindDict['fwhm'] = str(result.fwhm)
            starfindDict['roundness'] = str(result.roundness)
            starfindDict['pa'] = str(result.pa)
            starfindDict['sharpness'] = str(result.sharpness)

            etree.SubElement(root, "StarfindResult", starfindDict)

    elif request.GET['queryfor'] == 'userSubmittedResult':
        orderField, ascDesc = parseQueryOrderBy(request, {'confidence': 'confidence'}, 'confidence', '-')
        results = UserSubmittedResult.objects

        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(image__pk__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            userSubmittedDict = {}
            ra, dec = result.getRaDec()
            userSubmittedDict['ra'] = str(ra)
            userSubmittedDict['dec'] = str(dec)
            userSubmittedDict['id'] = str(result.pk)
            userSubmittedDict['confidence'] = str(result.confidence)
            userSubmittedDict['imageId'] = str(result.image.pk)
            userSubmittedDict['pixelX'] = str(result.pixelX)
            userSubmittedDict['pixelY'] = str(result.pixelY)
            userSubmittedDict['pixelZ'] = str(result.pixelZ)

            etree.SubElement(root, "UserSubmittedResult", userSubmittedDict)

    elif request.GET['queryfor'] == 'userSubmittedHotPixel':
        orderField, ascDesc = parseQueryOrderBy(request, {'confidence': 'confidence'}, 'confidence', '-')
        results = UserSubmittedHotPixel.objects

        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(image__pk__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            userSubmittedDict = {}
            ra, dec = result.getRaDec()
            userSubmittedDict['ra'] = str(ra)
            userSubmittedDict['dec'] = str(dec)
            userSubmittedDict['id'] = str(result.pk)
            userSubmittedDict['confidence'] = str(result.confidence)
            userSubmittedDict['imageId'] = str(result.image.pk)
            userSubmittedDict['pixelX'] = str(result.pixelX)
            userSubmittedDict['pixelY'] = str(result.pixelY)
            userSubmittedDict['pixelZ'] = str(result.pixelZ)

            etree.SubElement(root, "UserSubmittedHotPixel", userSubmittedDict)

    elif request.GET['queryfor'] == 'sourceFindMatch':
        orderField, ascDesc = parseQueryOrderBy(request, {'confidence': 'confidence'}, 'confidence', '-')
        results = SourceFindMatch.objects

        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(image__pk__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            sourceFindMatchDict = {}
            ra, dec = result.getRaDec()
            sourceFindMatchDict['ra'] = str(ra)
            sourceFindMatchDict['dec'] = str(dec)
            sourceFindMatchDict['id'] = str(result.pk)
            sourceFindMatchDict['confidence'] = str(result.confidence)
            sourceFindMatchDict['numMatches'] = str(result.numMatches)
            sourceFindMatchDict['pixelX'] = str(result.pixelX)
            sourceFindMatchDict['pixelY'] = str(result.pixelY)
            sourceFindMatchDict['pixelZ'] = str(result.pixelZ)
            sourceFindMatchDict['imageId'] = str(result.image.pk)
            if result.sextractorResult:
                sourceFindMatchDict['sextractorResult'] = str(result.sextractorResult.pk)
            if result.image2xyResult:
                sourceFindMatchDict['image2xyResult'] = str(result.image2xyResult.pk)
            if result.daofindResult:
                sourceFindMatchDict['daofindResult'] = str(result.daofindResult.pk)
            if result.starfindResult:
                sourceFindMatchDict['starfindResult'] = str(result.starfindResult.pk)
            if result.userSubmittedResult:
                sourceFindMatchDict['userSubmittedResult'] = str(result.userSubmittedResult.pk)

            etree.SubElement(root, "SourceFindMatch", sourceFindMatchDict)

    elif request.GET['queryfor'] == 'objectsInImage':
        #TODO: Need to consider adding order by and limit statements to the queries for the actual objects, and need to
        # figure out decent values for these limits.
        images = None
        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    images = Image.objects.filter(pk__in=values)

        bufferDistance = 0.00000001
        if 'bufferDistance' in request.GET:
            bufferDistance = float(request.GET['bufferDistance'])

        if bufferDistance > 3:
            bufferDistance = 3

        for image in images:
            imageSubElement = etree.SubElement(root, "Image_" + str(image.pk))

            plateSolution = image.getBestPlateSolution()
            if plateSolution == None:
                continue

            w = wcs.WCS(header=plateSolution.wcsHeader)

            #TODO: Consider adding the details of the plate solution to the queryresult.

            twoMassXSCResults = TwoMassXSCRecord.objects.filter(geometry__dwithin=(plateSolution.geometry, bufferDistance))

            for result in twoMassXSCResults:
                x, y = w.all_world2pix(result.ra, result.dec, 1)    #TODO: Determine if this 1 should be a 0.
                twoMassXSCDict = {}
                twoMassXSCDict['id'] = str(result.pk)
                twoMassXSCDict['identifier'] = str(result.identifier)
                twoMassXSCDict['ra'] = str(result.ra)
                twoMassXSCDict['dec'] = str(result.dec)
                twoMassXSCDict['pixelX'] = str(x)
                twoMassXSCDict['pixelY'] = str(y)
                twoMassXSCDict['isophotalKSemiMajor'] = str(result.isophotalKSemiMajor)
                twoMassXSCDict['isophotalKMinorMajor'] = str(result.isophotalKMinorMajor)
                twoMassXSCDict['isophotalKAngle'] = str(result.isophotalKAngle)
                twoMassXSCDict['isophotalKMag'] = str(result.isophotalKMag)
                twoMassXSCDict['isophotalKMagErr'] = str(result.isophotalKMagErr)

                etree.SubElement(imageSubElement, "TwoMassXSCRecord", twoMassXSCDict)

            messierResults = MessierRecord.objects.filter(geometry__dwithin=(plateSolution.geometry, bufferDistance))

            for result in messierResults:
                x, y = w.all_world2pix(result.ra, result.dec, 1)    #TODO: Determine if this 1 should be a 0.
                messierDict = {}
                messierDict['id'] = str(result.pk)
                messierDict['identifier'] = str(result.identifier)
                messierDict['ra'] = str(result.ra)
                messierDict['dec'] = str(result.dec)
                messierDict['pixelX'] = str(x)
                messierDict['pixelY'] = str(y)
                messierDict['objectType'] = str(result.objectType)
                messierDict['spectralType'] = str(result.spectralType)
                messierDict['magU'] = str(result.magU)
                messierDict['magB'] = str(result.magB)
                messierDict['magV'] = str(result.magV)
                messierDict['magR'] = str(result.magR)
                messierDict['magI'] = str(result.magI)
                messierDict['numReferences'] = str(result.numReferences)

                etree.SubElement(imageSubElement, "MessierRecord", messierDict)

            gcvsResults = GCVSRecord.objects.filter(geometry__dwithin=(plateSolution.geometry, bufferDistance))

            for result in gcvsResults:
                x, y = w.all_world2pix(result.ra, result.dec, 1)    #TODO: Determine if this 1 should be a 0.
                gcvsDict = {}
                gcvsDict['id'] = str(result.pk)
                gcvsDict['identifier'] = str(result.identifier)
                gcvsDict['ra'] = str(result.ra)
                gcvsDict['dec'] = str(result.dec)
                gcvsDict['pixelX'] = str(x)
                gcvsDict['pixelY'] = str(y)
                gcvsDict['constellationNumber'] = str(result.constellationNumber)
                gcvsDict['starNumber'] = str(result.starNumber)
                gcvsDict['pmRA'] = str(result.pmRA)
                gcvsDict['pmDec'] = str(result.pmDec)
                gcvsDict['variableType'] = str(result.variableType)
                gcvsDict['variableType2'] = str(result.variableType2)
                gcvsDict['magMax'] = str(result.magMax)
                gcvsDict['magMaxFlag'] = str(result.magMaxFlag)
                gcvsDict['magMin'] = str(result.magMin)
                gcvsDict['magMinFlag'] = str(result.magMinFlag)
                gcvsDict['magMin2'] = str(result.magMin2)
                gcvsDict['magMin2Flag'] = str(result.magMin2Flag)
                gcvsDict['epochMaxMag'] = str(result.epochMaxMag)
                gcvsDict['outburstYear'] = str(result.outburstYear)
                gcvsDict['period'] = str(result.period)
                gcvsDict['periodRisingPercentage'] = str(result.periodRisingPercentage)
                gcvsDict['spectralType'] = str(result.spectralType)

                etree.SubElement(imageSubElement, "GCVSRecord", gcvsDict)

            asteroidResults = getAsteroidsAroundGeometry(plateSolution.geometry, bufferDistance, image.dateTime, 999, 1000)

            for result in asteroidResults:
                x, y = w.all_world2pix(result['ephem'].ra*(180/math.pi), result['ephem'].dec*(180/math.pi), 1)    #TODO: Determine if this 1 should be a 0.
                asteroidDict = {}
                asteroidDict['id'] = str(result['record'].pk)
                asteroidDict['number'] = str(result['record'].number)
                asteroidDict['name'] = str(result['record'].name)
                asteroidDict['ra'] = str(result['ephem'].ra*(180/math.pi))
                asteroidDict['dec'] = str(result['ephem'].dec*(180/math.pi))
                asteroidDict['mag'] = str(result['ephem'].mag)
                asteroidDict['pixelX'] = str(x)
                asteroidDict['pixelY'] = str(y)

                etree.SubElement(imageSubElement, "AsteroidEphemerisShortRecord", asteroidDict)

            exoplanetResults = ExoplanetRecord.objects.filter(geometry__dwithin=(plateSolution.geometry, bufferDistance))

            for result in exoplanetResults:
                x, y = w.all_world2pix(result.ra, result.dec, 1)    #TODO: Determine if this 1 should be a 0.
                exoplanetDict = {}
                exoplanetDict['id'] = str(result.pk)
                exoplanetDict['identifier'] = str(result.identifier)
                exoplanetDict['identifier2'] = str(result.identifier2)
                exoplanetDict['starIdentifier'] = str(result.starIdentifier)
                exoplanetDict['component'] = str(result.component)
                exoplanetDict['numComponents'] = str(result.numComponents)
                exoplanetDict['ra'] = str(result.ra)
                exoplanetDict['dec'] = str(result.dec)
                exoplanetDict['pixelX'] = str(x)
                exoplanetDict['pixelY'] = str(y)
                exoplanetDict['magV'] = str(result.magV)
                exoplanetDict['period'] = str(result.period)
                exoplanetDict['transitEpoch'] = str(result.transitEpoch)
                exoplanetDict['transitDuration'] = str(result.transitDuration)
                exoplanetDict['transitDepth'] = str(result.transitDepth)

                etree.SubElement(imageSubElement, "ExoplanetRecord", exoplanetDict)

            ucac4Results = UCAC4Record.objects.filter(geometry__dwithin=(plateSolution.geometry, bufferDistance))

            for result in ucac4Results:
                x, y = w.all_world2pix(result.ra, result.dec, 1)    #TODO: Determine if this 1 should be a 0.
                ucac4Dict = {}
                ucac4Dict['id'] = str(result.pk)
                ucac4Dict['identifier'] = str(result.identifier)
                ucac4Dict['ra'] = str(result.ra)
                ucac4Dict['dec'] = str(result.dec)
                ucac4Dict['pmra'] = str(result.pmra)
                ucac4Dict['pmdec'] = str(result.pmdec)
                ucac4Dict['pixelX'] = str(x)
                ucac4Dict['pixelY'] = str(y)
                ucac4Dict['magFit'] = str(result.magFit)
                ucac4Dict['magAperture'] = str(result.magAperture)
                ucac4Dict['magError'] = str(result.magError)
                ucac4Dict['id2mass'] = str(result.id2mass)

                etree.SubElement(imageSubElement, "UCAC4Record", ucac4Dict)

    elif request.GET['queryfor'] == 'ota':
        results = OTA.objects
        results = results.order_by('make', 'model', 'aperture', 'design', 'focalLength')

        for result in results:
            otaDict = {}
            otaDict['id'] = str(result.pk)
            otaDict['make'] = str(result.make)
            otaDict['model'] = str(result.model)
            otaDict['focalLength'] = str(result.focalLength)
            otaDict['aperture'] = str(result.aperture)
            otaDict['design'] = str(result.design)

            etree.SubElement(root, "OTA", otaDict)

    elif request.GET['queryfor'] == 'camera':
        results = Camera.objects
        results = results.order_by('make', 'model')

        for result in results:
            cameraDict = {}
            cameraDict['id'] = str(result.pk)
            cameraDict['make'] = str(result.make)
            cameraDict['model'] = str(result.model)
            cameraDict['dimX'] = str(result.dimX)
            cameraDict['dimY'] = str(result.dimY)
            cameraDict['pixelDimX'] = str(result.pixelDimX)
            cameraDict['pixelDimY'] = str(result.pixelDimY)
            cameraDict['readNoise'] = str(result.readNoise)
            cameraDict['ePerADU'] = str(result.ePerADU)
            cameraDict['exposureMin'] = str(result.exposureMin)
            cameraDict['exposureMax'] = str(result.exposureMax)
            cameraDict['coolingCapacity'] = str(result.coolingCapacity)

            etree.SubElement(root, "Camera", cameraDict)

    #TODO: Also write the values used in the query into the result, so the client can check if the limit they set was reduced, etc.
    return HttpResponse(etree.tostring(root, pretty_print=False), content_type='application/xml')

def questions(request):
    context = {"user" : request.user}

    return render(request, "cosmicapp/questions.html", context)

def equipment(request):
    def validateRequiredFields(reqFields):
        missingFields = []
        for field in reqFields:
            if not field in request.POST:
                missingFields.append(field)
                continue

            if request.POST[field].strip() == '':
                missingFields.append(field)

        return missingFields

    context = {"user" : request.user}

    if request.method == 'POST' and request.user.is_authenticated:
    #TODO: Store user who created this equipment.
        if request.POST['equipmentType'] == 'ota':
            missingFields = validateRequiredFields( ('make', 'model', 'aperture', 'focalLength', 'design') )
            if len(missingFields) > 0:
                context['otaMessage'] = 'ERROR: Missing fields: ' + ', '.join(missingFields)
            else:
                newOTA, created = OTA.objects.get_or_create(
                    make = request.POST['make'].strip(),
                    model = request.POST['model'].strip(),
                    focalLength = request.POST['focalLength'].strip(),
                    aperture = request.POST['aperture'].strip(),
                    design = request.POST['design'].strip()
                    )

                if created:
                    context['otaMessage'] = 'New OTA Created'
                else:
                    context['otaMessage'] = 'OTA was identical to an existing OTA, no duplicate created.'

        elif request.POST['equipmentType'] == 'Camera':
            missingFields = validateRequiredFields( ('make', 'model', 'dimX', 'dimY') )
            if len(missingFields) > 0:
                context['cameraMessage'] = 'ERROR: Missing fields: ' + ', '.join(missingFields)
            else:
                newCamera, created = Camera.objects.get_or_create(
                    make = request.POST['make'].strip(),
                    model = request.POST['model'].strip(),
                    dimX = request.POST['dimX'].strip(),
                    dimY = request.POST['dimY'].strip(),
                    pixelDimX = request.POST['pixelDimX'].strip(),
                    pixelDimY = request.POST['pixelDimY'].strip(),
                    readNoise = request.POST['readNoise'].strip(),
                    ePerADU = request.POST['ePerADU'].strip(),
                    exposureMin = request.POST['exposureMin'].strip(),
                    exposureMax = request.POST['exposureMax'].strip(),
                    coolingCapacity = request.POST['coolingCapacity'].strip()
                    )

                if created:
                    context['cameraMessage'] = 'New Camera Created'
                else:
                    context['cameraMessage'] = 'Camera was identical to an existing Camera, no duplicate created.'

    return render(request, "cosmicapp/equipment.html", context)

@login_required
def questionImage(request, id):
    context = {"user" : request.user}
    context['id'] = id

    try:
        image = Image.objects.get(pk=id)
    except Image.DoesNotExist:
        return render(request, "cosmicapp/imagenotfound.html", context)

    context['image'] = image

    if request.method == 'POST':
        question = Question.objects.get(pk=int(request.POST['questionID']))
        user = User.objects.get(pk=request.user.id)

        #TODO: If the user clicks 'submit' without entering an answer a blank answer gets entered and the site thinks
        # the question has been answered.  This needs to be addressed by checking that there is something other than the
        # csrf token and questionID in the post results.
        #TODO: Need to check to see that this user has not already answered this question before.  If so, decide how to
        # handle it.  (this will be common if a user hits 'reload' on the page and resends the post data)
        with transaction.atomic():
            answer = Answer(
                question = question,
                user = user,
                dateTime = timezone.now(),
                content_object = image
                )

            answer.save()

            p = request.POST
            for entry in request.POST:
                if entry in ['csrfmiddlewaretoken', 'questionID']:
                    continue

                kv = AnswerKV(
                    answer = answer,
                    key = entry,
                    value = request.POST[entry]
                    )

                kv.save()

    return render(request, "cosmicapp/questionImage.html", context)

@login_required
def getQuestionImage(request, id):
    context = {"user" : request.user}

    root = etree.Element("queryresult")

    try:
        image = Image.objects.get(pk=id)
    except Image.DoesNotExist:
        #TODO: Convert this to xml.
        return HttpResponse("bad request: image not found")

    questions = Question.objects.all().order_by('-priority')

    questionFound = False
    for question in questions:
        # Check to see what type of object this question pertains to.
        # Right now we only handle images in this function.
        if question.aboutType != 'Image':
            continue

        #TODO: Check if this question is an earlier version of another question and if so, skip it.

        # Check to see if this user has already answered this question for this image, if they have then skip it.
        imageContentType = ContentType.objects.get_for_model(Image)
        if Answer.objects.filter(question=question.pk, user=request.user.pk,
                                content_type__pk=imageContentType.pk, object_id=image.id).count() > 0:
            continue

        # Check for prerequisites to this question to see if it is appropriate to ask based on previously answered questions.
        #NOTE: There is a possible optimisation where we exit these loops early if allPreconditionsMet ever becomes
        # false, but I don't think it is worth the extra code clutter since the loops should all be short anyway.
        allPreconditionsMet = True
        preconditions = AnswerPrecondition.objects.filter(secondQuestion=question.pk)
        for precondition in preconditions:
            # For each precondition, get any answers to the first question that the user has already provided.
            previousAnswers = Answer.objects.filter(question=precondition.firstQuestion, user=request.user.pk,
                                    content_type__pk=imageContentType.pk, object_id=image.id)

            # If the user has not answered the previous question at all, then the precondition is definitely not met.
            if len(previousAnswers) == 0:
                allPreconditionsMet = False
                break

            # The user has answered the previous question, so now loop over any additional conditions and check each one
            # to make sure that the answer to the previous question was an appropriate answer to make this question relevant.
            pccs = AnswerPreconditionCondition.objects.filter(answerPrecondition=precondition.pk)
            for pcc in pccs:

                # For each previous answer check that that answer meets all the conditions.
                for answer in previousAnswers:

                    # Split the key/value into the 'or' components and loop over them checking to see that at least
                    # one is true.
                    oneOrIsTrue = False
                    orKeys = pcc.key.split('|')
                    orValues = pcc.value.split('|')
                    for orKey, orValue in zip(orKeys, orValues):

                        # Loop over all the key-value pairs for the given answer and check that each one is consistent with
                        # the current pcc we are checking.
                        kvs = AnswerKV.objects.filter(answer=answer.pk)
                        for kv in kvs:

                            # If the keys are different then just skip to the next one as the pcc has nothing to say about
                            # this particular key.
                            if orKey != kv.key:
                                continue

                            # If the keys do match then check to see if the values match as well.
                            valuesMatch = (orValue == kv.value)

                            # Finally check whether we want the values to match or to NOT match, depending on the invert flag.
                            #NOTE: If invert is true and there are multiple entries on an 'or' clause it will behave
                            #funny.  This probably doesn't need to be fixed but it is technically a bug.
                            if valuesMatch == pcc.invert:
                                allPreconditionsMet = False
                            else:
                                oneOrIsTrue = True

                    # If at least one of the 'or' conditons was met we pass, otherwise if none were met we fail.
                    if (not pcc.invert) and (not oneOrIsTrue):
                        allPreconditionsMet = False

        if not allPreconditionsMet:
            continue

        questionFound = True

        responses = QuestionResponse.objects.filter(question=question.pk).order_by('index')
        responsesHTML = ''
        responsesHTML += "<input type='hidden' name='csrfmiddlewaretoken' value='" + csrf.get_token(request) + "' />\n"
        responsesHTML += "<input type='hidden' name='questionID' value='" + str(question.pk) + "' />\n"
        for response in responses:
            if response.inputType == 'radioButton':
                responsesHTML += '<input type="radio" name="' + response.keyToSet +'" value="' + response.valueToSet + '">'
                responsesHTML += response.text + ' - <i>' + response.descriptionText + '</i><br>\n\n'
            elif response.inputType == 'checkbox':
                responsesHTML += '<input type="checkbox" name="' + response.keyToSet +'" value="' + response.valueToSet + '">'
                responsesHTML += response.text + ' - <i>' + response.descriptionText + '</i><br>\n\n'

        questionDict = {}
        questionDict['id'] = str(question.pk)
        questionDict['text'] = question.text
        questionDict['descriptionText'] = question.descriptionText
        questionDict['titleText'] = question.titleText
        questionDict['responsesHTML'] = responsesHTML

        etree.SubElement(root, "Question", questionDict)
        break

    if not questionFound:
        #TODO: Make this query a bit better to only find images needing questions answered and also don't just stop at the highest number.
        nextImage = Image.objects.filter(pk__gt=id, fileRecord__uploadingUser=request.user.pk)[0:1]
        if len(nextImage) > 0:
            nextImageDict = {'id': str(nextImage[0].pk)}
            etree.SubElement(root, "NextImage", nextImageDict)

    return HttpResponse(etree.tostring(root, pretty_print=False), content_type='application/xml')

@login_required
def mosaic(request):
    context = {"user" : request.user}

    return render(request, "cosmicapp/mosaic.html", context)

@login_required
@require_http_methods(['POST'])
def saveTransform(request):
    referenceId = request.POST.get('referenceId', None)
    subjectId = request.POST.get('subjectId', None)
    m00 = request.POST.get('m00', None)
    m01 = request.POST.get('m01', None)
    m02 = request.POST.get('m02', None)
    m10 = request.POST.get('m10', None)
    m11 = request.POST.get('m11', None)
    m12 = request.POST.get('m12', None)

    for variable in [referenceId, subjectId, m00, m01, m02, m10, m11, m12]:
        if variable == None:
            return HttpResponse('', status=400, reason='Parameters missing.')

    referenceId = int(referenceId)
    subjectId = int(subjectId)
    m00 = float(m00)
    m01 = float(m01)
    m02 = float(m02)
    m10 = float(m10)
    m11 = float(m11)
    m12 = float(m12)

    transform = ImageTransform.objects.filter(user=request.user.pk, referenceImage=referenceId, subjectImage=subjectId)
    if len(transform) > 0:
        record = transform[0]
    else:
        try:
            referenceImage = Image.objects.get(pk=referenceId)
            subjectImage = Image.objects.get(pk=subjectId)
        except Image.DoesNotExist:
            return HttpResponse('', status=400, reason='Image not found.')

        record = ImageTransform(
            user = request.user,
            referenceImage = referenceImage,
            subjectImage = subjectImage
        )

    record.m00 = m00
    record.m01 = m01
    record.m02 = m02
    record.m10 = m10
    record.m11 = m11
    record.m12 = m12
    record.save()

    return HttpResponse('')

@login_required
@require_http_methods(['POST'])
def saveUserSubmittedSourceResults(request):
    id = int(request.POST.get('imageId', '-1'))
    if id != -1:
        image = Image.objects.get(pk=id)
    else:
        return HttpResponse(json.dumps({'text': 'Image Not Found: ' + str(request.POST.get('imageId')),}), status=400,  reason='Image Not Found.')

    userResults = json.loads(request.POST.get('userResults'))
    for result in userResults:
        userSubmittedResult = UserSubmittedResult(
            user = request.user,
            image = image,
            pixelX = float(result['x']),
            pixelY = float(result['y']),
            pixelZ = None,  #TODO: Handle multi extension files.
            confidence = 1.0
            )

        userSubmittedResult.save()

    userHotPixels = json.loads(request.POST.get('hotPixels'))
    for result in userHotPixels:
        userSubmittedHotPixel = UserSubmittedHotPixel(
            user = request.user,
            image = image,
            pixelX = float(result['x']),
            pixelY = float(result['y']),
            pixelZ = None,  #TODO: Handle multi extension files.
            confidence = 1.0
            )

        userSubmittedHotPixel.save()

    with transaction.atomic():
        #TODO: We only need to add a flagSources task if the use submitted new hot pixels in the request.
        piFlagSources = ProcessInput(
            process = "flagSources",
            requestor = User.objects.get(pk=request.user.pk),
            submittedDateTime = timezone.now(),
            priority = ProcessPriority.getPriorityForProcess("flagSources", "interactive") + 0.8,
            estCostCPU = 10,
            estCostBandwidth = 0,
            estCostStorage = 0,
            estCostIO = 10000
            )

        piFlagSources.save()
        piFlagSources.addArguments([str(image.pk)])

        piStarmatch = ProcessInput(
            process = "starmatch",
            requestor = User.objects.get(pk=request.user.pk),
            submittedDateTime = timezone.now(),
            priority = ProcessPriority.getPriorityForProcess("starmatch", "interactive") + 0.7,
            estCostCPU = 10,
            estCostBandwidth = 0,
            estCostStorage = 3000,
            estCostIO = 10000
            )

        piStarmatch.save()
        piStarmatch.addArguments([image.fileRecord.onDiskFileName])
        piStarmatch.prerequisites.add(piFlagSources)

        piAstrometryNet = ProcessInput(
            process = "astrometryNet",
            requestor = User.objects.get(pk=request.user.pk),
            submittedDateTime = timezone.now(),
            priority = ProcessPriority.getPriorityForProcess("starmatch", "interactive") + 0.5,
            estCostCPU = 100,
            estCostBandwidth = 3000,
            estCostStorage = 3000,
            estCostIO = 10000000000
            )

        piAstrometryNet.save()
        piAstrometryNet.addArguments([image.fileRecord.onDiskFileName])
        piAstrometryNet.prerequisites.add(piFlagSources)

    return HttpResponse(json.dumps({'text': 'Response Saved Successfully'}), status=200)

@login_required
@require_http_methods(['POST'])
def bookmark(request):

    def getResultDictForBookmarkObject(targetObject, user):
        bookmarks = targetObject.bookmarks.filter(user=user)
        tempDict = {}
        tempDict['count'] = bookmarks.count()
        tempDict['folders'] = []
        for bookmark in bookmarks:
            for folder in bookmark.folders.all():
                tempDict['folders'].append(folder.name)

        return tempDict

    action = request.POST.get('action', None)
    targetType = request.POST.get('targetType', None)
    targetID = request.POST.get('targetID', None)
    folderName = request.POST.get('folderName', None)

    typeDict = {
        'asteroid': AstorbRecord,
        'exoplanet': ExoplanetRecord,
        'variableStar': GCVSRecord,
        'messierObject': MessierRecord,
        '2MassXSC': TwoMassXSCRecord
        }

    if targetType != None:
        if targetType not in typeDict:
            return HttpResponse(json.dumps({'error': 'unknown object type: ' + targetType}), status=400)

    if action == 'query':
        #TODO: Consider splitting the query targets into types on the client side and sending an array of id's for each
        # object type to both minimize bandwidth and also reduce load on the server.
        idDict = {}
        for item in request.POST.get('queryString').strip(' ').split(' '):
            obj = item.split('_')
            if obj[0] in idDict:
                if obj[1] not in idDict[obj[0]]:
                    idDict[obj[0]].append(obj[1])
            else:
                idDict[obj[0]] = [ obj[1] ]

        resultDict = {}
        for targetType in idDict:
            if targetType in typeDict:
                targetObjects = typeDict[targetType].objects.filter(pk__in=idDict[targetType])

                for targetObject in targetObjects:
                    resultDict[targetType + '_' + str(targetObject.pk)] = getResultDictForBookmarkObject(targetObject, request.user)
            else:
                return HttpResponse(json.dumps({'error': 'unknown object type: ' + targetType}), status=400)

        #print(json.dumps(resultDict, sort_keys=True, indent=4, separators=(',', ': ')))
        return HttpResponse(json.dumps(resultDict))

    elif action == 'queryFolderForObserving':
        if folderName == None:
            return HttpResponse(json.dumps({'error': 'no folder name specified'}), status=400)

        includeOtherTargets = True if request.POST.get('includeOtherTargets', 'false').lower == 'true' else False
        startTime = dateparser.parse(request.POST.get('startTime', str(timezone.now())),
                                     settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True})
        endTime = dateparser.parse(request.POST.get('endTime', str(timezone.now() + timedelta(hours=4))),
                                     settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True})
        minTimeBetween = float(request.POST.get('minTimeBetween', 0))
        maxTimeBetween = float(request.POST.get('maxTimeBetween', 120))
        limitingMag = float(request.POST.get('limitingMag', 16))
        minimumScore = float(request.POST.get('minimumScore', 0))
        observatoryID = int(request.POST.get('observatoryID', -1))

        folder = BookmarkFolder.objects.filter(user=request.user, name=folderName).first()
        bookmarks = Bookmark.objects.filter(folders=folder)  #TODO: This probably fails for bookmarks which are in more than one folder.
        observatory = Observatory.objects.filter(pk=observatoryID).first()
        observingPlan = formulateObservingPlan(request.user, observatory, bookmarks, includeOtherTargets, startTime, endTime,
                                               minTimeBetween, maxTimeBetween, limitingMag, minimumScore)

        return HttpResponse(json.dumps(observingPlan))

    elif action == 'add':
        targetObject = typeDict[targetType].objects.get(pk=targetID)
        content_type = ContentType.objects.get_for_model(targetObject)

        bookmark, created = Bookmark.objects.get_or_create(
            user = request.user,
            content_type = content_type,
            object_id = targetObject.pk
            )

        if folderName != None:
            folder = BookmarkFolder.objects.filter(user=request.user, name=folderName).first()

            if folder == None:
                #TODO: Sanitize folder name.
                folder = BookmarkFolder(
                    user = request.user,
                    name = folderName
                    )

                folder.save()

            link = BookmarkFolderLink(
                bookmark = bookmark,
                folder = folder
                )

            link.save()

        responseDict = {}
        responseDict['code'] = 'added'
        responseDict['info'] = getResultDictForBookmarkObject(targetObject, request.user)

        return HttpResponse(json.dumps(responseDict))

    elif action == 'remove':
        targetObject = typeDict[targetType].objects.get(pk=targetID)

        bookmarks = targetObject.bookmarks.filter(user=request.user)
        for bookmark in bookmarks:
            linkRemoved = False
            if folderName != None:
                for folder in bookmark.folders.all():
                    if folder.name == folderName:
                        BookmarkFolderLink.objects.get(bookmark=bookmark, folder=folder).delete()
                        linkRemoved = True

            if (linkRemoved and bookmark.folders.count() == 0) or (folderName == None and bookmarks.folders.count() == 0):
                bookmark.delete()

        responseDict = {}
        responseDict['code'] = 'removed'
        responseDict['info'] = getResultDictForBookmarkObject(targetObject, request.user)

        return HttpResponse(json.dumps(responseDict))

    elif action == 'newFolder':
        newFolderName = request.POST.get('newFolderName', None)
        redirectUrl = request.POST.get('redirectUrl', None)

        newFolder, created = BookmarkFolder.objects.get_or_create(
            user = request.user,
            name = newFolderName
            )

        responseDict = {}
        if created:
            newFolder.save()
            responseDict['code'] = 'createdFolder'
        else:
            responseDict['code'] = 'folderAlreadyExisted'

        if redirectUrl != None:
            return HttpResponseRedirect(redirectUrl)

        return HttpResponse(json.dumps(responseDict))

    elif action == 'removeFolder':
        try:
            targetFolder = BookmarkFolder.objects.get(user=request.user, name=folderName)
        except BookmarkFolder.DoesNotExist:
            return HttpResponse(json.dumps({'error' : 'folder does not exist: ' + folderName}), status=400)

        links = BookmarkFolderLink.objects.filter(folder=targetFolder)
        for link in links:
            bookmark = link.bookmark
            link.delete()
            if bookmark.folders.count() == 0:
                bookmark.delete()

        targetFolder.delete()

        responseDict = {}
        responseDict['code'] = 'removedFolder'

        return HttpResponse(json.dumps(responseDict))

    elif action == 'queryStartEndTime':
        inputDate = dateparser.parse(request.POST.get('inputDate', None))
        startTime = request.POST.get('startTime', None)
        observingDuration = float(request.POST.get('observingDuration', None))
        observatoryID = int(request.POST.get('observatoryID', None))

        observatory = Observatory.objects.filter(pk=observatoryID).first()

        if observatory == None:
            return HttpResponse(json.dumps({'error' : 'Observatory not found with id: ' + observatoryID}), status=400)

        observer = ephem.Observer()
        observer.lat, observer.lon = observatory.lat*math.pi/180.0, observatory.lon*math.pi/180.0
        observer.date = inputDate

        observingDurationDelta = timedelta(seconds=observingDuration)

        #TODO: Make next_setting, etc, optionally run a while loop if it throws a circumpolar or never_rises error.
        if startTime == 'rightNow':
            startTime = datetime.now()
            endTime = startTime + observingDurationDelta

        elif startTime == 'evening':
            startTime = dateparser.parse(str(observer.next_setting(ephem.Sun())))
            endTime = startTime + observingDurationDelta

        elif startTime == 'midnight':
            startTime = dateparser.parse(str(observer.next_antitransit(ephem.Sun()))) - (observingDurationDelta/2)
            endTime = startTime + (observingDurationDelta/2)

        elif startTime == 'morning':
            endTime = dateparser.parse(str(observer.next_rising(ephem.Sun())))
            startTime = endTime - observingDurationDelta

        elif startTime == 'daytimeMorning':
            startTime = dateparser.parse(str(observer.next_rising(ephem.Sun())))
            endTime = startTime + observingDurationDelta

        elif startTime == 'noon':
            startTime = dateparser.parse(str(observer.next_transit(ephem.Sun()))) - (observingDurationDelta/2)
            endTime = startTime + (observingDurationDelta/2)

        elif startTime == 'daytimeEvening':
            endTime = dateparser.parse(str(observer.next_setting(ephem.Sun())))
            startTime = endTime - observingDurationDelta

        else:
            return HttpResponse(json.dumps({'error' : 'unknown startTime: ' + str(startTime)}), status=400)

        return HttpResponse(json.dumps({'startTime' : str(startTime), 'endTime' : str(endTime)}))

    else:
        return HttpResponse(json.dumps({'error' : 'unknown action: ' + action}), status=400)

    return HttpResponse(json.dumps({'error' : "reached end of function and shouldn't have."}), status=400)

@login_required
def bookmarkPage(request, username):
    context = {"user" : request.user}

    try:
        foruser = User.objects.get(username = username)
    except User.DoesNotExist:
        context['foruser'] = username
        return render(request, "cosmicapp/usernotfound.html", context)

    context['foruser'] = foruser

    folders = BookmarkFolder.objects.filter(user=foruser).order_by('-dateTime')
    context['folders'] = folders

    return render(request, "cosmicapp/bookmark.html", context)

@login_required
def calibration(request):
    context = {"user" : request.user}

    return render(request, "cosmicapp/calibration.html", context)

def observing(request):
    context = {"user" : request.user}
    promptProfileEdit = False
    profileMissingFields = []

    if request.user.is_authenticated:
        context['otherObservatories'] = Observatory.objects.filter(user=request.user).order_by('-pk')
        if request.user.profile.defaultObservatory != None:
            context['otherObservatories'] = context['otherObservatories'].exclude(pk=request.user.profile.defaultObservatory.pk)

    if 'ele' in request.GET:
        ele = float(request.GET['ele'])
    else:
        ele = 0

    if 'limitingMag' in request.GET:
        limitingMag = float(request.GET['limitingMag'])
    else:
        limitingMag = 16
        if request.user.is_authenticated:
            if request.user.profile.limitingMag != None:
                limitingMag = request.user.profile.limitingMag

    if 'windowSize' in request.GET:
        windowSize = float(request.GET['windowSize'])
    else:
        windowSize = 30

    #TODO: Provide a input field like the ones for lat/lon/etc to set the observation date and then use position to calculate evening/midnight/morning for that location.

    lat = None
    lon = None
    if 'lat' in request.GET and 'lon' in request.GET:
        lat = float(request.GET['lat'])
        lon = float(request.GET['lon'])
    else:
        if request.user.is_authenticated:
            if request.user.profile.defaultObservatory != None:
                lat = request.user.profile.defaultObservatory.lat
                lon = request.user.profile.defaultObservatory.lon
                ele = request.user.profile.defaultObservatory.elevation
            #TODO: Set limiting mag from user profile.

            if lat == None or lon == None:
                (lat, lon) = getLocationForIp(getClientIp(request))
                promptProfileEdit = True
                profileMissingFields.append('Latitude and Longitude')

            if ele == None:
                ele = 0
                promptProfileEdit = True
                profileMissingFields.append('Elevation')
        else:
            (lat, lon) = getLocationForIp(getClientIp(request))

    limit = 10
    if 'limit' in request.GET:
        limit = int(request.GET['limit'])

    if limit > 500:
        limit = 500;

    if windowSize > 90:
        windowSize = 90

    context['lat'] = lat
    context['lon'] = lon
    context['ele'] = ele
    context['limitingMag'] = limitingMag
    context['windowSize'] = windowSize
    context['limit'] = limit

    context['promptProfileEdit'] = promptProfileEdit
    context['profileMissingFields'] = profileMissingFields

    currentTime = timezone.now()
    context['currentTime'] = currentTime

    observerNow = ephem.Observer()
    observerNow.lat = lat*(math.pi/180)
    observerNow.lon = lon*(math.pi/180)
    observerNow.elevation = ele
    observerNow.date = currentTime

    zenithNowRA, zenithNowDec = observerNow.radec_of('0', '90')

    context['observerNow'] = observerNow
    context['zenithNowRA'] = zenithNowRA
    context['zenithNowDec'] = zenithNowDec

    zenithNowRA = zenithNowRA * 180/math.pi
    zenithNowDec = zenithNowDec * 180/math.pi
    zenithGeometry = GEOSGeometry('POINT({} {})'.format(zenithNowRA, zenithNowDec))

    variableStars = GCVSRecord.objects.filter(
        geometry__dwithin=(zenithGeometry, windowSize),
        magMin__lt=limitingMag
        ).order_by('magMin')[:limit]

    context['variableStars'] = variableStars

    exoplanets = ExoplanetRecord.objects.filter(
        geometry__dwithin=(zenithGeometry, windowSize),
        magV__lt=limitingMag
        ).order_by('magV', 'identifier')[:limit]

    context['exoplanets'] = exoplanets

    messierObjects = MessierRecord.objects.filter(
        geometry__dwithin=(zenithGeometry, windowSize),
        magV__lt=limitingMag
        ).order_by('magV')[:limit]

    context['messierObjects'] = messierObjects

    extendedSources = TwoMassXSCRecord.objects.filter(
        geometry__dwithin=(zenithGeometry, windowSize),
        isophotalKMag__lt=limitingMag
        ).order_by('isophotalKMag')[:limit]

    context['extendedSources'] = extendedSources

    asteroids = getAsteroidsAroundGeometry(zenithGeometry, windowSize, currentTime, limitingMag, limit)

    #asteroids = sorted(asteroids, key = lambda x: x['record'].ceu, reverse=True)[:limit]

    context['asteroids'] = asteroids

    return render(request, "cosmicapp/observing.html", context)

@login_required
def exportBookmarks(request):
    #TODO: We should store both the output of the observing plan routine as well as a
    # database record for each row of observing suggestion we send to the user.  Then later
    # when they upload data to us we can correlate it against what we told them to image and
    # this will help in finding plate solutions for tricky plates, etc.
    context = {"user" : request.user}

    if request.method == "POST":
        fileName = 'export.txt'
        fileContent = ''

        folderName = request.POST.get('folderName', None)
        fileFormat = request.POST.get('fileFormat', None)
        observingPlan = json.loads(request.POST.get('observingPlan', None))
        observingPlan.sort(key=lambda x: x['startTime'])

        if folderName == None or fileFormat == None:
            return HttpResponse('bad request: parameters missing', status=400, reason='Parameters missing.')

        #TODO: Add file format: ekos scheduler list / ekos sequence queue.
        #TODO: Add file format: itelescope.net 'image' plan file.
        if fileFormat == 'oal':
            fileName = 'Observing_List.xml'   #TODO: Set a date on the filename or something.
            root = etree.Element("observations")
            targets = etree.SubElement(root, "targets")

            for t in observingPlan:
                targetDict = {}
                targetDict['id'] = t['identifier']
                targetDict['type'] = t['type']
                target = etree.SubElement(targets, "target", targetDict)

                datasource = etree.SubElement(target, "datasource")
                datasource.text = "Cosmic.science"

                name = etree.SubElement(target, "name")
                name.text = t['identifier']

                position = etree.SubElement(target, "position")
                ra = etree.SubElement(position, "ra", {'unit': 'rad'})
                dec = etree.SubElement(position, "dec", {'unit': 'rad'})
                #TODO: Need to properly set these.
                ra.text = str(0)
                dec.text = str(0)

            fileContent = etree.tostring(root, pretty_print=True)

        elif fileFormat == 'human':
            fileName = 'Observing_List.txt'   #TODO: Set a date on the filename or something.
            #TODO: Include details about date/location/etc/user and maybe a unique ID.
            fileContent += 'Observing plan:\n\n\n'
            for t in observingPlan:
                #TODO: Include magnitude.
                fileContent += (
                    '========== {} ==========\n'
                    'Object Type: {}\n'
                    'RA: {}    Dec: {}\n'
                    'Score: {}\n'
                    '\n'
                    'Observation Start Time: {}\n'
                    'Rise: {}    Transit: {}    Set: {}\n'
                    '\n'
                    'Scheduled for {} exposures of {} seconds each.\n'
                    '\n'
                    'Observing Notes: \n\n\n\n\n' #TODO: Add Fields for seeing, weather, etc.
                    '\n'
                    ).format(t['identifier'], t['type'], t['ra'], t['dec'], t['score'], t['startTime'], t['nextRising'], t['nextTransit'],
                             t['nextSetting'], t['numExposures'], t['exposureTime'])

        else:
            return HttpResponse('bad request: unknown file format', status=400)

        response = HttpResponse(fileContent, content_type='application/force-download')
        response['Content-Disposition'] = 'attachment; filename=' + fileName
        #TODO: It's usually a good idea to set the 'Content-Length' header too.
        #TODO: You can also set any other required headers: Cache-Control, etc.
        return response

    # If we got here the method is not POST so just build and render the export form.
    folders = BookmarkFolder.objects.filter(user=request.user).order_by('name')
    context['folders'] = folders

    defaultObservatory = request.user.profile.defaultObservatory
    observatories = [ defaultObservatory ] if defaultObservatory != None else []

    otherObservatories = Observatory.objects.filter(user=request.user)
    if defaultObservatory != None:
        otherObservatories = otherObservatories.exclude(pk=defaultObservatory.pk)
    otherObservatories = otherObservatories.order_by('-pk')

    for observatory in otherObservatories:
        observatories.append(observatory)

    context['observatories'] = observatories

    return render(request, "cosmicapp/exportBookmarks.html", context)

