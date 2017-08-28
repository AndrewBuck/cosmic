import hashlib
import os

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

from lxml import etree

from .models import *
from .forms import *

def index(request):
    context = {"user" : request.user}
    return render(request, "cosmicapp/index.html", context)

@login_required
def members(request):
    context = {"user" : request.user}
    return render(request, "cosmicapp/members.html", context)

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

    numSources = SextractorResult.objects.filter(image_id=image.pk).count()
    context['numSources'] = numSources

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

def query(request):
    root = etree.Element("queryresult")

    if not ('queryfor' in request.GET):
        #TODO: Convert this to xml.
        return HttpResponse("bad request: missing 'queryfor'")

    if 'limit' in request.GET:
        #TODO Catch parse error.
        limit = int(request.GET['limit'])
    else:
        limit = 10

    if 'offset' in request.GET:
        #TODO Catch parse error.
        offset = int(request.GET['offset'])
    else:
        offset = 0

    if request.GET['queryfor'] == 'image':
        if 'order' in request.GET:
            orderField, ascDesc = request.GET['order'].split('_')
            if orderField == 'time':
                orderField = 'fileRecord__uploadDateTime'
            else:
                orderField = 'fileRecord__uploadDateTime'

            #TODO: The asc/desc code is probably the same for all query types, try to refactor this out if this inner 'if' statement.
            if ascDesc == 'desc':
                ascDesc = '-'
            else:
                ascDesc = ''
        else:
            orderField = 'fileRecord__uploadDateTime'
            ascDesc = '-'

        results = Image.objects

        if 'user' in request.GET:
            results = results.filter(fileRecord__uploadingUser__username=request.GET['user'])

        results = results.order_by(ascDesc + orderField)[offset:offset+limit]

        for result in results:
            imageDict = {}
            #TODO: These lines could probably all (or mostly) be collapsed into a for loop.
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

    return HttpResponse(etree.tostring(root, pretty_print=False), content_type='application/xml')

