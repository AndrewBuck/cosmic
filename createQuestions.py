import os
import django
from graphviz import Digraph
from textwrap import wrap

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

"""
Things to ask about:

noise characteristics (smooth, patchy, high/low noise, snr)
"""

#--------------------------------------------------------------------------------

qImageProblems, created = Question.objects.get_or_create(
    text = 'Are there any problems with the image?',
    descriptionText = 'Look over the image as a whole and check any of the following problems if they are present in the image.',
    titleText = 'Image Problems',
    aboutType = 'Image',
    priority = 100000,
    previousVersion = None
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qImageProblems,
    index = 0,
    inputType = 'checkbox',
    text = 'Uneven brightness',
    descriptionText = 'Different portions of the image have very different image brightness levels, especially the background.',
    keyToSet = 'unevenBrightness',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qImageProblems,
    index = 1,
    inputType = 'checkbox',
    text = 'Over exposed',
    descriptionText = 'All of the stars are very bright, showing no gradual dropoff in brightness as you move away from them.',
    keyToSet = 'overExposed',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qImageProblems,
    index = 2,
    inputType = 'checkbox',
    text = 'Out of focus',
    descriptionText = 'The stars look like doughnuts with a dark spot in the middle and a bright ring around.',
    keyToSet = 'outOfFocus',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qImageProblems,
    index = 3,
    inputType = 'checkbox',
    text = 'Needs cropping',
    descriptionText = 'There is a region around the perimeter of the image (or just along some edges) that needs to be trimmed off as it contains bad data (or calibration data).',
    keyToSet = 'needsCropping',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qImageProblems,
    index = 4,
    inputType = 'checkbox',
    text = 'Streaks',
    descriptionText = 'Bright lines running across the image from airplanes, satelites, meteors, or from mosaicing multiple images together.',
    keyToSet = 'badStreaks',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qImageProblems,
    index = 5,
    inputType = 'checkbox',
    text = 'Bad lines',
    descriptionText = 'More than a few scatterered bad lines, several large clusters of many bad lines near eachother.',
    keyToSet = 'badLines',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qImageProblems,
    index = 6,
    inputType = 'checkbox',
    text = 'Bad pixels',
    descriptionText = 'More than a few scatterered bad pixels, several large clusters of many bad pixels near eachother.',
    keyToSet = 'badPixels',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qImageProblems,
    index = 7,
    inputType = 'checkbox',
    text = 'Not science',
    descriptionText = 'The image is not science data (or calibration data), it is a picture of a person, a telescope, or anything else.',
    keyToSet = 'notScience',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qImageProblems,
    index = 8,
    inputType = 'checkbox',
    text = 'Spam',
    descriptionText = 'The image is an advertisement, etc.',
    keyToSet = 'spam',
    valueToSet = 'yes'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qImageProblems,
    index = 9,
    inputType = 'checkbox',
    text = 'xxx',
    descriptionText = 'The image contains adult content, or otherwise obscene material that should not be shown to non-moderators.',
    keyToSet = 'xxx',
    valueToSet = 'yes'
    )

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

pcImageProblems, created = AnswerPrecondition.objects.get_or_create(
    descriptionText = 'Only for science frames.',
    firstQuestion = qImageProblems,
    secondQuestion = qFrameType
    )

pccImageProblems, created = AnswerPreconditionCondition.objects.get_or_create(
    answerPrecondition = pcImageProblems,
    invert = True,
    key = 'notScience|spam|xxx',
    value = 'yes|yes|yes'
    )

#--------------------------------------------------------------------------------

qObjectsPresent, created = Question.objects.get_or_create(
    text = 'What kinds of objects appear to be present in the image?',
    descriptionText = 'Having images tagged with what is visible in them helps determine the limiting magnitude of the instrument used to take the image, as well as in locating images which could not be automatically plate solved.',
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
    descriptionText = 'Only for science frames.',
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

pcPointSourcesInFrame, created = AnswerPrecondition.objects.get_or_create(
    descriptionText = 'If stars or other pointlike objects are present.',
    firstQuestion = qObjectsPresent,
    secondQuestion = qMotionBlur
    )

pccPointSourcesInFrame, created = AnswerPreconditionCondition.objects.get_or_create(
    answerPrecondition = pcPointSourcesInFrame,
    invert = False,
    key = 'containsStars|containsPlanets|containsAsteroids|containsTheMoon',
    value = 'yes|yes|yes|yes'
    )

#--------------------------------------------------------------------------------

qGalaxyStructure, created = Question.objects.get_or_create(
    text = 'Can you see structure in any of the galaxies in the image?',
    descriptionText = 'Galaxy structure means any of: spiral arms, a central bar, a prominent central bulge, etc.',
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

pccGalaxiesInFrameYes, created = AnswerPreconditionCondition.objects.get_or_create(
    answerPrecondition = pcGalaxiesInFrame,
    invert = False,
    key = 'containsGalaxies',
    value = 'yes'
    )

#--------------------------------------------------------------------------------

qClustersPresent, created = Question.objects.get_or_create(
    text = 'Are there any dense clusters of stars in the image?',
    descriptionText = 'Knowing if there are dense star clusters can help locate images which do not have plate solutions.',
    titleText = 'Clusters Present',
    aboutType = 'Image',
    priority = 1000,
    previousVersion = None
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qClustersPresent,
    index = 0,
    inputType = 'radioButton',
    text = 'No dense clusters',
    descriptionText = 'Just individual stars or small groups of 2 or 3.',
    keyToSet = 'containsStarClusters',
    valueToSet = 'none'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qClustersPresent,
    index = 1,
    inputType = 'radioButton',
    text = 'Small clusters',
    descriptionText = 'Clusters of tens of stars.',
    keyToSet = 'containsStarClusters',
    valueToSet = 'moderate'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qClustersPresent,
    index = 2,
    inputType = 'radioButton',
    text = 'Dense clusters',
    descriptionText = 'Globular or open cluster with hundreds of stars.',
    keyToSet = 'containsStarClusters',
    valueToSet = 'dense'
    )

pcStarsInFrame, created = AnswerPrecondition.objects.get_or_create(
    descriptionText = 'If stars are present.',
    firstQuestion = qObjectsPresent,
    secondQuestion = qClustersPresent
    )

pccStarsInFrameYes, created = AnswerPreconditionCondition.objects.get_or_create(
    answerPrecondition = pcStarsInFrame,
    invert = False,
    key = 'containsStars',
    value = 'yes'
    )

#--------------------------------------------------------------------------------

qNumStars, created = Question.objects.get_or_create(
    text = 'How many stars are visible in the image?',
    descriptionText = 'Knowing roughly how many stars we should expect to find in an image helps us fine tune the star detection algorithms for each specific image.',
    titleText = 'Number of Stars',
    aboutType = 'Image',
    priority =  1000,
    previousVersion = None
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qNumStars,
    index = 0,
    inputType = 'radioButton',
    text = 'None',
    descriptionText = 'No stars at all.',
    keyToSet = 'numStars',
    valueToSet = '0'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qNumStars,
    index = 1,
    inputType = 'radioButton',
    text = 'Only one',
    descriptionText = 'Only a single star.',
    keyToSet = 'numStars',
    valueToSet = '1'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qNumStars,
    index = 2,
    inputType = 'radioButton',
    text = 'A few',
    descriptionText = 'A few stars, up to 10 or so.',
    keyToSet = 'numStars',
    valueToSet = 'few'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qNumStars,
    index = 3,
    inputType = 'radioButton',
    text = 'Tens',
    descriptionText = '10 to 50 or so, more than can easily be counted, but not hundreds.',
    keyToSet = 'numStars',
    valueToSet = 'tens'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qNumStars,
    index = 4,
    inputType = 'radioButton',
    text = 'Hundreds',
    descriptionText = 'A large image containing hundreds or many hundreds of stars.',
    keyToSet = 'numStars',
    valueToSet = 'hundreds'
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qNumStars,
    index = 4,
    inputType = 'radioButton',
    text = 'Thousands',
    descriptionText = 'A very large image covering a wide portion of the sky with many thousands of stars in total.',
    keyToSet = 'numStars',
    valueToSet = 'thousands'
    )

pcStarsInFrame2, created = AnswerPrecondition.objects.get_or_create(
    descriptionText = 'If stars are present.',
    firstQuestion = qObjectsPresent,
    secondQuestion = qNumStars
    )

pccStarsInFrameYes2, created = AnswerPreconditionCondition.objects.get_or_create(
    answerPrecondition = pcStarsInFrame2,
    invert = False,
    key = 'containsStars',
    value = 'yes'
    )

#--------------------------------------------------------------------------------


qOutlineDSO, created = Question.objects.get_or_create(
    text = 'Future Question: Outline galaxies and mark structure, etc.',
    descriptionText = 'This will be a javascript tool to outline galaxies, nebula, etc, in an image manually.',
    titleText = 'Outline DSO',
    aboutType = '',
    priority = 1000,
    previousVersion = None
    )

r, created = QuestionResponse.objects.get_or_create(
    question = qOutlineDSO,
    index = 0,
    inputType = 'checkbox',
    text = 'Ok',
    descriptionText = 'This does nothing right now.',
    keyToSet = 'nothing',
    valueToSet = 'yes'
    )

pcStarsInFrame, created = AnswerPrecondition.objects.get_or_create(
    descriptionText = 'Always.',
    firstQuestion = qGalaxyStructure,
    secondQuestion = qOutlineDSO
    )

pcStarsInFrame, created = AnswerPrecondition.objects.get_or_create(
    descriptionText = 'Always.',
    firstQuestion = qClustersPresent,
    secondQuestion = qOutlineDSO
    )

#--------------------------------------------------------------------------------

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

