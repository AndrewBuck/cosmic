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

    url(r'^$', views.index),
    url(r'^members/', views.members),
    url(r'^processqueue/', views.processQueue),
    url(r'^catalogs/', views.catalogs),

    url(r'^user/(?P<username>.+)/', views.userpage),

    url(r'^image/(?P<id>[0-9]+)/$', views.image),
    url(r'^image/(?P<id>[0-9]+)/thumbnail/(?P<size>[a-zA-Z]+)/$', views.imageThumbnailUrl),
    url(r'^image/(?P<id>[0-9]+)/sources/$', views.imageSources),
    url(r'^image/(?P<id>[0-9]+)/properties/$', views.imageProperties),

    url(r'^query/$', views.query),

    url(r'^image/(?P<id>[0-9]+)/question/$', views.questionImage),
    url(r'^image/(?P<id>[0-9]+)/getquestion/$', views.getQuestionImage),
    url(r'^questions/$', views.questions),

    url(r'^upload/$', views.upload)
]
