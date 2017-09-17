from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django.db import transaction
from django.conf import settings
from pyraf import iraf

import subprocess
import json
import sys
import os
import re

from astropy import wcs
from astropy.io import fits
from astropy.stats import sigma_clipped_stats

from .models import *

staticDirectory = os.path.dirname(os.path.realpath(__file__)) + "/static/cosmicapp/"

@shared_task
def imagestats(filename):
    formatString = '{"width" : %w, "height" : %h, "depth" : %z, "channels" : "%[channels]"},'
    proc = subprocess.Popen(['identify', '-format', formatString, settings.MEDIA_ROOT + filename],
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
            #TODO: This should maybe cause the task to fail, not sure.
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
    proc = subprocess.Popen(['identify', '-format', formatString, settings.MEDIA_ROOT + filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    print("imagestats:tags: " + filename)
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

    print("imagestats:wcs: " + filename)
    if os.path.splitext(filename)[-1].lower() in ['.fit', '.fits']:
        w = wcs.WCS(settings.MEDIA_ROOT + filename)

        if w.has_celestial:
            print("WCS found in header")

            #TODO: should check w.lattyp and w.lontyp to make sure we are storing these world coordinates correctly.
            raCen, decCen = w.all_pix2world(image.dimX/2, image.dimY/2, 1)
            raScale, decScale = wcs.utils.proj_plane_pixel_scales(w)
            raScale *= 3600.0
            decScale *= 3600.0

            image.centerRA = raCen
            image.centerDEC = decCen
            image.resolutionX = raScale
            image.resolutionY = decScale
            #TODO: Store image.centerROT
            #TODO: Should also store the four corners of the image position on the sky.
            image.save()
        else:
            print("WCS not found in header")

    print("imagestats:background: " + filename)
    if os.path.splitext(filename)[-1].lower() in ['.fit', '.fits']:
        hdulist = fits.open(settings.MEDIA_ROOT + filename)
        with transaction.atomic():
            channelIndex = 0
            for hdu in hdulist:
                frames = []
                if len(hdu.data.shape) == 2:
                    frames.append(hdu.data)

                if len(hdu.data.shape) == 3:
                    for i in range(hdu.data.shape[0]):
                        frames.append(hdu.data[channelIndex])

                for frame in frames:
                    channelInfo = ImageChannelInfo.objects.get(image=image, index=channelIndex)
                    mean, median, stdDev = sigma_clipped_stats(frame, iters=0)
                    bgMean, bgMedian, bgStdDev = sigma_clipped_stats(frame, iters=1)

                    #TODO: For some reason the median and bgMedain are always 0.  Need to fix this.
                    channelInfo.mean = mean
                    channelInfo.median = median
                    channelInfo.stdDev = stdDev
                    channelInfo.bgMean = bgMean
                    channelInfo.bgMedian = bgMedian
                    channelInfo.bgStdDev = bgStdDev
                    channelInfo.save()

                    channelIndex += 1

        hdulist.close()

    return True

@shared_task
def generateThumbnails(filename):
    filenameFull = os.path.splitext(filename)[0] + "_thumb_full.png"
    filenameSmall = os.path.splitext(filename)[0] + "_thumb_small.png"
    filenameMedium = os.path.splitext(filename)[0] + "_thumb_medium.png"
    filenameLarge = os.path.splitext(filename)[0] + "_thumb_large.png"

    image = Image.objects.get(fileRecord__onDiskFileName=filename)

    for tempFilename, sizeArg, sizeString in [(filenameFull, "100%", "full"), (filenameSmall, "100x100", "small"),
                                              (filenameMedium, "300x300", "medium"), (filenameLarge, "900x900", "large")]:
        proc = subprocess.Popen(['convert', "-contrast-stretch", "2%x1%", "-strip", "-filter", "spline", "-unsharp", "0x1", "-resize",
                sizeArg, "-verbose", settings.MEDIA_ROOT + filename, staticDirectory + "images/" + tempFilename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

        output, error = proc.communicate()
        output = output.decode('utf-8')
        error = error.decode('utf-8')

        print("generateThumbnails: " + tempFilename)
        sys.stdout.flush()

        with transaction.atomic():
            for line in error.splitlines():
                if '=>' in line:
                    fields = line.split()
                    outputFilename = fields[0].split('=>')[1]
                    channelIndicator = re.findall(r'\[\d+\]$', outputFilename)
                    print('channelIndicator "', channelIndicator, '"')

                    if len(channelIndicator) == 0:
                        channel = 0
                    else:
                        channel = int(channelIndicator[0].strip('[]'))
                        outputFilename = outputFilename.split('[')[0]

                    outputFilename = os.path.basename(outputFilename)

                    record = ImageThumbnail(
                        image = image,
                        size = sizeString,
                        channel = channel,
                        filename = outputFilename
                        )

                    record.save()

    return True

@shared_task
def sextractor(filename):
    #TODO: sextractor can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    catfileName = settings.MEDIA_ROOT + filename + ".cat"
    proc = subprocess.Popen(['sextractor', '-CATALOG_NAME', catfileName, settings.MEDIA_ROOT + filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=settings.MEDIA_ROOT
        )

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    print("sextractor: " + filename + "   " + output + "   " + error)
    sys.stdout.flush()

    # Get the image record
    image = Image.objects.get(fileRecord__onDiskFileName=filename)

    with open(catfileName, 'r') as catfile:
        fieldDict = {}
        with transaction.atomic():
            for line in catfile:
                # Split the line into fields (space separated) and throw out empty fields caused by multiple spaces in a
                # row.  I.E. do a "combine consecutive delimeters" operation.
                fields = line.split()

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

    try:
        os.remove(catfileName)
    except OSError:
        pass

    return True

@shared_task
def daofind(filename):
    print("daofind: " + filename)
    sys.stdout.flush()

    #TODO: daofind can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    catfileName = settings.MEDIA_ROOT + filename + ".daofind.cat"

    image = Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = ImageChannelInfo.objects.filter(image=image).order_by('index')

    iraf.datapars.sigma = channelInfos[0].bgStdDev

    iraf.unlearn(iraf.daofind)
    iraf.daofind(settings.MEDIA_ROOT + filename, output=catfileName)

    with open(catfileName, 'r') as catfile:
        with transaction.atomic():
            for line in catfile:
                #TODO: Read in and store the parameters in the commented section.
                if line.startswith('#'):
                    continue

                fields = line.split()

                try:
                    mag = float(fields[2])
                except:
                    mag = None

                result = DaofindResult(
                    image = image,
                    pixelX = float(fields[0]),
                    pixelY = float(fields[1]),
                    pixelZ = None,    #TODO: Handle multi-extension fits files.
                    mag = mag,
                    sharpness = float(fields[3]),
                    sround = float(fields[4]),
                    ground = float(fields[5])
                    )

                result.save()

    try:
        os.remove(catfileName)
    except OSError:
        pass

    return True

@shared_task
def parseHeaders(imageId):
    image = Image.objects.get(pk=imageId)
    headers = ImageHeaderField.objects.filter(image=imageId)

    with transaction.atomic():
        for header in headers:
            if header.key == 'fits:bitpix':
                key = 'bitDepth'
                value = str(abs(int(header.value.split()[0])))

            elif header.key in ['fits:date_obs', 'fits:date-obs']:
                key = 'dateObs'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:exptime', 'fits:exposure']:
                key = 'exposureTime'
                value = header.value.split()[0]

            elif header.key == 'fits:instrume':
                key = 'instrument'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:swcreate', 'fits:creator', 'fits:origin']:
                key = 'createdBySoftware'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key == 'fits:naxis':
                key = 'numAxis'
                value = header.value.split()[0]

            elif header.key in ['fits:naxis1', 'fits:imagew']:
                key = 'width'
                value = header.value.split()[0]

            elif header.key == ['fits:naxis2', 'fits:imageh']:
                key = 'height'
                value = header.value.split()[0]

            elif header.key == 'fits:naxis3':
                key = 'numChannels'
                value = header.value.split()[0]

            elif header.key == 'fits:xbinning':
                key = 'binningX'
                value = header.value.split()[0]

            elif header.key == 'fits:ybinning':
                key = 'binningY'
                value = header.value.split()[0]

            #TODO: Pixel size is supposed to be after binning however this does not appear to be correct in binned frames.
            elif header.key == 'fits:xpixsz':
                key = 'pixelSizeX'
                value = header.value.split()[0]

            #TODO: Pixel size is supposed to be after binning however this does not appear to be correct in binned frames.
            elif header.key == 'fits:ypixsz':
                key = 'pixelSizeY'
                value = header.value.split()[0]

            elif header.key == 'fits:ccd-temp':
                key = 'ccdTemp'
                value = header.value.split()[0]

            elif header.key == 'fits:set-temp':
                key = 'ccdSetTemp'
                value = header.value.split()[0]

            elif header.key == 'fits:imagtyp':
                key = 'imageType'
                value = header.value.split('/')[0].strip().strip("'").lower()

                if 'light' in value:
                    value = 'light'
                elif 'dark' in value:
                    value = 'dark'
                elif 'bias' in value:
                    value = 'bias'
                elif 'flat' in value:
                    value = 'flat'

                image.frameType = value
                image.save()

            elif header.key == 'fits:aperture':
                key = 'aperture'
                value = header.value.split()[0].strip().strip("'").lower()

            elif header.key == 'fits:filter':
                key = 'filter'
                value = header.value.split()[0].strip().strip("'").lower()

            elif header.key == 'fits:iso':
                key = 'iso'
                value = str(abs(int(header.value.split()[0].strip())))

            else:
                continue

            # Many of these are stripped already, but strip them once more just to be sure no extra whitespace got included.
            key = key.strip()
            value = value.strip()

            prop = ImageProperty(
                image = image,
                header = header,
                key = key,
                value = value
                )

            prop.save()

    return True

