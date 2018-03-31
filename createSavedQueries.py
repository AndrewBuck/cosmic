import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

#--------------------------------------------------------------------------------

textBlob, created = TextBlob.objects.get_or_create(
    user = None,
    markdownText = 'Below you will see the results of a query for all the images in the '
                   'database where the locally running *astrometry.net* plate solver was unable to find a '
                   'plate solution for the image.  Very often, the reason for this is that the star '
                   'detection algorithms we ran on the image were either too sensitive (and found a bunch '
                   'of false positive stars) or they were not sensitive enough (and they missed most of '
                   'the stars in the image).\n'
                   '\n'
                   'You can help us try to find a plate solution by *providing feedback* on the *view '
                   'sources* page for each image shown in the table below.  Simply go to the view sources '
                   'page for a given image, then click the *feedback* button under one of the 4 detection '
                   'methods.  Look at the detected sources for that method and then scroll back up to '
                   'click one of the buttons telling us how well that particular star finding method did. '
                   'Every time you provide feedback on an image we will re-run the astrometry.net plate '
                   'solver with better detection settings based on your feedback.  *Note: Re-running the '
                   'plate solver takes many minutes so you will want to give feedback on a few images, and '
                   'then either re-load their view sources pages after a few minutes, or just move on to '
                   'other images.*\n'
    )

try:
    SavedQuery.objects.get(name='helpFindPlateSolutions').delete()
except:
    pass

savedQuery = SavedQuery(
    name = 'helpFindPlateSolutions',
    text = textBlob,
    header = 'Help Find Plate Solutions',
    queryParams = 'imageProperty=astrometryNet=failure'
    )

savedQuery.save()

