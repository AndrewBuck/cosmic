from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django.db import transaction
from django.conf import settings
from django.db.models import Avg, StdDev
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.storage import FileSystemStorage
from django.db.models import Sum, Max
from django.utils import timezone

import subprocess
import json
import sys
import os
import time
import re
import itertools
import math
import random
import dateparser
import scipy
import imageio
import scipy.stats
import numpy
import ephem
from datetime import timedelta
import julian
import time
import hashlib

from astropy import wcs
from astropy import units as u
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.table import Table
from astropy.nddata import CCDData
from photutils import make_source_mask, DAOStarFinder, IRAFStarFinder
from ccdproc import Combiner, wcs_project
from collections import Counter
from sortedcontainers import SortedList, SortedDict, SortedListWithKey

from cosmicapp import models
from .functions import *

def longestCommonPrefix(string1, string2):
    length = 0
    for a, b in zip(string1, string2):
        if a == b:
            length += 1
        else:
            break

    return str(string1)[0:length]

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def constructProcessOutput(outputText, errorText, executionTime=None):
    """ A Simple convenience function to construct a ProcessOutput object to be returned to the dispatcher. """
    processOutput = {
        'outputText': outputText,
        'outputErrorText': errorText,
        'executionTime': executionTime
        }

    return processOutput

@shared_task
def imagestats(filename, processInputId):
    """
    A celery task to read an image file and record stats about the basic structure of the
    image into the database.  Some things calculated and stored by this routine are:

    * Image dimensions (width, height, number of channels, multi-hdu fits files, etc)
    * Image metadata (exif data, fits headers, etc)
    * Image WCS (check fits header and store wcs with source = 'original' if it has one)
    * Image histogram and basic pixel rejection masking
    * Write a full size, gamma corrected png thumbnail
    """
    outputText = ""
    errorText = ""
    taskStartTime = time.time()

    # Run the command line tool 'identify' (part of image magick) with a format string
    # given to it, causing it to return JSON formatted output which we then parse with the
    # standard JSON parsing library.
    formatString = '{"width" : %w, "height" : %h, "depth" : %z, "channels" : "%[channels]"},'
    proc = subprocess.Popen(['identify', '-format', formatString, settings.MEDIA_ROOT + filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    proc.wait()

    output = output.rstrip().rstrip(',')
    output = '[' + output + ']'

    outputText += output
    errorText += error
    outputText += '\n ==================== End of process output ====================\n\n'
    errorText += '\n ==================== End of process error =====================\n\n'

    jsonObject = json.loads(output)

    # Loop over the channels that image magick found and for each one, record what kind of
    # color channel image magick thought it was.  We also handle multicolor entries like
    # RGB or RGBA where one returned output line from image magick actually represents a
    # full 3 or 4 channel image.  At the end of the loop numChannels should be the true
    # total for images like this.
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

    # Store the image dimensionality.
    #NOTE: These assume that all channels have the same width, height, and depth.  This may not always be true.
    with transaction.atomic():
        image = models.Image.objects.get(fileRecord__onDiskFileName=filename)
        image.dimX = jsonObject[0]['width']
        image.dimY = jsonObject[0]['height']
        image.bitDepth = jsonObject[0]['depth']

        if numChannels > 0:
            image.dimZ = numChannels
            image.save()

            for channelEntry in channelColors:
                channelInfo = models.ImageChannelInfo(
                    image = image,
                    index = channelEntry[0],
                    channelType = channelEntry[1]
                    )

                channelInfo.save()

        else:
            image.save()

    # Run the command line tool 'identify' (part of image magick) with a format string to
    # print all key-value metadata pairs in the image header.
    formatString = '%[*]'
    proc = subprocess.Popen(['identify', '-format', formatString, settings.MEDIA_ROOT + filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

    output2, error2 = proc.communicate()
    output2 = output2.decode('utf-8')
    error2 = error2.decode('utf-8')

    proc.wait()

    outputText += '\n ===============================================================\n\n'
    outputText += output2
    outputText += '\n ==================== End of process output ====================\n\n'
    errorText += '\n ===============================================================\n\n'
    errorText += error2
    errorText += '\n ==================== End of process error =====================\n\n'


    outputText += "imagestats:tags: " + filename + "\n"

    with transaction.atomic():
        i = 0
        #TODO: Long lines starting with 'HISTORY' in the fits headers do not seem to be output by ImageMagick in the same way that 'COMMENT' lines are.  We may need to submit a ticket about this or something.
        for line in output2.splitlines():
            split = line.split('=', 1)
            key = ''
            value = ''

            # If there was no equals sign on the line, or there was an equals sign but it
            # was more than 8 characters into the line + 5 characters in in the prefix 'fits:'.
            if len(split) == 1 or (len(split) == 2 and len(split[0]) > 13 and ()):
                newSplit = split[0].split(' ', 1)
                if len(newSplit) == 2:
                    key = newSplit[0].strip()
                    value = newSplit[1].strip()
            # If there was an equals sign on the line (and by extension, it was within 8 characters of the start of the line).
            elif len(split) == 2:
                key = split[0].strip()
                value = split[1].strip()
            # This never should really happen.
            else:
                #TODO: Throw an error or something.
                continue

            if key == "" or value == "" or key in settings.IGNORED_KEYS:
                continue

            maxWidth = 77 - len(key)
            valueArray = []
            tempString = ''
            for c in value:
                if len(tempString) <= maxWidth:
                    tempString += c
                else:
                    valueArray.append(tempString)
                    tempString = ''

            if tempString != '':
                valueArray.append(tempString)

            headerFields = []
            for valueString in valueArray:
                headerField = models.ImageHeaderField(
                    image = image,
                    index = i,
                    key = key,
                    value = valueString
                    )

                headerFields.append(headerField)

                i += 1

            models.ImageHeaderField.objects.bulk_create(headerFields)

    outputText += "imagestats:wcs: " + filename + "\n"
    if os.path.splitext(filename)[-1].lower() in settings.SUPPORTED_IMAGE_TYPES:
        # FIXME: Bug with image from DSLR with astronomy.net plate solution
        """FITS WCS distortion paper lookup tables and SIP distortions only work in 2
        dimensions. However, WCSLIB has detected 3 dimensions in the core WCS keywords. To
        use core WCS in conjunction with FITS WCS distortion paper lookup tables or SIP
        distortion, you must select or reduce these to 2 dimensions using the naxis
        kwarg.""" 
        w = wcs.WCS(settings.MEDIA_ROOT + filename)

        if w.has_celestial:
            outputText += "WCS found in header" + "\n"

            # If the image was created by cosmic itself we will have set a wcsSource image
            # property when we wrote the wcs to the fits file.
            source = image.getImageProperty('wcsSource')
            if source is None:
                source = 'original'

            models.storeImageLocation(image, w, source)
        else:
            image.addImageProperty('numPlateSolutions', 0)
            outputText += "WCS not found in header" + "\n"


    # TODO: Perform image processing.
    #   1: Detect and mark non-data pixels: cosmic rays, hot pixels, dead pixels,
    #   over-exposed pixels, under-exposed pixels, artificial satellite.
    #       NOTE: Check if pixels adjacent to non-data pixels can be used, or should be
    #       discarded.
    #       TODO: Figure out how to use this data
    #           a: cosmic rays
    #
    #   2: Generate and apply bias, dark, flat, air mass, moonlight scatter, light
    #   pollution
    #       NOTE: combining will be generated as a seperate task, the results of which
    #       will be passed back into the image analysis queue
    #   3: Detect haze and clouds

    outputText += "imagestats:histogram: " + filename + "\n"
    if os.path.splitext(filename)[-1].lower() in settings.SUPPORTED_IMAGE_TYPES:
        hdulist = fits.open(settings.MEDIA_ROOT + filename)
        with transaction.atomic():
            channelIndex = 0
            hduIndex = 0
            for hdu in hdulist:
                frames = []
                #TODO: Check that this is really image data and not a table, etc.
                if len(hdu.data.shape) == 2:
                    frames.append(hdu.data)

                elif len(hdu.data.shape) == 3:
                    for i in range(hdu.data.shape[0]):
                        frames.append(hdu.data[channelIndex+i])

                else:
                    #TODO: Throw an error.
                    pass

                frameIndex = 0
                for frame in frames:
                    try:
                        channelInfo = models.ImageChannelInfo.objects.get(image=image, index=channelIndex)
                    except:
                        outputText += '\n\nERROR: continuing loop because channel info not found. id: {} index: {}\n\n\n'.format(image.pk, channelIndex)
                        continue

                    outputText += "Starting analysis of channel: {}\n\n".format(channelIndex)
                    startms = int(1000 * time.time())
                    # TODO: Need to filter all non-data pixels
                    #   NOTE: now finds and removes bathtub pixels

                    # Compute and store the row and column averages for the image frame.
                    outputText += "Computing row and column mean values ... "
                    msec = int(1000 * time.time())
                    rowMeans = numpy.nanmean(frame, axis=1)
                    colMeans = numpy.nanmean(frame, axis=0)

                    imageSliceMeans = []
                    for direction, means in [('r', rowMeans), ('c', colMeans)]:
                        for mean, index in zip(means, range(len(means))):
                            imageSliceMean = models.ImageSliceMean(
                                channelInfo = channelInfo,
                                direction = direction,
                                index = index,
                                mean = mean
                                )

                            imageSliceMeans.append(imageSliceMean)

                    models.ImageSliceMean.objects.bulk_create(imageSliceMeans)

                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n".format(msec)

                    for direction, means, xsize, ysize, rangeString, usingString in [
                            ('row', rowMeans, 75, 900*(frame.shape[0]/frame.shape[1]), 'set yrange [0:{}]'.format(frame.shape[0]), 'using 1:0'),
                            ('col', colMeans, 900, 75, 'set xrange [0:{}]'.format(frame.shape[1]), 'using 0:1')
                            ]:
                        dataFilename = direction + "MeanData_{}_{}.txt".format(image.pk, channelIndex)
                        plotFilename = direction + "MeanData_{}_{}.gnuplot".format(image.pk, channelIndex)
                        imageFilename = direction + "MeanData_{}_{}.gnuplot.svg".format(image.pk, channelIndex)
                        with open(settings.MEDIA_ROOT + dataFilename, "w") as outputFile:
                            for mean in means:
                                outputFile.write("{}\n".format(mean))

                        with open(settings.MEDIA_ROOT + plotFilename, "w") as outputFile:
                            outputFile.write("set terminal svg size {},{} dynamic mouse standalone\n".format(xsize, ysize) +
                                             "set output '{}'\n".format(settings.COSMIC_STATIC + "images/" + imageFilename) +
                                             "set lmargin 0\n" +
                                             "set rmargin 0\n" +
                                             "set tmargin 0\n" +
                                             "set bmargin 0\n" +
                                             "set key off\n" +
                                             rangeString + "\n" +
                                             "set format x \"\"\n" +
                                             "set format y \"\"\n" +
                                             "plot '{}' {} with lines".format(settings.MEDIA_ROOT + dataFilename, usingString))

                        outputText += "Generating {} mean image ... ".format(direction)
                        msec = int(1000 * time.time())
                        proc = subprocess.Popen(['gnuplot', settings.MEDIA_ROOT + plotFilename],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        output, error = proc.communicate()
                        output = output.decode('utf-8')
                        error = error.decode('utf-8')
                        proc.wait()
                        msec = int(1000 * time.time()) - msec
                        errorText += '==================== start process error ====================\n'
                        errorText += error
                        errorText += '===================== end process error =====================\n'
                        outputText += "completed: {}ms\n".format(msec)
                        outputText += '==================== start process output ====================\n'
                        outputText += output
                        outputText += '===================== end process output =====================\n'

                    # Count all pixel values into a 2D numpy array. Column 1 contains
                    # sorted, unique values from the frame, and column 2 contains the
                    # respective count.
                    outputText += "Counting pixel values ... "
                    msec = int(1000 * time.time())
                    # FIXME: More sophisticated pixel count than xdim * ydim
                    # NOTE: Partially implemented with masking below
                    pixelNumber = frame.shape[0]*frame.shape[1]
                    valueFrequency = scipy.stats.itemfreq(frame)
                    pixelValues = valueFrequency.take(0, axis=1)
                    pixelCounts = valueFrequency.take(1, axis=1)
                    uniquePixelValues = valueFrequency.shape[0]
                    approximateBitDepth = round(math.log(uniquePixelValues, 2),2)
                    minIndex = 0
                    maxIndex = uniquePixelValues - 1
                    minValue = valueFrequency[minIndex][0]
                    maxValue = valueFrequency[maxIndex][0]
                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n".format(msec)
                    outputText += "pixel number: {}\n".format(pixelNumber)
                    outputText += "minValue: {}\n".format(minValue)
                    outputText += "maxValue: {}\n".format(maxValue)
                    outputText += "unique values: {}\n".format(uniquePixelValues)
                    outputText += "approximate bits/pixel: {}\n".format(approximateBitDepth)
                    outputText += "\n"

                    # Now we will do some trimming
                    currentPixelNumber = pixelNumber
                    outputText += "Searching for bathtub pixel values ... "
                    msec = int(1000 * time.time())
                    currentPixelValueNumber = uniquePixelValues
                    bathtubLimit = 0.25 / 100 / 2
                    bathtubValues = SortedDict()
                    bathtubValueNumber = 0
                    bathtubPixelNumber = 0
                    bathtubLow = None
                    bathtubHigh = None
                    bathtubFound = True
                    bathtubFail = False
                    while bathtubFound :
                        bathtubFound = False
                        while valueFrequency[minIndex][1] / currentPixelNumber > bathtubLimit :
                            value, count = valueFrequency[minIndex]
                            bathtubValues[value] = int(count)
                            minIndex += 1
                            currentPixelNumber -= count
                            bathtubPixelNumber += count
                            bathtubLow = value
                            currentPixelValueNumber -= 1
                            bathtubValueNumber += 1
                            bathtubFound = True
                            if minIndex >= maxIndex :
                                bathtubFail = True
                                bathtubFound = False
                                break
                        while valueFrequency[maxIndex][1] / currentPixelNumber > bathtubLimit :
                            value, count = valueFrequency[maxIndex]
                            bathtubValues[value] = int(count)
                            maxIndex -= 1
                            currentPixelNumber -= count
                            bathtubPixelNumber += count
                            bathtubHigh = value
                            currentPixelValueNumber -= 1
                            bathtubValueNumber += 1
                            bathtubFound = True
                            if maxIndex <= minIndex :
                                bathtubFail = True
                                bathtubFound = False
                                break
                    if bathtubPixelNumber / currentPixelNumber > 1./3 :
                        outputText += "\nToo many suspect bathtub pixels found!\n"
                        outputText += "Recording bathtub values, but resetting min and max values.\n"
                        minIndex = 0
                        maxIndex = uniquePixelValues - 1
                        currentPixelNumber += bathtubPixelNumber
                        currentPixelValueNumber += bathtubValueNumber
                        bathtubFail = True
                    minValue = valueFrequency[minIndex][0]
                    maxValue = valueFrequency[maxIndex][0]
                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n".format(msec)
                    outputText += "bathtub limit: {}%\n".format(100*bathtubLimit)
                    outputText += "total bathtub values: {}, {}%\n".format( bathtubValueNumber,
                        round(100*bathtubValueNumber/(bathtubValueNumber + currentPixelValueNumber),4))
                    outputText += "total bathtub pixels: {}, {}%\n".format(bathtubPixelNumber,
                        round(100*bathtubPixelNumber/(bathtubPixelNumber + currentPixelNumber),4))
                    outputText += "bathtub (value,pixels): " + str(list(bathtubValues.items())) + "\n"
                    outputText += "highest low bathtub value: {}\n".format(bathtubLow)
                    outputText += "lowest high bathtub value: {}\n".format(bathtubHigh)
                    outputText += "remaining values: {}, {}%\n".format( currentPixelValueNumber,
                        round(100*currentPixelValueNumber/(bathtubValueNumber + currentPixelValueNumber),4))
                    outputText += "remaining pixels: {}, {}%\n".format(currentPixelNumber,
                        round(100*currentPixelNumber/(bathtubPixelNumber + currentPixelNumber),4))
                    outputText += "remaining min(Index, Value): ({}, {})\n".format(minIndex, minValue)
                    outputText += "remaining max(Index, Value): ({}, {})\n".format(maxIndex, maxValue)
                    outputText += "\n"


                    # Get pixel value bounds assuming we will ignore the values for some
                    # percentage of the brightest and darkest pixels when making thumbnails.
                    # I can't believe I can't suss out the syntax for a do while loop. I
                    # guess the internet is sometimes useful ... or maybe I should have
                    # kept that little python o'rielys pocketbook.  Hmm ... books.
                    outputText += "Finding dark and light points ... "
                    msec = int(1000 * time.time())
                    ignoreLower = models.CosmicVariable.getVariable('histogramIgnoreLower') / 100.0
                    ignoredLowerValue = valueFrequency[minIndex][0]
                    ignoredLowerPixels = valueFrequency[minIndex][1]
                    while ignoredLowerPixels < ignoreLower * currentPixelNumber :
                        minIndex += 1
                        peekValue, peekPixels = valueFrequency[minIndex]
                        if ignoredLowerPixels + peekPixels > ignoreLower * currentPixelNumber :
                            includeFraction = (ignoreLower * currentPixelNumber - ignoredLowerPixels) / peekPixels
                            ignoredLowerValue = (1.0-includeFraction)*valueFrequency[minIndex-1][0] + includeFraction*peekValue
                        else :
                            ignoredLowerValue = peekValue
                        ignoredLowerPixels += peekPixels
                    ignoreUpper = models.CosmicVariable.getVariable('histogramIgnoreUpper') / 100.0
                    ignoredUpperValue, ignoredUpperPixels = valueFrequency[maxIndex]
                    while ignoredUpperPixels < ignoreUpper * currentPixelNumber :
                        maxIndex -= 1
                        peekValue, peekPixels = valueFrequency[maxIndex]
                        if ignoredUpperPixels + peekPixels > ignoreUpper * currentPixelNumber :
                            includeFraction = (ignoreUpper * currentPixelNumber - ignoredUpperPixels) / peekPixels
                            ignoredUpperValue = includeFraction*peekValue + (1.0-includeFraction)*valueFrequency[maxIndex+1][0]
                        else :
                            ignoredUpperValue = peekValue
                        ignoredUpperPixels += peekPixels
                    minValue = valueFrequency[minIndex][0]
                    maxValue = valueFrequency[maxIndex][0]
                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n".format(msec)
                    outputText += "dark point {}, contains {} pixels, {}%, {}% of originial frame\n".format(
                        ignoredLowerValue, ignoredLowerPixels,
                        round(100*ignoredLowerPixels / currentPixelNumber, 4),
                        round(100*ignoredLowerPixels / pixelNumber, 4) )
                    outputText += "light point {}, contains {} pixels, {}%, {}% of originial frame\n".format(
                        ignoredUpperValue, ignoredUpperPixels,
                        round(100*ignoredUpperPixels / currentPixelNumber, 4),
                        round(100*ignoredUpperPixels / pixelNumber, 4) )
                    outputText += "min(Index, Value): ({}, {})\n".format(minIndex, minValue)
                    outputText += "max(Index, Value): ({}, {})\n".format(maxIndex, maxValue)
                    outputText += "\n"


                    # Get the mean value of remaining pixels to calculate gamma correction
                    outputText += "Finding mean value of clipped pixels ... "
                    msec = int(1000 * time.time())
                    unclippedPixelNumber = currentPixelNumber - ignoredLowerPixels - ignoredUpperPixels
                    meanUnclippedPixels = sum( pixelValues[minIndex:maxIndex] *
                        pixelCounts[minIndex:maxIndex] ) / unclippedPixelNumber
                    mean = sum( pixelValues[minIndex:maxIndex] * pixelCounts[minIndex:maxIndex] ) / unclippedPixelNumber
                    meanFrac = (meanUnclippedPixels - minValue)/(maxValue - minValue)
                    targetMean = 0.8 * minValue + 0.2 * maxValue
                    targetMeanFrac = (targetMean - minValue)/(maxValue - minValue)
                    gammaCorrection = math.log(meanFrac)/math.log(targetMeanFrac)
                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n".format(msec)
                    outputText += "mean: {}, {}%\n".format(meanUnclippedPixels,meanFrac)
                    outputText += "targetmean: {}, {}%\n".format(targetMean,targetMeanFrac)
                    outputText += "gamma: {}\n".format(gammaCorrection)
                    outputText += "\n"


                    # Digitize and rebin the the value counts to a histogram
                    outputText += "Generating histograms from value counts ... "
                    msec = int(1000 * time.time())
                    thumbnailBitDepth = 8
                    binNumber = pow(2, thumbnailBitDepth)
                    binsLinear = minValue + (maxValue - minValue) * numpy.linspace(0, 1, binNumber)
                    binsGamma = minValue + (maxValue - minValue) * pow(numpy.linspace(0, 1, binNumber), gammaCorrection)
                    binAssignLinear = numpy.digitize(pixelValues.clip(minValue, maxValue), binsLinear)
                    binAssignGamma = numpy.digitize(pixelValues.clip(minValue, maxValue), binsGamma)
                    histCountLinear = numpy.bincount(binAssignLinear, pixelCounts, binNumber)
                    histCountGamma = numpy.bincount(binAssignGamma, pixelCounts, binNumber)
                    histContribLinear = pixelCounts / histCountLinear[binAssignLinear]
                    histContribGamma = pixelCounts / histCountGamma[binAssignGamma]
                    histCenterLinear = numpy.bincount(binAssignLinear, pixelValues * histContribLinear, binNumber)
                    histCenterGamma = numpy.bincount(binAssignGamma, pixelValues * histContribGamma, binNumber)
                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n".format(msec)
                    outputText += "digitized bits/pixel: {}\n".format(thumbnailBitDepth)
                    outputText += "digitized shades: {}\n".format(binNumber)
                    outputText += "\n"


                    # Generate fast histogram for image info page
                    outputText += "Writing histograms to file ... "
                    msec = int(1000 * time.time())
                    histDataFilename = "histogramData_{}_{}.txt".format(image.pk, channelIndex)
                    histPlotFilename = "histogramData_{}_{}.gnuplot".format(image.pk, channelIndex)
                    histImageFilename = "histogramData_{}_{}.gnuplot.svg".format(image.pk, channelIndex)
                    histDataLongFilename = settings.MEDIA_ROOT + histDataFilename
                    histPlotLongFilename = settings.MEDIA_ROOT + histPlotFilename
                    histImageLongFilename = settings.COSMIC_STATIC + "images/" + histImageFilename
                    with open(histDataLongFilename, "w") as outputFile :
                        for i in range(binNumber) :
                            outputFile.write("{} {} {} {}\n".format(
                                histCenterLinear[i],
                                histCountLinear[i],
                                histCenterGamma[i],
                                histCountGamma[i]
                            ))
                    with open(histPlotLongFilename, "w") as outputFile :
                        outputFile.write("set terminal svg size 400,300 dynamic mouse standalone\n" +
                                         "set output '{}'\n".format(histImageLongFilename) +
                                         "set key off\n" +
                                         "set logscale y\n" +
                                         "set xrange [{}:{}]\n".format(minValue, maxValue) +
                                         "set style line 1 linewidth 3 linecolor 'blue'\n" +
                                         "set style line 2 linewidth 2 linecolor 'red'\n" +
                                         "plot '{}' using 1:2 with lines linestyle 1, ".format(histDataLongFilename) +
                                         "'' using 3:4 with lines linestyle 2\n")
                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n".format(msec)
                    outputText += "histogram data file: {}\n".format(histDataFilename)
                    outputText += "histogram plot file: {}\n".format(histPlotFilename)
                    outputText += "\n"


                    # Run gnuplot
                    outputText += "Generating histogram image ... "
                    msec = int(1000 * time.time())
                    proc = subprocess.Popen(['gnuplot', histPlotLongFilename],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    output, error = proc.communicate()
                    output = output.decode('utf-8')
                    error = error.decode('utf-8')
                    proc.wait()
                    msec = int(1000 * time.time()) - msec
                    errorText += '==================== start process error ====================\n'
                    errorText += error
                    errorText += '===================== end process error =====================\n'
                    outputText += "completed: {}ms\n".format(msec)
                    outputText += '==================== start process output ====================\n'
                    outputText += output
                    outputText += '===================== end process output =====================\n'
                    outputText += "histogram image file: {}\n".format(histImageFilename)
                    outputText += "\n"


                    # Digitize the raw value counts into an image
                    if channelIndex == 0 :
                        outputText += "Digitizing the frame to a full size image ... "
                        msec = int(1000 * time.time())
                        binNumber = pow(2, thumbnailBitDepth)
                        binsGamma = minValue + (maxValue - minValue) * pow(numpy.linspace(0, 1, binNumber), gammaCorrection)
                        binAssignment = numpy.digitize(frame.clip(minValue, maxValue), binsGamma)
                        msec = int(1000 * time.time()) - msec
                        outputText += "completed: {}ms\n".format(msec)
                        outputText += "\n"


                    # Write the gamma corrected png full size thumbnail.
                    outputText += "Writing full size png thumbnail ... "
                    pngImageFilename = os.path.splitext(filename)[0] + "_thumb_full.png"
                    ydim, xdim = binAssignment.shape
                    msec = int(1000 * time.time())
                    imageio.imwrite(settings.COSMIC_STATIC + "images/" + pngImageFilename, numpy.flip(binAssignment, axis=0), optimize=True, bits=8)
                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n\n".format(msec)

                    # Create a database record for the thumbnail.
                    if channelIndex == 0:
                        record = models.ImageThumbnail(
                            image = image,
                            width = xdim,
                            height = ydim,
                            size = 'full',
                            channel = channelIndex,
                            filename = pngImageFilename
                            )

                        record.save()

                    #TODO: Look into this masking and potentially record the masked pixel
                    # data as a stored thing which can be accessed later on.
                    # Create frame mask
                    outputText += "Generating frame mask ... "
                    msec = int(1000 * time.time())
                    # mask = make_source_mask(frame, snr=10, npixels=5, dilate_size=11)
                    rejectValues = numpy.array([])
                    rejectPixelNumber = 0
                    bathtubRejects = numpy.array(bathtubValues.keys())
                    bathtubPixelCounts = numpy.array(bathtubValues.values())
                    if not bathtubFail and bathtubRejects.shape[0] > 0 :
                        rejectValues = numpy.union1d(rejectValues, bathtubRejects)
                        rejectPixelNumber += sum(bathtubPixelCounts)
                    otherRejects = numpy.array([])
                    if otherRejects.shape[0] > 0 :
                        rejectValues = numpy.union1d(rejectValues, otherRejects)
                    moreRejects = numpy.array([])
                    if moreRejects.shape[0] > 0 :
                        rejectValues = numpy.union1d(rejectValues, moreRejects)
                    rejectValueNumber = rejectValues.shape[0]
                    mask = numpy.ma.in1d(frame.ravel(), rejectValues).reshape(frame.shape)
                    maskedFrame = numpy.ma.masked_array(frame, mask)
                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n".format(msec)
                    outputText += "masked values: {}\n".format(rejectValueNumber)
                    outputText += "masked pixels: {}\n".format(rejectPixelNumber)
                    outputText += "\n"


                    # Get statistics on unmasked frame
                    outputText += "Non-masked frame statistics ... "
                    msec = int(1000 * time.time())
                    ( nonmaskedNumber, (nonmaskedMin, nonmaskedMax),
                      nonmaskedMean, nonmaskedVariance,
                      nonmaskedSkewness, nonmaskedKurtosis ) = scipy.stats.describe(frame.ravel())
                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n".format(msec)
                    outputText += "pixels: {}\n".format(nonmaskedNumber)
                    outputText += "min: {}\n".format(nonmaskedMin)
                    outputText += "max: {}\n".format(nonmaskedMax)
                    outputText += "mean: {}\n".format(nonmaskedMean)
                    outputText += "variance: {}\n".format(nonmaskedVariance)
                    outputText += "skewness: {}\n".format(nonmaskedSkewness)
                    outputText += "kurtosis: {}\n".format(nonmaskedKurtosis)
                    outputText += "\n"


                    # Get statistics on masked frame
                    outputText += "Getting statistics on masked frame ... "
                    msec = int(1000 * time.time())
                    maskedMean, maskedMedian, maskedStdDev = sigma_clipped_stats(maskedFrame, sigma=0, maxiters=0)
                    # Converges well with 3 iterations.  Half as much time as maxiters=None
                    bgMean, bgMedian, bgStdDev = sigma_clipped_stats(maskedFrame, sigma=3, maxiters=3)
                    msec = int(1000 * time.time()) - msec
                    outputText += "completed: {}ms\n".format(msec)
                    outputText += "mean: {}\n".format(maskedMean)
                    outputText += "median: {}\n".format(maskedMedian)
                    outputText += "stdDev: {}\n".format(maskedStdDev)
                    outputText += "background mean: {}\n".format(bgMean)
                    outputText += "background median: {}\n".format(bgMedian)
                    outputText += "background stdDev: {}\n".format(bgStdDev)
                    outputText += "\n"

                    channelInfo.hduIndex = hduIndex
                    channelInfo.frameIndex = frameIndex
                    channelInfo.mean = maskedMean
                    channelInfo.median = maskedMedian
                    channelInfo.stdDev = maskedStdDev
                    channelInfo.bgMean = bgMean
                    channelInfo.bgMedian = bgMedian
                    channelInfo.bgStdDev = bgStdDev
                    channelInfo.pixelNumber = pixelNumber
                    channelInfo.minValue = nonmaskedMin
                    channelInfo.maxValue = nonmaskedMax
                    channelInfo.uniqueValues = uniquePixelValues
                    channelInfo.approximateBits = approximateBitDepth
                    channelInfo.bathtubLimit = bathtubLimit
                    channelInfo.bathtubValueNumber = bathtubValueNumber
                    channelInfo.bathtubPixelNumber = bathtubPixelNumber
                    channelInfo.bathtubLow = bathtubLow
                    channelInfo.bathtubHigh = bathtubHigh
                    channelInfo.thumbnailBlackPoint = ignoredLowerValue
                    channelInfo.thumbnailWhitePoint = ignoredUpperValue
                    channelInfo.thumbnailGamma = gammaCorrection
                    channelInfo.maskedValues = rejectValueNumber
                    channelInfo.maskedPixels = rejectPixelNumber

                    channelInfo.save()

                    frameIndex += 1
                    channelIndex += 1

            hduIndex += 1

        hdulist.close()

        numChannels = models.ImageChannelInfo.objects.filter(image=image).count()
        image.addImageProperty('totalNumChannels', numChannels)

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

# TODO: Histogram of FITS data (count vs adu) in linear and logarithmic (if possible?).
# Needs to be high resolution, but deal efficiently with large swaths of 0-count.  Must
# ignore non-data pixels properly. Design as per discussion.

# TODO: Fit a gaussian curve to the dark pixels in the histogram.
#   Histogram area used for fitting should start at the darkest populated pixel and extend
#   to include at least * 10% of the total data pixels and as many further bins as
#   improves + fitting metric.
# NOTE: Extending past the * 10% may be tricky.  Though we are assumed to be in a dense
# region there may be empty bins or features that result in the addition of * one bin to be
# detrimental to the fitting metric, but adding * two bins improves the fit.
#   Step by a minimum number of pixels rather than by number of bins.  Set number of pixels
#   as some percentage of the total pixels * 1%, or as a percentage of the pixels used in the
#   fitting so far * 10%.
# * Arbitrary value
# + Mimize sum of square of difference, or something more clever.
#   Maybe too clever: minimize \sum_{i=0}^{b(n)} \frac{w_i^2 (f_i - c_i)^2}{n^a}, where
#       n = number of pixels used to fit
#       b(n) = minimum bin number with n cumulative pixels
#       w_i = width of bin i
#       f_i = value of functional fit at bin i
#       c_i = count at bin i
#       a = coeffecient ... suspect = 1
#   Now, vary n along with coeffecients of f

# Generate a histogram for initial image analysis.

# Due to the nature of the data, naive histogram approaches with even
# very many fixed width bins often fail to produce satisfactory
# results.

# Here we count every pixel value.  An individual pixel value count
# represents samples of the image in the neighborhood of that value.
# The neighborhood of a pixel value is the interval half way to the
# next lowest and highest value.

# The histogram is constructed from the counts by dividing the counts
# by the width of the neighborhood for each pixel value found.

# Compression of the histogram is accomplished by the following process:
#   1: Select a pixel value at random
#       1a: Generate a random sequence of the indexes
#       1b: Subtract from the index the count of deleted indices less
#       than the generated index to generate an index to the squozen
#       data.
#   2: Perform a trial deletion of the pixel value, where the nearest
#   two values and counts are adjusted minimize distortion of the
#   histogram and preserve total count.
#   3: Accept deletion randomly based on percent error of histogram
#   introduced by the deletion.
#       3a: Record the index of deleted value/count pairs.
#   4: Repeat above until all pixel values have been tested exactly
#   once.  Note that a pixel value and count changed by a deletion
#   process may still be selected for trial deletion if it had not yet
#   been selected.
#   5: If histogram is still too large, loosen acception criteria and
#   repeat.
def depricatedHistogram(frame) :
    def overlapError(x, a):
        """ Computes the percent overlap of the histogram defined by two
        sets of bin center / bin count pairs. """
        aCenters = numpy.array(a.keys())
        aCounts = numpy.array(a.values())
        bCenters = numpy.array([ aCenters[0], x[0], x[2], aCenters[4] ])
        bCounts = numpy.array([ aCounts[0], x[1], x[3], aCounts[4] ])
        assert( len(bCenters) + 1 == len(aCenters) )

        aLeft = numpy.array([
            1.5*aCenters[0] - 0.5*aCenters[1],
            0.5*aCenters[0] + 0.5*aCenters[1],
            0.5*aCenters[1] + 0.5*aCenters[2],
            0.5*aCenters[2] + 0.5*aCenters[3],
            0.5*aCenters[3] + 0.5*aCenters[4]
            ])

        bLeft = numpy.array([
            1.5*bCenters[0] - 0.5*bCenters[1],
            0.5*bCenters[0] + 0.5*bCenters[1],
            0.5*bCenters[1] + 0.5*bCenters[2],
            0.5*bCenters[2] + 0.5*bCenters[3]
            ])

        aRight = numpy.array([
            0.5*aCenters[0] + 0.5*aCenters[1],
            0.5*aCenters[1] + 0.5*aCenters[2],
            0.5*aCenters[2] + 0.5*aCenters[3],
            0.5*aCenters[3] + 0.5*aCenters[4],
            1.5*aCenters[4] - 0.5*aCenters[3]
            ])

        bRight = numpy.array([
            0.5*bCenters[0] + 0.5*bCenters[1],
            0.5*bCenters[1] + 0.5*bCenters[2],
            0.5*bCenters[2] + 0.5*bCenters[3],
            1.5*bCenters[3] - 0.5*bCenters[2],
            ])

        aWidth = aRight - aLeft
        bWidth = bRight - bLeft

        aHistogram = aCounts / aWidth
        bHistogram = bCounts / bWidth

        overlapHeightMins = numpy.empty([5,4])
        overlapHeightMins.flat = list( min(x,y) for (x,y) in
            itertools.product(aHistogram,bHistogram) )

        overlapLeftMaxs = numpy.empty([5,4])
        overlapLeftMaxs.flat = list( max(x,y) for (x,y) in
            itertools.product(aLeft,bLeft) )

        overlapRightMins = numpy.empty([5,4])
        overlapRightMins.flat = list( min(x,y) for (x,y) in
            itertools.product(aRight,bRight) )

        overlapWidths = overlapRightMins - overlapLeftMaxs

        overlapMask = overlapRightMins > overlapLeftMaxs

        overlapAreas = overlapMask * overlapHeightMins * overlapWidths

        initialArea = sum(aCounts)
        totalOverlapArea = sum(overlapAreas.flat)
        # Scale relative to overall contribution
        fitness = (initialArea - totalOverlapArea) / currentPixelNumber
        fitness *= fitness

        fitnessJacobian = numpy.zeros([4])

        return fitness

    def conserveTotalPixelCountConstraint(x, total):
        return (x[1] + x[3]) - total

    # Perform initial statistics
    # TODO: prefilter known bad values from frame
    outputText += "Initial frame statistics ... "
    msec = int(1000 * time.time())
    ( pixelNumber, (pixelValueMin, pixelValueMax),
      pixelValueMean, pixelValueVariance,
      pixelValueSkewness, pixelValueKurtosis ) = scipy.stats.describe(frame.flat)
    currentPixelNumber = pixelNumber
    msec = int(1000 * time.time()) - msec
    outputText += "completed: {}ms\n".format(msec)
    outputText += "data pixels:  " + str(pixelNumber) + "\n"
    outputText += "min: " + str(pixelValueMin) + "\n"
    outputText += "max: " + str(pixelValueMax) + "\n"
    outputText += "mean: " + str(pixelValueMean) + "\n"
    outputText += "variance: " + str(pixelValueVariance) + "\n"
    outputText += "skewness: " + str(pixelValueSkewness) + "\n"
    outputText += "kurtosis:  " + str(pixelValueKurtosis) + "\n"
    outputText += "\n"


    # Count all pixel values into a sorted dict with key of the pixel
    # value and the value is the number of pixels with that value.
    outputText += "Counting pixel values ... "
    msec = int(1000 * time.time())
    pixelCounts = SortedDict(Counter(frame.flat))
    uniquePixelValues = len(pixelCounts)
    approximateBitDepth = round(math.log(uniquePixelValues, 2),2)
    msec = int(1000 * time.time()) - msec
    outputText += "completed: {}ms\n".format(msec)
    outputText += "unique values: " + str(uniquePixelValues) + "\n"
    outputText += "approximate bit depth:" + str(approximateBitDepth) + "\n"
    outputText += "\n"


    # Look for and remove from histogram bathtub values that might
    # indicate over-or-under-exposed pixels.
    bathtubLimit = 0.25 / 100
    outputText += "Searching for bathtub pixel values ... "
    msec = int(1000 * time.time())
    currentPixelValueNumber = uniquePixelValues
    bathtubValues = SortedDict()
    bathtubValueNumber = 0
    bathtubPixelNumber = 0
    bathtubFound = True
    while bathtubFound :
        bathtubFound = False
        while pixelCounts.peekitem(index=0)[1] / currentPixelNumber > bathtubLimit :
            popKey, popCount = pixelCounts.popitem(last=False)
            bathtubValues[popKey] = popCount
            currentPixelNumber -= popCount
            bathtubPixelNumber += popCount
            currentPixelValueNumber -= 1
            bathtubValueNumber += 1
            bathtubFound = True
        while pixelCounts.peekitem(index=-1)[1] / currentPixelNumber > bathtubLimit :
            popKey, popCount = pixelCounts.popitem(last=True)
            bathtubValues[popKey] = popCount
            currentPixelNumber -= popCount
            bathtubPixelNumber += popCount
            currentPixelValueNumber -= 1
            bathtubValueNumber += 1
            bathtubFound = True
        if bathtubFound :
            outputText += ". "

    msec = int(1000 * time.time()) - msec
    outputText += "completed: {}ms\n".format(msec)
    if bathtubPixelNumber / currentPixelNumber > 1.0 / 3.0 :
        outputText += "Too many suspect bathtub pixels found!\n"
        outputText += "\tRestoring bathtub values to histogram ... "
        pixelCounts.update = bathtubValues
        currentPixelNumber += bathtubPixelNumber
        bathtubFailure = True
    else :
        bathtubFailure = False
    outputText += "total bathtub values: {}, {}%\n".format( bathtubValueNumber,
        round(100*bathtubValueNumber/(bathtubValueNumber + currentPixelValueNumber),4))
    outputText += "remaining values: {}, {}%\n".format( currentPixelValueNumber,
        round(100*currentPixelValueNumber/(bathtubValueNumber + currentPixelValueNumber),4))
    outputText += "total bathtub pixels: {}, {}%\n".format(bathtubPixelNumber,
        round(100*bathtubPixelNumber/(bathtubPixelNumber +
        currentPixelNumber),4))
    outputText += "remaining pixels: {}, {}%\n".format(currentPixelNumber,
        round(100*currentPixelNumber/(bathtubPixelNumber +
        currentPixelNumber),4))
    outputText += "bathtub (value,pixels): " + str(list(bathtubValues.items())) + "\n"
    outputText += "\n"


    # Get pixel value bounds assuming we will ignore the values for some
    # percentage of the brightest and darkest pixels when making thumbnails.
    # I can't believe I can't suss out the syntax for a do while loop. I
    # guess the internet is sometimes useful ... or maybe I should have
    # kept that little python o'rielys pocketbook.  Hmm ... books.
    outputText += "Finding dark and light points ... "
    msec = int(1000 * time.time())
    ignoreLower = models.CosmicVariable.getVariable('histogramIgnoreLower') / 100.0
    i = 0
    ignoredLowerValue, ignoredLowerPixels = pixelCounts.peekitem(index=i)
    while ignoredLowerPixels / currentPixelNumber < ignoreLower :
        i += 1
        peekValue, peekPixels = pixelCounts.peekitem(index=i)
        ignoredLowerValue = peekValue
        ignoredLowerPixels += peekPixels
    ignoreUpper = models.CosmicVariable.getVariable('histogramIgnoreUpper') / 100.0
    i = -1
    ignoredUpperValue, ignoredUpperPixels = pixelCounts.peekitem(index=i)
    while ignoredUpperPixels / currentPixelNumber < ignoreUpper :
        i -= 1
        peekValue, peekPixels = pixelCounts.peekitem(index=i)
        ignoredUpperValue = peekValue
        ignoredUpperPixels += peekPixels
    msec = int(1000 * time.time()) - msec
    outputText += "completed: {}ms\n".format(msec)
    outputText += "dark point {}, contains {} pixels, {}%, {}% of originial frame\n".format(
        ignoredLowerValue, ignoredLowerPixels,
        round(100*ignoredLowerPixels / currentPixelNumber, 4),
        round(100*ignoredLowerPixels / pixelNumber, 4) )
    outputText += "light point {}, contains {} pixels, {}%, {}% of originial frame\n".format(
        ignoredUpperValue, ignoredUpperPixels,
        round(100*ignoredUpperPixels / currentPixelNumber, 4),
        round(100*ignoredUpperPixels / pixelNumber, 4) )
    outputText += "\n"

    currentPixelValueNumber = len(pixelCounts)
    # If we have way too many values, do some rough binning.
    uniqueValuesStart = uniqueValuesLimit * 10
    if currentPixelValueNumber > uniqueValuesStart:
        outputText += "Beginning rough binning ... "
        msec = int(1000 * time.time())
        tempPixelCounts = SortedDict()
        roughStride = 1 + (currentPixelValueNumber // uniqueValuesStart)
        roughBins = currentPixelValueNumber // roughStride
        outputText += "Performing initial rough binning.  Goal values: " + str(roughBins) + "\n"
        for i in range(roughBins):
            roughKey = 0.0
            roughValue = 0.0
            for j in range(roughStride):
                key, value = pixelCounts.popitem()
                roughKey += key*value
                roughValue += value
            roughKey /= roughValue
            tempPixelCounts[roughKey] = roughValue
        # Check for leftovers and throw them in the last key/value
        if len(pixelCounts) > 0:
            roughKey = numpy.average(list(pixelCounts.iterkeys()),
                weights = list(pixelCounts.itervalues()) )
            roughValue = numpy.sum(list(pixelCounts.itervalues()))
            tempPixelCounts[roughKey] = roughValue
        pixelCounts.update(tempPixelCounts)
        msec = int(1000 * time.time()) - msec
        outputText += "completed: {}ms\n".format(msec)


    outputText += "Beginning adaptive re-binning ... "
    msec = int(1000 * time.time())
    # Replacement rejection exponent, lower this to accept more disruptive
    # deletions.  This will automatically adjust if one pass is not
    # sufficient to reduce the number of unique values.
    rejectionExponent = models.CosmicVariable.getVariable('histogramRejectionExponent')

    currentUniqueValues = len(pixelCounts)
    while currentUniqueValues > uniqueValuesLimit:

        # Initialize the list of deleted indices
        deletedIndices = SortedList()

        # Select in random order (almost) all unique pixel values to test
        # for trial deletion.
        for rawIndex in random.sample(range(2, currentUniqueValues - 2), currentUniqueValues - 4):
            # Adjust index to account for any deleted indices
            index = rawIndex - deletedIndices.bisect_left(rawIndex)

            indexStart = index - 2
            indexEnd = index + 3

            a = SortedDict(itertools.islice(pixelCounts.items(), indexStart, indexEnd))
            removedKey = a.peekitem(2)[0]
            removedCount = a.peekitem(2)[1]
            newCount1 = a.peekitem(1)[1] + removedCount/2.0
            newCount2 = a.peekitem(3)[1] + removedCount/2.0
            conservedCount = newCount1 + newCount2

            x0 = [
                a.peekitem(1)[0],
                newCount1,
                a.peekitem(3)[0],
                newCount2
                ]

            bounds = [
                (0.99*a.peekitem(0)[0] + 0.01*a.peekitem(1)[0],
                0.01*a.peekitem(1)[0] + 0.99*a.peekitem(2)[0] ),
                (a.peekitem(1)[1], None),
                (0.99*a.peekitem(2)[0] + 0.01*a.peekitem(3)[0],
                0.01*a.peekitem(3)[0] + 0.99*a.peekitem(4)[0]),
                (a.peekitem(3)[1], None)
                ]

            constraints = ({
                'type': 'eq',
                'fun' : conserveTotalPixelCountConstraint,
                'args': [conservedCount]
                })

            # TODO: Jacobian
            jacobian = False

            result = scipy.optimize.minimize(overlapError, x0, args=(a),
            bounds=bounds, constraints=constraints, method='SLSQP')
            if result.success:
                if result.fun < math.pow(random.uniform(0, 1), rejectionExponent):
                    deletedIndices.add(rawIndex)
                    pixelCounts.pop(removedKey)
                    pixelCounts.pop(x0[0])
                    pixelCounts.pop(x0[2])
                    pixelCounts[result.x[0]] = result.x[1]
                    pixelCounts[result.x[2]] = result.x[3]
                    if len(pixelCounts) == uniqueValuesLimit:
                        break
            else:
                errorText += 'Minimization failed:\n\n' + str(result) + '\n'

        deletionsThisCycle = currentUniqueValues - len(pixelCounts)
        deletionsNeeded = len(pixelCounts) - uniqueValuesLimit

        outputText += "Reduction step complete." +\
            " deletions: " + str(deletionsThisCycle) +\
            " , values: " + str(len(pixelCounts)) +\
            " , bits: " + str(round(math.log(len(pixelCounts),2),2)) +\
            " , rejection exponent: " + str(round(rejectionExponent,2)) +\
            " , deletions needed: " + str(deletionsNeeded) + "\n"

        # Adjust rejection exponent based on results
        if deletionsNeeded > 0:
            if deletionsThisCycle > 0:
                try:
                    rejectionExponent *= 0.5 + 1.5*math.exp( -1.0*deletionsNeeded/deletionsThisCycle )
                except ValueError:
                    outputText += '\nValueError exception in math.log(deletionsNeeded / deletionsThisCycle, rejectionExponent):\n' +\
                        'deletionsNeeded = ' + str(deletionsNeeded) +\
                        ', deletionsThisCycle = ' + str(deletionsThisCycle) +\
                        ', rejectionExponent = ' + str(rejectionExponent) + '\n'
            else:
                rejectionExponent /= 2.0

        currentUniqueValues = len(pixelCounts)
    # end of while
    msec = int(1000 * time.time()) - msec
    outputText += "completed: {}ms\n".format(msec)


    # This will injest the pixel count and histogram dicts into some numpy arrays
    histogramLength = len(pixelCounts)
    binCenters = numpy.empty([histogramLength])
    histPixels = numpy.empty([histogramLength])
    cumulativePixels = numpy.empty([histogramLength])
    totalCount = 0
    for i in range(histogramLength):
        (binCenters[i], histPixels[i]) = pixelCounts.popitem(last=False)
        totalCount += histPixels[i]
        cumulativePixels[i] = totalCount

    assert(totalCount == sum(histPixels))

    binLefts = numpy.empty([histogramLength])
    binRights = numpy.empty([histogramLength])
    binLefts[0] = 1.5 * binCenters[0] - 0.5 * binCenters[1]
    for i in range(1,histogramLength):
        binLefts[i] = 0.5 * (binCenters[i-1] + binCenters[i])
        binRights[i-1] = binLefts[i]
    binRights[histogramLength-1] = 1.5 * binCenters[histogramLength-1] - 0.5 * binCenters[histogramLength-2]

    histCounts = numpy.empty([histogramLength])
    for i in range(histogramLength):
        histCounts[i] = histPixels[i] / (1.0*binRights[i] - 1.0*binLefts[i])

    histogramBins = []
    errorText += 'histogram length is: ' + str(histogramLength)
    for i in range(histogramLength):
        histogramBin = models.ImageHistogramBin(
            image = image,
            binCenter = binCenters[i],
            binCount = histCounts[i]
            )

        histogramBins.append(histogramBin)

    models.ImageHistogramBin.objects.bulk_create(histogramBins)

    plotFilename = "histogramData_{}_{}.gnuplot".format(image.pk, channelIndex)
    binFilename = "histogramData_{}_{}.txt".format(image.pk, channelIndex)

    # Write the column data to be read in by gnuplot.
    lowerBound = binLefts[0]
    upperBound = binRights[histogramLength-1]
    cumulativeCount = 0.0
    cumulativeFraction = cumulativeCount / totalCount
    with open("/cosmicmedia/" + binFilename, "w") as outputFile:
        ignoreLower = models.CosmicVariable.getVariable('histogramIgnoreLower') / 100.0
        ignoreUpper = models.CosmicVariable.getVariable('histogramIgnoreUpper') / 100.0
        for i in range(histogramLength):
            binCount = histCounts[i]
            binCenter = binCenters[i]
            # Skip writing values for up 0.25% of the darkest and
            # brightest pixels. This is to match the parameters used in
            # generating thumnails.
            pixelCount = histPixels[i]
            pixelCountFraction = histPixels[i] / totalCount
            if cumulativeFraction < ignoreLower:
                if cumulativeFraction + pixelCountFraction >= ignoreLower:
                    overageFraction = cumulativeFraction + pixelCountFraction - ignoreLower
                    includeFraction = overageFraction / pixelCountFraction
                    lowerBound = includeFraction*binLefts[i]  + (1.0 - includeFraction)*binRights[i]
            cumulativeCount += histPixels[i]
            cumulativeFraction = cumulativeCount / totalCount
            if cumulativeFraction > 1.0 - ignoreUpper:
                if binCenter < upperBound:
                    overageFraction = cumulativeFraction - 1.0 + ignoreUpper
                    countFraction = histPixels[i] / totalCount
                    includeFraction = 1.0 - overageFraction / countFraction
                    upperBound = (1.0 - includeFraction)*binLefts[i] + includeFraction*binRights[i]

            outputFile.write("{} {} {}\n".format(binLefts[i], histCounts[i], (cumulativePixels[i]/totalCount) ) )
            outputFile.write("{} {} {}\n".format(binRights[i], histCounts[i], (cumulativePixels[i]/totalCount) ) )

    targetMean = 0.8*lowerBound + 0.2*upperBound
    meanFrac = (mean - lowerBound)/(upperBound - lowerBound)
    targetMeanFrac = (targetMean - lowerBound)/(upperBound - lowerBound)
    gammaCorrection = math.log(meanFrac, 10)/math.log(targetMeanFrac, 10)

    # Write the gnuplot script file.
    with open("/cosmicmedia/" + plotFilename, "w") as outputFile:
        outputFile.write("set terminal svg size 400,300 dynamic mouse standalone\n" +
                         "set output '{}/{}.svg'\n".format(settings.COSMIC_STATIC + "images", plotFilename) +
                         "set key off\n" +
                         "set logscale y\n" +
                         "set xrange ["+str(lowerBound)+":"+str(upperBound)+"]\n" +
                         "set style line 1 linewidth 3 linecolor 'blue'\n" +
                         "set style line 2 linewidth 2 linecolor 'red'\n" +
                         "plot '/cosmicmedia/{0}' using 1:2 with lines linestyle 1, ".format(binFilename) +
                         "'/cosmicmedia/{0}' using ( $1 * {3}**(($1-{1})/({2}-{1})) ):2 with lines linestyle 2\n".format(
                            binFilename, lowerBound, upperBound, gammaCorrection))

    outputText += "Running gnuplot:\n\n"
    proc = subprocess.Popen(['gnuplot', "/cosmicmedia/" + plotFilename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
            )

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    proc.wait()

    outputText += output
    errorText += error

    outputText += '\n ==================== End of process output ====================\n\n'
    errorText += '\n ==================== End of process error =====================\n\n'


@shared_task
def generateThumbnails(filename, processInputId):
    """
    A celery task to produce thumbnails of several standard sizes starting from the
    original full size png.
    """
    outputText = ""
    errorText = ""
    taskStartTime = time.time()

    filenameFull = os.path.splitext(filename)[0] + "_thumb_full.png"
    filenameSmall = os.path.splitext(filename)[0] + "_thumb_small.png"
    filenameMedium = os.path.splitext(filename)[0] + "_thumb_medium.png"
    filenameLarge = os.path.splitext(filename)[0] + "_thumb_large.png"

    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    imageChannels = models.ImageChannelInfo.objects.filter(image=image)

    # NOTE: For setting black-point, white-point, and gamma, we will apply a naive ideal
    # model for the thumbnail histogram.  See notebook for more details.  We will use the
    # range of [0:1] for intensity values.
    #   Ideal image properties:
    #       All data pixels are strictly above 0.0 and strictly below 1.0.
    #       Over-saturated pixels are exactly 1.0.
    #       Non-data pixels (hot, dead, etc) are flagged (have transparancy of 1.0, etc.)
    #       Pixels may have any shape and size?
    #   Ideal image assumptions:
    #       Sky background constitutes a large portion of the image.
    #           Sky background pixels can be found in a roughly gaussian-shaped grouping
    #           at the low end of the linear-scale histogram of the data pixels. See TODO
    #       Nebulosity results in a skewing of the histogram gaussian to the brighter
    #       values in proportion to the relative area.
    #           Fitting only the dimmer half of the histogram gaussian should be
    #           less sensitive to nebulosity.
    #               We may be able to stop the fitting well before the peak, making the
    #               fitting even less sensitive to nebulosity, etc.
    #   Ideal thumbnail properties:
    #       Show all the interesting features in an image.
    #       Viewable in wide range of ambient lighting.
    #       Be just large enough (bytes, dim) for the viewing context. NOTE: There are
    #       some interesting optimizations possible here.
    #           
    #
    #   Ideal thumbnail assumptions: Some ideas based on playing with source fits for a
    #   while.  Probably will evolve significantly over time.
    #       Over-exposed pixels represented as 1.0 
    #       About 0.01% of brightest, non-over-exposed pixels should be crushed to 1.0
    #       About 0.01% of darkest, non-dead pixels crushed to 0.0
    #       The fraction of bits devoted to sky pixels (and dim stars and nebulosity by
    #       extension) is proportional to their "interestingness" (scientifically, or
    #       asthetically, or whatever) rather than their proportion in the original data.
    #           We will devote the lower ~2/5 of the range for the sky gaussian, centered
    #           at ~1/5, leaving the rest for un-over-exposed "bright" pixels.
    #               Here we assume that the 3-sigma (~99%) width of the sky background
    #               gaussian (at least the ideal lower half which is less effected by
    #               nebulosity) is less than ~1/5.

    # TODO: Classify all non-data pixels.
    #       Read pixel classification from FITS header
    #       Run auto-classification on remaining pixels 
    #           Normalize image to [0,1]
    #           Mark dead any pixel with value = 0
    
    #TODO: For the really commonly loaded sizes like the ones in search results, etc, we
    # should consider sending a smaller size and scaling it up to the size we want on screen
    # to save bandwidth and decrease load times.
    
    #TODO: All the thumbnails are square so we should decide what to do about this.
    
    #TODO: Add some python logic to decide the exact dimensions we want the thumbnails to
    # be to preserve aspect ratio but still respect screen space requirements.
    for tempFilename, sizeArg, sizeString in [
        (filenameSmall, "100x100", "small"),
        (filenameMedium, "300x300", "medium"),
        (filenameLarge, "900x900", "large") ] :

        #TODO: Small images will actually get thumbnails made which are bigger than the original, should implement
        # protection against this - will need to test all callers to make sure that is safe.
        # Consider bad horiz/vert lines, also bad pixels, and finally noise.
        # For bad lines use low/negative values along the middle row/col in the kernel.
        proc = subprocess.Popen(['convert', '-verbose', '-strip', '-filter', 'Box', '-resize', sizeArg,
            settings.COSMIC_STATIC + "images/"+ filenameFull, '-depth', '8', settings.COSMIC_STATIC + "images/" + tempFilename],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        #TODO: Only looking at the first channel here, need to loop and add all channels if it is an RGB image, etc.

        output, error = proc.communicate()
        output = output.decode('utf-8')
        error = error.decode('utf-8')

        proc.wait()

        outputText += output
        errorText += error
        outputText += '\n ==================== End of process output ====================\n\n'
        errorText += '\n ==================== End of process error =====================\n\n'

        outputText += "generateThumbnails: " + tempFilename + "\n"

        # Read through the standard error output from image magick and parse the output to
        # grab the exact sizes and number of thumbnails that were created.  The output
        # sizes of the thumbnails will not exactly match the requested sizes since in general,
        # the aspect ratios will be different.  For images with more than one channel
        # image magick will also sometimes create extra thumbnails for each channel in the input image.
        with transaction.atomic():
            for line in error.splitlines():
                if '=>' in line:
                    fields = line.split()
                    outputFilename = fields[0].split('=>')[1]
                    channelIndicator = re.findall(r'\[\d+\]$', outputFilename)

                    if len(channelIndicator) == 0:
                        channel = 0
                    else:
                        channel = int(channelIndicator[0].strip('[]'))
                        outputFilename = outputFilename.split('[')[0]

                    outputFilename = os.path.basename(outputFilename)

                    dimensions = fields[3].split('+')[0].split('x')
                    w = int(dimensions[0])
                    h = int(dimensions[1])
                    outputText += 'Thumbnail width: {}      height: {}'.format(w, h) + "\n"

                    record = models.ImageThumbnail(
                        image = image,
                        width = w,
                        height = h,
                        size = sizeString,
                        channel = channel,
                        filename = outputFilename
                        )

                    record.save()

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

def initSourcefind(method, image):
    """
    This is a small helper function that parses the standard configuration options common
    to all or most of the source finding methods.  This function returns a tuple of
    information containting:

        detectionThresholdMultiplier - the number of standard deviations above background
        to consider a valid source.

        shouldReturn - a bool, if true the source find method does not need to be run at
        all for some reason.  For example, it is a calibration frame, or it already has
        found the number of sources the user said it should in a previous run.

        outputText and errorText - strings to be appended to the current output and error
        text streams for the task.  These strings contain information on how the other
        returned values were determined.
    """
    methodDict = {
        'sextractor': models.SextractorResult,
        'image2xy': models.Image2xyResult,
        'daofind': models.DaofindResult,
        'starfind': models.StarfindResult
        }

    shouldReturn = False
    outputText = ""
    errorText = ""

    outputText += "Running {}.\n\n".format(method)

    # If this is a calibration image we do not need to run this task.
    shouldReturn, retText = checkIfCalibrationImage(image, method, 'skippedCalibration')
    outputText += retText
    if shouldReturn:
        return (1, shouldReturn, outputText, errorText)

    # For image2xy there is no detectThresholdMultiplier to compute so we just return early.
    if method == 'image2xy':
        return (1, False, outputText, errorText)

    # Check to see if we have run this task before and adjust the sensitivity higher or lower
    # Start by seeing if we have a previously saved value, if not then load the default.
    detectThresholdMultiplier = image.getImageProperty(method + 'Multiplier')
    if detectThresholdMultiplier is None:
        detectThresholdMultiplier = models.CosmicVariable.getVariable(method + 'Threshold')
        outputText += 'Have not run before, setting default multiplier of {} standard deviations.\n'.format(detectThresholdMultiplier)
    else:
        detectThresholdMultiplier = float(detectThresholdMultiplier)
        outputText += "Last detect threshold was {}.\n".format(detectThresholdMultiplier)

        # Check to see if there is a recommendation from a method that got the sourcefind "about right".
        previousRunNumFound = methodDict[method].objects.filter(image=image).count()
        outputText += 'Previous run of this method found {} results.\n'.format(previousRunNumFound)
        numExpectedFeedback = image.getImageProperty('userNumExpectedResults', asList=True)
        minValid = 0
        maxValid = 1e9
        aboutRightRange = 0.2
        feedbackFound = False
        for feedback in numExpectedFeedback:
            feedbackFound = True
            numExpected, rangeString = feedback.value.split()
            numExpected = float(numExpected)
            findFactor = previousRunNumFound / numExpected
            outputText += 'User feedback indicates that {} results is {}.\n'.format(numExpected, rangeString)
            if rangeString == 'aboutRight':
                minValid = numExpected*(1-aboutRightRange)
                maxValid = numExpected*(1+aboutRightRange)
            elif rangeString in ['tooMany', 'wayTooMany']:
                maxValid = min(maxValid, numExpected*(1-aboutRightRange))
            elif rangeString in ['tooFew', 'wayTooFew']:
                minValid = max(minValid, numExpected*(1+aboutRightRange))

        #TODO: We should subtract the number of sources found by the previous run which are flagged as hot pixels, etc, before doing this comparison.
        if feedbackFound:
            outputText += "Valid range of results is between {} and {}.\n".format(minValid, maxValid)
            if previousRunNumFound <= 0.1*minValid:
                detectThresholdMultiplier -= 0.7 + 0.3*(.1*minValid)/previousRunNumFound
                outputText += "Last run was less than 10% of the user submitted range, reducing detection threshold a lot.\n"
            elif previousRunNumFound <= minValid:
                detectThresholdMultiplier -= 0.25
                outputText += "Last run was less than {}% of the user submitted range, reducing detection threshold a little.\n".format(100*(1-aboutRightRange))
            elif previousRunNumFound <= maxValid:
                outputText += "Last run was within {}% of the user submitted range, not running again.".format(100*aboutRightRange)
                shouldReturn = True
            elif previousRunNumFound <= 10*maxValid:
                detectThresholdMultiplier += 0.25
                outputText += "Last run was more than {}% of the user submitted range, increasing detection threshold a little.\n".format(100*(1+aboutRightRange))
            else:
                detectThresholdMultiplier += 0.7 + 0.3*previousRunNumFound/(10*maxValid)
                outputText += "Last run was more than 10 times the user submitted figure, increasing detection threshold a lot.\n"

    if detectThresholdMultiplier < 0.1:
        outputText += "Not running threshold of {} standard deviations, exiting.\n".format(detectThresholdMultiplier)
        shouldReturn = True

    # Store the multiplier we decided to use in case we re-run this method in the future.
    image.addImageProperty(method + 'Multiplier', str(detectThresholdMultiplier))

    return (detectThresholdMultiplier, shouldReturn, outputText, errorText)

def checkIfCalibrationImage(image, propertyKeyToSet, propertyValueToSet):
    """
    A simple helper function which returns a tuple whose first entry is True if the image
    is a calibration image of some sort and False if it is unknown or a science image.
    The second entry in the tuple is the output text to append to the output stream of the
    task calling this function.

    If the image is a calibration image then then in addition to returning true, the image
    will get an image property added to it with the specified key and value.  This can be
    used to tag the image as having been skipped for processing by the calling routine if
    it is a calibration image.

    TODO: Allow propertyKeyToSet, etc, to be None and skip creating the image property if so.
    """
    outputText = ''

    imageType = image.getImageProperty('imageType')
    outputText += "Image type is: " + str(imageType) + "\n"
    if imageType in ('bias', 'dark', 'flat', 'masterBias', 'masterDark', 'masterFlat'):
        outputText += "\n\n\nReturning, do not need to run this task on calibration images (bias, dark, flat, etc)\n"

        image.addImageProperty(propertyKeyToSet, propertyValueToSet)
        return (True, outputText)
    else:
        outputText += "\n\n\nNot returning, image is not known to be a calibration image (bias, dark, flat, etc)\n"
        return (False, outputText)

@shared_task
def sextractor(filename, processInputId):
    taskStartTime = time.time()

    # Get the image record
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = models.ImageChannelInfo.objects.filter(image=image).order_by('index')

    detectThresholdMultiplier, shouldReturn, outputText, errorText = initSourcefind('sextractor', image)

    if shouldReturn:
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    detectThreshold = detectThresholdMultiplier*channelInfos[0].bgStdDev
    outputText += 'Final multiplier of {} standard deviations.\n'.format(detectThresholdMultiplier)
    outputText += 'Final detect threshold of {} above background.\n'.format(detectThreshold)

    #TODO: sextractor can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    #TODO: sextractor has a ton of different modes and options, we should consider running
    # it multiple times to detect point sources, then again for extended sources, etc.
    # Each of these different settings options could be combined into a single output, or
    # they could be independently matched against other detection algorithms.
    catfileName = settings.MEDIA_ROOT + filename + ".cat"
    proc = subprocess.Popen(['source-extractor', '-CATALOG_NAME', catfileName, settings.MEDIA_ROOT + filename,
    '-THRESH_TYPE', 'ABSOLUTE', '-DETECT_THRESH', str(detectThreshold)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=settings.MEDIA_ROOT
        )

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    proc.wait()

    outputText += output
    errorText += error
    outputText += '\n ==================== End of process output ====================\n\n'
    errorText += '\n ==================== End of process error =====================\n\n'

    with open(catfileName, 'r') as catfile:
        fieldDict = {}
        with transaction.atomic():
            models.SextractorResult.objects.filter(image=image).delete()
            fwhmValues = []
            ellipticityValues = []
            sextractorResults = []
            for line in catfile:
                # Split the line into fields (space separated) and throw out empty fields caused by multiple spaces in a
                # row.  I.E. do a "combine consecutive delimeters" operation.
                fields = line.split()

                # Read the comment lines at the top of the file to record what fields are present and in what order.
                if line.startswith("#"):
                    fieldDict[fields[2]] = int(fields[1]) - 1

                #For lines that are not comments, use the fieldDict to determine what fields to read and store in the database.
                else:
                    zPos = None   #TODO: Add image layer number if this is a data cube, just leaving null for now.
                    sextractorResult = models.SextractorResult(
                        image = image,
                        pixelX = fields[fieldDict['X_IMAGE_DBL']],
                        pixelY = fields[fieldDict['Y_IMAGE_DBL']],
                        pixelZ = zPos,
                        fluxAuto = fields[fieldDict['FLUX_AUTO']],
                        fluxAutoErr = fields[fieldDict['FLUXERR_AUTO']],
                        fwhm = fields[fieldDict['FWHM_IMAGE']],
                        ellipticity = fields[fieldDict['ELLIPTICITY']],
                        flags = fields[fieldDict['FLAGS']],
                        boxXMin = fields[fieldDict['XMIN_IMAGE']],
                        boxYMin = fields[fieldDict['YMIN_IMAGE']],
                        boxXMax = fields[fieldDict['XMAX_IMAGE']],
                        boxYMax = fields[fieldDict['YMAX_IMAGE']]
                        )

                    sextractorResults.append(sextractorResult)

                    fwhmValues.append(parseFloat(fields[fieldDict['FWHM_IMAGE']]))
                    ellipticityValues.append(parseFloat(fields[fieldDict['ELLIPTICITY']]))

                    """
                    fields[fieldDict['NUMBER']]
                    fields[fieldDict['FLUX_ISO']]
                    fields[fieldDict['FLUXERR_ISO']]
                    fields[fieldDict['MAG_ISO']]
                    fields[fieldDict['MAGERR_ISO']]
                    fields[fieldDict['MAG_AUTO']]
                    fields[fieldDict['MAGERR_AUTO']]
                    fields[fieldDict['FLUX_BEST']]
                    fields[fieldDict['FLUXERR_BEST']]
                    fields[fieldDict['MAG_BEST']]
                    fields[fieldDict['MAGERR_BEST']]
                    fields[fieldDict['THRESHOLD']]
                    fields[fieldDict['FLUX_MAX']]
                    fields[fieldDict['XPEAK_IMAGE']]
                    fields[fieldDict['YPEAK_IMAGE']]
                    fields[fieldDict['X_IMAGE']]
                    fields[fieldDict['Y_IMAGE']]
                    fields[fieldDict['ISO0']]
                    fields[fieldDict['ISO1']]
                    fields[fieldDict['ISO2']]
                    fields[fieldDict['ISO3']]
                    fields[fieldDict['ISO4']]
                    fields[fieldDict['ISO5']]
                    fields[fieldDict['ISO6']]
                    fields[fieldDict['ISO7']]
                    fields[fieldDict['IMAFLAGS_ISO']]
                    fields[fieldDict['NIMAFLAGS_ISO']]
                    fields[fieldDict['FLUX_GROWTH']]
                    fields[fieldDict['FLUX_GROWTHSTEP']]
                    fields[fieldDict['MAG_GROWTH']]
                    fields[fieldDict['MAG_GROWTHSTEP']]
                    fields[fieldDict['FLUX_RADIUS']]
                    fields[fieldDict['XPSF_IMAGE']]
                    fields[fieldDict['YPSF_IMAGE']]
                    fields[fieldDict['FLUX_PSF']]
                    fields[fieldDict['FLUXERR_PSF']]
                    fields[fieldDict['MAG_PSF']]
                    fields[fieldDict['MAGERR_PSF']]
                    fields[fieldDict['ERRAPSF_IMAGE']]
                    fields[fieldDict['ERRBPSF_IMAGE']]
                    fields[fieldDict['FLUX_MODEL']]
                    fields[fieldDict['FLUXERR_MODEL']]
                    fields[fieldDict['MAG_MODEL']]
                    fields[fieldDict['MAGERR_MODEL']]
                    fields[fieldDict['XMODEL_IMAGE']]
                    fields[fieldDict['YMODEL_IMAGE']]
                    fields[fieldDict['FLUX_POINTSOURCE']]
                    fields[fieldDict['FLUXERR_POINTSOURCE']]
                    fields[fieldDict['MAG_POINTSOURCE']]
                    fields[fieldDict['MAGERR_POINTSOURCE']]
                    """

            models.SextractorResult.objects.bulk_create(sextractorResults)

            fwhmMean = numpy.nanmean(fwhmValues)
            fwhmMedian = numpy.nanmedian(fwhmValues)
            fwhmStdDev = numpy.nanstd(fwhmValues)

            ellipticityMean = numpy.nanmean(ellipticityValues)
            ellipticityMedian = numpy.nanmedian(ellipticityValues)
            ellipticityStdDev = numpy.nanstd(ellipticityValues)

            image.addImageProperty('fwhmMean', fwhmMean, overwriteValue=True)
            image.addImageProperty('fwhmMedian', fwhmMedian, overwriteValue=True)
            image.addImageProperty('fwhmStdDev', fwhmStdDev, overwriteValue=True)

            image.addImageProperty('ellipticityMean', ellipticityMean, overwriteValue=True)
            image.addImageProperty('ellipticityMedian', ellipticityMedian, overwriteValue=True)
            image.addImageProperty('ellipticityStdDev', ellipticityStdDev, overwriteValue=True)

            #TODO: Recode this section to calculate its own local average and standard deviation and then modify the confidence on sextractorResults array before doing the bulk_create.
            records = models.SextractorResult.objects.filter(image=image)
            meanFluxAuto = records.aggregate(Avg('fluxAuto'))['fluxAuto__avg']
            stdDevFluxAuto = records.aggregate(StdDev('fluxAuto'))['fluxAuto__stddev']

            outputText += "Found {} sources.\n".format(records.count())
            for record in records:
                # Assign the detected source a confidence based on the detected brightness with bright objects being high confidence.
                try:
                    record.confidence = sigmoid((record.fluxAuto-meanFluxAuto)/stdDevFluxAuto)
                except ZeroDivisionError:
                    record.confidence = 0.5
                    outputText += "stdDevFluxAuto was 0 so assigning a confidence of 0.5 to detected source."

                # Check the source to see if it looks like a hot pixel, and if so, add a hot pixel flag for the image.

                # Check to see if the source has near perfect roundness and very high brightness dropoff (HP often have
                # ellipticity of 0 so score1 ends up at or very near 0)
                score1 = record.fwhm * record.ellipticity

                #TODO Add score2, score3, ... etc to account for other HP that don't quite fit this form.  Maybe
                # something along the lines of N standard devs off of the fwhm and ellipticity values.

                if score1 < 0.1:
                    hotPixel = models.UserSubmittedHotPixel(
                        image = image,
                        user = None,
                        pixelX = record.pixelX,
                        pixelY = record.pixelY,
                        pixelZ = record.pixelZ,
                        )

                    hotPixel.save()

                record.save()

                #TODO: Consider removing entries that were flagged as hot pixels from the fwhm and ellipticity averages
                # for the image.  Would mean re-computing a second round and re-saving the values.

    try:
        os.remove(catfileName)
    except OSError:
        pass

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

@shared_task
def image2xy(filename, processInputId):
    outputText = ""
    errorText = ""
    taskStartTime = time.time()

    # Get the image record
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    # Image2xy does not use the detectThresholdMultiplier, but we still call this just so
    # any additional init routines are still run for this task.
    detectThresholdMultiplier, shouldReturn, outputText, errorText = initSourcefind('image2xy', image)

    if shouldReturn:
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    #TODO: Use the -P option to handle images with multiple planes.  Also has support for multi-extension fits built in if called with appropriate params.
    #TODO: Consider using the -d option to downsample by a given factor before running.
    #TODO: image2xy can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    #TODO: use the -g and -p options to set the detection threshold (probable -g is bgStdDev and -p is detThreshMult) also include -a option.
    outputFilename = settings.MEDIA_ROOT + filename + ".xy.fits"
    proc = subprocess.Popen(['image2xy', '-o', outputFilename, settings.MEDIA_ROOT + filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=settings.MEDIA_ROOT
        )

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    proc.wait()

    outputText += output
    errorText += error
    outputText += '\n ==================== End of process output ====================\n\n'
    errorText += '\n ==================== End of process error =====================\n\n'

    table = Table.read(outputFilename, format='fits')

    with transaction.atomic():
        models.Image2xyResult.objects.filter(image=image).delete()
        image2xyResults = []
        for row in table:
            if row['FLUX'] < 0.1:
                continue

            result = models.Image2xyResult(
                image = image,
                pixelX = row['X'],
                pixelY = row['Y'],
                pixelZ = None,
                flux = row['FLUX'],
                background = row['BACKGROUND']
                )

            image2xyResults.append(result)

        models.Image2xyResult.objects.bulk_create(image2xyResults)

        #TODO: Recode this section to calculate its own local average and standard deviation and then modify the confidence on sextractorResults array before doing the bulk_create.
        records = models.Image2xyResult.objects.filter(image=image)
        meanFlux = records.aggregate(Avg('flux'))['flux__avg']
        stdDevFlux = records.aggregate(StdDev('flux'))['flux__stddev']

        outputText += "Found {} sources.\n".format(records.count())
        for record in records:
            record.confidence = sigmoid((record.flux-meanFlux)/stdDevFlux)
            record.save()

    try:
        os.remove(outputFilename)
    except OSError:
        pass

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

@shared_task
def daofind(filename, processInputId):
    taskStartTime = time.time()

    #TODO: daofind can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = models.ImageChannelInfo.objects.filter(image=image).order_by('index')

    detectThresholdMultiplier, shouldReturn, outputText, errorText = initSourcefind('daofind', image)

    if shouldReturn:
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    detectThreshold = detectThresholdMultiplier*channelInfos[0].bgStdDev
    outputText += 'Final multiplier of {} standard deviations.\n'.format(detectThresholdMultiplier)
    outputText += 'Final detect threshold of {} above background.\n'.format(detectThreshold)

    hdulist = fits.open(settings.MEDIA_ROOT + filename)
    data = hdulist[0].data

    if len(data.shape) == 3:
        data = data[0]

    #TODO: Make use of the 'headerMeanFWHM' image property if set.
    fwhm = parseFloat(image.getImageProperty('fwhmMedian', 2.5))
    outputText += "\nUsing FWHM of {}\n".format(fwhm)
    daofind = DAOStarFinder(fwhm = fwhm, threshold = detectThreshold)
    sources = daofind(data - channelInfos[0].bgMedian)

    with transaction.atomic():
        models.DaofindResult.objects.filter(image=image).delete()
        daofindResults = []
        for source in (sources or []):
            result = models.DaofindResult(
                image = image,
                pixelX = source['xcentroid'],
                pixelY = source['ycentroid'],
                pixelZ = None,    #TODO: Handle multi-extension fits files.
                mag = source['mag'],
                flux = source['flux'],
                peak = source['peak'],
                sharpness = source['sharpness'],
                sround = source['roundness1'],
                ground = source['roundness2']
                )

            daofindResults.append(result)

        models.DaofindResult.objects.bulk_create(daofindResults)

        #TODO: Recode this section to calculate its own local average and standard deviation and then modify the confidence on sextractorResults array before doing the bulk_create.
        records = models.DaofindResult.objects.filter(image=image)
        meanMag = records.aggregate(Avg('mag'))['mag__avg']
        stdDevMag = records.aggregate(StdDev('mag'))['mag__stddev']

        outputText += "Found {} sources.\n".format(records.count())
        for record in records:
            #TODO: Incorporate sharpness, sround, and ground into the calculation.
            #TODO: Ensure stdDevMag is not zero and check that other sourcefind methods don't have the same issue.
            record.confidence = sigmoid((meanMag-record.mag)/stdDevMag)
            record.save()

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

@shared_task
def starfind(filename, processInputId):
    taskStartTime = time.time()

    #TODO: starfind can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = models.ImageChannelInfo.objects.filter(image=image).order_by('index')

    detectThresholdMultiplier, shouldReturn, outputText, errorText = initSourcefind('starfind', image)

    if shouldReturn:
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    detectThreshold = detectThresholdMultiplier*channelInfos[0].bgStdDev
    outputText += 'Final multiplier of {} standard deviations.\n'.format(detectThresholdMultiplier)
    outputText += 'Final detect threshold of {} above background.\n'.format(detectThreshold)

    hdulist = fits.open(settings.MEDIA_ROOT + filename)
    data = hdulist[0].data

    if len(data.shape) == 3:
        data = data[0]

    #TODO: Make use of the 'headerMeanFWHM' image property if set.
    fwhm = parseFloat(image.getImageProperty('fwhmMedian', 2.5))
    outputText += "\nUsing FWHM of {}\n".format(fwhm)
    starfinder = IRAFStarFinder(fwhm = fwhm, threshold = detectThreshold)
    sources = starfinder(data - channelInfos[0].bgMedian)

    with transaction.atomic():
        models.StarfindResult.objects.filter(image=image).delete()
        starfindResults = []
        for source in (sources or []):
            result = models.StarfindResult(
                image = image,
                pixelX = source['xcentroid'],
                pixelY = source['ycentroid'],
                pixelZ = None,    #TODO: Handle multi-extension fits files.
                mag = source['mag'],
                peak = source['peak'],
                flux = source['flux'],
                fwhm = source['fwhm'],
                sharpness = source['sharpness'],
                roundness = source['roundness'],
                pa = source['pa']
                )

            starfindResults.append(result)

        models.StarfindResult.objects.bulk_create(starfindResults)

        #TODO: Recode this section to calculate its own local average and standard deviation and then modify the confidence on sextractorResults array before doing the bulk_create.
        records = models.StarfindResult.objects.filter(image=image)
        meanMag = records.aggregate(Avg('mag'))['mag__avg']
        stdDevMag = records.aggregate(StdDev('mag'))['mag__stddev']

        outputText += "Found {} sources.\n".format(records.count())
        for record in records:
            #TODO: Incorporate sharpness, roundness, etc, into the calculation.
            record.confidence = sigmoid((meanMag-record.mag)/stdDevMag)
            record.save()

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

@shared_task
def starmatch(filename, processInputId):
    """
    A celery task to loop over every pair of source finding methods, and for every pair,
    try to match corresponding sources between the two methods.  After every pair of
    methods has been compared against each other, the matched results are combined into
    "super matches" which are then stored in the database with links to the individual
    source method results that contributed to the given super match.
    """
    outputText = ""
    errorText = ""
    taskStartTime = time.time()

    outputText += "starmatch: " + filename + "\n"

    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    outputText += '\n\nTiming:'
    millis = int(round(time.time() * 1000))

    # If this is a calibration image we do not need to run this task.
    shouldReturn, retText = checkIfCalibrationImage(image, 'astrometryNet', 'skippedCalibration')
    outputText += retText
    if shouldReturn:
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    models.SourceFindMatch.objects.filter(image=image).delete()

    #NOTE: It may be faster if these dictionary 'name' entries were shortened or changed to 'ints', maybe an enum.
    inputs = [
        { 'name': 'sextractor', 'model': models.SextractorResult },
        { 'name': 'image2xy', 'model': models.Image2xyResult },
        { 'name': 'daofind', 'model': models.DaofindResult },
        { 'name': 'starfind', 'model': models.StarfindResult },
        { 'name': 'userSubmitted', 'model': models.UserSubmittedResult },
        { 'name': 'userSubmitted2', 'model': models.UserSubmittedResult }
        ]

    for method in inputs:
        method['query'] = SortedListWithKey(method['model'].objects.filter(image=image), key=lambda x: x.pixelX)

    # Loop over all the pairs of source extraction methods listed in 'inputs'.
    matchedResults = []
    for i1, i2 in itertools.combinations(inputs, 2):
        results1 = i1['query']
        results2 = i2['query']

        outputText += 'Matching {} {} results with {} {} results'.format(len(results1), i1['name'], len(results2), i2['name']) + "\n"

        # Loop over all the pairs of results in the two current methods and for each item
        # in the first result set, find the closest item in the second result set that is
        # within the specified maxAllowedDistance.  If such a result is found add it to
        # the matches array.
        matches = []
        maxAllowedDistance = 3.0
        for r1 in results1:
            nearestDist = maxAllowedDistance
            nearestDistSq = nearestDist * nearestDist
            nearestResult = None
            x1 = r1.pixelX
            y1 = r1.pixelY

            # This inner loop loops over the second result set, but since the result sets
            # are sorted by pixelX, we only loop over the portion of the result set where
            # the pixelX is within the maxAllowedDistance.  Limiting the search like this
            # speeds this function up by several orders of magnitude.
            for r2 in results2.irange_key(r1.pixelX - maxAllowedDistance, r1.pixelX + maxAllowedDistance):
                dx = r2.pixelX - x1
                dy = r2.pixelY - y1
                dSq = dx*dx + dy*dy

                if dSq < nearestDistSq:
                    nearestDist = math.sqrt(dSq)
                    nearestDistSq = dSq
                    nearestResult = r2

            if nearestResult != None:
                matches.append( (r1, nearestResult) )

        # Now that we have found all the matches between these two methods, store this
        # list of matches (and which two methods they are from) in the matchedResults array.
        outputText += '   Found {} matches.'.format(len(matches)) + "\n"
        matchedResults.append( (i1, i2, matches) )

    newMillis = int(round(time.time() * 1000))
    deltaT = newMillis - millis
    outputText += 'pairwise took {} ms.'.format(deltaT )
    millis = int(round(time.time() * 1000))

    def sortKeyForSuperMatch(superMatch):
        average = 0.0
        for entry in superMatch.values():
            average += entry.pixelX

        return average/len(superMatch.values())

    # Now that we have all the matches between every two individual methods, combine them into 'superMatches' where 2
    # or more different match types all agree on the same star.
    outputText += 'Calculating super matches:' + "\n"
    superMatches = SortedListWithKey(key=lambda x: sortKeyForSuperMatch(x))
    for i1, i2, matches in matchedResults:
        for match in matches:
            # Check to see if either of the matched pair in the current match exist
            # anyhere in the super matches already.  Since the superMatches list is sorted
            # on pixelX we can limit our checking to only the range of ones within the
            # maxAllowedDistance away in pixelX.  The factor of 2 is bit of a hack since
            # the average position of the match is not completely stable as new detections
            # are added to it.  In any case, it does not affect the accuracy of the
            # results, it only results in checking a few extra objects before the correct
            # one is found.
            for superMatch in superMatches.irange_key(match[0].pixelX - 2*maxAllowedDistance, match[0].pixelX + 2*maxAllowedDistance):
                # Check to see if the superMatch has an entry for the detection method in i1.
                if i1['name'] in superMatch:
                    # Check to see if the actual detection object is the one we are looking at currently.
                    if superMatch[i1['name']] == match[0]:
                        # We found that i1 is part of this superMatch so now we add i2 to it as well.
                        superMatch[i2['name']] = match[1]
                        break
                if i2['name'] in superMatch:
                    if superMatch[i2['name']] == match[1]:
                        superMatch[i1['name']] = match[0]
                        break
            # Neither of the current match pair exists anywhere in the superMatch array already, so create a new entry
            # containing the current match pair.
            else:
                d = {}
                d[i1['name']] = match[0]
                d[i2['name']] = match[1]
                superMatches.add(d)

    newMillis = int(round(time.time() * 1000))
    deltaT = newMillis - millis
    outputText += 'superMatches took {} ms.'.format(deltaT )
    millis = int(round(time.time() * 1000))

    # Loop over all the superMatch entries and create a database entry for each one.
    outputText += 'Found {} super matches.  Writing them to the DB...'.format(len(superMatches)) + "\n"
    with transaction.atomic():
        models.SourceFindMatch.objects.filter(image=image).delete()
        sourceFindMatches = []
        for superMatch in superMatches:
            sextractorResult = superMatch.get('sextractor', None)
            image2xyResult = superMatch.get('image2xy', None)
            daofindResult = superMatch.get('daofind', None)
            starfindResult = superMatch.get('starfind', None)
            userSubmittedResult = superMatch.get('userSubmitted', None)
            userSubmittedResult2 = superMatch.get('userSubmitted2', None)

            numMatches = 0
            confidence = 1
            x = 0
            y = 0
            z = 0
            for result in [sextractorResult, image2xyResult, daofindResult, starfindResult, userSubmittedResult, userSubmittedResult2]:
                # TODO: Should add an else clause here to pull down the confidence if the given result
                # does not agree with the others.  Need to figure out how to weigh this disagreement.
                if result != None:
                    numMatches += 1
                    confidence *= result.confidence
                    x += result.pixelX
                    y += result.pixelY
                    z = result.pixelZ
                else:
                    confidence *= 0.75

            confidence = math.pow(confidence, 1/numMatches)
            x /= numMatches
            y /= numMatches

            record = models.SourceFindMatch(
                image = image,
                pixelX = x,
                pixelY = y,
                pixelZ = z,
                confidence = confidence,
                numMatches = numMatches,
                sextractorResult = sextractorResult,
                image2xyResult = image2xyResult,
                daofindResult = daofindResult,
                starfindResult = starfindResult,
                userSubmittedResult = userSubmittedResult
                )

            sourceFindMatches.append(record)

        models.SourceFindMatch.objects.bulk_create(sourceFindMatches)

    outputText += 'Done.' + "\n"

    newMillis = int(round(time.time() * 1000))
    deltaT = newMillis - millis
    outputText += 'write to db took {} ms.'.format(deltaT )
    millis = int(round(time.time() * 1000))

    # Force a save of the images best plate solution to calculate the RA and Dec of all
    # the assosciated source find methods.
    outputText += "Checking for plate solution: "
    ps = image.getBestPlateSolution()
    if ps is not None:
        outputText += "Image has a plate solution, forcing a save to trigger update of RA, Dec for all source find results.\n"
        ps.save()
    else:
        outputText += "No plate solution found, not pre-caclulating RA-Dec values for source find results.\n"

    newMillis = int(round(time.time() * 1000))
    deltaT = newMillis - millis
    outputText += 'RA, Dec recalc took {} ms.'.format(deltaT )
    millis = int(round(time.time() * 1000))

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

@shared_task
def astrometryNet(filename, processInputId):
    """
    A celery task to run the astrometry.net plate solver with a custom list of detected
    sources from the SourceFindMatch table.  The plate solver is also fed as much
    information as possible with regard to the known location of the plate.
    """
    outputText = ""
    errorText = ""
    taskStartTime = time.time()

    outputText += "astrometrynet: " + filename + "\n"

    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    # If this is a calibration image we do not need to run this task.
    shouldReturn, retText = checkIfCalibrationImage(image, 'astrometryNet', 'skippedCalibration')
    outputText += retText
    if shouldReturn:
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    #TODO: Move this to after we know if the task actually has to run or not.
    superMatches = models.SourceFindMatch.objects.filter(image=image)

    # Loop over the super matches and add the x-y and confidence values to the appropriate
    # arrays since constructing the fits table requires a separate array for each column.
    xValues = []
    yValues = []
    confidenceValues = []
    for star in superMatches:
        #TODO: Add a check here to skip the source if the confidence is too low, or it is flagged as a false positive, etc.
        xValues.append(star.pixelX)
        yValues.append(star.pixelY)
        confidenceValues.append(star.confidence)

    if len(superMatches) < 4:
        outputText += 'Task is exiting because there are {} detected sources in the image and the plate solver needs at least 4.'.format(len(superMatches))
        image.addImageProperty('astrometryNet', 'noSources')
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    try:
        tableFilename = settings.MEDIA_ROOT + filename + ".sources.xyls"
        table = Table([xValues, yValues, confidenceValues], names=("XIMAGE", "YIMAGE", "CONFIDENCE"), dtype=('f4', 'f4', 'f4'));
        table.write(tableFilename, format='fits')
    except OSError:
        errorText += 'ERROR: Could not open file for writing: ' + tableFilename + "\n"
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    outputText += "Chose {} objects to use in plate solution.".format(len(table)) + "\n"

    previousResult = image.getImageProperty('astrometryNet')
    cpuLimit = '30'
    depth = '8,14,22'
    if previousResult == None or previousResult == 'noSources':
        cpuLimit = str(models.CosmicVariable.getVariable('astrometryNetTimeout1'))
        depth = str(models.CosmicVariable.getVariable('astrometryNetDepth1'))
    elif previousResult == 'failure':
        cpuLimit = str(models.CosmicVariable.getVariable('astrometryNetTimeout2'))
        depth = str(models.CosmicVariable.getVariable('astrometryNetDepth2'))
    elif previousResult == 'success':
        #TODO: Decide what to do here.
        cpuLimit = '10'
        depth = '50'

    outputText += "Limiting runtime to {} seconds of CPU time.".format(cpuLimit) + "\n"
    outputText += "Limiting depth to {} objects.".format(depth) + "\n"

    argArray = ['solve-field', '--depth', depth,
            '--no-plots', '--overwrite', '--timestamp',
            '--x-column', 'XIMAGE', '--y-column', 'YIMAGE', '--sort-column', 'CONFIDENCE',
            '--width', str(image.dimX), '--height', str(image.dimY),
            '--cpulimit', cpuLimit,
            tableFilename
            ]

    ra, dec = image.getBestRaDec()
    objectRA = image.getImageProperty('objectRA')
    objectDec = image.getImageProperty('objectDec')
    overlapsImage = image.getImageProperty('overlapsImage')
    if ra is not None:
        argArray.append('--ra')
        argArray.append(str(ra))
        argArray.append('--dec')
        argArray.append(str(dec))
        argArray.append('--radius')
        argArray.append(str(models.CosmicVariable.getVariable('astrometryNetRadius')))

        outputText += 'Image has a previous plate solution.\n'
        outputText += 'Searching a {} degree radius around the ra, dec of ({}, {})\n'.format(models.CosmicVariable.getVariable('astrometryNetRadius'), ra, dec)

    elif overlapsImage is not None:
        overlappingImage = models.Image.objects.filter(pk=int(overlapsImage)).first()
        if overlappingImage is not None:
            ra, dec = overlappingImage.getBestRaDec()
            if ra is not None:
                argArray.append('--ra')
                argArray.append(str(ra))
                argArray.append('--dec')
                argArray.append(str(dec))
                argArray.append('--radius')
                argArray.append(str(models.CosmicVariable.getVariable('astrometryNetRadius')))

                outputText += 'Image overlaps image {} which has a plate solution.\n'.format(overlapsImage)
                outputText += 'Searching a {} degree radius around the ra, dec of ({}, {})\n'.format(models.CosmicVariable.getVariable('astrometryNetRadius'), ra, dec)
            else:
                outputText += 'Image overlaps image {} but that image does not have a plate solution.\n'.format(overlapsImage)
        else:
            outputText += 'ERROR: Could not find overlapping image with id "{}".\n'.format(overlapsImage)

    elif objectRA != None and objectDec != None:
        # Change the spaces into ':' symbols in the HMS and DMS positions which is what solve-field expects.
        formattedRA = ':'.join(objectRA.split())
        formattedDec = ':'.join(objectDec.split())

        argArray.append('--ra')
        argArray.append(str(formattedRA))
        argArray.append('--dec')
        argArray.append(str(formattedDec))
        argArray.append('--radius')
        argArray.append(str(models.CosmicVariable.getVariable('astrometryNetRadius')))

        outputText += 'Image has target RA and Dec in the image header.\n'
        outputText += 'Searching a {} degree radius around the ra, dec of ({}, {})\n'.format(models.CosmicVariable.getVariable('astrometryNetRadius'), objectRA, objectDec)

    elif image.dateTime is not None and image.observatory is not None:
        outputText += 'Image has an obervatory and a time set, only searching the half of the sky which is visible from that site at that time.\n'
        observer = ephem.Observer()
        observer.lat = image.observatory.lat*(math.pi/180)
        observer.lon = image.observatory.lon*(math.pi/180)
        observer.elevation = image.observatory.elevation
        observer.date = image.dateTime

        zenithRA, zenithDec = observer.radec_of('0', '90')

        argArray.append('--ra')
        argArray.append(str(zenithRA))
        argArray.append('--dec')
        argArray.append(str(zenithDec))
        argArray.append('--radius')
        argArray.append(str(models.CosmicVariable.getVariable('astrometryNetZenithRadius')))

        outputText += 'Searching a {} degree radius around the observer\'s zenith ra, dec of ({} {})\n'\
            .format(models.CosmicVariable.getVariable('astrometryNetZenithRadius'), zenithRA, zenithDec)

    else:
        outputText += 'Image has no plate solution or header data indicating where to search, searching the whole sky.\n'

    ps = image.getBestPlateSolution()
    if ps is not None:
        resolution = (ps.resolutionX + ps.resolutionY)/2.0
        outputText += 'Image has a plate solution, restricting the scale to be within 30% of {} arcseconds per pixel.\n'.format(resolution)
        argArray.append('--scale-low')
        argArray.append(str(0.7*resolution))
        argArray.append('--scale-high')
        argArray.append(str(1.3*resolution))
        argArray.append('--scale-units')
        argArray.append('arcsecperpix')
    else:
        plateScale = image.getImageProperty('plateScale')
        if plateScale is not None:
            try:
                plateScale = float(plateScale)
                argArray.append('--scale-low')
                argArray.append(str(0.7*plateScale))
                argArray.append('--scale-high')
                argArray.append(str(1.3*plateScale))
                argArray.append('--scale-units')
                argArray.append('arcsecperpix')
                outputText += 'Image has a plate scale listed in its image properties.  Using a scale of {} arcsec per pixel.\n'.format(plateScale)
            except:
                outputText += 'ERROR: Could not parse plateScale string "{}" as a float.\n'.format(plateScale)

        else:
            outputText += 'Image does not have a plate solution.  Not restricting image scale range.\n'

    proc = subprocess.Popen(argArray,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
            )

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    proc.wait()

    outputText += output
    errorText += error
    outputText += '\n ==================== End of process output ====================\n\n'
    errorText += '\n ==================== End of process error =====================\n\n'

    solvedFilename = settings.MEDIA_ROOT + filename + '.sources.solved'
    if os.path.isfile(solvedFilename):
        outputText += '\n\nPlate solved successfully.' + "\n"
        w = wcs.WCS(settings.MEDIA_ROOT + filename + '.sources.wcs')

        models.storeImageLocation(image, w, 'cosmic:astrometry.net')
        image.addImageProperty('astrometryNet', 'success')
        #TODO: Check to see if this image has an overlapsImage image property and if
        # so, check to see if that image has a plate solution.  If not, try solving it
        # with this location as a hint.  Also need to check for images which have an
        # overlapsImage pointing to this image that we just solved.  Check all of these to
        # see if they have plate solutions and if not, try solving with this location as a hint.
    else:
        outputText += '\n\nNo plate solution found.' + "\n"
        image.addImageProperty('astrometryNet', 'failure')
        #TODO: Add another job to the proess queue to re-run starfind algorithms with lower detection thresholds.
        #TODO: Add another job to the proess queue with lower priority and a deeper search.

    filesToCleanup = [
        tableFilename,
        settings.MEDIA_ROOT + filename + '.sources.axy',
        settings.MEDIA_ROOT + filename + '.sources.corr',
        settings.MEDIA_ROOT + filename + '.sources-indx.xyls',
        settings.MEDIA_ROOT + filename + '.sources.match',
        settings.MEDIA_ROOT + filename + '.sources.rdls',
        settings.MEDIA_ROOT + filename + '.sources.solved',
        settings.MEDIA_ROOT + filename + '.sources.wcs'
        ]

    for f in filesToCleanup:
        try:
            os.remove(f)
        except FileNotFoundError:
            pass
        except:
            errorText += 'Error in removing file {}\nError was: {}'.format(f, sys.exc_info()[0]) + "\n"

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

@shared_task
def parseHeaders(imageId, processInputId):
    outputText = ""
    errorText = ""
    taskStartTime = time.time()

    try:
        image = models.Image.objects.get(pk=imageId)
    except:
        errorText += "Image {} does not exist".format(imageId)
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    headers = models.ImageHeaderField.objects.filter(image=imageId)

    with transaction.atomic():
        # Loop over all the headers for this image, determine if their ending comment is
        # the same as another previously seen header.  Then parse the key=value pair into
        # an ImageProperty that is more standardized than the dizzying variety of formats
        # used in fits headers in the wild.
        for header in headers:
            if header.key not in ['comment', 'fits:comment', 'fits:history']:
                # Look for comments at the end of the 'value' portion of the header to build
                # up a list of commonly used comments.  By enumerating as many as we can
                # automatically and manually flagging a few others that get missed, we should
                # be able to build a very large dataset of comments used in different fields.
                # Then, data-mining this dataset could help us discover alternate keys for the
                # same field, and other things like that.  It will also help in building
                # regular expressions which help capture this text to strip it from the
                # headers before parsing below.  This will make it signifigantly easier to
                # refactor the parsing code to group common parsing code since the format of
                # the actual data is much more standard than the comments (which could
                # literally contain any string of characters which confuses the parser).
                commonEndings = models.ImageHeaderFieldCommonEnding.objects.filter(key=header.key)

                # Check to see that there is exactly one comment identifier in the string (a
                # bit overly strict for now but prevents a lot of false positives).
                count = header.value.count(' /')
                if count == 1:
                    idx = header.value.find(' /')
                    reversedValue = header.value[:idx-1:-1]
                else:
                    reversedValue = ""

                # Loop over all the other ImageHeaderFields that are already in the database for this same key.
                keys = models.ImageHeaderField.objects.filter(key=header.key).distinct('value')
                for otherKey in keys:
                    #TODO: Consider adding value__contains to the db query to avoid this if statement.
                    idx = otherKey.value.find(' /')
                    if idx != -1:
                        reversedOtherValue = otherKey.value[:idx-1:-1]
                    else:
                        continue

                    # Check the two reversed strings and find the longest string that is
                    # common to both as a prefix (or a suffix in this case since they are reversed).
                    suffix = longestCommonPrefix(reversedValue, reversedOtherValue)[::-1]
                    #TODO: This 'startswith' clause is a bit of a hack, should not be needed, try to fix this.
                    if len(suffix) > 3 and suffix.startswith(' /'):
                        commonEnding, created = models.ImageHeaderFieldCommonEnding.objects.get_or_create(
                            key = header.key,
                            ending = suffix
                            )

                # Re-run the query to pick up any new common endings that were just added to the database.
                # NOTE: This is commented out for now because we don't do anything with the query anyway.
                # It is here to be uncommented in the future if we actually want to use these for something.
                #commonEndings = models.ImageHeaderFieldCommonEnding.objects.filter(key=header.key)

            if header.key == 'fits:bitpix':
                key = 'bitDepth'
                value = str(abs(int(header.value.split()[0])))

            elif header.key == 'fits:simple':
                #TODO: Some images appear to have the image creation time, or something like it as a
                # comment in this header.  See if the is standard, and if so parse it appropriately.
                key = 'simpleFits'
                value = header.value.split()[0]

            elif header.key == 'fits:extend':
                key = 'extendedFits'
                value = header.value.split()[0]

            elif header.key == 'fits:sbstdver':
                key = 'extendedFits'
                value = header.value.split()[0].strip().strip("'")

            elif header.key == 'fits:encoding':
                key = 'fitsEncoding'
                value = header.value.split()[0].strip("'")

            elif header.key == 'fits:pedestal':
                key = 'pedestal'
                value = header.value.split()[0]

            elif header.key == 'fits:datamax':
                key = 'saturationLevel'
                value = header.value.split()[0]

            elif header.key == 'fits:ccdmean':
                key = 'headerCCDMean'
                value = header.value.split()[0]

            elif header.key == 'fits:fwhm':
                key = 'headerMeanFWHM'
                value = header.value.split()[0]

            elif header.key == 'fits:zmag':
                key = 'magnitudeZeroPoint'
                value = header.value.split()[0]

            elif header.key == 'fits:bzero':
                key = 'bzero'
                value = header.value.split()[0]

            elif header.key == 'fits:bscale':
                key = 'bscale'
                value = header.value.split()[0]

            elif header.key == 'fits:bunit':
                key = 'bunit'
                value = header.value.split()[0].strip("'")

            elif header.key == 'fits:cblack':
                key = 'displayBlackLevel'
                value = header.value.split()[0].strip().strip("'")

            elif header.key == 'fits:cwhite':
                key = 'displayWhiteLevel'
                value = header.value.split()[0].strip().strip("'")

            elif header.key == 'fits:cstretch':
                key = 'displayStretchMode'
                value = header.value.split()[0].strip().strip("'")

            elif header.key == 'fits:resolutn':
                key = 'resolutionPerUnit'
                value = header.value.split()[0].strip().strip("'")

            elif header.key == 'fits:resounit':
                key = 'resolutionUnit'
                value = header.value.split()[0].strip().strip("'")

            elif header.key == 'fits:timesys':
                key = 'headerTimeSystem'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:radecsys', 'fits:radesysa']:
                key = 'headerCoordinateSystem'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key == 'fits:photsys':
                key = 'photometryFilterSystem'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:mjd', 'fits:mjd-obs']:
                key = 'julianDate'
                mjdValue = float(header.value.split('/')[0].strip().strip("'"))
                value = str(julian.to_jd(julian.from_jd(mjdValue, fmt='mjd'), fmt='jd'))

            elif header.key in ['fits:jd', 'fits:jd-obs']:
                key = 'julianDate'
                value = header.value.split()[0]

            elif header.key in ['fits:jd-helio', 'fits:hjd-obs']:
                key = 'julianDateHeliocentric'
                value = header.value.split()[0]

            elif header.key == 'fits:bjd-obs':
                key = 'barycentricJulianDate'
                value = header.value.split()[0]

            elif header.key in ['fits:date-avg']:
                key = 'dateAverage'
                value = header.value.split('/')[0].strip().strip("'")
                try:
                    image.dateTime = dateparser.parse(value)
                    image.save()
                except ValueError:
                    outputError += "ERROR: Could not parse dateHDU: " + value + "\n"

            elif header.key in ['fits:date']:
                key = 'dateHDU'
                value = header.value.split('/')[0].strip().strip("'")
                try:
                    image.dateTime = dateparser.parse(value)
                    image.save()
                except ValueError:
                    outputError += "ERROR: Could not parse dateHDU: " + value + "\n"

            elif header.key in ['fits:date_obs', 'fits:date-obs']:
                key = 'dateObs'
                value = header.value.split('/')[0].strip().strip("'")
                try:
                    image.dateTime = dateparser.parse(value)
                    image.save()
                except ValueError:
                    outputError += "ERROR: Could not parse dateObs: " + value + "\n"

            elif header.key in ['fits:time_obs', 'fits:time-obs', 'fits:ut']:
                key = 'timeObs'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:st', 'fits:lst']:
                key = 'localApparentSiderialTime'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:exptime', 'fits:exposure']:
                key = 'exposureTime'
                value = header.value.strip("'").split()[0]

            elif header.key in ['fits:traktime']:
                key = 'autoguiderExposureTime'
                value = header.value.split()[0]

            elif header.key in ['fits:darktime']:
                key = 'totalDarkTime'
                value = header.value.split()[0]

            elif header.key == 'fits:telescop':
                key = 'telescope'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key == 'fits:instrume':
                key = 'instrument'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:swcreate', 'fits:creator', 'fits:origin', 'fits:software', 'fits:program', 'fits:swacquir']:
                key = 'createdBySoftware'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:swowner']:
                key = 'createdBySoftwareOwner'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:swserial']:
                key = 'createdBySoftwareSerialNumber'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:iraftype']:
                key = 'irafPixelType'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:irafname']:
                key = 'irafImageFileName'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:iraf-min']:
                key = 'irafDataMin'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:iraf-max']:
                key = 'irafDataMax'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:iraf-bpx']:
                key = 'irafBitsPerPixel'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:iraf-tlm']:
                key = 'irafTimeOfLastModification'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key == 'fits:naxis':
                key = 'numAxis'
                value = header.value.split()[0]

            elif header.key in ['fits:naxis1', 'fits:imagew']:
                key = 'width'
                value = header.value.split()[0]

            elif header.key in ['fits:naxis2', 'fits:imageh']:
                key = 'height'
                value = header.value.split()[0]

            elif header.key == 'fits:naxis3':
                key = 'numChannels'
                value = header.value.split()[0]

            elif header.key in ['fits:trimsec']:
                key = 'trimsec'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:datasec']:
                key = 'datasec'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:ccdsec']:
                key = 'ccdsec'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:biassec']:
                key = 'biassec'
                value = header.value.split('/')[0].strip().strip("'")

            # Apparently the meaning of this fits key has to do with whether the image should be flipped or not.
            elif header.key == 'fits:imgroll':
                key = 'imgroll'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key == 'fits:xbinning':
                key = 'binningX'
                value = header.value.split()[0]

            elif header.key == 'fits:ybinning':
                key = 'binningY'
                value = header.value.split()[0]

            elif header.key == 'fits:xorgsubf':
                key = 'subframeX'
                value = header.value.split()[0]

            elif header.key == 'fits:yorgsubf':
                key = 'subframeY'
                value = header.value.split()[0]

            #TODO: Pixel size is supposed to be after binning however this does not appear to be correct in binned frames.
            elif header.key == 'fits:xpixsz':
                key = 'pixelSizeX'
                value = header.value.split()[0]

            #TODO: Pixel size is supposed to be after binning however this does not appear to be correct in binned frames.
            elif header.key == 'fits:ypixsz':
                key = 'pixelSizeY'
                value = header.value.split()[0]

            elif header.key == 'fits:readoutm':
                key = 'readoutMode'
                value = header.value.split()[0].strip().strip("'")

            elif header.key in ['fits:egain', 'fits:gain']:
                key = 'ePerADU'
                value = header.value.split()[0]

            elif header.key == 'fits:rdnoise':
                key = 'readNoise'
                value = header.value

            elif header.key in ['fits:ccd-temp', 'fits:temperat']:
                key = 'ccdTemp'
                value = header.value.split()[0]

            elif header.key == 'fits:set-temp':
                key = 'ccdSetTemp'
                value = header.value.split()[0]

            elif header.key == 'fits:focusssz':
                key = 'focuserSizeStep'
                value = header.value.split()[0]

            elif header.key == 'fits:focuspos':
                key = 'focuserPosition'
                value = header.value.split()[0]

            elif header.key == 'fits:focustem':
                key = 'focuserTemp'
                value = header.value.split()[0]

            elif header.key in ['fits:imagtyp', 'fits:imagetyp']:
                key = 'imageType'
                value = header.value.split('/')[0].strip().strip("'").lower()

                #NOTE: If values are added here they need to be added to stackedTypeDict at the end of this function as well.
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

            elif header.key in ['fits:ncombine', 'fits:snapshot']:
                key = 'numCombinedImages'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key.startswith('fits:imcmb'):
                num = header.key[len('fits:imcmb'):]
                key = 'combinedImage' + num
                value = header.value.strip().strip("'")

            elif header.key in ['fits:ccdproc']:
                key = 'ccdProcessing'
                value = header.value.split('/')[0].strip().strip("'")

            #TODO: Need to handle fits:calstat which contains B, D, F, or any combination of the three to indicate if the images is bias, dark, or flat corrected.

            elif header.key in ['fits:zerocor', 'fits:biassub']:
                key = 'biasCorrected'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:darksub', 'fits:darkcor']:
                key = 'darkCorrected'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:flatted', 'fits:flatcor']:
                key = 'flatCorrected'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:pltsolvd']:
                key = 'plateSolvedBeforeUpload'
                value = header.value

            elif header.key in ['fits:ccdsec']:
                key = 'ccdDataSection'
                value = header.value.strip("'")

            #TODO: Find out what this is and maybe change the key we set for it.  It was found
            # in an image with 'darksub' and 'flatted' headers and all three had values of 1
            elif header.key in ['fits:replace']:
                key = 'replace'
                value = header.value.split('/')[0].strip().strip("'")

            elif header.key in ['fits:observer']:
                key = 'observerName'
                value = header.value.split('/')[0].strip().strip("'").lower()

            elif header.key in ['fits:observat']:
                key = 'observatoryName'
                value = header.value.split('/')[0].strip().strip("'").lower()

            elif header.key in ['fits:sitelat', 'fits:lat-obs', 'fits:latitude']:
                key = 'observerLat'
                value = header.value.split('/')[0].strip().strip("'").lower()
                value = str(parseDMS(value))

            elif header.key in ['fits:sitelong', 'fits:long-obs', 'fits:longitud']:
                key = 'observerLon'
                value = header.value.split('/')[0].strip().strip("'").lower()
                value = str(parseDMS(value))

            elif header.key in ['fits:winddir']:
                key = 'weatherWindDirection'
                value = header.value

            elif header.key in ['fits:skytemp']:
                key = 'weatherSkyTemperature'
                value = header.value

            elif header.key in ['fits:ambtemp']:
                key = 'weatherAmbientTemperature'
                value = header.value

            elif header.key in ['fits:humidity']:
                key = 'weatherHumidity'
                value = header.value

            elif header.key in ['fits:windspd']:
                key = 'weatherWindSpeed'
                value = header.value

            elif header.key in ['fits:dewpoint']:
                key = 'weatherDewPoint'
                value = header.value

            elif header.key in ['fits:alt-obs']:
                key = 'observerAlt'
                value = header.value.split('/')[0].strip().strip("'").lower()

            elif header.key in ['fits:pierside']:
                key = 'pierSide'
                value = header.value.split('/')[0].strip().strip("'").lower()

            elif header.key in ['fits:flipstat']:
                key = 'pierFlipState'
                value = header.value

            elif header.key in ['fits:object']:
                key = 'object'
                value = header.value.split('/')[0].strip().strip("'")

            #TODO: Check if there is a declination component for hour angle or if it just uses regular declination.
            #TODO: The documentation for 'fits:ha' says it is the 'telescope hour angle', need to confirm if this is the same as 'fits:objctha'.
            elif header.key in ['fits:objctha', 'fits:ha']:
                key = 'objectHA'
                value = header.value.split('/')[0].strip().strip("'").lower()

            elif header.key in ['fits:objctra', 'fits:ra']:
                key = 'objectRA'
                value = header.value.split('/')[0].strip().strip("'").lower()
                if 'degree' in header.value.lower():
                    value = str(parseDMS(value))
                else:
                    value = str(parseHMS(value))

            elif header.key in ['fits:objctdec', 'fits:dec']:
                key = 'objectDec'
                value = header.value.split('/')[0].strip().strip("'").lower()
                value = str(parseDMS(value))

            elif header.key in ['fits:equinox', 'fits:epoch']:
                key = 'equinox'
                value = header.value.split()[0]

            elif header.key in ['fits:objctalt', 'fits:altitude', 'fits:alt-obj']:
                key = 'objectAlt'
                value = header.value.split('/')[0].strip().strip("'").lower()
                value = str(parseDMS(value))

            elif header.key in ['fits:objctaz', 'fits:azimuth', 'fits:az-obj']:
                key = 'objectAz'
                value = header.value.split('/')[0].strip().strip("'").lower()
                value = str(parseDMS(value))

            elif header.key in ['fits:airmass', 'fits:secz']:
                key = 'airmass'
                value = header.value.split()[0]

            elif header.key in ['fits:notes']:
                key = 'notes'
                value = header.value

            elif header.key in ['comment', 'fits:comment']:
                key = 'comment'
                value = header.value

            elif header.key in ['fits:history']:
                key = 'history'
                value = header.value

            elif header.key in ['fits:aperture', 'fits:aptdia']:
                key = 'aperture'
                value = header.value.split()[0].strip().strip("'").lower()

            elif header.key in ['fits:aptarea']:
                key = 'apertureArea'
                value = header.value.split()[0].strip().strip("'").lower()

            elif header.key in ['fits:focallen']:
                key = 'focalLength'
                value = header.value.split()[0].strip().strip("'").lower()

            elif header.key == 'fits:filter':
                key = 'filter'
                value = header.value.split()[0].strip().strip("'").lower()

            elif header.key == 'fits:clrband':
                key = 'colorBand'
                value = header.value.split('/')[0].strip().strip("'").lower()

            elif header.key == 'fits:colorspc':
                key = 'colorSpace'
                value = header.value.split('/')[0].strip().strip("'").lower()

            elif header.key == 'fits:iso':
                key = 'iso'
                value = str(abs(int(header.value.split()[0].strip())))

            else:
                if header.key not in settings.NON_PROPERTY_KEYS:
                    errorText += 'Warning: Unhandled header key: ' + header.key + '\n'
                continue

            # Many of these are stripped already, but strip them once more just to be sure no extra whitespace got included.
            key = key.strip()
            value = value.strip()

            if key != "" and value != "":
                #TODO: Consider setting up a function to do bulk_create of image properties.
                image.addImageProperty(key, value, False, header)

        #TODO: Also need to read all the image properties like flatCorrected, etc, and set imageIsCalibrated accordingly.
        for result in image.getImageProperty('history', asList=True):
            if result.value.lower() == 'calibrated':
                image.addImageProperty('imageIsCalibrated', 'true', True, result.header)

        # Handle data split across multiple header fields like dateObs and timeObs.
        dateObsResult = models.ImageProperty.objects.filter(image=image, key='dateObs').first()
        timeObsResult = models.ImageProperty.objects.filter(image=image, key='timeObs').first()
        if dateObsResult != None and timeObsResult != None:
            try:
                #TODO: Need to check that dateObs does not already include the time value, some do, some don't.
                image.dateTime = dateparser.parse(dateObsResult.value + ' ' + timeObsResult.value)
                image.save()
            except ValueError:
                errorText += "ERROR: Could not parse dateObs: " + value + "\n"

        # If this image was stacked from multiple images we need to set/modify some ImageProperties.
        numCombinedImages = models.ImageProperty.objects.filter(image=image, key='numCombinedImages').first()
        if numCombinedImages is not None:
            numCombinedImages = int(numCombinedImages.value)
            if numCombinedImages > 1:
                image.addImageProperty('imageIsStacked', 'yes', False, None)

                stackedTypeDict = {
                    'light': 'stackedLight',
                    'dark': 'masterDark',
                    'bias': 'masterBias',
                    'flat': 'masterFlat',
                    }

                imageType = image.getImageProperty('imageType')

                try:
                    newImageType = stackedTypeDict[imageType]
                except KeyError:
                    errorText += 'Unknown stacked image type: ' + str(imageType)
                    newImageType = imageType

                if newImageType is not None:
                    image.addImageProperty('imageType', newImageType, True)
                    image.frameType = newImageType
                    image.save()

        # If both objectRA and objectDec are 0 then remove them since they are likely just null values from the
        # software that wrote the fits file.
        objectRA = image.getImageProperty('objectRA')
        objectDec = image.getImageProperty('objectDec')
        if objectRA is not None and objectDec is not None:
            if abs(float(objectRA) - 0) < 1e-9 and abs(float(objectDec) - 0) < 1e-9:
                image.removeImageProperty('objectRA')
                image.removeImageProperty('objectDec')
                image.addImageProperty('objectRADecRemoved', 'true', True)

        # If this image has one or more 'object' tags we should examine them to see what we can determine.
        for obj in image.getImageProperty('object', asList=True):
            imageTypeObjectDict = {
                'master bias frame': 'masterBias',
                'master dark frame': 'masterDark',
                'master flat frame': 'masterFlat'
                }

            if obj.value.lower() in imageTypeObjectDict:
                newImageType = imageTypeObjectDict[obj.value.lower()]
                image.addImageProperty('imageType', newImageType, True)
                image.frameType = newImageType
                image.save()
            else:
                #TODO: Try to look up the object in the various catalogs we have in the database.
                pass

        # Set "known unknown" tags on fields that should be set for all images, but
        # haven't been read in from the header in the file.
        knownUnknownKeys = [ 'imageType', 'filter', 'exposureTime', 'flatCorrected',
            'darkCorrected', 'biasCorrected', 'width', 'height', 'binningX', 'binningY',
            'imageIsStacked' ]

        for key in knownUnknownKeys:
            imageProperty = image.getImageProperty(key)
            if imageProperty is None:
                image.addImageProperty(key, 'unknown');

        # Examine the filename of the original file and see if there are parts of the file
        # name that make sense now because of the headers we have parsed in.
        filenameMask = [''] * len(image.fileRecord.originalFileName)
        for c, i in zip(image.fileRecord.originalFileName, range(len(image.fileRecord.originalFileName))):
            if c in [' ', '_', '-']:
                filenameMask[i] = c

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

@shared_task
def flagSources(imageIdString, processInputId):
    outputText = ""
    errorText = ""
    taskStartTime = time.time()

    outputText += "Flagging image sources for image '{}'\n".format(imageIdString)

    imageId = int(imageIdString)
    image = models.Image.objects.get(pk=imageId)

    # If this is a calibration image we do not need to run this task.
    shouldReturn, retText = checkIfCalibrationImage(image, 'astrometryNet', 'skippedCalibration')
    outputText += retText
    if shouldReturn:
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    hotPixels = models.UserSubmittedHotPixel.objects.filter(image_id=imageId)
    numHotPixels = hotPixels.count()
    if numHotPixels > 0:
        outputText += "Image has {} user submitted hot pixels in it:\n".format(numHotPixels)

        tablesToSearch = [models.SextractorResult, models.Image2xyResult, models.DaofindResult,
                          models.StarfindResult, models.UserSubmittedResult, models.SourceFindMatch]
        fwhmMedian = parseFloat(image.getImageProperty('fwhmMedian', 3.0))
        for table in tablesToSearch:
            sources = table.objects.filter(image_id=imageId)
            for source in sources:
                # Flagging as near edge if it is within 3 fwhm of the edge.
                edgeDist = 3.0 * fwhmMedian
                if source.pixelX <= edgeDist or source.pixelY <= edgeDist or \
                    source.pixelX >= image.dimX - edgeDist or source.pixelY >= image.dimY - edgeDist:

                    source.flagEdge = True
                else:
                    source.flagEdge = False

                for hotPixel in hotPixels:
                    deltaX = source.pixelX - hotPixel.pixelX
                    deltaY = source.pixelY - hotPixel.pixelY
                    distSquared = deltaX*deltaX + deltaY*deltaY
                    # Flagging as hot pixel if the source is within 3 fwhm of a hot pixel.
                    if math.sqrt(distSquared) < 3.0 * fwhmMedian:
                        outputText += "source {} is within 3 pixels of hot pixel {}.\n".format(source.pk, hotPixel.pk)
                        source.flagHotPixel = True
                        source.confidence = 0.1

                # If the source is not flagged as being near a hot pixel, change its value from Null to False in the
                # database to differentiate between 'has not been checked yet' and 'has been checked but is not flagged'.
                if source.flagHotPixel is None:
                    source.flagHotPixel = False

                source.save()
    else:
        outputText += "Image has no user submitted hot pixels in it.\n"

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

@shared_task
def imageCombine(argList, processInputId):
    outputText = ""
    errorText = ""
    taskStartTime = time.time()
    argDict = {}

    processInput = models.ProcessInput.objects.get(pk=processInputId)

    #TODO: Change this.
    desiredFilename = 'cosmic_combined.fit'
    fss = FileSystemStorage()
    outputFilename = fss.get_available_name(desiredFilename)

    idList = []
    for arg in argList:
        try:
            pk = int(arg)
            idList.append(pk)
        except ValueError:
            splits = arg.split('=', 1)
            if len(splits) == 2:
                argType, argVal = splits[1].split(':', 1)
                if argType == 'str':
                    argDict[splits[0]] = argVal

                elif argType == 'int':
                    argDict[splits[0]] = int(argVal)

                else:
                    errorText += "argType '{}' not recognised, aborting.".format(argType)
                    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

            else:
                errorText += "Could not parse '{}' as int or as 'arg=type:val', skipping argument.".format(arg)
                return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    outputText += "argDict is:\n"
    for key in argDict:
        outputText += "   " + key + " = " + str(argDict[key]) + "\n"

    outputText += '\n\n'

    if 'masterBiasId' in argDict:
        masterBiasImage = models.Image.objects.filter(pk=argDict['masterBiasId']).first()
    else:
        masterBiasImage = None

    if 'masterDarkId' in argDict:
        masterDarkImage = models.Image.objects.filter(pk=argDict['masterDarkId']).first()
        darkExposure = masterDarkImage.getImageProperty('exposureTime')
    else:
        masterDarkImage = None

    if 'masterFlatId' in argDict:
        masterFlatImage = models.Image.objects.filter(pk=argDict['masterFlatId']).first()
    else:
        masterFlatImage = None

    images = models.Image.objects.filter(pk__in=idList)
    dataArray = []
    exposureSum = 0
    exposureCount = 0
    doReproject = True
    for image in images:
        if image.getBestPlateSolution() is None:
            outputText += 'Image {} does not have a plate solution, not reprojecting.\n'.format(image.pk)
            doReproject = False

    if doReproject:
        referenceWCS = images[0].getBestPlateSolution().wcs()

        minX = None
        minY = None
        maxX = None
        maxY = None
        for image in images:
            outputText += 'image footprint for image {}\n'.format(image.pk)
            outputText += '  ra, dec ; x, y\n'
            for coord in image.getBestPlateSolution().wcs().calc_footprint(axes=(image.dimX, image.dimY)):
                ra = numpy.asscalar(coord[0])
                dec = numpy.asscalar(coord[1])

                # NOTE: The third parameter is the origin.  From the documentation:
                #   Here, *origin* is the coordinate in the upper left corner of the
                #   image.  In FITS and Fortran standards, this is 1.  In Numpy and C
                #   standards this is 0.  0 for Fortan / FITS, 1 for C / Numpy
                x, y = referenceWCS.all_world2pix(ra, dec, 1)
                outputText += '  {}, {} ; {}, {}\n'.format(ra, dec, x, y)

                if minX is None:
                    minX = maxX = x
                    minY = maxY = y

                minX = min(minX, x)
                maxX = max(maxX, x)
                minY = min(minY, y)
                maxY = max(maxY, y)

        outputText += '\n\n'
        outputText += 'Output mosaic coordinates:\n'
        outputText += '     ra, dec ; x, y\n'
        minRaXY, minDecXY = referenceWCS.all_pix2world(minX, minY, 1)
        outputText += 'min: {}, {} ; {}, {}\n'.format(minRaXY, minDecXY, minX, minY)
        maxRaXY, maxDecXY = referenceWCS.all_pix2world(maxX, maxY, 1)
        outputText += 'max: {}, {} ; {}, {}\n'.format(maxRaXY, maxDecXY, maxX, maxY)
        dimX = int(maxX - minX)
        dimY = int(maxY - minY)
        outputText += 'dim: {}, {}\n'.format(dimX, dimY)

        outputShape = (dimY+2, dimX+2)
        referenceWCS.wcs.crpix -= [minX+1, minY+1]

    for image in images:
        #TODO: Look into using ccdproc.ccd_process() to do the bias, dark, flat, etc, corrections.
        outputText += "\n\n"
        outputText += "Loading image {}: {}\n".format(image.pk, image.fileRecord.originalFileName)
        hdulist = fits.open(settings.MEDIA_ROOT + image.fileRecord.onDiskFileName)

        imageExposure = image.getImageProperty('exposureTime')
        outputText += "   Image exposure time is: {}\n".format(imageExposure)

        imageTransforms = models.ImageTransform.objects.filter(subjectImage=image)
        doMatrixTransform = False
        imageTransform = None
        for transform in imageTransforms:
            for otherImage in images:
                if transform.referenceImage == otherImage:
                    doMatrixTransform = True
                    imageTransform = transform
                    break

            if doMatrixTransform:
                break

        #TODO: Do a better job than just choosing the first frame like we do now.
        data = hdulist[0].data
        if len(data.shape) == 3:
            data = data[0]

        #NOTE: This bias subtraction is done here inside the loop for code cleanliness
        # reasons, and in case of future expansions when it might want to be treated
        # differently from image to image.  It would be more computationally efficient to
        # subtract it once at the end of the loop.
        if masterBiasImage is not None:
            outputText += "Bias correcting image.\n"
            masterBiasHdulist = fits.open(settings.MEDIA_ROOT + masterBiasImage.fileRecord.onDiskFileName)

            #TODO: Do a better job than just choosing the first frame like we do now.
            masterBiasData = masterBiasHdulist[0].data
            if len(masterBiasData.shape) == 3:
                masterBiasData = masterBiasData[0]

            outputText += "  Before subtract: data:{} masterBiasData:{}\n".format(data.dtype.name, masterBiasData.dtype.name)
            #NOTE: Do not switch to -= operator since that precludes datatype upcasting.
            data = data - masterBiasData
            outputText += "  After subtract: data:{} masterBiasData:{}\n".format(data.dtype.name, masterBiasData.dtype.name)

        if masterDarkImage is not None:
            outputText += "Dark correcting image.\n"
            masterDarkHdulist = fits.open(settings.MEDIA_ROOT + masterDarkImage.fileRecord.onDiskFileName)

            #TODO: Do a better job than just choosing the first frame like we do now.
            masterDarkData = masterDarkHdulist[0].data
            if len(masterDarkData.shape) == 3:
                masterDarkData = masterDarkData[0]

            if darkExposure is not None and imageExposure is not None and imageExposure != 'unknown':
                try:
                    darkScaleFactor = float(imageExposure) / float(darkExposure)
                except:
                    outputText += '    Warning: using dark scale factor of 1.0 instead of \'{}\' / \'{}\'\n'.format(imageExposure, darkExposure)
                    darkScaleFactor = 1.0
            else:
                darkScaleFactor = 1.0

            outputText += '    Dark scale factor: {}\n'.format(darkScaleFactor)
            outputText += "  Before subtract: data:{} masterDarkData:{}\n".format(data.dtype.name, masterDarkData.dtype.name)
            #NOTE: Do not switch to -= operator since that precludes datatype upcasting.
            data = data - masterDarkData * darkScaleFactor
            outputText += "  After subtract: data:{} masterDarkData:{}\n".format(data.dtype.name, masterDarkData.dtype.name)

        if masterFlatImage is not None:
            outputText += "Flat correcting image.\n"
            masterFlatHdulist = fits.open(settings.MEDIA_ROOT + masterFlatImage.fileRecord.onDiskFileName)

            #TODO: Do a better job than just choosing the first frame like we do now.
            masterFlatData = masterFlatHdulist[0].data
            if len(masterFlatData.shape) == 3:
                masterFlatData = masterFlatData[0]

            outputText += "  Before divide: data:{} masterFlatData:{}\n".format(data.dtype.name, masterFlatData.dtype.name)
            #NOTE: Do not switch to /= operator since that precludes datatype upcasting.
            data = data / masterFlatData
            outputText += "  After divide: data:{} masterFlatData:{}\n".format(data.dtype.name, masterFlatData.dtype.name)

        if doReproject:
            outputText += 'Reprojecting image.\n'
            hdulist[0].data = data
            dataToProject = CCDData(data, wcs=image.getBestPlateSolution().wcs(), unit=u.adu)
            data = wcs_project(dataToProject, referenceWCS, target_shape=outputShape)
            dataArray.append(data)

        elif doMatrixTransform:
            outputText += 'Doing matrix transform. Reference: {}   Subject: {}\n'\
                .format(imageTransform.referenceImage.pk, imageTransform.subjectImage.pk)
            transformedData = scipy.ndimage.interpolation.affine_transform(data, imageTransform.matrix())
            dataArray.append(CCDData(transformedData, unit=u.adu))

        else:
            outputText += 'Not Reprojecting image.\n'
            dataArray.append(CCDData(data, unit=u.adu))

        if imageExposure is not None and imageExposure != 'unknown':
            exposureSum += float(imageExposure.strip().strip("'"))
            exposureCount += 1

    outputText += "\n---------------------------------------\n\n"

    exposureMean = exposureSum / exposureCount
    outputText += 'Exposure sum: {}\nExposure mean: {}\n'.format(exposureSum, exposureMean)

    outputText += "Creating Combiner.\n"
    combiner = Combiner(dataArray)

    if argDict['combineType'] == 'flat':
        outputText += "Combine type is 'flat' - scaling input images by their individual mean values.\n"
        scaling_func = lambda arr: 1/numpy.ma.average(arr)
        combiner.scaling = scaling_func

    outputText += "Performing sigma clipping.\n"
    combiner.sigma_clipping()

    if argDict['combineType'] == 'light':
        if 'lightCombineMethod' in argDict:
            outputText += "Light combine method: " + argDict['lightCombineMethod'] + "\n"
            if argDict['lightCombineMethod'] == 'mean':
                combinedData = combiner.average_combine()
            elif argDict['lightCombineMethod'] == 'median':
                combinedData = combiner.median_combine()
            else:
                outputText += "WARNING: light combine method not recognized - defaulting to 'median'\n"
                errorText += "WARNING: light combine method not recognized - defaulting to 'median'\n"
                combinedData = combiner.median_combine()
        else:
            outputText += "Light combine method not set - defaulting to 'median'\n"
            combinedData = combiner.median_combine()
    else:
        outputText += "Combining via median combine"
        combinedData = combiner.median_combine()

    primaryHDU = fits.PrimaryHDU(combinedData)

    if argDict['combineType'] in ['light']:
        primaryHDU.header.append( ('exptime', str(exposureSum)) )
    elif argDict['combineType'] in ['bias', 'dark', 'flat']:
        primaryHDU.header.append( ('exptime', str(exposureMean)) )

    primaryHDU.header.append( ('origin', 'Cosmic.science') )
    primaryHDU.header.append( ('imagetyp', 'master ' + argDict['combineType']) )
    primaryHDU.header.append( ('ncombine', str(len(dataArray))) )
    for image, i in zip(images, range(1, 1+len(images))):
        imageString = 'Image ' + str(image.pk) + ':  ' + image.fileRecord.originalFileName
        primaryHDU.header.append( ('imcmb{:03d}'.format(i), imageString) )
        primaryHDU.header.append( ('exptim{:02d}'.format(i), image.getImageProperty('exposureTime')) )

    if masterBiasImage is not None:
        imageString = 'Image ' + str(masterBiasImage.pk) + ':  ' + masterBiasImage.fileRecord.originalFileName
        primaryHDU.header.append( ('zerocor', imageString) )

    if masterDarkImage is not None:
        imageString = 'Image ' + str(masterDarkImage.pk) + ':  ' + masterDarkImage.fileRecord.originalFileName
        primaryHDU.header.append( ('darkcor', imageString) )

    if masterFlatImage is not None:
        imageString = 'Image ' + str(masterFlatImage.pk) + ':  ' + masterFlatImage.fileRecord.originalFileName
        primaryHDU.header.append( ('flatcor', imageString) )

    if doReproject:
        wcsHeader = referenceWCS.to_header()
        for card in wcsHeader:
            primaryHDU.header[card] = wcsHeader[card]

    else:
        #TODO: Look at the headers of the input images to see if they have ra-dec properties set.
        pass

    combinedHDUList = fits.HDUList([primaryHDU])
    outputText += "\nWriting image.\n"
    combinedHDUList.writeto(settings.MEDIA_ROOT + outputFilename)
    outputText += "Done.\n"

    hashObject = hashlib.sha256()
    with open(settings.MEDIA_ROOT + outputFilename, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hashObject.update(chunk)

    fileRecord = models.UploadedFileRecord(
        uploadSession = None,
        user = processInput.requestor,
        createdByProcess = processInput,
        unpackedFromFile = None,
        originalFileName = desiredFilename,
        onDiskFileName = outputFilename,
        fileSha256 = hashObject.hexdigest(),
        uploadSize = os.stat(settings.MEDIA_ROOT + outputFilename).st_size
        )

    fileRecord.save()

    #TODO: Make this function call take a reference to this task so it can give it as a
    # pre-requisite to all of the created tasks so that none of them (for example image
    # stats) can run before the remainder of this function finishes.  An unlikely scenario
    # but still a possible race condition none the less.
    image = createTasksForNewImage(fileRecord, processInput.requestor)
    if doReproject:
        image.addImageProperty('wcsSource', 'cosmic:stack-reproject')

    # Set parentImages on the newly created image.
    for parent in images:
        image.parentImages.add(parent)

    for calibrationImage in [masterBiasImage, masterDarkImage, masterFlatImage]:
        if calibrationImage is not None:
            image.parentImages.add(calibrationImage)

    #TODO: Set instrument/observatory if it was set on the parent images.

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

@shared_task
def calculateUserCostTotals(startTimeString, endTimeString, processInputId):
    outputText = ""
    errorText = ""
    taskStartTime = time.time()

    if startTimeString != '':
        startTime = dateparser.parse(startTimeString)
    else:
        startTime = models.CostTotal.objects.aggregate(Max('endDate'))['endDate__max']

    if endTimeString != '':
        endTime = dateparser.parse(endTimeString)
    else:
        endTime = timezone.now()

    if startTime is None or endTime is None:
        errorText += 'Exiting due to Null start time or end time.'
        return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

    outputText += 'Calculating user resource cost totals for the following period.\n'
    outputText += 'Start Time: {}\nEnd Time: {}\n\n'.format(startTime, endTime)

    with transaction.atomic():
        storageCostPerMonth = models.CosmicVariable.getVariable('storageCostPerMonth')
        users = models.User.objects.all()
        costTotals = []
        for user in users:
            userStartTime = max(startTime, user.date_joined)
            deltaTime = endTime - userStartTime
            storageCostPerByte = deltaTime.total_seconds() * ((storageCostPerMonth / 1e9) / (86400*30))
            storageSize = models.Image.objects\
                .filter(fileRecord__user=user, fileRecord__uploadDateTime__lte=endTime)\
                .aggregate(Sum('fileRecord__uploadSize'))['fileRecord__uploadSize__sum']

            if storageSize is not None:
                storageCost = storageSize * storageCostPerByte
                siteCost = models.SiteCost(
                    user = user,
                    dateTime = endTime,
                    text = 'Image storage cost for ' + str(userStartTime) + ' to ' + str(endTime),
                    cost = storageCost
                    )

                siteCost.save()

            storageSize = models.AudioNote.objects\
                .filter(fileRecord__user=user, fileRecord__uploadDateTime__lte=endTime)\
                .aggregate(Sum('fileRecord__uploadSize'))['fileRecord__uploadSize__sum']

            if storageSize is not None:
                storageCost = storageSize * storageCostPerByte
                siteCost = models.SiteCost(
                    user = user,
                    dateTime = endTime,
                    text = 'Audio note storage cost for ' + str(userStartTime) + ' to ' + str(endTime),
                    cost = storageCost
                    )

                siteCost.save()

            totalCost = models.SiteCost.objects\
                .filter(user=user, dateTime__gt=startTime, dateTime__lte=endTime)\
                .aggregate(Sum('cost'))['cost__sum']

            if totalCost is None:
                continue

            costTotal = models.CostTotal(
                user = user,
                startDate = startTime,
                endDate = endTime,
                text = 'Daily cost total for ' + str(startTime),
                cost = totalCost
                )

            costTotals.append(costTotal)

        models.CostTotal.objects.bulk_create(costTotals)

        for user in users:
            userCost = models.CostTotal.objects\
                .filter(user=user)\
                .aggregate(Sum('cost'))['cost__sum']

            user.profile.totalCost = userCost
            user.save()

    return constructProcessOutput(outputText, errorText, time.time() - taskStartTime)

