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

@shared_task
def sextractor(filename):
    proc = subprocess.Popen(['sextractor', '-CATALOG_NAME', storageDirectory + filename + ".cat", storageDirectory + filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=storageDirectory
        )

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    print("sextractor: " + filename + "   " + output + "   " + error)
    sys.stdout.flush()

    # Get the image record
    image = Image.objects.get(fileRecord__onDiskFileName=filename)

    with open(storageDirectory + filename + ".cat", 'r') as catfile:
        fieldDict = {}
        for line in catfile:
            # Split the line into fields (space separated) and throw out empty fields caused by multiple spaces in a
            # row.  I.E. do a "combine consecutive delimeters" operation.
            #TODO: Calling this as split() (with no delimeter) should combine whitespace and make the for loop below unnecessary.
            tempFields = line.split(' ')
            fields = []
            for field in tempFields:
                if len(field) > 0:
                    fields.append(field)

            # Read the comment lines at the top of the file to record what fields are present and in what order.
            if line.startswith("#"):
                fieldDict[fields[2]] = int(fields[1]) - 1

            #For lines that are not comments, use the fieldDict to determine what fields to read and store in the database.
            else:
                xPos = fields[fieldDict['X_IMAGE']]
                yPos = fields[fieldDict['Y_IMAGE']]
                zPos = None   #TODO: Add image layer number if this is a data cube, just leaving null for now.
                fluxAuto = fields[fieldDict['FLUX_AUTO']]
                fluxAutoErr = fields[fieldDict['FLUXERR_AUTO']]
                flags = fields[fieldDict['FLAGS']]

                record = SextractorResult(
                    image = image,
                    pixelX = xPos,
                    pixelY = yPos,
                    pixelZ = zPos,
                    fluxAuto = fluxAuto,
                    fluxAutoErr = fluxAutoErr,
                    flags = flags
                    )

                record.save()

    #TODO: Clean up filename.cat which is written to disk but not needed anymore.

