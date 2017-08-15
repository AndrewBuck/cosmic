from __future__ import absolute_import, unicode_literals
from celery import shared_task

import subprocess
import json
import sys
import os

from .models import *

storageDirectory = '/cosmicmedia/'
staticDirectory = os.path.dirname(os.path.realpath(__file__)) + "/static/cosmicapp/"

@shared_task
def imagestats(filename):
    formatString = '{"width" : %w, "height" : %h, "depth" : %z}'
    proc = subprocess.Popen(['identify', '-format', formatString, storageDirectory + filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    print("imagestats: " + output)
    sys.stdout.flush()

    jsonObject = json.loads(output)

    image = Image.objects.get(fileRecord__onDiskFileName=filename)
    image.dimX = jsonObject['width']
    image.dimY = jsonObject['height']
    image.bitDepth = jsonObject['depth']
    image.save()

@shared_task
def generateThumbnails(filename):
    filenameFull = os.path.splitext(filename)[0] + "_thumb_full.png"
    filenameSmall = os.path.splitext(filename)[0] + "_thumb_small.png"

    for tempFilename, sizeArg in [(filenameFull, "100%"), (filenameSmall, "100x100")]:
        proc = subprocess.Popen(['convert', "-normalize", "-strip", "-filter", "spline", "-unsharp", "0x1", "-resize",
                sizeArg, storageDirectory + filename, staticDirectory + "images/" + tempFilename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

        output, error = proc.communicate()
        output = output.decode('utf-8')
        error = error.decode('utf-8')

        print("generateThumnails: " + tempFilename + "   " + output + "   " + error)
        sys.stdout.flush()

    image = Image.objects.get(fileRecord__onDiskFileName=filename)
    image.thumbnailFullName = filenameFull
    image.thumbnailSmallName = filenameSmall
    image.save()

