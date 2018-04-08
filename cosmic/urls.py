"""cosmic URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url, include
from django.contrib import admin
from django.contrib.auth import views as auth_views


from cosmicapp import views

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url('^', include('django.contrib.auth.urls')),
    url(r'^createuser/', views.createuser),

    url(r'^donate/', views.donate),

    url(r'^$', views.index),

    url(r'^processqueue/', views.processQueue),
    url(r'^processoutput/(?P<id>[0-9]+)', views.processOutput),

    url(r'^catalogs/', views.catalogs),
    url(r'^catalog/(?P<method>.+)/(?P<pk>.+)', views.objectInfo),
    url(r'^detectedSource/(?P<method>.+)/(?P<pk>.+)', views.objectInfo),
    url(r'^uploadSession/(?P<pk>.+)', views.uploadSession),

    url(r'^user/(?P<username>.+)/bookmarks/$', views.bookmarkPage),
    url(r'^user/(?P<username>.+)/', views.userpage),
    url(r'^observatory/(?P<id>.+)/', views.observatory),

    url(r'^image/(?P<id>[0-9]+)/$', views.image),
    url(r'^image/(?P<id>[0-9]+)/sources/$', views.imageSources),
    url(r'^image/(?P<id>[0-9]+)/properties/$', views.imageProperties),
    url(r'^imageProperties/$', views.allImageProperties),

    url(r'^query/$', views.query),

    url(r'^image/(?P<id>[-0-9]+)/question/$', views.questionImage),
    url(r'^image/(?P<id>[0-9]+)/getquestion/$', views.getQuestionImage),
    url(r'^image/gallery/$', views.imageGallery),
    url(r'^questions/$', views.questions),

    url(r'^equipment/$', views.equipment),

    url(r'^mosaic/$', views.mosaic),
    url(r'^save/transform/$', views.saveTransform),
    url(r'^save/userSubmittedSourceResults/$', views.saveUserSubmittedSourceResults),
    url(r'^save/userSubmittedFeedback/$', views.saveUserSubmittedFeedback),
    url(r'^save/userOwnedEquipment/$', views.saveUserOwnedEquipment),
    url(r'^save/instrumentConfigurationLink/$', views.saveInstrumentConfigurationLink),
    url(r'^save/newInstrumentConfiguration/$', views.saveNewInstrumentConfiguration),
    url(r'^save/query/$', views.saveQuery),

    url(r'^delete/userOwnedEquipment/$', views.deleteUserOwnedEquipment),
    url(r'^delete/instrumentConfigurationLink/$', views.deleteInstrumentConfigurationLink),
    url(r'^delete/instrumentConfiguration/$', views.deleteInstrumentConfiguration),
    url(r'^bookmark/$', views.bookmark),

    url(r'^calibration/$', views.calibration),

    url(r'^observing/$', views.observing),

    url(r'^about/$', views.about),
    url(r'^about/processes/$', views.processes),
    url(r'^about/processes/(?P<process>[a-zA-Z0-9]+)$', views.processes),

    url(r'^learn/$', views.learn),

    url(r'^export/bookmarks/$', views.exportBookmarks),

    url(r'^upload/$', views.upload)
]
