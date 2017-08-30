import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

"""
image focus quality

image motion blur

image artefacts (meteor, cosmic ray, satellite, etc)

noise characteristics (smooth, patchy, high/low noise, snr)

what is in the image (stars, nebula, galaxy, etc)

questions about observing notes
"""

q, created = Question.objects.get_or_create(  
    text = 'What kind of image is this?',
    descriptionText = 'We need to know what category of image this is to know how to properly process it and combine it with other images.',
    titleText = 'Image type',
    aboutType = 'Image',
    priority = 10000,
    previousVersion = None
    )

r, created = QuestionResponse.objects.get_or_create(
    question = q,
    index = 0,
    inputType = 'radioButton',
    text = 'Science Frame',
    descriptionText = 'A "light" frame containing stars, galaxies, etc, on the sky.',
    keyToSet = 'imageType',
    valueToSet = 'light'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = q,
    index = 1,
    inputType = 'radioButton',
    text = 'Flat Frame',
    descriptionText = 'A "flat field" image to calibrate the image sensor.',
    keyToSet = 'imageType',
    valueToSet = 'flat'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = q,
    index = 2,
    inputType = 'radioButton',
    text = 'Dark Frame',
    descriptionText = 'A "dark" image taken with the lens cap on to calibrate the image sensor.',
    keyToSet = 'imageType',
    valueToSet = 'dark'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = q,
    index = 3,
    inputType = 'radioButton',
    text = 'Bias Frame',
    descriptionText = 'A "bias" image taken with the lens cap for 0 seconds on to calibrate the image sensor.',
    keyToSet = 'imageType',
    valueToSet = 'bias'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = q,
    index = 4,
    inputType = 'radioButton',
    text = 'Spectra',
    descriptionText = 'A picture of the light spectrum of an astronomical object.',
    keyToSet = 'imageType',
    valueToSet = 'spectrum'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = q,
    index = 5,
    inputType = 'radioButton',
    text = 'Non-astronomical',
    descriptionText = 'Any kind of picture that is not astronomical in nature, pictures of people, buildings, etc.',
    keyToSet = 'imageType',
    valueToSet = 'non-astronomical'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = q,
    index = 6,
    inputType = 'radioButton',
    text = 'Corrupt/Nothing',
    descriptionText = 'A picture showing no visible objects or just showing corrupted data, etc.',
    keyToSet = 'imageType',
    valueToSet = 'corrupt'
    )



'''
q, created = Question.objects.get_or_create(  
    text = '',
    descriptionText = '',
    titleText = '',
    aboutType = '',
    priority = ,
    previousVersion = None
    )

r, created = QuestionResponse.objects.get_or_create(
    question = q,
    index = ,
    inputType = '',
    text = '',
    descriptionText = '',
    keyToSet = '',
    valueToSet = ''
    )
'''

