import os
import django
from graphviz import Digraph
from textwrap import wrap

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

"""
image focus quality

image artefacts (meteor, cosmic ray, satellite, etc)

noise characteristics (smooth, patchy, high/low noise, snr)

questions about observing notes
"""

#--------------------------------------------------------------------------------

#TODO: Maybe we want to combine all of dark/flat/bias into 'calibration' frame since you can't tell them apart by looking?
qFrameType, created = Question.objects.get_or_create(
    text = 'What kind of image is this?',
    descriptionText = 'We need to know what category of image this is to know how to properly process it and combine it with other images.',
    titleText = 'Image Type',
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
    text = 'Planets',
    descriptionText = '',
    keyToSet = 'containsPlanets',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qObjectsPresent,
    index = 4,
    inputType = 'checkbox',
    text = 'Comets',
    descriptionText = '',
    keyToSet = 'containsComets',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qObjectsPresent,
    index = 5,
    inputType = 'checkbox',
    text = 'Asteroids',
    descriptionText = 'If you know any are present.',
    keyToSet = 'containsAsteroids',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qObjectsPresent,
    index = 6,
    inputType = 'checkbox',
    text = 'The Moon',
    descriptionText = 'Our moon.',
    keyToSet = 'containsTheMoon',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qObjectsPresent,
    index = 7,
    inputType = 'checkbox',
    text = 'The Sun',
    descriptionText = 'Our sun.',
    keyToSet = 'containsOtherCelestial',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qObjectsPresent,
    index = 8,
    inputType = 'checkbox',
    text = 'Other',
    descriptionText = 'Any other celestial object that is not noise/corruption of the image.',
    keyToSet = 'containsOtherCelestial',
    valueToSet = 'yes'
    )

pcObjectsInFrameType, created = AnswerPrecondition.objects.get_or_create(
    descriptionText = 'Only for light frames.',
    firstQuestion = qFrameType,
    secondQuestion = qObjectsPresent
    )

pccObjectsInFrameTypeLight, created = AnswerPreconditionCondition.objects.get_or_create(
    answerPrecondition = pcObjectsInFrameType,
    invert = False,
    key = 'imageType',
    value = 'light'
    )

#--------------------------------------------------------------------------------

qMotionBlur, created = Question.objects.get_or_create(
    text = 'Do the stars in the image exhibit "motion blur"?',
    descriptionText = 'If the telescope is bumped during the image exposure, or if the mount is not tracking perfectly, the stars in the image will be stretched and not round.',
    titleText = 'Motion Blur',
    aboutType = 'Image',
    priority = 8000,
    previousVersion = None
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qMotionBlur,
    index = 0,
    inputType = 'radioButton',
    text = 'None',
    descriptionText = 'The stars are perfectly round.',
    keyToSet = 'motionBlur',
    valueToSet = '0'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qMotionBlur,
    index = 1,
    inputType = 'radioButton',
    text = 'Moderate',
    descriptionText = 'The stars slightly out of round, but the image is still useable for most analysis.',
    keyToSet = 'motionBlur',
    valueToSet = '1'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qMotionBlur,
    index = 2,
    inputType = 'radioButton',
    text = 'Severe',
    descriptionText = 'The stars are streaked severely and the image is unusable for scientific analysis.',
    keyToSet = 'motionBlur',
    valueToSet = '2'
    )

pcStarsInFrame, created = AnswerPrecondition.objects.get_or_create(
    descriptionText = 'If stars or other pointlike objects are present.',
    firstQuestion = qObjectsPresent,
    secondQuestion = qMotionBlur
    )

pccStarsInFrameYes, created = AnswerPreconditionCondition.objects.get_or_create(
    answerPrecondition = pcStarsInFrame,
    invert = False,
    key = 'containsStars|containsPlanets|containsAsteroids|containsTheMoon',
    value = 'yes|yes|yes|yes'
    )

#--------------------------------------------------------------------------------

qGalaxyStructure, created = Question.objects.get_or_create(
    text = 'Can you see structure in any of the galaxies in the image?',
    descriptionText = 'Galaxy structure means spiral arms, a central bar, or a prominent central bulge.',
    titleText = 'Galaxy Structure',
    aboutType = 'Image',
    priority = 15000,
    previousVersion = None
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qGalaxyStructure,
    index = 0,
    inputType = 'radioButton',
    text = 'Yes',
    descriptionText = 'One or more galaxies has visible structure.',
    keyToSet = 'galaxyStructure',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qGalaxyStructure,
    index = 1,
    inputType = 'radioButton',
    text = 'No',
    descriptionText = 'None of the galaxies have visible structure.',
    keyToSet = 'galaxyStructure',
    valueToSet = 'no'
    )

pcGalaxiesInFrame, created = AnswerPrecondition.objects.get_or_create(
    descriptionText = 'If galaxies are present.',
    firstQuestion = qObjectsPresent,
    secondQuestion = qGalaxyStructure
    )

pccStarsInFrameYes, created = AnswerPreconditionCondition.objects.get_or_create(
    answerPrecondition = pcGalaxiesInFrame,
    invert = False,
    key = 'containsGalaxies',
    value = 'yes'
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

# Make a 'dot' graph showing all the questions, their possible responses, and the precondition links among them.
graph = Digraph("Question Flow Chart", format='svg')

questions = Question.objects.all()
for question in questions:
    label = question.titleText.replace(' ', '_')
    text = '< <table>'
    text += '<tr><td>' + question.titleText + '</td></tr>'
    text += '<tr><td>'
    text += '<font point-size="10">' + '<br/>'.join(wrap(question.text, 40)) + '</font>'

    text += '<font point-size="8"><br/><br/>'
    responses = QuestionResponse.objects.filter(question=question.pk).order_by('index')
    responseStrings = []
    for response in responses:
        responseStrings.append(response.text)
    text += '<br/>'.join(wrap(', '.join(responseStrings), 50))
    text += '</font>'

    text +='</td></tr>'
    text += '</table> >'
    graph.node(label, text, shape='none', margin='0')

preconditions = AnswerPrecondition.objects.all()
for pc in preconditions:
    label1 = pc.firstQuestion.titleText.replace(' ', '_')
    label2 = pc.secondQuestion.titleText.replace(' ', '_')

    conditions = AnswerPreconditionCondition.objects.filter(answerPrecondition=pc.pk)
    text = '< <font point-size="10">'
    text += '<br/>'.join(wrap(pc.descriptionText, 30)) + '</font><font point-size="8"><br/><br/>'
    for condition in conditions:
        if condition.invert:
            text += "not "

        orKeys = condition.key.split('|')
        orValues = condition.value.split('|')

        if len(orKeys) > 1:
            text += "<i>any one of</i><br/>"

        for orKey, orValue in zip(orKeys, orValues):
            text += orKey + '=' + orValue + '<br/>'

    text += '</font> >'
    graph.edge(label1, label2, label=text, constraint='true')

graph.render('QuestionGraph', directory='./cosmicapp/static/cosmicapp/', view=False, cleanup=True)

