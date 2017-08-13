from django.shortcuts import render
from django.template import loader
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponseRedirect

from .models import User, Profile
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

def upload(request):
    context = {"user" : request.user}

    if request.method == 'POST' and request.FILES['myfile']:
        myfile = request.FILES['myfile']
        fs = FileSystemStorage()
        filename = fs.save(myfile.name, myfile)

        uploaded_file_url = fs.url(filename)
        context['uploaded_file_url'] = uploaded_file_url

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

