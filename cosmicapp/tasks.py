from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django.db import transaction
from django.conf import settings
from django.db.models import Avg, StdDev

import subprocess
import json
import sys
import os
import re
import itertools
import math

from astropy import wcs
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.table import Table
from photutils import make_source_mask, DAOStarFinder, IRAFStarFinder

import ephem

from .models import *

staticDirectory = os.path.dirname(os.path.realpath(__file__)) + "/static/cosmicapp/"

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def storeImageLocation(image, w):
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

@shared_task
def imagestats(filename):
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

    proc.wait()

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

            storeImageLocation(image, w)

            ps = PlateSolution(
                image = image,
                wcsHeader = w.to_header_string(True),
                source = 'original'
                )

            ps.save()
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
                        frames.append(hdu.data[channelIndex+i])

                for frame in frames:
                    channelInfo = ImageChannelInfo.objects.get(image=image, index=channelIndex)
                    mean, median, stdDev = sigma_clipped_stats(frame, sigma=10, iters=0)

                    #mask = make_source_mask(frame, snr=10, npixels=5, dilate_size=11)
                    bgMean, bgMedian, bgStdDev = sigma_clipped_stats(frame, sigma=3, iters=1)

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

        #TODO: Change to 8 bit thumbnails instead of the default of 16 bit.
        #TODO: Small images will actually get thumbnails made which are bigger than the original, should implement
        # protection against this - will need to test all callers to make sure that is safe.
        #TODO: Play around with the 'convolve' kernel here to see what the best one to use is.
        # Consider bad horiz/vert lines, also bad pixels, and finally noise.
        # For bad lines use low/negative values along the middle row/col in the kernel.
        proc = subprocess.Popen(['convert', "-gamma", "0.8", "-convolve", "1,2,4,2,1,2,4,6,4,2,3,5,10,5,3,2,4,6,4,2,1,2,4,2,1",
                "-contrast-stretch", ".1%x.1%", "-strip", "-filter", "spline", "-resize",
                sizeArg, "-verbose", settings.MEDIA_ROOT + filename, staticDirectory + "images/" + tempFilename],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

        output, error = proc.communicate()
        output = output.decode('utf-8')
        error = error.decode('utf-8')

        proc.wait()

        print("generateThumbnails: " + tempFilename)
        sys.stdout.flush()

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
                    print('Thumbnail width: {}      height: {}'.format(w, h))

                    record = ImageThumbnail(
                        image = image,
                        width = w,
                        height = h,
                        size = sizeString,
                        channel = channel,
                        filename = outputFilename
                        )

                    record.save()

    return True

@shared_task
def sextractor(filename):
    # Get the image record
    image = Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = ImageChannelInfo.objects.filter(image=image).order_by('index')

    detectThreshold = 4.0*channelInfos[0].bgStdDev

    #TODO: sextractor can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
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

    print("sextractor: " + filename + "   " + output + "   " + error)
    sys.stdout.flush()

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

            records = SextractorResult.objects.filter(image=image)
            meanFluxAuto = records.aggregate(Avg('fluxAuto'))['fluxAuto__avg']

            #TODO: Switch to this commented out line when we convert to postgre-sql.
            #stdDevFluxAuto = records.aggregate(StdDev('fluxAuto'))
            stdDevFluxAuto = 0
            if len(records) >= 2:
                for record in records:
                    stdDevFluxAuto += math.pow(record.fluxAuto - meanFluxAuto, 2)
                stdDevFluxAuto /= len(records) - 1
                stdDevFluxAuto = math.sqrt(stdDevFluxAuto)
            else:
                stdDevFluxAuto = 1

            for record in records:
                record.confidence = sigmoid((record.fluxAuto-meanFluxAuto)/stdDevFluxAuto)
                record.save()

    try:
        os.remove(catfileName)
    except OSError:
        pass

    return True

@shared_task
def image2xy(filename):
    # Get the image record
    image = Image.objects.get(fileRecord__onDiskFileName=filename)

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

    print("image2xy: " + filename + "   " + output + "   " + error)
    sys.stdout.flush()

    table = Table.read(outputFilename, format='fits')

    with transaction.atomic():
        for row in table:
            if row['FLUX'] < 0.1:
                continue

            result = Image2xyResult(
                image = image,
                pixelX = row['X'],
                pixelY = row['Y'],
                pixelZ = None,
                flux = row['FLUX'],
                background = row['BACKGROUND']
                )

            result.save()

        records = Image2xyResult.objects.filter(image=image)
        meanFlux = records.aggregate(Avg('flux'))['flux__avg']

        #TODO: Switch to this commented out line when we convert to postgre-sql.
        #stdDevFlux = records.aggregate(StdDev('flux'))
        stdDevFlux = 0
        if len(records) >= 2:
            for record in records:
                stdDevFlux += math.pow(record.flux - meanFlux, 2)
            stdDevFlux /= len(records) - 1
            stdDevFlux = math.sqrt(stdDevFlux)
        else:
            stdDevFlux = 1

        for record in records:
            record.confidence = sigmoid((record.flux-meanFlux)/stdDevFlux)
            record.save()

    try:
        os.remove(outputFilename)
    except OSError:
        pass

    return True

@shared_task
def daofind(filename):
    print("daofind: " + filename)
    sys.stdout.flush()

    #TODO: daofind can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    image = Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = ImageChannelInfo.objects.filter(image=image).order_by('index')

    hdulist = fits.open(settings.MEDIA_ROOT + filename)
    data = hdulist[0].data
    daofind = DAOStarFinder(fwhm = 2.5, threshold = 4*channelInfos[0].bgStdDev)
    sources = daofind(data - channelInfos[0].bgMedian)

    with transaction.atomic():
        for source in sources:
            result = DaofindResult(
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

        records = DaofindResult.objects.filter(image=image)
        meanMag = records.aggregate(Avg('mag'))['mag__avg']

        #TODO: Switch to this commented out line when we convert to postgre-sql.
        #TODO: Also incorporate sharpness, sround, and ground into the calculation.
        #stdDevMag = records.aggregate(StdDev('mag'))
        stdDevMag = 0
        if len(records) >= 2:
            for record in records:
                stdDevMag += math.pow(record.mag - meanMag, 2)
            stdDevMag /= len(records) - 1
            stdDevMag = math.sqrt(stdDevMag)
        else:
            stdDevMag = 1

        for record in records:
            record.confidence = sigmoid((meanMag-record.mag)/stdDevMag)
            record.save()

    return True

@shared_task
def starfind(filename):
    print("starfind: " + filename)
    sys.stdout.flush()

    #TODO: starfind can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    image = Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = ImageChannelInfo.objects.filter(image=image).order_by('index')

    hdulist = fits.open(settings.MEDIA_ROOT + filename)
    data = hdulist[0].data
    starfinder = IRAFStarFinder(fwhm = 2.5, threshold = 4*channelInfos[0].bgStdDev)
    sources = starfinder(data - channelInfos[0].bgMedian)

    with transaction.atomic():
        for source in sources:
            result = StarfindResult(
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

        records = StarfindResult.objects.filter(image=image)
        meanMag = records.aggregate(Avg('mag'))['mag__avg']

        #TODO: Switch to this commented out line when we convert to postgre-sql.
        #TODO: Also incorporate sharpness, roundness, etc, into the calculation.
        #stdDevMag = records.aggregate(StdDev('mag'))
        stdDevMag = 0
        if len(records) >= 2:
            for record in records:
                stdDevMag += math.pow(record.mag - meanMag, 2)
            stdDevMag /= len(records) - 1
            stdDevMag = math.sqrt(stdDevMag)
        else:
            stdDevMag = 1

        for record in records:
            record.confidence = sigmoid((meanMag-record.mag)/stdDevMag)
            record.save()

    return True

@shared_task
def starmatch(filename):
    print("starmatch: " + filename)
    sys.stdout.flush()

    image = Image.objects.get(fileRecord__onDiskFileName=filename)

    #NOTE: It may be faster if these dictionary 'name' entries were shortened or changed to 'ints', maybe an enum.
    inputs = [
        { 'name': 'sextractor', 'model': SextractorResult },
        { 'name': 'image2xy', 'model': Image2xyResult },
        { 'name': 'daofind', 'model': DaofindResult },
        { 'name': 'starfind', 'model': StarfindResult }
        ]

    # Loop over all the pairs of source extraction methods listed in 'inputs'.
    matchedResults = []
    for i1, i2 in itertools.combinations(inputs, 2):
        results1 = i1['model'].objects.filter(image=image)
        results2 = i2['model'].objects.filter(image=image)

        print('Matching {} {} results with {} {} results'.format(len(results1), i1['name'], len(results2), i2['name']))

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

        print('   Found {} matches.'.format(len(matches)))
        matchedResults.append( (i1, i2, matches) )

    # Now that we have all the matches between every two individual methods, combine them into 'superMatches' where 3
    # or more different match types all agree on the same star.
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
    with transaction.atomic():
        for superMatch in superMatches:
            sextractorResult = superMatch.get('sextractor', None)
            image2xyResult = superMatch.get('image2xy', None)
            daofindResult = superMatch.get('daofind', None)
            starfindResult = superMatch.get('starfind', None)

            numMatches = 0
            confidence = 1
            x = 0
            y = 0
            z = 0
            for result in [sextractorResult, image2xyResult, daofindResult, starfindResult]:
                # TODO: Should add an else clause here to pull down the confidence if the given result
                # does not agree with the others.  Need to figure out how to weigh this disagreement.
                if result != None:
                    numMatches += 1
                    confidence *= result.confidence
                    x += result.pixelX
                    y += result.pixelY
                    z = result.pixelZ

            confidence = math.pow(confidence, 1/numMatches)
            x /= numMatches
            y /= numMatches

            record = SourceFindMatch(
                image = image,
                pixelX = x,
                pixelY = y,
                pixelZ = z,
                confidence = confidence,
                numMatches = numMatches,
                sextractorResult = sextractorResult,
                image2xyResult = image2xyResult,
                daofindResult = daofindResult,
                starfindResult = starfindResult
                )

            record.save()

    return True

@shared_task
def astrometryNet(filename):
    print("astrometrynet: " + filename)
    sys.stdout.flush()

    image = Image.objects.get(fileRecord__onDiskFileName=filename)
    superMatches = SourceFindMatch.objects.filter(image=image)

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
        print('ERROR: Could not open file for writing: ' + tableFilename)
        return False

    print("Chose {} objects to use in plate solution.".format(len(table)))
    print('\n', table)

    proc = subprocess.Popen(['solve-field', '--depth', '12,22,30',
            '--no-plots', '--overwrite', '--timestamp',
            '--x-column', 'XIMAGE', '--y-column', 'YIMAGE', '--sort-column', 'CONFIDENCE',
            '--width', str(image.dimX), '--height', str(image.dimY),
            '--cpulimit', '30',
            tableFilename
            ])

    proc.wait()

    solvedFilename = settings.MEDIA_ROOT + filename + '.sources.solved'
    if os.path.isfile(solvedFilename):
        print('\n\nPlate solved successfully.')
        w = wcs.WCS(settings.MEDIA_ROOT + filename + '.sources.wcs')

        storeImageLocation(image, w)

        ps = PlateSolution(
            image = image,
            wcsHeader = w.to_header_string(True),
            source = 'astrometryNet'
            )

        ps.save()
    else:
        print('\n\nNo plate solution found.')
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
            print('Error in removing file {}\nError was: {}'.format(f, sys.exc_info()[0]))

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

#TODO:  Need to figure out a way to schedule this task somehow.  Calling it manually works fine, but a more permanent solution needs to be found.
@shared_task
def computeAsteroidEphemerides(ephemTime):
    asteroids = AstorbRecord.objects.all()

    with transaction.atomic():
        #Clear all asteroid ephemerides.
        #TODO: Should we only clear old ones?  Maybe only ones where user=None?  Not really sure.
        AstorbEphemeris.objects.all().delete()

        for asteroid in asteroids:
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
            body.compute(ephemTime)

            ephemeris = AstorbEphemeris(
                astorbRecord = asteroid,
                dateTime = ephemTime,
                ra = body.ra * 180/math.pi,
                dec = body.dec * 180/math.pi,
                earthDist = body.earth_distance,
                sunDist = body.sun_distance,
                mag = body.mag,
                elong = body.elong * 180/math.pi
                )

            ephemeris.save()

    return True

