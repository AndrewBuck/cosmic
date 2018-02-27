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

    print(geometryString)

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

            headerField = models.ImageHeaderField(
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

            storeImageLocation(image, w, 'original')
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
                    try:
                        channelInfo = models.ImageChannelInfo.objects.get(image=image, index=channelIndex)
                    except:
                        continue

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

    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

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

                    record = models.ImageThumbnail(
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
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = models.ImageChannelInfo.objects.filter(image=image).order_by('index')

    detectThreshold = 4.0*channelInfos[0].bgStdDev

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

                    record = models.SextractorResult(
                        image = image,
                        pixelX = xPos,
                        pixelY = yPos,
                        pixelZ = zPos,
                        fluxAuto = fluxAuto,
                        fluxAutoErr = fluxAutoErr,
                        flags = flags
                        )

                    record.save()

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

    return True

@shared_task
def image2xy(filename):
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

    print("image2xy: " + filename + "   " + output + "   " + error)
    sys.stdout.flush()

    table = Table.read(outputFilename, format='fits')

    with transaction.atomic():
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

    return True

@shared_task
def daofind(filename):
    print("daofind: " + filename)
    sys.stdout.flush()

    #TODO: daofind can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = models.ImageChannelInfo.objects.filter(image=image).order_by('index')

    hdulist = fits.open(settings.MEDIA_ROOT + filename)
    data = hdulist[0].data
    daofind = DAOStarFinder(fwhm = 2.5, threshold = 4*channelInfos[0].bgStdDev)
    sources = daofind(data - channelInfos[0].bgMedian)

    with transaction.atomic():
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

    return True

@shared_task
def starfind(filename):
    print("starfind: " + filename)
    sys.stdout.flush()

    #TODO: starfind can only handle .fit files.  Should autoconvert the file to .fit if necessary before running.
    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #TODO: Handle multi-extension fits files.
    channelInfos = models.ImageChannelInfo.objects.filter(image=image).order_by('index')

    hdulist = fits.open(settings.MEDIA_ROOT + filename)
    data = hdulist[0].data
    starfinder = IRAFStarFinder(fwhm = 2.5, threshold = 4*channelInfos[0].bgStdDev)
    sources = starfinder(data - channelInfos[0].bgMedian)

    with transaction.atomic():
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

    return True

@shared_task
def starmatch(filename):
    print("starmatch: " + filename)
    sys.stdout.flush()

    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)

    #NOTE: It may be faster if these dictionary 'name' entries were shortened or changed to 'ints', maybe an enum.
    inputs = [
        { 'name': 'sextractor', 'model': models.SextractorResult },
        { 'name': 'image2xy', 'model': models.Image2xyResult },
        { 'name': 'daofind', 'model': models.DaofindResult },
        { 'name': 'starfind', 'model': models.StarfindResult }
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
    print('Calculating super matches:')
    sys.stdout.flush()
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
    print('Found {} super matches.  Writing them to the DB...'.format(len(superMatches)))
    sys.stdout.flush()
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
                starfindResult = starfindResult
                )

            record.save()

    print('Done.')
    sys.stdout.flush()
    return True

@shared_task
def astrometryNet(filename):
    print("astrometrynet: " + filename)
    sys.stdout.flush()

    image = models.Image.objects.get(fileRecord__onDiskFileName=filename)
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

        storeImageLocation(image, w, 'astrometry.net')
    else:
        print('\n\nNo plate solution found.')
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
            print('Error in removing file {}\nError was: {}'.format(f, sys.exc_info()[0]))

    return True

@shared_task
def parseHeaders(imageId):
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
                    print("ERROR: Could not parse dateObs: " + value)

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

            prop = models.ImageProperty(
                image = image,
                header = header,
                key = key,
                value = value
                )

            prop.save()

        # Handle data split across multiple header fields like dateObs and timeObs.
        dateObsResult = models.ImageProperty.objects.filter(image=image, key='dateObs').first()
        timeObsResult = models.ImageProperty.objects.filter(image=image, key='timeObs').first()
        if dateObsResult != None and timeObsResult != None:
            try:
                image.dateTime = dateparser.parse(dateObsResult.value + ' ' + timeObsResult.value)
                image.save()
            except ValueError:
                print("ERROR: Could not parse dateObs: " + value)

    return True

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



