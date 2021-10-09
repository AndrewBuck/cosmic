"""
This is a simple script to give a specific user some mod points so they are able to moderate comments.  In normal use
on the site this should not need to be run, it exists solely for testing.
"""

import sys

usage = "\n\n\n\tUSAGE: " + sys.argv[0] + " <username> <numPointsToAssign>\n\n\n"
if len(sys.argv) < 3:
    print(usage)
    sys.exit(1)

import os
import django
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *
from cosmicapp.functions import *


username = sys.argv[1]
modPoints = parseInt(sys.argv[2])

with transaction.atomic():
    user = User.objects.get(username = username)
    profile = Profile.objects.get(user = user)
    profile.modPoints = modPoints
    profile.save()
    print("Mod points updated for user")

