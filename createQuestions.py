import os
import django
from graphviz import Digraph
from textwrap import wrap

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

        text += condition.key + '=' + condition.value + '<br/>'

    text += '</font> >'
    graph.edge(label1, label2, label=text, constraint='true')

graph.render('QuestionGraph', directory='./cosmicapp/static/cosmicapp/', view=False, cleanup=True)
