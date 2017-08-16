import hashlib
import os

from django.shortcuts import render
from django.template import loader
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponseRedirect
from django.utils import timezone

from .models import User, Profile, UploadedFileRecord, Image
from .models import ProcessInput, ProcessOutput, ProcessArgument, ProcessOutputFile
from .forms import UserForm, ProfileForm

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

    if request.method == 'POST' and 'myfiles' in request.FILES:
        records = []
        for myfile in request.FILES.getlist('myfiles'):
            fs = FileSystemStorage()
            filename = fs.save(myfile.name, myfile)

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

            #TODO: Move this extension list into variables define in a configuration file somewhere.
            if fileExtension in [".fit", ".fits", ".png", ".jpg"]:
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
                    estCostIO = record.uploadSize / 10
                    )

                piThumbnails.save()

                paThumbnails = ProcessArgument(
                    processInput = piThumbnails,
                    argIndex = 1,
                    arg = record.onDiskFileName
                    )

                paThumbnails.save()

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

    return render(request, "cosmicapp/userpage.html", context)

def processQueue(request):
    context = {"user" : request.user}

    processInputsUncompleted = ProcessInput.objects.filter(completed=False)[:50]
    processInputsCompleted = ProcessInput.objects.filter(completed=True)[:50]
    context['processInputsUncompleted'] = processInputsUncompleted
    context['processInputsCompleted'] = processInputsCompleted

    return render(request, "cosmicapp/processqueue.html", context)

def image(request, id):
    context = {"user" : request.user}
    context['id'] = id

    try:
        image = Image.objects.get(pk=id)
    except Image.DoesNotExist:
        return render(request, "cosmicapp/imagenotfound.html", context)

    context['image'] = image

    return render(request, "cosmicapp/image.html", context)

