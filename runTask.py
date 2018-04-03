import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.tasks import *

ret = imagestats("M51-B_r_lUxLNYH.fit")
print(ret['outputText'])
print(ret['outputErrorText'])

