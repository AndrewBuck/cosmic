from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django.db import transaction
from django.conf import settings
from django.db.models import Avg, StdDev
from django.contrib.gis.geos import GEOSGeometry

import subprocess
import json
import sys
import os
import re
import itertools
import math
import dateparser

from astropy import wcs
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.table import Table
from photutils import make_source_mask, DAOStarFinder, IRAFStarFinder

import ephem

from cosmicapp import models

staticDirectory = os.path.dirname(os.path.realpath(__file__)) + "/static/cosmicapp/"

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def storeImageLocation(image, w, sourceString):
    #TODO: should check w.lattyp and w.lontyp to make sure we are storing these world coordinates correctly.
    raCen, decCen = w.all_pix2world(image.dimX/2, image.dimY/2, 1)    #TODO: Determine if this 1 should be a 0.
    raScale, decScale = wcs.utils.proj_plane_pixel_scales(w)
    raScale *= 3600.0
    decScale *= 3600.0

    polygonPixelsList = [
        (1, 1),
        (image.dimX, 1),
        (image.dimX, image.dimY),
        (1, image.dimY),
        (1, 1)
        ]

    polygonCoordsList = []
    geometryString = 'POLYGON(('
    commaString = ''

    for x, y in polygonPixelsList:
        ra, dec = w.all_pix2world(x, y, 1)    #TODO: Determine if this 1 should be a 0.
        geometryString += commaString + str(ra) + ' ' + str(dec)
        commaString = ', '

    geometryString += '))'

    #TODO: Store image.centerRot
    ps = models.PlateSolution(
        image = image,
        wcsHeader = w.to_header_string(True),
        source = sourceString,
        centerRA = raCen,
        centerDec = decCen,
        centerRot = None,
        resolutionX = raScale,
        resolutionY = decScale,
        geometry = geometryString
        )

    ps.area = ps.geometry.area
    ps.save()

def constructProcessOutput(outputText, errorText):
    processOutput = {
        'outputText': outputText,
        'outputErrorText': errorText
        }

    return processOutput

@shared_task
def imagestats(filename):
    outputText = ""
    errorText = ""

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
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)
    image.dimX = jsonObject[0]['width']
    image.dimY = jsonObject[0]['height']
    image.bitDepth = jsonObject[0]['depth']

    with transaction.atomic():
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
        for line in output2.splitlines():
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

            headerField = models.ImageHeaderField(
                image = image,
                index = i,
                key = key,
                value = value
                )

            headerField.save()

            i += 1

    outputText += "imagestats:wcs: " + filename + "\n"
    if os.path.splitext(filename)[-1].lower() in ['.fit', '.fits']:
        w = wcs.WCS(settings.MEDIA_ROOT + filename)

        if w.has_celestial:
            outputText += "WCS found in header" + "\n"

            storeImageLocation(image, w, 'original')
        else:
            outputText += "WCS not found in header" + "\n"

    outputText += "imagestats:background: " + filename + "\n"
    if os.path.splitext(filename)[-1].lower() in ['.fit', '.fits']:
        hdulist = fits.open(settings.MEDIA_ROOT + filename)
        with transaction.atomic():
            channelIndex = 0
            for hdu in hdulist:
                frames = []
                #TODO: Check that this is really image data and not a table, etc.
                if len(hdu.data.shape) == 2:
                    frames.append(hdu.data)

                if len(hdu.data.shape) == 3:
                    for i in range(hdu.data.shape[0]):
                        frames.append(hdu.data[channelIndex+i])

                for frame in frames:
                    outputText += "imagestats:histogram:\n"
                    # Compute min/max of data values and count valid pixels.
                    minValue = frame[0][0]
                    maxValue = frame[0][0]
                    numValidPixels = 0
                    for i in frame:
                        for j in i:
                            #TODO: Need to check that the pixel is not a hot pixel, etc.
                            numValidPixels += 1

                            if j < minValue:
                                minValue = j

                            if j > maxValue:
                                maxValue = j

                    # Fill the bins array with zero count for every bin.
                    numBins = 10000
                    binWidth = (maxValue-minValue)/float(numBins)
                    bins = []
                    for i in range(numBins+1):
                        bins.append(0)

                    # Now that we know the data range, compute the bin values and then
                    # loop over again to sort the pixels into bins.
                    for i in frame:
                        for j in i:
                            binIndex = math.floor( (j-minValue)/binWidth )
                            bins[binIndex] += 1

                    plotFilename = "histogramData_{}_{}.gnuplot".format(image.pk, channelIndex)
                    binFilename = "histogramData_{}_{}.txt".format(image.pk, channelIndex)

                    # Write the gnuplot script file.
                    with open("/cosmicmedia/" + plotFilename, "w") as outputFile:
                        outputFile.write("set terminal svg size 400,300 dynamic mouse standalone\n" +
                                         "set output '{}/{}.svg'\n".format(staticDirectory + "images", plotFilename) +
                                         "set key off\n" +
                                         "set logscale y\n" +
                                         "set style line 1 linewidth 3 linecolor 'blue'\n" +
                                         "plot '/cosmicmedia/{}' using 1:2 with lines linestyle 1\n".format(binFilename)
                                         )

                    # Write the 2 column data to be read in by gnuplot.
                    cumulativePixelFraction = 0.0
                    with open("/cosmicmedia/" + binFilename, "w") as outputFile:
                        for binCount, binNumber in zip(bins, range(len(bins))):
                            if binCount == 0.0:
                                continue


                            binFloor = minValue + binNumber*binWidth
                            binCount = binCount/numValidPixels
                            cumulativePixelFraction += binCount

                            # Skip writing values for up 0.05% of the darkest and
                            # brightest pixels. This is to match the parameters used in
                            # generating thumnails.
                            ignoreLower = 0.0005
                            ignoreUpper = 0.0005
                            if cumulativePixelFraction <= ignoreLower:
                                continue
                            if cumulativePixelFraction - binCount >= 1.0 - ignoreLower:
                                continue

                            histogramBin = models.ImageHistogramBin(
                                image = image,
                                binFloor = binFloor,
                                binCount = binCount
                                )

                            histogramBin.save()

                            outputFile.write("{} {}\n".format(binFloor, binCount))

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

                    try:
                        channelInfo = models.ImageChannelInfo.objects.get(image=image, index=channelIndex)
                    except:
                        continue

                    mean, median, stdDev = sigma_clipped_stats(frame, sigma=10, iters=0)

                    #TODO: Look into this masking and potentially record the masked pixel data as a stored thing which can be accessed later on.
                    #mask = make_source_mask(frame, snr=10, npixels=5, dilate_size=11)
                    bgMean, bgMedian, bgStdDev = sigma_clipped_stats(frame, sigma=3, iters=3)

                    #TODO: For some reason the median and bgMedain are always 0.  Need to fix this.
                    channelInfo.mean = mean
                    channelInfo.median = median
                    channelInfo.stdDev = stdDev
                    channelInfo.bgMean = bgMean
                    channelInfo.bgMedian = bgMedian
                    channelInfo.bgStdDev = bgStdDev
                    channelInfo.numValidHistogramPixels = numValidPixels
                    channelInfo.histogramBinWidth = binWidth
                    channelInfo.save()

                    channelIndex += 1

        hdulist.close()

    return constructProcessOutput(outputText, errorText)

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
    
@shared_task
def generateThumbnails(filename):
    outputText = ""
    errorText = ""

    filenameFull = os.path.splitext(filename)[0] + "_thumb_full.png"
    filenameSmall = os.path.splitext(filename)[0] + "_thumb_small.png"
    filenameMedium = os.path.splitext(filename)[0] + "_thumb_medium.png"
    filenameLarge = os.path.splitext(filename)[0] + "_thumb_large.png"

    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

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
    
    # TODO: Generate transformation by looking at plate solutions for subsections of
    #   full image and extracting coeffecients

    #TODO: For the really commonly loaded sizes like the ones in search results, etc, we
    # should consider sending a smaller size and scaling it up to the size we want on screen
    # to save bandwidth and decrease load times.
    
    #TODO: All the thumbnails are square so we should decide what to do about this.
    
    #TODO: Add some python logic to decide the exact dimensions we want the thumbnails to
    # be to preserve aspect ratio but still respect screen space requirements.
    for tempFilename, sizeArg, sizeString in [(filenameFull, "100%", "full"), (filenameSmall, "100x100", "small"),
                                              (filenameMedium, "300x300", "medium"), (filenameLarge, "900x900", "large")]:

        #TODO: Small images will actually get thumbnails made which are bigger than the original, should implement
        # protection against this - will need to test all callers to make sure that is safe.
        #TODO: Play around with the 'convolve' kernel here to see what the best one to use is.
        # Consider bad horiz/vert lines, also bad pixels, and finally noise.
        # For bad lines use low/negative values along the middle row/col in the kernel.
        proc = subprocess.Popen(['convert', "-gamma", "0.8", "-convolve", "1,2,4,2,1,2,4,6,4,2,3,5,10,5,3,2,4,6,4,2,1,2,4,2,1",
                "-contrast-stretch", ".1%x.1%", "-strip", "-filter", "spline", "-resize",
                sizeArg, "-verbose", settings.MEDIA_ROOT + filename, "-depth", "8", staticDirectory + "images/" + tempFilename],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

        output, error = proc.communicate()
        output = output.decode('utf-8')
        error = error.decode('utf-8')

        proc.wait()

        outputText += output
        errorText += error
        outputText += '\n ==================== End of process output ====================\n\n'
        errorText += '\n ==================== End of process error =====================\n\n'

        outputText += "generateThumbnails: " + tempFilename + "\n"

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

    return constructProcessOutput(outputText, errorText)

def initSourcefind(method, image):
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
        numExpectedFeedback = image.getImageProperty('userNumExpectedResults', True)
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

        if feedbackFound:
            outputText += "Valid range of results is between {} and {}.\n".format(minValid, maxValid)
            if previousRunNumFound <= 0.1*minValid:
                detectThresholdMultiplier -= 1.0
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
                detectThresholdMultiplier += 1.0
                outputText += "Last run was more than 10 times the user submitted figure, increasing detection threshold a lot.\n"

    if detectThresholdMultiplier < 0.1:
        outputText += "Not running threshold of {} standard deviations, exiting.\n".format(detectThresholdMultiplier)
        shouldReturn = True

    # Store the multiplier we decided to use in case we re-run this method in the future.
    image.addImageProperty(method + 'Multiplier', str(detectThresholdMultiplier))

    return (detectThresholdMultiplier, shouldReturn, outputText, errorText)

@shared_task
def sextractor(filename):
    # Get the image record
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = models.ImageChannelInfo.objects.filter(image=image).order_by('index')

    detectThresholdMultiplier, shouldReturn, outputText, errorText = initSourcefind('sextractor', image)

    if shouldReturn:
        return constructProcessOutput(outputText, errorText)

    detectThreshold = detectThresholdMultiplier*channelInfos[0].bgStdDev
    outputText += 'Final multiplier of {} standard deviations.\n'.format(detectThresholdMultiplier)
    outputText += 'Final detect threshold of {} above background.\n'.format(detectThreshold)

    #TODO: sextractor can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    #TODO: sextractor has a ton of different modes and options, we should consider running
    # it multiple times to detect point sources, then again for extended sources, etc.
    # Each of these different settings options could be combined into a single output, or
    # they could be independently matched against other detection algorithms.
    catfileName = settings.MEDIA_ROOT + filename + ".cat"
    proc = subprocess.Popen(['sextractor', '-CATALOG_NAME', catfileName, settings.MEDIA_ROOT + filename,
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

    outputText += "sextractor: " + filename + "\n"

    with open(catfileName, 'r') as catfile:
        fieldDict = {}
        with transaction.atomic():
            models.SextractorResult.objects.filter(image=image).delete()
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
                    record = models.SextractorResult(
                        image = image,
                        pixelX = fields[fieldDict['X_IMAGE_DBL']],
                        pixelY = fields[fieldDict['Y_IMAGE_DBL']],
                        pixelZ = zPos,
                        fluxAuto = fields[fieldDict['FLUX_AUTO']],
                        fluxAutoErr = fields[fieldDict['FLUXERR_AUTO']],
                        flags = fields[fieldDict['FLAGS']],
                        boxXMin = fields[fieldDict['XMIN_IMAGE']],
                        boxYMin = fields[fieldDict['YMIN_IMAGE']],
                        boxXMax = fields[fieldDict['XMAX_IMAGE']],
                        boxYMax = fields[fieldDict['YMAX_IMAGE']]
                        )

                    record.save()

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
                    fields[fieldDict['FWHM_IMAGE']]
                    fields[fieldDict['ELLIPTICITY']]
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

            records = models.SextractorResult.objects.filter(image=image)
            meanFluxAuto = records.aggregate(Avg('fluxAuto'))['fluxAuto__avg']
            stdDevFluxAuto = records.aggregate(StdDev('fluxAuto'))['fluxAuto__stddev']

            for record in records:
                record.confidence = sigmoid((record.fluxAuto-meanFluxAuto)/stdDevFluxAuto)
                record.save()

    try:
        os.remove(catfileName)
    except OSError:
        pass

    return constructProcessOutput(outputText, errorText)

@shared_task
def image2xy(filename):
    outputText = ""
    errorText = ""

    # Get the image record
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Use the -P option to handle images with multiple planes.  Also has support for multi-extension fits built in if called with appropriate params.
    #TODO: Consider using the -d option to downsample by a given factor before running.
    #TODO: image2xy can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
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

    outputText += "image2xy: " + filename + "\n"
    sys.stdout.flush()

    table = Table.read(outputFilename, format='fits')

    with transaction.atomic():
        models.Image2xyResult.objects.filter(image=image).delete()
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

            result.save()

        records = models.Image2xyResult.objects.filter(image=image)
        meanFlux = records.aggregate(Avg('flux'))['flux__avg']
        stdDevFlux = records.aggregate(StdDev('flux'))['flux__stddev']

        for record in records:
            record.confidence = sigmoid((record.flux-meanFlux)/stdDevFlux)
            record.save()

    try:
        os.remove(outputFilename)
    except OSError:
        pass

    return constructProcessOutput(outputText, errorText)

@shared_task
def daofind(filename):
    #TODO: daofind can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = models.ImageChannelInfo.objects.filter(image=image).order_by('index')

    detectThresholdMultiplier, shouldReturn, outputText, errorText = initSourcefind('daofind', image)

    if shouldReturn:
        return constructProcessOutput(outputText, errorText)

    detectThreshold = detectThresholdMultiplier*channelInfos[0].bgStdDev
    outputText += 'Final multiplier of {} standard deviations.\n'.format(detectThresholdMultiplier)
    outputText += 'Final detect threshold of {} above background.\n'.format(detectThreshold)

    hdulist = fits.open(settings.MEDIA_ROOT + filename)
    data = hdulist[0].data
    #TODO: Set the fwhm from a variable if this is the first run, or from the previous run average if this is the second run of this task.
    daofind = DAOStarFinder(fwhm = 2.5, threshold = detectThresholdMultiplier*channelInfos[0].bgStdDev)
    sources = daofind(data - channelInfos[0].bgMedian)

    with transaction.atomic():
        models.DaofindResult.objects.filter(image=image).delete()
        for source in sources:
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

            result.save()

        records = models.DaofindResult.objects.filter(image=image)
        meanMag = records.aggregate(Avg('mag'))['mag__avg']
        stdDevMag = records.aggregate(StdDev('mag'))['mag__stddev']

        for record in records:
            #TODO: Incorporate sharpness, sround, and ground into the calculation.
            record.confidence = sigmoid((meanMag-record.mag)/stdDevMag)
            record.save()

    return constructProcessOutput(outputText, errorText)

@shared_task
def starfind(filename):
    #TODO: starfind can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = models.ImageChannelInfo.objects.filter(image=image).order_by('index')

    detectThresholdMultiplier, shouldReturn, outputText, errorText = initSourcefind('starfind', image)

    if shouldReturn:
        return constructProcessOutput(outputText, errorText)

    detectThreshold = detectThresholdMultiplier*channelInfos[0].bgStdDev
    outputText += 'Final multiplier of {} standard deviations.\n'.format(detectThresholdMultiplier)
    outputText += 'Final detect threshold of {} above background.\n'.format(detectThreshold)

    hdulist = fits.open(settings.MEDIA_ROOT + filename)
    data = hdulist[0].data
    #TODO: Set the fwhm from a variable if this is the first run, or from the previous run average if this is the second run of this task.
    starfinder = IRAFStarFinder(fwhm = 2.5, threshold = detectThresholdMultiplier*channelInfos[0].bgStdDev)
    sources = starfinder(data - channelInfos[0].bgMedian)

    with transaction.atomic():
        models.StarfindResult.objects.filter(image=image).delete()
        for source in sources:
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

            result.save()

        records = models.StarfindResult.objects.filter(image=image)
        meanMag = records.aggregate(Avg('mag'))['mag__avg']
        stdDevMag = records.aggregate(StdDev('mag'))['mag__stddev']

        for record in records:
            #TODO: Incorporate sharpness, roundness, etc, into the calculation.
            record.confidence = sigmoid((meanMag-record.mag)/stdDevMag)
            record.save()

    return constructProcessOutput(outputText, errorText)

@shared_task
def starmatch(filename):
    outputText = ""
    errorText = ""

    outputText += "starmatch: " + filename + "\n"

    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

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

    # Loop over all the pairs of source extraction methods listed in 'inputs'.
    matchedResults = []
    for i1, i2 in itertools.combinations(inputs, 2):
        results1 = i1['model'].objects.filter(image=image)
        results2 = i2['model'].objects.filter(image=image)

        outputText += 'Matching {} {} results with {} {} results'.format(len(results1), i1['name'], len(results2), i2['name']) + "\n"

        # Loop over all the pairs of results in the two current methods and record
        # any match pairs that are within 3 pixels of eachother.
        #TODO: Sort stars into bins first to cut down on the n^2 growth.
        matches = []
        for r1 in results1:
            nearestDist = 3.0
            nearestDistSq = nearestDist * nearestDist
            nearestResult = None
            x1 = r1.pixelX
            y1 = r1.pixelY
            for r2 in results2:
                dx = r2.pixelX - x1
                dy = r2.pixelY - y1
                dSq = dx*dx + dy*dy

                if dSq < nearestDistSq:
                    nearestDist = math.sqrt(dSq)
                    nearestDistSq = dSq
                    nearestResult = r2

            if nearestResult != None:
                matches.append( (r1, nearestResult) )

        outputText += '   Found {} matches.'.format(len(matches)) + "\n"
        matchedResults.append( (i1, i2, matches) )

    # Now that we have all the matches between every two individual methods, combine them into 'superMatches' where 3
    # or more different match types all agree on the same star.
    outputText += 'Calculating super matches:' + "\n"
    superMatches = []
    for i1, i2, matches in matchedResults:
        for match in matches:
            # Check to see if either of the matched pair in the current match exist anyhere in the super matches already
            for superMatch in superMatches:
                if i1['name'] in superMatch:
                    if superMatch[i1['name']] == match[0]:
                        superMatch[i2['name']] = match[1]
                        break
                if i2['name'] in superMatch:
                    if superMatch[i2['name']] == match[1]:
                        superMatch[i1['name']] = match[0]
                        break
            # Nether of the current match pair exists anywhere in the superMatch array already, so create a new entry
            # containing the current match pair.
            else:
                d = {}
                d[i1['name']] = match[0]
                d[i2['name']] = match[1]
                superMatches.append(d)

    # Loop over all the superMatch entries and create a database entry for each one.
    outputText += 'Found {} super matches.  Writing them to the DB...'.format(len(superMatches)) + "\n"
    sys.stdout.flush()
    with transaction.atomic():
        models.SourceFindMatch.objects.filter(image=image).delete()
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

            record.save()

    outputText += 'Done.' + "\n"

    return constructProcessOutput(outputText, errorText)

@shared_task
def astrometryNet(filename):
    outputText = ""
    errorText = ""

    outputText += "astrometrynet: " + filename + "\n"

    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    imageType = image.getImageProperty('imageType')
    outputText += "Image type is: " + str(imageType) + "\n"
    if imageType in ('bias', 'dark', 'flat'):
        outputText += "\n\n\nReturning, do not need to plate solve calibration images (bias, dark, flat)\n"

        processOutput = {
            'outputText': outputText,
            'outputErrorText': errorText
            }

        return processOutput


    superMatches = models.SourceFindMatch.objects.filter(image=image)

    xValues = []
    yValues = []
    confidenceValues = []
    for star in superMatches:
        xValues.append(star.pixelX)
        yValues.append(star.pixelY)
        confidenceValues.append(star.confidence)

    try:
        tableFilename = settings.MEDIA_ROOT + filename + ".sources.xyls"
        table = Table([xValues, yValues, confidenceValues], names=("XIMAGE", "YIMAGE", "CONFIDENCE"), dtype=('f4', 'f4', 'f4'));
        table.write(tableFilename, format='fits')
    except OSError:
        errorText += 'ERROR: Could not open file for writing: ' + tableFilename + "\n"
        return False

    outputText += "Chose {} objects to use in plate solution.".format(len(table)) + "\n"

    previousResult = image.getImageProperty('astrometryNet')
    cpuLimit = '30'
    depth = '8,14,22'
    if previousResult == None:
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
    if ra is not None:
        argArray.append('--ra')
        argArray.append(str(ra))
        argArray.append('--dec')
        argArray.append(str(dec))
        argArray.append('--radius')
        argArray.append(str(models.CosmicVariable.getVariable('astrometryNetRadius')))

        outputText += 'Searching a {} degree radius around the ra, dec of ({}, {})\n'.format(models.CosmicVariable.getVariable('astrometryNetRadius'), ra, dec)

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

        storeImageLocation(image, w, 'astrometry.net')
        image.addImageProperty('astrometryNet', 'success')
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

    return constructProcessOutput(outputText, errorText)

@shared_task
def parseHeaders(imageId):
    outputText = ""
    errorText = ""

    image = models.Image.objects.get(pk=imageId)
    headers = models.ImageHeaderField.objects.filter(image=imageId)

    with transaction.atomic():
        for header in headers:
            if header.key == 'fits:bitpix':
                key = 'bitDepth'
                value = str(abs(int(header.value.split()[0])))

            elif header.key in ['fits:date_obs', 'fits:date-obs']:
                key = 'dateObs'
                value = header.value.split('/')[0].strip().strip("'")
                try:
                    image.dateTime = dateparser.parse(value)
                    image.save()
                except ValueError:
                    outputError += "ERROR: Could not parse dateObs: " + value + "\n"

            elif header.key in ['fits:time_obs', 'fits:time-obs']:
                key = 'timeObs'
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

            image.addImageProperty(key, value, False, header)

        # Handle data split across multiple header fields like dateObs and timeObs.
        dateObsResult = models.ImageProperty.objects.filter(image=image, key='dateObs').first()
        timeObsResult = models.ImageProperty.objects.filter(image=image, key='timeObs').first()
        if dateObsResult != None and timeObsResult != None:
            try:
                image.dateTime = dateparser.parse(dateObsResult.value + ' ' + timeObsResult.value)
                image.save()
            except ValueError:
                errorText += "ERROR: Could not parse dateObs: " + value + "\n"

    return constructProcessOutput(outputText, errorText)

@shared_task
def flagSources(imageIdString):
    outputText = ""
    errorText = ""

    outputText += "Flagging image sources for image '{}'\n".format(imageIdString)

    imageId = int(imageIdString)
    image = models.Image.objects.get(pk=imageId)

    hotPixels = models.UserSubmittedHotPixel.objects.filter(image_id=imageId)
    numHotPixels = hotPixels.count()
    if numHotPixels > 0:
        outputText += "Image has {} user submitted hot pixels in it:\n".format(numHotPixels)
        hotPixelIdList = list(map(lambda x: x.pk, hotPixels))
        outputText += "    " + str(hotPixelIdList) + "\n\n"

        tablesToSearch = [models.SextractorResult, models.Image2xyResult, models.DaofindResult,
                          models.StarfindResult, models.UserSubmittedResult, models.SourceFindMatch]
        for table in tablesToSearch:
            sources = table.objects.filter(image_id=imageId)
            for source in sources:
                #TODO: Should come up with a good definition of edge distance.
                edgeDist = 10
                if source.pixelX <= edgeDist or source.pixelY <= edgeDist or \
                    source.pixelX >= image.dimX - edgeDist or source.pixelY >= image.dimY - edgeDist:

                    source.flagEdge = True
                else:
                    source.flagEdge = False

                for hotPixel in hotPixels:
                    deltaX = source.pixelX - hotPixel.pixelX
                    deltaY = source.pixelY - hotPixel.pixelY
                    distSquared = deltaX*deltaX + deltaY*deltaY
                    if distSquared < 9:
                        outputText += "source {} is within 3 pixels of hot pixel {}.\n".format(source.pk, hotPixel.pk)
                        source.flagHotPixel = True
                        source.confidence = 0.1

                if source.flagHotPixel is None:
                    source.flagHotPixel = False

                source.save()
    else:
        outputText += "Image has no user submitted hot pixels in it\n"

    return constructProcessOutput(outputText, errorText)

def computeSingleEphemeris(asteroid, ephemTime):
    ephemTimeObject = ephem.Date(ephemTime)

    body = ephem.EllipticalBody()

    body._inc = asteroid.inclination
    body._Om = asteroid.lonAscendingNode
    body._om = asteroid.argPerihelion
    body._a = asteroid.semiMajorAxis
    body._M = asteroid.meanAnomaly
    body._epoch_M = asteroid.epoch
    body._epoch = asteroid.epoch
    body._e = asteroid.eccentricity
    body._H = asteroid.absMag
    body._G = asteroid.slopeParam

    #TODO: The computed RA/DEC are off slightly, fix this.  I think it is due the +0.5 day issue in the epoch time in the import script.
    body.compute(ephemTimeObject)

    return body

def computeSingleEphemerisRange(asteroid, ephemTimeStart, ephemTimeEnd, tolerance, timeTolerance, startEphemeris, endEphemeris):
    if startEphemeris == None and endEphemeris == None:
        firstCall = True
    else:
        firstCall = False

    ephemerideList = []

    if startEphemeris == None:
        startEphemeris = computeSingleEphemeris(asteroid, ephemTimeStart)

    if endEphemeris == None:
        endEphemeris = computeSingleEphemeris(asteroid, ephemTimeEnd)

    if firstCall:
        ephemerideList.append( (ephemTimeStart, startEphemeris) )

    positionDelta = (180/math.pi)*ephem.separation(startEphemeris, endEphemeris)
    if positionDelta > tolerance:
        steps = math.ceil(positionDelta/tolerance)
        timeDelta = (ephemTimeEnd - ephemTimeStart) / steps

        if timeDelta > timeTolerance:
            timeDelta = timeTolerance
            steps = math.ceil((ephemTimeEnd - ephemTimeStart) / timeDelta)

        s = startEphemeris
        for i in range(steps-1):
            ephemTimeMid = ephemTimeStart + timeDelta
            tempList = computeSingleEphemerisRange(asteroid, ephemTimeStart, ephemTimeMid, tolerance, timeTolerance, s, None)

            #TODO: Add a check here and perform a linear interpolation between the s and m ephemeride positions.  If
            # the interpolated position differs by more than some smaller tolerance, then compute an extra step in the
            # middle.  This should mostly catch the special case where the asteroid undergoes retrograde motion and
            # moves back to nearly the same spot, even though it was quite a bit farther away in between those two
            # points.  This will not be a perfect solution but should be so close to perfect as to not matter.

            ephemerideList.extend(tempList)
            ephemTimeStart = ephemTimeMid
            s = tempList[-1][1]

    ephemerideList.append( (ephemTimeEnd, endEphemeris) )

    return ephemerideList

def computeAsteroidEphemerides(ephemTimeStart, ephemTimeEnd, tolerance, timeTolerance, clearFirst):
    def writeAstorbEphemerisToDB(astorbRecord, startTime, endTime, dimMag, brightMag, geometry):
        #print("saving " + str(startTime) + "       " + str(endTime) + "     " + geometry)
        record = models.AstorbEphemeris(
            astorbRecord = asteroid,
            startTime = startTime,
            endTime = endTime,
            dimMag = dimMag,
            brightMag = brightMag,
            geometry = geometry
            )

        record.save()

    offset = 0
    pagesize = 25000

    numAsteroids = models.AstorbRecord.objects.count()
    print('Num asteroids to compute: {}'.format(numAsteroids))
    sys.stdout.flush()

    with transaction.atomic():
        if clearFirst:
            models.AstorbEphemeris.objects.all().delete()

        while offset < numAsteroids:
            asteroids = models.AstorbRecord.objects.all()[offset : offset+pagesize]

            for asteroid in asteroids:
                #TODO: Add a check to see if there is already an ephemeris calculated near the start/end time and if so
                # pass it along to this function (remember to change the time to match the ephemeris we are passing).
                ephemerideList = computeSingleEphemerisRange(asteroid, ephemTimeStart, ephemTimeEnd, tolerance, timeTolerance, None, None)

                startingElement = ephemerideList[0]
                previousElement = ephemerideList[0]
                brightMag = startingElement[1].mag
                dimMag = startingElement[1].mag
                geometryString = 'LINESTRING(' + str(startingElement[1].ra*180/math.pi) + " " + str(startingElement[1].dec*180/math.pi)
                angularDistance = 0.0
                resultsWritten = False
                for element in ephemerideList[1:]:
                    resultsWritten = False
                    #print(element[0], element[1].ra*180/math.pi, element[1].dec*180/math.pi, element[1].mag)
                    if element[1].mag < brightMag:
                        brightMag = element[1].mag

                    if element[1].mag > dimMag:
                        dimMag = element[1].mag

                    # Check to see if the asteroid crosses the meridian
                    dRA = element[1].ra - previousElement[1].ra
                    dDec = element[1].dec - previousElement[1].dec
                    meridianCrossDistance = (180/math.pi)*math.sqrt(dRA*dRA + dDec*dDec)
                    if meridianCrossDistance < 180:    # Does not cross the meridian, handle normally.
                        meridianCross = False
                        geometryString += "," + str(element[1].ra*180/math.pi) + " " + str(element[1].dec*180/math.pi)
                    else:    # Does cross the meridian, end the line 1 segment early and start a new segment
                        meridianCross = True

                        # Check to see which direction we are crossing the meridian in and set up variables for later use.
                        if element[1].ra > math.pi and previousElement[1].ra < math.pi:
                            highRAElement = element
                            lowRAElement = previousElement
                            firstEdgeRA = 0
                            secondEdgeRA = 360
                        elif element[1].ra < math.pi and previousElement[1].ra > math.pi:
                            highRAElement = previousElement
                            lowRAElement = element
                            firstEdgeRA = 360
                            secondEdgeRA = 0
                        else:
                            print("ERROR: Got confused in meridian cross of asteroid.")
                            print("asteroid:", asteroid.number, "\t", asteroid.name, "\telement: ",
                                element[1].ra*(180/math.pi), element[1].dec*(180/math.pi),
                                "\tprev element: ", previousElement[1].ra*(180/math.pi), previousElement[1].dec*(180/math.pi))

                        # Calculate the edgeDec which is the declination at which the line segment crosses the
                        # meridian.  We do this by simple linear interpolation.
                        deltaRA = (180/math.pi)*(lowRAElement[1].ra + (2*math.pi-highRAElement[1].ra))
                        deltaDec =  (180/math.pi)*(lowRAElement[1].dec - highRAElement[1].dec)
                        deltaRAToEdge = (180/math.pi)*((2*math.pi-highRAElement[1].ra))
                        edgeDec = highRAElement[1].dec*(180/math.pi) + deltaDec*(deltaRAToEdge/deltaRA)

                        geometryString += "," + str(firstEdgeRA) + " " + str(edgeDec)

                    # TODO: Consider adding a constraint that dimMag-brightMag must be less than some value to handle highly
                    # eccentric objects whose brightness might change rapidly as it moves radially inward.  It also
                    # would handle objects passing very close to the earth as well.  Not sure if this would make sense or not.
                    # The only code change required to implement this is adding an 'or' statement to the 'if' statement below.
                    angularDistance += (180/math.pi)*ephem.separation(previousElement[1], element[1])
                    if angularDistance > 60 or meridianCross:
                        geometryString += ')'

                        #TODO: When there is a meridian cross the start and end times of the two line segments are
                        # slightly different than what is recorded.  We can probably just ignore this but there may be
                        # some minor issues with doing so.
                        writeAstorbEphemerisToDB(asteroid, startingElement[0], element[0], dimMag, brightMag, geometryString)
                        startingElement = element
                        brightMag = startingElement[1].mag
                        dimMag = startingElement[1].mag
                        angularDistance = 0.0
                        resultsWritten = True

                        if meridianCross:
                            geometryString = 'LINESTRING(' + str(secondEdgeRA) + " " + str(edgeDec) + ","
                        else:
                            geometryString = 'LINESTRING('

                        geometryString += str(startingElement[1].ra*180/math.pi) + " " + str(startingElement[1].dec*180/math.pi)

                    previousElement = element

                if not resultsWritten:
                    geometryString += ")"
                    writeAstorbEphemerisToDB(asteroid, startingElement[0], element[0], dimMag, brightMag, geometryString)

            offset += pagesize
            print('Processed {} asteroids - {}% complete.'.format(offset, round(100*offset/numAsteroids,0)))
            sys.stdout.flush()

    return True



