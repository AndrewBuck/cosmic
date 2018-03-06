import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

CosmicVariable.setVariable('astrometryNetTimeout1', 'int', '30')

CosmicVariable.setVariable('astrometryNetTimeout2', 'int', '120')

