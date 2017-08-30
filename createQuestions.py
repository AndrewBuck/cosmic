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

questions about observing notes
"""

#--------------------------------------------------------------------------------

qFrameType, created = Question.objects.get_or_create(
    text = 'What kind of image is this?',
    descriptionText = 'We need to know what category of image this is to know how to properly process it and combine it with other images.',
    titleText = 'Image type',
    aboutType = 'Image',
    priority = 10000,
    previousVersion = None
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qFrameType,
    index = 0,
    inputType = 'radioButton',
    text = 'Science Frame',
    descriptionText = 'A "light" frame containing stars, galaxies, etc, on the sky.',
    keyToSet = 'imageType',
    valueToSet = 'light'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qFrameType,
    index = 1,
    inputType = 'radioButton',
    text = 'Flat Frame',
    descriptionText = 'A "flat field" image to calibrate the image sensor.',
    keyToSet = 'imageType',
    valueToSet = 'flat'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qFrameType,
    index = 2,
    inputType = 'radioButton',
    text = 'Dark Frame',
    descriptionText = 'A "dark" image taken with the lens cap on to calibrate the image sensor.',
    keyToSet = 'imageType',
    valueToSet = 'dark'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qFrameType,
    index = 3,
    inputType = 'radioButton',
    text = 'Bias Frame',
    descriptionText = 'A "bias" image taken with the lens cap for 0 seconds on to calibrate the image sensor.',
    keyToSet = 'imageType',
    valueToSet = 'bias'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qFrameType,
    index = 4,
    inputType = 'radioButton',
    text = 'Spectra',
    descriptionText = 'A picture of the light spectrum of an astronomical object.',
    keyToSet = 'imageType',
    valueToSet = 'spectrum'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qFrameType,
    index = 5,
    inputType = 'radioButton',
    text = 'Non-astronomical',
    descriptionText = 'Any kind of picture that is not astronomical in nature (pictures of people, buildings, etc.)',
    keyToSet = 'imageType',
    valueToSet = 'non-astronomical'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qFrameType,
    index = 6,
    inputType = 'radioButton',
    text = 'Corrupt/Nothing',
    descriptionText = 'A picture showing no visible objects or just showing corrupted data, etc.',
    keyToSet = 'imageType',
    valueToSet = 'corrupt'
    )

#--------------------------------------------------------------------------------

qObjectsPresent, created = Question.objects.get_or_create(
    text = 'What kinds of objects appear to be present in the image?',
    descriptionText = 'Having images tagged with what is visible in them helps determine the limiting magnitude of the instrument used to take the image, as well as in locating images who could not be automatically plate solved.',
    titleText = 'Objects Present',
    aboutType = 'Image',
    priority = 1000,
    previousVersion = None
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qObjectsPresent,
    index = 0,
    inputType = 'checkbox',
    text = 'Stars',
    descriptionText = '',
    keyToSet = 'containsStars',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qObjectsPresent,
    index = 1,
    inputType = 'checkbox',
    text = 'Galaxies',
    descriptionText = '',
    keyToSet = 'containsGalaxies',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qObjectsPresent,
    index = 2,
    inputType = 'checkbox',
    text = 'Nebulae',
    descriptionText = '',
    keyToSet = 'containsNebulae',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qObjectsPresent,
    index = 3,
    inputType = 'checkbox',
    text = 'Other',
    descriptionText = 'Any other celestial object that is not noise/corruption of the image. (comets, planets, the moon, etc)',
    keyToSet = 'containsOtherCelestial',
    valueToSet = 'yes'
    )

pcObjectsInFrameType, created = AnswerPrecondition.objects.get_or_create(
    descriptionText = 'Only ask about objects in image for light frames.',
    firstQuestion = qFrameType,
    secondQuestion = qObjectsPresent
    )

pccObjectsInFrameTypeLight, created = AnswerPreconditionCondition.objects.get_or_create(
    answerPrecondition = pcObjectsInFrameType,
    invert = False,
    key = 'imageType',
    value = 'light'
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
    question = ,
    index = ,
    inputType = '',
    text = '',
    descriptionText = '',
    keyToSet = '',
    valueToSet = ''
    )
'''

#TODO: Make a 'dot' graph showing all the questions, their possible responses, and the precondition links among them.

