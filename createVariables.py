import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

CosmicVariable.setVariable('astrometryNetTimeout1', 'int', '30')
CosmicVariable.setVariable('astrometryNetDepth1', 'string', '6,10,20')

CosmicVariable.setVariable('astrometryNetTimeout2', 'int', '120')
CosmicVariable.setVariable('astrometryNetDepth2', 'string', '8,26,50')

CosmicVariable.setVariable('astrometryNetRadius', 'float', '10')

CosmicVariable.setVariable('sextractorThreshold', 'float', '2.0')
CosmicVariable.setVariable('daofindThreshold', 'float', '3.0')
CosmicVariable.setVariable('starfindThreshold', 'float', '3.0')

CosmicVariable.setVariable('histogramMaxBins', 'int', '255')
CosmicVariable.setVariable('histogramRejectionExponent', 'float', '1000.0')
