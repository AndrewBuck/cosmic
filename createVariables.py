import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

CosmicVariable.setVariable('astrometryNetTimeout1', 'int', '30')
CosmicVariable.setVariable('astrometryNetDepth1', 'string', '8,12,22,36')

CosmicVariable.setVariable('astrometryNetTimeout2', 'int', '120')
CosmicVariable.setVariable('astrometryNetDepth2', 'string', '12,25,35,45,70')

CosmicVariable.setVariable('astrometryNetRadius', 'float', '10')
CosmicVariable.setVariable('astrometryNetZenithRadius', 'float', '80')

CosmicVariable.setVariable('sextractorThreshold', 'float', '2.0')
CosmicVariable.setVariable('daofindThreshold', 'float', '4.0')
CosmicVariable.setVariable('starfindThreshold', 'float', '3.5')

CosmicVariable.setVariable('histogramMaxBins', 'int', '255')
CosmicVariable.setVariable('histogramRejectionExponent', 'float', '100.0')
CosmicVariable.setVariable('histogramIgnoreLower', 'float', '.25')
CosmicVariable.setVariable('histogramIgnoreUpper', 'float', '.25')

CosmicVariable.setVariable('asteroidEphemerideTolerance', 'float', '5')
CosmicVariable.setVariable('asteroidEphemerideTimeTolerance', 'float', '90')
CosmicVariable.setVariable('asteroidEphemerideMaxAngularDistance', 'float', '20')

CosmicVariable.setVariable('storageCostPerMonth', 'float', '0.02')
CosmicVariable.setVariable('cpuCostPerSecond', 'float', '0.00001')

