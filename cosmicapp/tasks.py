from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django.db import transaction

import subprocess
import json
import sys
import os

from .models import *

storageDirectory = '/cosmicmedia/'
staticDirectory = os.path.dirname(os.path.realpath(__file__)) + "/static/cosmicapp/"

@shared_task
def imagestats(filename):
    formatString = '{"width" : %w, "height" : %h, "depth" : %z, "channels" : "%[channels]"},'
    proc = subprocess.Popen(['identify', '-format', formatString, storageDirectory + filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    output = output.rstrip().rstrip(',')
    output = '[' + output + ']'

    print("imagestats: " + filename + "   " + output + "   " + error)
    sys.stdout.flush()

    jsonObject = json.loads(output)

    numChannels = 0
    channelColors = []
    for frame in jsonObject:
        if frame['channels'].lower() in ['red', 'green', 'blue', 'alpha', 'gray', 'cyan', 'magenta', 'yellow', 'black', 'opacity', 'index']:
            colors = [ frame['channels'].lower() ]
        elif frame['channels'].lower() in ['rgb', 'srgb']:
            colors = ['red', 'green', 'blue']
        elif frame['channels'].lower() == 'rgba':
            colors = ['red', 'green', 'blue', 'alpha']
        elif frame['channels'].lower() == 'cmyk':
            colors = ['cyan', 'magenta', 'yellow', 'black']
        elif frame['channels'].lower() == 'cmyka':
            colors = ['cyan', 'magenta', 'yellow', 'black', 'alpha']
        else:
            error += "\n\nUnknown colorspace for image frame: " + frame.channels + "\n\n"
            numChannels = -1
            break

        for color in colors:
            channelColors.append( (numChannels, color) )
            numChannels += 1

    #NOTE: These assume that all channels have the same width, height, and depth.  This may not always be true.
    image = Image.objects.get(fileRecord__onDiskFileName=filename)
    image.dimX = jsonObject[0]['width']
    image.dimY = jsonObject[0]['height']
    image.bitDepth = jsonObject[0]['depth']

    with transaction.atomic():
        if numChannels > 0:
            image.dimZ = numChannels
            image.save()

            for channelEntry in channelColors:
                channelInfo = ImageChannelInfo(
                    image = image,
                    index = channelEntry[0],
                    channelType = channelEntry[1]
                    )

                channelInfo.save()

        else:
            image.save()

    formatString = '%[*]'
    proc = subprocess.Popen(['identify', '-format', formatString, storageDirectory + filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    print("imagestats:tags: " + filename + "   " + output + "   " + error)
    sys.stdout.flush()

    with transaction.atomic():
        i = 0
        for line in output.splitlines():
            split = line.split('=', 1)
            key = None
            value = None

            if len(split) == 1:
                key = split[0].strip()
            elif len(split) == 2:
                key = split[0].strip()
                value = split[1].strip()
            else:
                continue

            if (key == None and value == None) or (key == "" and value == "") or (key == "" and value == None):
                continue

            headerField = ImageHeaderField(
                image = image,
                index = i,
                key = key,
                value = value
                )

            headerField.save()

            i += 1

@shared_task
def generateThumbnails(filename):
    filenameFull = os.path.splitext(filename)[0] + "_thumb_full.png"
    filenameSmall = os.path.splitext(filename)[0] + "_thumb_small.png"

    for tempFilename, sizeArg in [(filenameFull, "100%"), (filenameSmall, "100x100")]:
        proc = subprocess.Popen(['convert', "-contrast-stretch", "2%x1%", "-strip", "-filter", "spline", "-unsharp", "0x1", "-resize",
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
    #TODO: sextractor cannot handle spaces in filenames (broken in the regular shell too, not just calling from python).
    #TODO: sextractor can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
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
        with transaction.atomic():
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

