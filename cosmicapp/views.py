import hashlib
import os

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
from django.db.models import Q
from django.db import transaction

from lxml import etree

from .models import *
from .forms import *

def index(request):
    context = {"user" : request.user}
    return render(request, "cosmicapp/index.html", context)

def createuser(request):
    context = {"user" : request.user}

    #TODO: Need a lot more validation here.
    if request.method == 'POST':
        p = request.POST
        if p['password'] != p['repeatpassword']:
            context['usercreationerror'] = "Entered passwords do not match"
        else:
            User.objects.create_user(p['username'], p['email'], p['password'])
            return HttpResponseRedirect('/login/')

    return render(request, "cosmicapp/createuser.html", context)

@login_required
def upload(request):
    context = {"user" : request.user}
    context['supportedImageTypes'] = settings.SUPPORTED_IMAGE_TYPES

    if request.method == 'POST' and 'myfiles' in request.FILES:
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

            #TODO: Need to wrap creation of these process inputs in a transaction so that processes and prerequisites are entered fully before any tasks start executing
            if fileExtension.lower() in settings.SUPPORTED_IMAGE_TYPES:
                imageRecord = Image(
                    fileRecord = record
                    )

                imageRecord.save()

                pi = ProcessInput(
                    process = "imagestats",
                    requestor = User.objects.get(pk=request.user.pk),
                    submittedDateTime = timezone.now(),
                    priority = 10000,
                    estCostCPU = record.uploadSize / 1e6,
                    estCostBandwidth = 0,
                    estCostStorage = 1000,
                    estCostIO = record.uploadSize
                    )

                pi.save()

                pa = ProcessArgument(
                    processInput = pi,
                    argIndex = 1,
                    arg = record.onDiskFileName
                    )

                pa.save()

                piThumbnails = ProcessInput(
                    process = "generateThumbnails",
                    requestor = User.objects.get(pk=request.user.pk),
                    submittedDateTime = timezone.now(),
                    priority = 5000,
                    estCostCPU = record.uploadSize / 1e6,
                    estCostBandwidth = 0,
                    estCostStorage = record.uploadSize / 10,
                    estCostIO = 1.5 * record.uploadSize
                    )

                piThumbnails.save()

                paThumbnails = ProcessArgument(
                    processInput = piThumbnails,
                    argIndex = 1,
                    arg = record.onDiskFileName
                    )

                paThumbnails.save()

                piSextractor = ProcessInput(
                    process = "sextractor",
                    requestor = User.objects.get(pk=request.user.pk),
                    submittedDateTime = timezone.now(),
                    priority = 3000,
                    estCostCPU = 2.0 * record.uploadSize / 1e6,
                    estCostBandwidth = 0,
                    estCostStorage = 3000,
                    estCostIO = record.uploadSize
                    )

                piSextractor.save()

                paSextractor = ProcessArgument(
                    processInput = piSextractor,
                    argIndex = 1,
                    arg = record.onDiskFileName
                    )

                paSextractor.save()

                piDaofind = ProcessInput(
                    process = "daofind",
                    requestor = User.objects.get(pk=request.user.pk),
                    submittedDateTime = timezone.now(),
                    priority = 3000,
                    estCostCPU = 2.0 * record.uploadSize / 1e6,
                    estCostBandwidth = 0,
                    estCostStorage = 3000,
                    estCostIO = record.uploadSize
                    )

                piDaofind.save()

                paDaofind = ProcessArgument(
                    processInput = piDaofind,
                    argIndex = 1,
                    arg = record.onDiskFileName
                    )

                paDaofind.save()

                piStarfind = ProcessInput(
                    process = "starfind",
                    requestor = User.objects.get(pk=request.user.pk),
                    submittedDateTime = timezone.now(),
                    priority = 3000,
                    estCostCPU = 2.0 * record.uploadSize / 1e6,
                    estCostBandwidth = 0,
                    estCostStorage = 3000,
                    estCostIO = record.uploadSize
                    )

                piStarfind.save()

                paStarfind = ProcessArgument(
                    processInput = piStarfind,
                    argIndex = 1,
                    arg = record.onDiskFileName
                    )

                paStarfind.save()

                piStarmatch = ProcessInput(
                    process = "starmatch",
                    requestor = User.objects.get(pk=request.user.pk),
                    submittedDateTime = timezone.now(),
                    priority = 3000,
                    estCostCPU = 10,
                    estCostBandwidth = 0,
                    estCostStorage = 3000,
                    estCostIO = 10000
                    )

                piStarmatch.save()

                paStarmatch = ProcessArgument(
                    processInput = piStarmatch,
                    argIndex = 1,
                    arg = record.onDiskFileName
                    )

                paStarmatch.save()
                piStarmatch.prerequisites.add(piSextractor)
                piStarmatch.prerequisites.add(piDaofind)
                piStarmatch.prerequisites.add(piStarfind)

                piHeaders = ProcessInput(
                    process = "parseheaders",
                    requestor = User.objects.get(pk=request.user.pk),
                    submittedDateTime = timezone.now(),
                    priority = 10000,
                    estCostCPU = .1,
                    estCostBandwidth = 0,
                    estCostStorage = 1000,
                    estCostIO = 2000,
                    )

                piHeaders.save()
                piHeaders.prerequisites.add(pi)

                paHeaders = ProcessArgument(
                    processInput = piHeaders,
                    argIndex = 1,
                    arg = imageRecord.pk
                    )

                paHeaders.save()

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
    if request.method == 'POST':
        if 'edit' in request.POST:
            context['edit'] = request.POST['edit']
        else:
            profileForm = ProfileForm(request.POST)

            if request.user.username == foruser.username and profileForm.is_valid():
                foruser.profile.homeLat = profileForm.cleaned_data['homeLat']
                foruser.profile.homeLon = profileForm.cleaned_data['homeLon']
                foruser.profile.birthDate = profileForm.cleaned_data['birthDate']
                foruser.profile.save()

                return HttpResponseRedirect('/user/' + foruser.username + '/')

    try:
        foruserImages = Image.objects.filter(fileRecord__uploadingUser = foruser.id)
        context['foruserImages'] = foruserImages
    except :
        pass


    return render(request, "cosmicapp/userpage.html", context)

def processQueue(request):
    context = {"user" : request.user}

    processInputsUncompleted = ProcessInput.objects.filter(completed=None)[:50]
    processInputsCompleted = ProcessInput.objects.filter(~Q(completed=None)).order_by('-startedDateTime')[:50]
    context['processInputsUncompleted'] = processInputsUncompleted
    context['processInputsCompleted'] = processInputsCompleted

    return render(request, "cosmicapp/processqueue.html", context)

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

    numSextractorSources = SextractorResult.objects.filter(image_id=image.pk).count()
    context['numSextractorSources'] = numSextractorSources

    numDaofindSources = DaofindResult.objects.filter(image_id=image.pk).count()
    context['numDaofindSources'] = numDaofindSources

    numStarfindSources = StarfindResult.objects.filter(image_id=image.pk).count()
    context['numStarfindSources'] = numStarfindSources

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

    sources = SextractorResult.objects.filter(image_id=image.pk)
    context['sources'] = sources

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

    return render(request, "cosmicapp/imageProperties.html", context)

#TODO: Allow this function to accept a size like 300px and have it return a suitable thumbnail.
def imageThumbnailUrl(request, id, size):
    context = {"user" : request.user}

    try:
        image = Image.objects.get(pk=id)
    except Image.DoesNotExist:
        return render(request, "cosmicapp/imagenotfound.html", context)

    return HttpResponse(image.getThumbnailUrl(size))

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

    limit = 10    # Set a default limit in cast the query did not specify one at all.
    if 'limit' in request.GET:
        try:
            limit = int(request.GET['limit'])
        except:
            pass

        if request.GET['queryfor'] == 'image':
            if limit > 100:
                limit = 100
        elif request.GET['queryfor'] in ['sextractorResult', 'daofindResult', 'starfindResult']:
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

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            imageDict = {}
            imageDict['id'] = str(result.pk)
            imageDict['dimX'] = str(result.dimX)
            imageDict['dimY'] = str(result.dimY)
            imageDict['dimZ'] = str(result.dimZ)
            imageDict['bitDepth'] = str(result.bitDepth)
            imageDict['frameType'] = result.frameType
            imageDict['centerRA'] = str(result.centerRA)
            imageDict['centerDEC'] = str(result.centerDEC)
            imageDict['centerROT'] = str(result.centerROT)
            imageDict['resolutionX'] = str(result.resolutionX)
            imageDict['resolutionY'] = str(result.resolutionY)
            imageDict['thumbUrlSmall'] = result.getThumbnailUrlSmall()
            imageDict['thumbUrlMedium'] = result.getThumbnailUrlMedium()
            imageDict['thumbUrlLarge'] = result.getThumbnailUrlLarge()
            imageDict['thumbUrlFull'] = result.getThumbnailUrlFull()

            etree.SubElement(root, "Image", imageDict)

    elif request.GET['queryfor'] == 'sextractorResult':
        orderField, ascDesc = parseQueryOrderBy(request, {'fluxAuto': 'fluxAuto'}, 'fluxAuto', '-')
        results = SextractorResult.objects

        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(image__pk__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            sextractorDict = {}
            sextractorDict['imageId'] = str(result.image.pk)
            sextractorDict['pixelX'] = str(result.pixelX)
            sextractorDict['pixelY'] = str(result.pixelY)
            sextractorDict['pixelZ'] = str(result.pixelZ)
            sextractorDict['fluxAuto'] = str(result.fluxAuto)
            sextractorDict['fluxAutoErr'] = str(result.fluxAutoErr)
            sextractorDict['flags'] = str(result.flags)

            etree.SubElement(root, "SextractorResult", sextractorDict)

    elif request.GET['queryfor'] == 'daofindResult':
        orderField, ascDesc = parseQueryOrderBy(request, {'mag': 'mag'}, 'mag', '')
        results = DaofindResult.objects

        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(image__pk__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            daofindDict = {}
            daofindDict['imageId'] = str(result.image.pk)
            daofindDict['pixelX'] = str(result.pixelX)
            daofindDict['pixelY'] = str(result.pixelY)
            daofindDict['pixelZ'] = str(result.pixelZ)
            daofindDict['mag'] = str(result.mag)
            daofindDict['sharpness'] = str(result.sharpness)
            daofindDict['sround'] = str(result.sround)
            daofindDict['ground'] = str(result.ground)

            etree.SubElement(root, "DaofindResult", daofindDict)

    elif request.GET['queryfor'] == 'starfindResult':
        orderField, ascDesc = parseQueryOrderBy(request, {'mag': 'mag'}, 'mag', '')
        results = StarfindResult.objects

        if 'imageId' in request.GET:
            for valueString in request.GET.getlist('imageId'):
                values = cleanupQueryValues(valueString, 'int')
                if len(values) > 0:
                    results = results.filter(image__pk__in=values)

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            starfindDict = {}
            starfindDict['imageId'] = str(result.image.pk)
            starfindDict['pixelX'] = str(result.pixelX)
            starfindDict['pixelY'] = str(result.pixelY)
            starfindDict['pixelZ'] = str(result.pixelZ)
            starfindDict['mag'] = str(result.mag)
            starfindDict['area'] = str(result.area)
            starfindDict['hwhm'] = str(result.hwhm)
            starfindDict['roundness'] = str(result.roundness)
            starfindDict['pa'] = str(result.pa)
            starfindDict['sharpness'] = str(result.sharpness)

            etree.SubElement(root, "StarfindResult", starfindDict)

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

    #TODO: Also write the values used in the query into the result, so the client can check if the limit they set was reduced, etc.
    return HttpResponse(etree.tostring(root, pretty_print=False), content_type='application/xml')

def questions(request):
    context = {"user" : request.user}

    return render(request, "cosmicapp/questions.html", context)

def equipment(request):
    context = {"user" : request.user}

    if request.method == 'POST':
        if request.POST['equipmentType'] == 'ota':
            missingFields = []
            for field in ('make', 'model', 'aperture', 'focalLength', 'design'):
                if not field in request.POST:
                    missingFields.append(field)
                    continue

                if request.POST[field].strip() == '':
                    missingFields.append(field)

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
                    if not oneOrIsTrue:
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

