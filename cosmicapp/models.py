import math
from datetime import date, datetime, timedelta, tzinfo
import pytz
import ephem
import numpy
from astropy import wcs
import markdown

from django.db import transaction
from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from .tasks import computeSingleEphemeris

#TODO:  Need to review the on_delete behaviour of all foreign keys to guarantee references remain intact as needed.

#TODO:  Set a related_name for all foreign keys and use that in the code where appropriate to make the code more readable.

#TODO:  Need to review the null constraint for all fields and try to minimize use of null=True, this is best done after the database is in a more stable state.

#TODO: Check all DateTime and similar type fields to see if they should be auto_now_add=True.

#TODO: Check all CharField fields to see if they should be TextFields instead.

#TODO: Check all TextField and CharField and remove null=True so you only have to check for empty string as null, not both empty string and null.

def storeImageLocation(image, w, sourceString):
    #TODO: should check w.lattyp and w.lontyp to make sure we are storing these world coordinates correctly.
    raCen, decCen = w.all_pix2world(image.dimX/2, image.dimY/2, 1)    #TODO: Determine if this 1 should be a 0.
    raScale, decScale = wcs.utils.proj_plane_pixel_scales(w)
    raScale *= 3600.0
    decScale *= 3600.0

    geometryString = 'POLYGON(('
    commaString = ''

    raDecArray = list(w.calc_footprint(axes=(image.dimX, image.dimY)))
    raDecArray.append([raDecArray[0][0], raDecArray[0][1]])
    for ra, dec in raDecArray:
        geometryString += commaString + str(ra) + ' ' + str(dec)
        commaString = ', '

    geometryString += '))'

    #TODO: Store image.centerRot
    ps = PlateSolution(
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

class CosmicVariable(models.Model):
    name = models.CharField(db_index=True, unique=True, max_length=64)
    variableType = models.CharField(max_length=32)
    value = models.TextField(null=True)

    @staticmethod
    def setVariable(name, variableType, value):
        variable = CosmicVariable.objects.filter(name=name).first()
        if variable == None:
            variable = CosmicVariable(
                name = name,
                variableType = variableType,
                value = value
                )
        else:
            variable.variableType = variableType
            variable.value = value

        variable.save()

    @staticmethod
    def getVariable(name):
        variable = CosmicVariable.objects.filter(name=name).first()
        if variable == None:
            return None

        if variable.variableType == 'int':
            return int(variable.value)
        elif variable.variableType == 'float':
            return float(variable.value)
        elif variable.variableType == 'string':
            return variable.value

        else:
            return None

class InstrumentComponent(models.Model):
    """
    An abstract base class holding common properties and functions for all hardware types.
    """
    make = models.CharField(db_index=True, max_length=64, null=True, blank=True)
    model = models.CharField(db_index=True, max_length=64, null=True, blank=True)

    comments = GenericRelation('TextBlob')

    def __str__(self):
        return type(self).__name__ + ": " + self.make + " - " + self.model

    class Meta:
        abstract = True

class ComponentInstance(models.Model):
    """
    A specific peice of equipment owned by a specific user.  A given ComponentInstance links to another
    ComponentInstance which it is physically attached to in a given instrument configuration.
    """
    #Generic FK to the InstrumentComponent that this component is attached to (or None if this component is a pier).
    #TODO: Add a reverse generic relation to the relevant classes this will link to (Camera, Mount, OTA, etc).
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    instrumentComponent = GenericForeignKey('content_type', 'object_id')

    user = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE)
    serialNumber = models.TextField(null=True)
    dateOnline = models.DateField(null=True, blank=True)
    dateOffline = models.DateField(null=True, blank=True)
    cost = models.FloatField(null=True, blank=True)
    askingPrice = models.FloatField(null=True, blank=True)

    comments = GenericRelation('TextBlob')

class InstrumentConfiguration(models.Model):
    """
    A database record to tie together all of the information about a particular
    configuration of specific pieces of hardware to form a description of the instrument
    used to acquire a particular image.
    """
    user = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE)
    name = models.TextField(null=True)

    comments = GenericRelation('TextBlob')

class InstrumentConfigurationLink(models.Model):
    """
    A database link representing the physical attachment of one component to another in a
    particular instrument configuration.  A given piece of physical hardware can only be
    used once in a single instrument configuration, but can be re-used in other ones (for
    example a user who owns one camera and two telescopes).
    """
    configuration = models.ForeignKey("InstrumentConfiguration", db_index=True, on_delete=models.CASCADE, related_name="configurationLinks")

    attachedFrom = models.ForeignKey("ComponentInstance", on_delete=models.CASCADE, related_name="attachedFromLinks")
    attachedTo = models.ForeignKey("ComponentInstance", null=True, on_delete=models.CASCADE, related_name="attachedToLinks")

class OTA(InstrumentComponent):
    """
    An Optical tube assembly that forms the core of the optical path of an instrument.
    """
    focalLength = models.FloatField(null=True, blank=True)
    aperture = models.FloatField(null=True, blank=True)
    design = models.CharField(max_length=64, null=True, blank=True)

    comments = GenericRelation('TextBlob')

class OTAPort(models.Model):
    """
    A port for a camera or eyepiece to be attached to an OTA.
    """
    ota = models.ForeignKey(OTA, on_delete=models.CASCADE)
    diameter = models.FloatField(null=True, blank=True)
    location = models.CharField(max_length=64, null=True, blank=True)
    extraOptics = models.CharField(max_length=64, null=True, blank=True)

    comments = GenericRelation('TextBlob')

class Eyepiece(models.Model):
    """
    An eyepiece to be inserted into a telescope for visual observations.
    """
    diameter = models.FloatField(null=True, blank=True)
    focalLength = models.FloatField(null=True, blank=True)
    apparentFOV = models.FloatField(null=True, blank=True)

    comments = GenericRelation('TextBlob')

class Camera(InstrumentComponent):
    """
    A camera to be inserted into a telescope for recording observations.
    """
    dimX = models.FloatField(null=True, blank=True)
    dimY = models.FloatField(null=True, blank=True)
    pixelDimX = models.FloatField(null=True, blank=True)
    pixelDimY = models.FloatField(null=True, blank=True)
    readNoise = models.FloatField(null=True, blank=True)
    ePerADU = models.FloatField(null=True, blank=True)
    exposureMin = models.FloatField(null=True, blank=True)
    exposureMax = models.FloatField(null=True, blank=True)
    coolingCapacity = models.FloatField(null=True, blank=True)

    comments = GenericRelation('TextBlob')

class Pier(InstrumentComponent):
    """
    The permanant pier or tripod, etc, that the telescope mount is connected to.  A pier
    should not connect to anything, since it is effectively connected to the ground at the
    observatory.
    """
    pierType = models.CharField(max_length=64, null=True, blank=True)
    maxPayload = models.FloatField(null=True, blank=True)

    comments = GenericRelation('TextBlob')

class Mount(InstrumentComponent):
    """
    The moving mount that a telescope OTA and all connected components ride on.
    """
    mountType = models.CharField(max_length=64, null=True, blank=True)
    maxWeight = models.FloatField(null=True, blank=True)
    autoguideCompatible = models.BooleanField(null=True)
    gotoCompatible = models.BooleanField(null=True)

    comments = GenericRelation('TextBlob')



#TODO: Add a class for an observing session storing details about equipment used, weather, seeing, goals, etc.


#TODO: Determine a list of questions to ask a user when they join the site that will
# narrow down very quickly what kind of user they are.  I.E. Do they observe from one
# location, or many, do they have lots of old data already that can be uploaded, do they
# only own one telescope, none, or many, etc.  Store these responses as fields in their profile.
class Profile(models.Model):
    """
    Extra user profile information not stored by the default Django User record.  The two 'reciever' functions below hook
    into updates to the User table and automatically create/update the Profile table as needed.  Care needs to be taken to
    make sure User updates are done through the standard Django methods to ensure that these receiver functions get called
    and the tables are kept in sync.  I.E. no raw sql queries to the User table, etc.
    """
    user = models.OneToOneField(User, db_index=True, on_delete=models.CASCADE)
    defaultObservatory = models.ForeignKey('Observatory', on_delete=models.CASCADE, null=True)
    defaultInstrument = models.ForeignKey('InstrumentConfiguration', on_delete=models.CASCADE, null=True)
    birthDate = models.DateField(null=True, blank=True)
    limitingMag = models.FloatField(null=True, blank=True)
    modPoints = models.PositiveIntegerField()
    commentScore = models.IntegerField()
    totalCost = models.FloatField(null=True)
    totalDonations = models.FloatField(null=True)

    def priorityModifier(self):
        balance = self.totalDonations - self.totalCost
        sign = math.copysign(1, balance)
        modifier = 1000 * sign * abs(balance)**0.5

        sign = math.copysign(1, self.commentScore)
        modifier += 10 * sign * self.commentScore**0.5

        return modifier

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance, limitingMag=12, modPoints=0, commentScore=0, totalCost=0, totalDonations=0)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

@receiver(post_save, sender='cosmicapp.PlateSolution')
def savePlateSolution(sender, instance, **kwargs):
    """
    When we save a plate solution it may have changed the best plate solution for the
    image.  If so, we need to re-compute the ra-dec for all objects detected in the image.
    """
    instance.image.addImageProperty('numPlateSolutions', instance.image.plateSolutions.all().count(), True)

    sourceFindMatchResults = [
        instance.image.sextractorResults.all(),
        instance.image.image2xyResults.all(),
        instance.image.daofindResults.all(),
        instance.image.starfindResults.all(),
        instance.image.userSubmittedResults.all(),
        instance.image.sourceFindMatchResults.all(),
        ]

    xCoords = []
    yCoords = []
    with transaction.atomic():
        for results in sourceFindMatchResults:
            for result in results:
                xCoords.append(result.pixelX)
                yCoords.append(result.pixelY)

            if len(xCoords) > 0:
                raArray, decArray = instance.getRaDec(xCoords, yCoords)

                for result, ra, dec in zip(results, raArray, decArray):
                    result.ra = ra
                    result.dec = dec

                    result.save()

    # If it is possible, compute the airmass and store it in the PlateSolution record.
    if instance.image.dateTime is not None and instance.image.observatory is not None:
        body = ephem.FixedBody()
        body._ra = (math.pi/180.0)*instance.centerRA
        body._dec = (math.pi/180.0)*instance.centerDec
        body._epoch = '2000'  #TODO: Determine if this should be different.

        observer = ephem.Observer()
        observer.lat = instance.image.observatory.lat*(math.pi/180)
        observer.lon = instance.image.observatory.lon*(math.pi/180)
        observer.elevation = instance.image.observatory.elevation
        observer.date = instance.image.dateTime

        body.compute(observer)
        print(1.0*body.alt)
        #TODO: Use a better formula or library to determine the airmass.  This only works down to about 30 degrees above the horizon.
        #TODO: Correct airmass for observer's elevation and atmospheric pressure (from weather database?)
        airmass = 1.0/math.cos(math.pi/2.0-1.0*body.alt)
        PlateSolution.objects.filter(pk=instance.pk).update(airmass=airmass)

#TODO: Add a check when a user adds a bookmark to see if they should be shown a tutorial popup assosciated with the newly added bookmark.
class Bookmark(models.Model):
    """
    A class storing a GenericForeignKey relation to an object to act as a bookmark.
    """
    user = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE)
    folders = models.ManyToManyField('BookmarkFolder', symmetrical=False, related_name='folderItems', through='BookmarkFolderLink')

    #Generic FK to image or object or whatever the bookmark is linking to.
    content_type = models.ForeignKey(ContentType, db_index=True, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    @property
    def getObjectTypeString(self):
        stringDict = {
            'image': 'image',
            'astorbrecord': 'asteroid',
            'exoplanetrecord': 'exoplanet',
            'gcvsrecord': 'variableStar',
            'messierrecord': 'messierObject',
            'twomassxscrecord': '2MassXSC',
            'sextractorresult': 'sextractorResult',
            'image2xyresult': 'image2xyResult',
            'daofindresult': 'daofindResult',
            'starfindresult': 'starfindResult',
            'sourcefindmatch': 'sourceFindMatch',
            'usersubmittedresult': 'userSubmittedResult',
            'usersubmittedhotpixel': 'userSubmittedHotPixel',
            'ucac4record': 'ucac4record'
            }

        #TODO: Rework these queries to use _id instead of .pk and do this everywhere.
        t = ContentType.objects.get(pk=self.content_type.pk)

        return stringDict[t.model]

    @property
    def getObjectTypeCommonName(self):
        stringDict = {
            'image': 'Image',
            'astorbrecord': 'Asteroid',
            'exoplanetrecord': 'Exoplanet',
            'gcvsrecord': 'Variable Star',
            'messierrecord': 'Messier Object',
            'twomassxscrecord': 'Deep Sky Object',
            'sextractorresult': 'Sextractor Result',
            'image2xyresult': 'Image2XY Result',
            'daofindresult': 'Daofind Result',
            'starfindresult': 'Starfind Result',
            'sourcefindmatch': 'Multiple Source Match Result',
            'usersubmittedresult': 'User Submitted Source',
            'usersubmittedhotpixel': 'User Submitted Hot Pixel',
            'ucac4record': 'UCAC4 Star'
            }

        t = ContentType.objects.get(pk=self.content_type.pk)

        return stringDict[t.model]

class BookmarkFolder(models.Model):
    user = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=256, null=True)
    dateTime = models.DateTimeField(auto_now_add=True)

    comments = GenericRelation('TextBlob')

    def getItemsInFolder(user, folderName):
        items = []
        links = BookmarkFolderLink.objects.filter(folder__user=user, folder__name=folderName).prefetch_related('bookmark')
        for link in links:
            item = link.bookmark.content_object
            items.append(item)

        return items

class BookmarkFolderLink(models.Model):
    bookmark = models.ForeignKey(Bookmark, db_index=True, on_delete=models.CASCADE)
    folder = models.ForeignKey(BookmarkFolder, db_index=True, on_delete=models.CASCADE)
    dateTime = models.DateTimeField(auto_now_add=True)

class BookmarkableItem:
    """
    A base class that any models defined from on this page should also inherit from (in addition to models.Model).
    This contains common base functionality required for displaying lists of bookmarks when the items in the list are
    of differing types.  I.E. it normalizes the display so that differing types can be displayed in a common format.
    """
    def getBookmarkTypeString(self):
        """
        --> Should be reimplemented by child classes. <--
        Returns a string which is used in the bookmark javascript code to send to the
        server indicating the type of object to be bookmarked.
        """
        return None

    def getUrl(self):
        """
        --> Should be reimplemented by child classes. <--
        Returns the url of the main info page about this object.
        """
        return None

    @property
    def getDisplayName(self):
        """
        --> Should be reimplemented by child classes. <--
        Returns the name for this object which should be shown to users.  The name can be
        any string and can follow whatever convention would be appropriate to the object type.
        """
        return "getDisplayName uniplemented"

class SkyObject:
    """
    A base class to inherit from for any object that has a presense in the sky that can be derived at a given time.
    This could be a fixed object like a star, or could be a moving object like a planet or asteroid, or something like
    an image with known sky coordinates.
    """
    def isMobile(self):
        """
        Returns 0 if the object always reports exactly the same position.

        Returns 1 if the object gives a different position as a function of time due to
        small effects like parralax, etc.

        Returns 2 if the object gives a very different position as a function of time due
        major things like it being in the solar system, etc.
        """
        return 0

    def getSkyCoords(self, dateTime=datetime.now()):
        return (None, None)

    def getMag(self, dateTime=datetime.now()):
        """
        --> Should be reimplemented by child classes. <--
        """
        return None

    #TODO: Alt text as third item returned for each?
    # Returns an array of tuples, the first being the URL to link to and the second being the text to display in the link.
    @property
    def getLinks(self):
        return []

class Observatory(models.Model):
    """
    A record storing the location and other basic information for an observing location.
    """
    user = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=256, null=True)
    lat = models.FloatField(db_index=True)
    lon = models.FloatField(db_index=True)
    elevation = models.FloatField(null=True, blank=True)

    comments = GenericRelation('TextBlob')


class UploadSession(models.Model):
    uploadingUser = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE, related_name='uploadSessions')
    dateTime = models.DateTimeField(auto_now_add=True)

    comments = GenericRelation('TextBlob')

class UploadedFileRecord(models.Model):
    """
    A record storing information about any type of file uploaded by a user to the site.  The original file name, size,
    hash, etc are stored here as well as onDiskFileName which is the name django assigns to our copy of the file (to handle
    multiple uploads of the same file, etc).
    """
    uploadSession = models.ForeignKey(UploadSession, db_index=True, null=True, on_delete=models.CASCADE, related_name='uploadedFileRecords')
    user = models.ForeignKey(User, db_index=True, null=True, on_delete=models.CASCADE, related_name='uploadedFileRecords')
    createdByProcess = models.ForeignKey('ProcessInput', db_index=True, null=True, on_delete=models.CASCADE, related_name='uploadedFileRecords')
    unpackedFromFile = models.ForeignKey('self', null=True, on_delete=models.CASCADE)
    originalFileName = models.CharField(db_index=True, max_length=256)
    onDiskFileName = models.CharField(db_index=True, max_length=256)
    fileSha256 = models.CharField(db_index=True, max_length=64)
    uploadDateTime = models.DateTimeField(auto_now_add=True)
    uploadSize = models.IntegerField()

class DownloadSession(models.Model):
    user = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE, related_name='downloadSessions')
    dateTime = models.DateTimeField(auto_now_add=True)
    stillActive = models.BooleanField(default=True)
    outputText = models.TextField(null=True)
    postData = models.TextField(null=True)

class DownloadFileRecord(models.Model):
    #TODO: Add file size, etc.
    downloadSession = models.ForeignKey(DownloadSession, db_index=True, on_delete=models.CASCADE, related_name='fileRecords')
    fileName = models.TextField(db_index=True)
    url = models.TextField(db_index=True)

#TODO: Make Question a ScorableObject (in the sense of "how useful is it to show this uploaded image to a user").
class Image(models.Model, SkyObject, BookmarkableItem):
    """
    A record storing details about an image on the site.  For images uploaded as a file directly, the fileRecord is a key
    to the UploadedFileRecord assosciated with that upload, for files generated by the site itself (like calibrated, or
    stacked images) this key will be null.  The dimX and dimY dimensions are assumed to be the same for all layers in the image
    and dimZ is the number of layers in the image (color channels, or planes in a data cube).  Similarly, the plate
    solution is assumed to be the same as well, again this may cause issues for complicated multi extension fits files.

    This cannot properly account for complicated multi extension fits files which have multiple data cubes in them.
    Currently we cannot claim to handle files like this in any reasonable fashion, other than simply warehousing the file
    and parsing the first HDU in the file.
    """
    fileRecord = models.ForeignKey(UploadedFileRecord, db_index=True, on_delete=models.PROTECT, null=True, related_name='image')
    parentImages = models.ManyToManyField('self', symmetrical=False, related_name='childImages')
    instrument = models.ForeignKey(InstrumentConfiguration, on_delete=models.PROTECT, null=True)
    observatory = models.ForeignKey(Observatory, on_delete=models.PROTECT, null=True)
    dimX = models.IntegerField(null=True)
    dimY = models.IntegerField(null=True)
    dimZ = models.IntegerField(null=True)
    bitDepth = models.IntegerField(null=True)
    frameType = models.CharField(max_length=32)
    dateTime = models.DateTimeField(db_index=True, null=True)

    answers = GenericRelation('Answer')
    comments = GenericRelation('TextBlob')
    bookmarks = GenericRelation('Bookmark')

    @property
    def getDisplayName(self):
        return "Image {}".format(self.pk)

    def getSkyCoords(self, dateTime=datetime.now()):
        ps = self.getBestPlateSolution()
        if ps is None:
            return (None, None)
        return (ps.centerRA, ps.centerDec)

    def getBookmarkTypeString(self):
        return 'image'

    def getUrl(self):
        return "/image/" + str(self.pk)

    #TODO: Include image channel in the thumbnail selection.  Make this a pipe char separated list to allow multiple
    # channels to be returned at once to save on requests.
    def getThumbnailUrl(self, sizeString, hintWidth=-1, hintHeight=-1, stretch='false'):
        """
        Returns the URL (relative to the website root) of a thumbnail for an image on the site.  If called with just a size
        string only, that size thumbnail will be returned directly.  If hintWidth or hintHeight are given then the
        thumbnail returned will be the smallest one which is larger than both the hintWidth and hintHeight.  If the
        'stretch' parameter is set to true, the behaviour will be nearly the same with the thumbnails being checked in
        increasing size, but the one returned will be the last one before the size hints are exceeded.  I.E. the largest
        thumbnail that is smaller than the requested size hints (suitable to be stretched to fit the space or to leave
        empty space around if desired).

        If you only care about the hint in one dimension but not the other, set the hint for the dimension you don't care
        about to 0, so that any image which matches the criteria for the hint you do care about will also match the ignored
        dimension.  Leaving either hint at -1 will cause the hint checking code to be skipped and just return the
        sizeString sized thumbnail directly.
        """
        #TODO: Specify an image with something like "thumbnail not found" to display in place of this thumbnail.
        thumbnailNotFound = ""

        # Select a list of all the thumbnails for this image and return the error image if no thumbnails have been generated yet.
        try:
            records = ImageThumbnail.objects.filter(image__pk=self.pk).order_by('width')
        except:
            return thumbnailNotFound

        if len(records) == 0:
            return thumbnailNotFound

        # If size hints are provided then loop over the thumbnails in increasing size until we find one bigger than
        # both size hints.
        if hintWidth != -1 and hintHeight != -1:
            for i in range(len(records)):
                if records[i].size == sizeString:
                    record = records[i]
                    break

                # Check if the current size is bigger than the requested size.
                if records[i].width >= hintWidth and records[i].height >= hintHeight:
                    # If the thumbnail will be stretched we return the last one before the size limit was exceeded,
                    # otherwise we return this one so it can be scaled down to preserve image quality.
                    if stretch == 'true' and i > 0:
                        record = records[i-1]
                    else:
                        record = records[i]
                    break;
            else:
                record = records[len(records)-1]
        # If size hints were not provided, then just find the thumbnail with the requested sizeString and return that.
        else:
            for i in range(len(records)):
                if records[i].size == sizeString:
                    record = records[i]
                    break
            else:
                return thumbnailNotFound

        # At this point 'record' contains the desired size thumbnail, so just return the full path to it.
        #TODO: Also return width, height, etc, in a proper XML response.  Will need to adapt the recivers of this call though.
        return '/static/images/' + record.filename

    #DEPRECATED: Should remove, need to fix callers first.
    def getThumbnail(self, sizeString):
        url = self.getThumbnailUrl(sizeString)
        return '<a href=/image/' + str(self.pk) + '><img src="' + url + '"></a>'

    def getThumbnailUrlFull(self):
        return self.getThumbnailUrl("full")

    def getThumbnailUrlSmall(self):
        return self.getThumbnailUrl("small")

    def getThumbnailUrlMedium(self):
        return self.getThumbnailUrl("medium")

    def getThumbnailUrlLarge(self):
        return self.getThumbnailUrl("large")

    #DEPRECATED: Should remove, need to fix callers first.
    def getThumbnailFull(self):
        return self.getThumbnail("full")

    #DEPRECATED: Should remove, need to fix callers first.
    def getThumbnailSmall(self):
        return self.getThumbnail("small")

    #DEPRECATED: Should remove, need to fix callers first.
    def getThumbnailMedium(self):
        return self.getThumbnail("medium")

    #DEPRECATED: Should remove, need to fix callers first.
    def getThumbnailLarge(self):
        return self.getThumbnail("large")

    def getBestPlateSolution(self):
        #TODO: Add code to make a more informed choice about which plate solution to use if there is more than 1.
        return self.plateSolutions.all().order_by('-createdDateTime').first()

    def getBestRaDec(self):
        ps = self.getBestPlateSolution()
        if ps is not None:
            return (ps.centerRA, ps.centerDec)
        else:
            #TODO: Make this check the image properties, etc.
            return (None, None)

    def addImageProperty(self, key, value, overwriteValue=True, header=None):
        createNew = False

        if overwriteValue:
            try:
                imageProperty = ImageProperty.objects.get(image=self, key=key)
                imageProperty.value = value
                imageProperty.header = header
            except:
                createNew = True

        else:
            createNew = True

        if createNew:
            imageProperty = ImageProperty(
                image = self,
                header = header,
                key = key,
                value = value
                )

        imageProperty.save()

    def getImageProperty(self, key, default=None, asList=False):
        imageProperty = ImageProperty.objects.filter(image=self, key=key).order_by('-createDateTime')
        if not asList:
            imageProperty = imageProperty.first()
            if imageProperty == None:
                return default

            return imageProperty.value
        else:
            return imageProperty

    def removeImageProperty(self, key):
        imageProperty = ImageProperty.objects.filter(image=self, key=key).delete()

    def getExposureTime(self):
        return self.getImageProperty('exposureTime')

class ImageThumbnail(models.Model):
    """
    A record containing details about an individual thumbnail for an image on the site.  Each uploaded image gets multiple
    size thumbnails made of it, each with its own ImageThumbnail record.
    """
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name='thumbnails')
    size = models.CharField(max_length=10)
    width = models.IntegerField()
    height = models.IntegerField()
    channel = models.IntegerField()
    filename = models.CharField(max_length=256)

class ImageHeaderField(models.Model):
    """
    A record storing a single header key value pair from an image on the site.  These KV pairs could be EXIF data entries,
    PNG metadata info, or most commonly FITS header entries.  No attempt by the system is made to sanitize or uniformize
    these ImageHeaderField records in any way, instead they are read in exactly as they are in the file in order to
    preserve as much information as possible about the setup of the user who created them (software versions, camera
    oddities, etc).

    For most uses on the site (queries, sorting, etc) you should not use these records directly, but should instead use
    ImageProperty records, which are sanitized versions of these headers.  Each image property record links back to the
    ImageHeaderField it was derived from in case you need the exact data after you query.

    The 'index' field of the record stores a running number counting up from 0 in the order the header fields were read in.
    The idea here is that we may be able to identify particular software packages by the order in which the header fields
    are stored in the file.  This is also used to sort header fields when they are displayed since some header keys
    (like 'comment' for example) are often long enough to require splitting over multiple lines and thus the order
    should be preserved when displayed.

    #TODO:  Some checking needs to be done on the index field.  I am storing them in the order that image magic spits them
    out, however the order it gives (at least for fits files) differs from other tools to list headers.  So this index
    number may not be trustworthy without changing to a different tool for the actual reading of the headers.
    """
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE)
    index = models.IntegerField(null=True)
    key = models.TextField(db_index=True)
    value = models.TextField()

    comments = GenericRelation('TextBlob')

class ImageHeaderFieldCommonEnding(models.Model):
    key = models.TextField(db_index=True)
    ending = models.TextField()

    comments = GenericRelation('TextBlob')

class ImageProperty(models.Model):
    """
    A record storing sanitized and normalized image metadata key value pairs.  Most of these records will be derived from
    one or possibly several ImageHeaderField records and the 'header' field will link back to the source field.  For some,
    it may be the case that there is no source header field in which case this field will be null (for example in the case
    of metadata added by the site itself or by a user on the site for information that was not present in the uploaded
    file, e.g. frame type, seeing conditions, etc).
    """
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name='properties')
    header = models.ForeignKey(ImageHeaderField, db_index=True, on_delete=models.CASCADE, null=True, related_name='properties')  #TODO: Make this many to many?
    key = models.TextField(db_index=True)
    value = models.TextField()
    createDateTime = models.DateTimeField(auto_now_add=True)

    comments = GenericRelation('TextBlob')

class ImageChannelInfo(models.Model):
    """
    A record representing the statistical measurements of a single channel of an image.  The channelType field represents
    what color channel the image represents (if it was taken from a color image with known red-green-blue channels, or will
    be grey for most other channels where the colorspace is not known.  Additionally we store the standard statistics
    (mean, median, and standard deviation) of the channel as well as the same statistics for just the background (i.e.
    after source removal by sigma clipping or other methods).
    """
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name="imageChannels")
    index = models.IntegerField()
    hduIndex = models.IntegerField(null=True)
    frameIndex = models.IntegerField(null=True)
    channelType = models.CharField(max_length=16)
    mean = models.FloatField(null=True)
    median = models.FloatField(null=True)
    stdDev = models.FloatField(null=True)
    bgMean = models.FloatField(null=True)
    bgMedian = models.FloatField(null=True)
    bgStdDev = models.FloatField(null=True)
    pixelNumber = models.IntegerField(null=True)
    minValue = models.FloatField(null=True)
    maxValue = models.FloatField(null=True)
    uniqueValues = models.IntegerField(null=True)
    approximateBits = models.FloatField(null=True)
    bathtubLimit = models.FloatField(null=True)
    bathtubValueNumber = models.IntegerField(null=True)
    bathtubPixelNumber = models.IntegerField(null=True)
    bathtubLow = models.FloatField(null=True)
    bathtubHigh = models.FloatField(null=True)
    thumbnailBlackPoint = models.FloatField(null=True)
    thumbnailWhitePoint = models.FloatField(null=True)
    thumbnailGamma = models.FloatField(null=True)
    maskedValues = models.IntegerField(null=True)
    maskedPixels = models.IntegerField(null=True)

    def getHistogramUrl(self):
        return '/static/images/histogramData_{}_{}.gnuplot.svg'.format(self.image.pk, self.index)

    def getRowMeanUrl(self):
        return '/static/images/rowMeanData_{}_{}.gnuplot.svg'.format(self.image.pk, self.index)

    def getColMeanUrl(self):
        return '/static/images/colMeanData_{}_{}.gnuplot.svg'.format(self.image.pk, self.index)

class ImageHistogramBin(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    binCenter = models.FloatField()
    binCount = models.FloatField()

class ImageSliceMean(models.Model):
    channelInfo = models.ForeignKey(ImageChannelInfo, on_delete=models.CASCADE)
    direction = models.CharField(max_length=1)
    index = models.IntegerField()
    mean = models.FloatField()

class ImageTransform(models.Model):
    """
    A record for storing an image transform generated by the Image Mosaic Tool.  The storage format in the database is
    basically just a direct copy of the transform matrix used internally in the tool.  The elements stored are the first
    two rows in a 3x3 transform matrix (i.e. 6 of the 9 elements are stored with the last row being fixed at 0 0 1 and
    therefore not needing to be stored).  The referenceImage is the image in the starting coordinate system, and then if
    you multiply its transform matrix by the stored matrix you get the coordinate system for the subjectImage.  The user
    field is the user who created the transform in the mosaic tool, allowing multiple users to store their own transforms
    in case not every one agrees on the proper shift to be applied.
    """
    user = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE)
    referenceImage = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name='transformReferences')
    subjectImage = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name='transformSubjects')
    m00 = models.FloatField()
    m01 = models.FloatField()
    m02 = models.FloatField()
    m10 = models.FloatField()
    m11 = models.FloatField()
    m12 = models.FloatField()

    def matrix(self):
        return numpy.matrix([
            [self.m11, self.m10, self.m12],
            [self.m01, self.m00, -self.m02],
            [0, 0, 1]
            ])

class AudioNote(models.Model):
    fileRecord = models.ForeignKey(UploadedFileRecord, on_delete=models.PROTECT, null=True, related_name='audioNote')
    observatory = models.ForeignKey(Observatory, db_index=True, on_delete=models.PROTECT, null=True)
    instrument = models.ForeignKey(InstrumentConfiguration, db_index=True, on_delete=models.PROTECT, null=True)
    dateTime = models.DateTimeField(auto_now_add=True, db_index=True, null=True)
    length = models.FloatField(null=True)
    transcriptions = models.ManyToManyField('TextBlob', symmetrical=False, related_name='audioNotes', through='AudioNoteTranscriptionLink')
    objectName = models.TextField()
    objectRA = models.FloatField(null=True)
    objectDec = models.FloatField(null=True)
    #TODO: Add flags for inaudible audio notes, etc.

class AudioNoteTranscriptionLink(models.Model):
    dateTime = models.DateTimeField(auto_now_add=True, db_index=True, null=True)
    user = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE)
    audioNote = models.ForeignKey('AudioNote', db_index=True, on_delete=models.CASCADE)
    transcription = models.ForeignKey('TextBlob', db_index=True, on_delete=models.CASCADE)

class PlateSolution(models.Model):
    """
    A record for storing the WCS plate solution of an image to be stored in the database.  The WCS is stored as a text blob
    in the format output by astropy using the to_header_string() function which writes the WCS as if it were header fields
    for a fits file.  We store these WCS headers in the database so that we can easily store, query, and manage multiple
    WCS solutions for each image.  Many images will be uploaded with an existing WCS and whether or not
    they are accurate we want to store them along side the ones we compute ourselves so that we can offer downloads of the
    file with any or all of them included upon user request.  The source field is for storing a simple text string denoting
    where we got the specific WCS from, i.e. was it from the original image, or computed by our astrometry.net plate
    solver, or by some other method like mosaic approximation, etc.
    """
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name='plateSolutions')
    wcsHeader = models.TextField()
    source = models.CharField(max_length=32)
    centerRA = models.FloatField(null=True)
    centerDec = models.FloatField(null=True)
    centerRot = models.FloatField(null=True)
    resolutionX = models.FloatField(null=True)
    resolutionY = models.FloatField(null=True)
    airmass = models.FloatField(null=True)
    geometry = models.PolygonField(srid=40000, db_index=True, geography=False, dim=2, null=True)
    area = models.FloatField(null=True)
    createdDateTime = models.DateTimeField(auto_now_add=True, db_index=True, null=True)

    comments = GenericRelation('TextBlob')

    def wcs(self):
        return wcs.WCS(self.wcsHeader)

    def getRaDec(self, x, y):
        if(type(x) == list):
            if len(x) == 0:
                return (None, None)

            ret = self.wcs().all_pix2world(x, y, 1, ra_dec_order=True)    #TODO: Determine if this 1 should be a 0.
            return ret
        else:
            ret = self.wcs().all_pix2world(x, y, 1, ra_dec_order=True)    #TODO: Determine if this 1 should be a 0.
            return (numpy.asscalar(ret[0]), numpy.asscalar(ret[1]))

class ProcessPriority(models.Model):
    """
    A record storing a priority level for a particular task type.  Having default
    priorities in a table makes it easy to compare and set them as well as to easily
    display them on a page so users can see what the numbers mean.
    """
    name = models.CharField(db_index=True, max_length=64)
    priorityClass = models.CharField(db_index=True, max_length=64)
    priority = models.FloatField(null=True)
    setDateTime = models.DateTimeField(auto_now_add=True, null=True)

    @staticmethod
    def getPriorityForProcess(processName, processClass='batch', user=None):
        try:
            priority = ProcessPriority.objects.get(name=processName, priorityClass=processClass)
        except:
            return 1

        if user is not None:
            return max(10, priority.priority + user.profile.priorityModifier())
        else:
            return priority.priority

class ProcessInput(models.Model):
    """
    A record storing parameters for a queued process to be run at a later time by the website.  The 'process' field is a
    string naming the process to be executed, these strings are used by the dispatcher to know which function to dispatch
    to a celery worker and how to interpret the provided arguments.  The process may have one or more 'prerequisites' which
    are required to be run before it and all of which are required to return a success result before the given process is
    allowed to be dispatched.  We also store the user id of the person who requested the process be run and the time it was
    submitted and dispatched.  The user id will be null for jobs submitted by the site itself like maintenence tasks, etc.

    The remaining fields list the priority of the job as an unsigned integer (higher numbers executed first) as well as
    estimates of the resource usage required to complete the task.  The resource estimates can be used by the dispatcher to
    assign IO heavy tasks to certain workers, CPU heavy ones to others, etc.  These estimates are only expected to be
    'order of magnitude' estimates, only for task segregation, not for estimating exact runtimes beyond very rough
    estimates (again order of magnitude).

    #TODO: Document how negative priorities will be handled by the dispatcher, i.e. how do we want to use this.
    """
    prerequisites = models.ManyToManyField('self', db_index=True, symmetrical=False)
    process = models.CharField(max_length=32)
    requestor = models.ForeignKey(User, db_index=True, null=True, on_delete=models.CASCADE)
    submittedDateTime = models.DateTimeField(auto_now_add=True)
    startedDateTime = models.DateTimeField(null=True)
    priority = models.FloatField(null=True)
    estCostCPU = models.FloatField(null=True)
    estCostBandwidth = models.BigIntegerField(null=True)
    estCostStorage = models.BigIntegerField(null=True)
    estCostIO = models.BigIntegerField(null=True)
    completed = models.TextField(db_index=True, null=True, default=None)
    #NOTE: We may want to add a field or an auto computed field for whether the process can be run now or not.  I.E.
    # whether it has any unmet prerequisites.

    images = models.ManyToManyField('Image', symmetrical=False, related_name='processInputs')

    class Meta:
        ordering = ['-priority', 'submittedDateTime']

    def addArguments(self, argList):
        index = 1
        for arg in argList:
            pa = ProcessArgument(
                processInput = self,
                argIndex = index,
                arg = str(arg)
                )

            pa.save()
            index += 1

class ProcessOutput(models.Model):
    processInput = models.ForeignKey(ProcessInput, db_index=True, on_delete=models.CASCADE, related_name='processOutput')
    finishedDateTime = models.DateTimeField(auto_now_add=True, null=True)
    actualCostCPU = models.FloatField(null=True)
    actualCostBandwidth = models.FloatField(null=True)
    actualCostStorage = models.FloatField(null=True)
    actualCostIO = models.FloatField(null=True)
    actualCost = models.FloatField(null=True)
    outputText = models.TextField(null=True)
    outputErrorText = models.TextField(null=True)
    outputDBLogText = models.TextField(null=True)

class ProcessArgument(models.Model):
    """
    A record storing a single argument to be passed to a task to fulfill a queued job (represented by a ProcessInput).  The
    argument is a simple string, and the argIndex is an integer which is the position of this particular argument in the
    arguments list for the job.  The index can be anything you want it to be as long as the handler in the dispatcher
    routine knows where to look for it.  So for example, you could have arguments 1 and 3 provided but nothing for argument
    2, allowing the use of positional parameters which act more like named parameters.  I.E. a particular positional index
    always contains one specific argument for the task.
    """
    processInput = models.ForeignKey(ProcessInput, db_index=True, on_delete=models.CASCADE, related_name='arguments')
    argIndex = models.IntegerField()
    arg = models.CharField(max_length=256)

    class Meta:
        ordering = ['argIndex']

#TODO: This class can probably be deleted.  Currently processes which create files create UploadedFileRecord entries, which should just be renamed to FileRecord.
class ProcessOutputFile(models.Model):
    processInput = models.ForeignKey(ProcessInput, db_index=True, on_delete=models.CASCADE)
    onDiskFileName = models.CharField(max_length=256)
    fileSha256 = models.CharField(max_length=64)
    size = models.IntegerField()





class SourceFindResult(models.Model, SkyObject):
    """
    An abstract base class containing the fields common to all source finding methods, such as position and confidence.
    Records of this type cannot be created directly and there is no actual table for this type in the database.  Rather one
    of the child classes derived from this is actually created and stored in the corresponding table.  Having this base
    class avoids duplicating code for the common fields in each derived child record type, but it also allows code
    manipulating those results to have a guarantee that certain fields are present on any of the found sources, no matter
    the algorithm used to detect them.
    """
    pixelX = models.FloatField(null=True)
    pixelY = models.FloatField(null=True)
    pixelZ = models.FloatField(null=True)
    #TODO: Instead of storing ra/dec here, store a link to each newly created plateSolution from all the objects detected in that image with the ra/dec stored as a property on an intermediate link.
    ra = models.FloatField(null=True)
    dec = models.FloatField(null=True)
    #TODO: Add a geometry point field for (ra, dec)?
    confidence = models.FloatField(null=True)
    flagHotPixel = models.BooleanField(null=True)
    flagBadLine = models.BooleanField(null=True)
    flagBadColumn = models.BooleanField(null=True)
    flagEdge = models.BooleanField(null=True)

    comments = GenericRelation('TextBlob')

    def isMobile(self):
        return 0

    def getSkyCoords(self, dateTime=datetime.now()):
        return (self.ra, self.dec)

    #TODO: Implement getMag() in all the child classes.

    class Meta:
        abstract = True

class SextractorResult(SourceFindResult, BookmarkableItem):
    """
    A record storing a single source detected in an image by the Source Extractor program.
    """
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name="sextractorResults")
    #TODO: Add in a bunch more fields here.
    fluxAuto = models.FloatField(null=True)
    fluxAutoErr = models.FloatField(null=True)
    fwhm = models.FloatField(null=True)
    ellipticity = models.FloatField(null=True)
    flags = models.IntegerField(null=True)
    boxXMin = models.FloatField(null=True)
    boxYMin = models.FloatField(null=True)
    boxXMax = models.FloatField(null=True)
    boxYMax = models.FloatField(null=True)

    bookmarks = GenericRelation('Bookmark')

    def getBookmarkTypeString(self):
        return 'sextractorResult'

    def getUrl(self):
        return '/detectedSource/sextractor/' + str(self.pk)

    @property
    def getDisplayName(self):
        return "Image " + str(self.image.pk) + ": Sextractor Result " + str(self.pk)

class Image2xyResult(SourceFindResult, BookmarkableItem):
    """
    A record storing a single source detected in an image by the image2xy program.
    """
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name="image2xyResults")
    flux = models.FloatField(null=True)
    background = models.FloatField(null=True)

    bookmarks = GenericRelation('Bookmark')

    def getBookmarkTypeString(self):
        return 'image2xyResult'

    def getUrl(self):
        return '/detectedSource/image2xy/' + str(self.pk)

    @property
    def getDisplayName(self):
        return "Image " + str(self.image.pk) + ": Image2XY Result " + str(self.pk)

class DaofindResult(SourceFindResult, BookmarkableItem):
    """
    A record storing a single source detected in an image by the daofind algorithm (part of astropy).
    """
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name="daofindResults")
    mag = models.FloatField(null=True)
    flux = models.FloatField(null=True)
    peak = models.FloatField(null=True)
    sharpness = models.FloatField(null=True)
    sround = models.FloatField(null=True)
    ground = models.FloatField(null=True)

    bookmarks = GenericRelation('Bookmark')

    def getBookmarkTypeString(self):
        return 'daofindResult'

    def getUrl(self):
        return '/detectedSource/daofind/' + str(self.pk)

    @property
    def getDisplayName(self):
        return "Image " + str(self.image.pk) + ": Daofind Result " + str(self.pk)

class StarfindResult(SourceFindResult, BookmarkableItem):
    """
    A record storing a single source detected in an image by the starfind algorithm (part of astropy).
    """
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name="starfindResults")
    mag = models.FloatField(null=True)
    peak = models.FloatField(null=True)
    flux = models.FloatField(null=True)
    fwhm = models.FloatField(null=True)
    roundness = models.FloatField(null=True)
    pa = models.FloatField(null=True)
    sharpness = models.FloatField(null=True)

    bookmarks = GenericRelation('Bookmark')

    def getBookmarkTypeString(self):
        return 'starfindResult'

    def getUrl(self):
        return '/detectedSource/starfind/' + str(self.pk)

    @property
    def getDisplayName(self):
        return "Image " + str(self.image.pk) + ": Starfind Result " + str(self.pk)

#TODO: We should create another model to tie a bunch of results submitted at the same time to a single session.
class UserSubmittedResult(SourceFindResult, BookmarkableItem):
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name="userSubmittedResults")
    user = models.ForeignKey(User, db_index=True, on_delete=models.CASCADE)

    bookmarks = GenericRelation('Bookmark')

    def getBookmarkTypeString(self):
        return 'userSubmittedResult'

    def getUrl(self):
        return '/detectedSource/userSubmittedResult/' + str(self.pk)

    @property
    def getDisplayName(self):
        return 'Image {}: User Submitted Source {}'.format(self.image.pk, self.pk)

class UserSubmittedHotPixel(SourceFindResult, BookmarkableItem):
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name="userSubmittedHotPixels")
    user = models.ForeignKey(User, null=True, db_index=True, on_delete=models.CASCADE)

    bookmarks = GenericRelation('Bookmark')

    def getBookmarkTypeString(self):
        return 'userSubmittedHotPixel'

    def getUrl(self):
        return '/detectedSource/userHotPixel/' + str(self.pk)

    @property
    def getDisplayName(self):
        return 'Image {}: User Submitted Hot Pixel {}'.format(self.image.pk, self.pk)

class SourceFindMatch(SourceFindResult, BookmarkableItem):
    """
    A record storing links to the individual SourceFindResult records for sources which are found at the same location in
    an image by two or more individual source find methods.  The confidence of the match is taken to be the "geometric mean"
    of the confidence values of the individual matched results.
    """
    image = models.ForeignKey(Image, db_index=True, on_delete=models.CASCADE, related_name="sourceFindMatchResults")
    numMatches = models.IntegerField()
    sextractorResult = models.ForeignKey(SextractorResult, null=True, on_delete=models.CASCADE)
    image2xyResult = models.ForeignKey(Image2xyResult, null=True, on_delete=models.CASCADE)
    daofindResult = models.ForeignKey(DaofindResult, null=True, on_delete=models.CASCADE)
    starfindResult = models.ForeignKey(StarfindResult, null=True, on_delete=models.CASCADE)
    userSubmittedResult = models.ForeignKey(UserSubmittedResult, null=True, on_delete=models.CASCADE)

    bookmarks = GenericRelation('Bookmark')

    def getBookmarkTypeString(self):
        return 'sourceFindMatch'

    def getUrl(self):
        return '/detectedSource/multi/' + str(self.pk)

    @property
    def getDisplayName(self):
        return "Image " + str(self.image.pk) + ": Multiple Source Match Result " + str(self.pk)

#TODO: Create a base class for catalog object entries with some standard params in it to make querying more uniform.
class Catalog(models.Model):
    """
    A record storing details about an individual astronomical catalog that has been imported into the database.  These
    records are not particularly necessary, as they don't really need to be used in the processing by the site, but having
    them as database entries makes keeping track of which catalogs are imported a bit easier.  It also makes it easier to
    display them on the /catalogs page.
    """
    name = models.CharField(max_length=64, null=True)
    fullName = models.CharField(max_length=256, null=True)
    objectTypes = models.TextField(null=True)
    numObjects = models.TextField(null=True)
    limMagnitude = models.FloatField(null=True)
    attributionShort = models.TextField(null=True)
    attributionLong = models.TextField(null=True)
    vizierID = models.TextField(null=True)
    vizierUrl = models.TextField(null=True)
    url = models.TextField(null=True)
    cosmicNotes = models.TextField(null=True)
    importDateTime = models.DateTimeField(auto_now_add=True, null=True)
    importPeriod = models.FloatField(null=True)

    comments = GenericRelation('TextBlob')

class ScorableObject:
    """
    This is a base class to provide a set common access functions to compute a "score" for an object indicating how
    valuable an observation of that target is at a given time, by a given user.  The score is made up of three components:

        Value - How scientifically useful an observation would be at a given time.

        Difficulty - The intrinsic difficulty in observing the target that any user would experience (like uncertainty
        in position, etc).

        User Difficulty - The difficulty in observing a target based on properties specific to the user (how dim the
        object is in comparison to their instrument, how high it is above their horizon, etc).

    A score of 0 should be assigned for objects which are impossible to observe due to equipment, location, time, etc.
    This is done to prevent the score routines from ranking this a high scoring object due to its enormous difficulty
    if it was very low, or below the horizon, or way too dim for the observer to detect, etc.  Since we want to
    discourage, rather than encourage, such observations we just return 0 to indicate it is impossible and therefore
    not worth any points so don't even try observing it in the first place.
    """
    def getScoreForTime(self, t, user, observatory=None):
        baseScore = self.getValueForTime(t) * self.getDifficultyForTime(t) * self.getUserDifficultyForTime(t, user, observatory)

        if observatory != None:
            baseScore *= self.observatoryCorrections(t, user, observatory)

        return baseScore

    def getPeakScoreForInterval(self, startTime, endTime, user, observatory=None):
        timeSkip = timedelta(minutes=5)
        currentTime = startTime
        maxScore = self.getScoreForTime(startTime, user, observatory)
        maxTime = startTime
        while currentTime < endTime:
            currentScore = self.getScoreForTime(currentTime, user, observatory)
            if currentScore > maxScore:
                maxScore = currentScore
                maxTime = currentTime

            currentTime = currentTime + timeSkip

        return (maxScore, maxTime)

    def getValueForTime(self, t):
        """
        --> Should be reimplemented by child classes. <--
        Returns the scientific value of this ScorableObject for the given time t.

        Reflects an estimation of the relative scientific value if an observation of a ScorableObject were to be performed
        at that time.  For example, an image of an asteroid with high ceu (current ephemeris uncertainty) is favorable to
        one with a low ceu, etc.
        """
        return 1.0

    def getDifficultyForTime(self, t):
        """
        --> Should be reimplemented by child classes. <--
        Returns the intrinsic observing difficulty score for difficulty common to all observers for this ScorableObject forven time t.
        the given time t.

        Reflects an estimation of the relative difficulty of observing different kinds of objects.  For example, stars and
        clusters are easier to observe than extended objects, etc.  Also includes sources of difficulty such as uncertainty
        in the objects position or brightness, etc.
        """
        return 1.0

    def getUserDifficultyForTime(self, t, user, observatory=None):
        """
        --> Should be reimplemented by child classes. <--
        Returns the difficulty score for this ScorableObject for the given time t for difficulties assosciated with
        observing from a given user's observatory.

        Reflects the difficulty related to observing the ScorableObject from a specific observatory at a given time. For
        example: off-zenith observing, light-gathering limitations, below horizion, etc.
        """
        #TODO: There should be a general set of score adjustments that happen in the base
        # class that always get executed by the child classes.  One of these is considering
        # the pointing accuracy of a telescope system.  The less accurate it is, the more we
        # should increase the score for objects in more dense fields, like in the plane of
        # the milky way vs out, etc.
        return 1.0

    def observatoryCorrections(self, t, user, observatory):
        return self.zenithDifficulty(t, observatory)

    @staticmethod
    def limitingStellarMagnitudeDifficulty(mag, limitingMag):
        """
        Compute and return a difficulty score for how difficult this (stellar, or point like) object is to observe
        given a specific limiting magnitude or the dimmest point source the observer can meaningfully detect.
        """
        if mag < (limitingMag - 6):
            return max(mag/(limitingMag - 6), 0)
        elif mag <= limitingMag:
            #TODO: Implement this as a function of magnitude.
            return 3.0
        elif mag > limitingMag:
            return 0.0

    @staticmethod
    def limitingDSOMagnitudeDifficulty(mag, limitingMag):
        """
        Compute and return a difficulty score for how difficult this (extended or DSO) object is to observe
        given a specific limiting magnitude or the dimmest point source the observer can meaningfully detect.
        """
        #This dsoFactor is used to roughly indicate the relative difficulty of detecting an extended object vs
        # detecting a point source.  A better approximation should be used than just a dumb constant.
        #TODO: Make this better.
        dsoFactor = 1.5

        if mag >= 0 and mag < limitingMag/dsoFactor:
            return 5.0 * mag / (limitingMag/dsoFactor)
        else:
            return 0.0

    #TODO: Need to implement this function and then call it from all the user difficulty calculations.
    def zenithDifficulty(self, t, observatory):
        """
        Compute and return a difficulty score for how difficult this object is to observe based on its distance from the
        observer's zenith.  The function returns 0.0 for objects impossible to observe due to airmass or being below the horizon.
        """
        observer = ephem.Observer()
        observer.lat = observatory.lat
        observer.lon = observatory.lon
        observer.elevation = observatory.elevation
        if isinstance(t, datetime):
            observer.date = t
        else:
            print('Warning: making a datetime out of something which was already supposed to be a datetime.')
            observer.date = datetime(t)

        if isinstance(self, SkyObject):
            ra, dec = self.getSkyCoords(t)
            body = ephem.FixedBody()
            body._ra = ra
            body._dec = dec
            body._epoch = '2000'  #TODO: Set this properly as elsewhere.

            body.compute(observer)
            if body.alt < 20*math.pi/180.0:
                factor = 0
            else:
                factor = math.pow(math.sin(body.alt), 2)
            return factor
        else:
            return 1.0

        return 1.0

class DataTimePoint(models.Model):
    #Generic FK to image or whatever the question is about.
    #TODO: Add a reverse generic relation to the relevant classes this will link to (image, observer notes, etc).
    content_type = models.ForeignKey(ContentType, db_index=True, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    scoreableObject = GenericForeignKey('content_type', 'object_id')

    dateTime = models.DateTimeField()
    score = models.FloatField(null=True)

class UCAC4Record(models.Model, BookmarkableItem, SkyObject, ScorableObject):
    """
    A record storing a single entry from the UCAC4 catalog of stars.
    """
    #build index on this for search.
    identifier = models.CharField(max_length=10, null=True)
    ra = models.FloatField(null=True)
    dec = models.FloatField(null=True)
    geometry = models.PointField(db_index=True, srid=40000, geography=False, dim=2, null=True)
    pmra = models.FloatField(null=True)     # proper motion in ra (mas/yr)      #TODO: Units
    pmdec = models.FloatField(null=True)    # proper motion in dec (mas/yr)     #TODO: Units
    magFit = models.FloatField(db_index=True, null=True)   # magnitude by fitting a psf
    magAperture = models.FloatField(null=True) # magnitude by aperture photometry
    magError = models.FloatField(null=True)
    id2mass = models.CharField(max_length=10, null=True) # 2MASS identifier if present in 2MASS
    #TODO: Should include at least B an V mags for stars that have them so we have some indication of color.

    bookmarks = GenericRelation('Bookmark')
    comments = GenericRelation('TextBlob')

    def getSkyCoords(self, dateTime=datetime.now()):
        return (self.ra, self.dec)

    def getMag(self, dateTime=datetime.now()):
        #TODO: Properly implement this function.
        return self.magFit

    def getBookmarkTypeString(self):
        return 'ucac4'

    def getUrl(self):
        return "/catalog/UCAC4/" + str(self.pk)

    @property
    def getLinks(self):
        links =  [
            ("http://simbad.u-strasbg.fr/simbad/sim-id?Ident=UCAC4 "+self.identifier, "SIMBAD")
            ]

        return links

    @property
    def getDisplayName(self):
        return self.identifier

    def getValueForTime(self, t):
        return 0.1

    def getDifficultyForTime(self, t):
        return 1.0

    def getUserDifficultyForTime(self, t, user, observatory=None):
        #TODO: Properly implement this function.
        if user.is_authenticated:
            return ScorableObject.limitingStellarMagnitudeDifficulty(self.getMag(t), user.profile.limitingMag)
        else:
            return ScorableObject.limitingStellarMagnitudeDifficulty(self.getMag(t), 16)

class GCVSRecord(models.Model, BookmarkableItem, SkyObject, ScorableObject):
    """
    A record storing a single entry from the General Catalog of Variable Stars.
    """
    constellationNumber = models.CharField(max_length=2, null=True)
    starNumber = models.CharField(max_length=5, null=True)
    identifier = models.CharField(max_length=10, null=True)
    ra = models.FloatField(null=True, db_index=True)
    dec = models.FloatField(null=True, db_index=True)
    geometry = models.PointField(db_index=True, srid=40000, geography=False, dim=2, null=True)
    pmRA = models.FloatField(null=True)
    pmDec = models.FloatField(null=True)
    variableType = models.CharField(max_length=10, null=True)
    variableType2 = models.CharField(max_length=10, null=True)
    magMax = models.FloatField(db_index=True, null=True)
    magMaxFlag = models.CharField(max_length=1, null=True)
    magMin = models.FloatField(db_index=True, null=True)
    magMinFlag = models.CharField(max_length=1, null=True)
    magMin2 = models.FloatField(db_index=True, null=True)
    magMin2Flag = models.CharField(max_length=1, null=True)
    epochMaxMag = models.FloatField(null=True)  #NOTE: This can be a max or a min depending on the variable type.
    outburstYear = models.FloatField(null=True)
    period = models.FloatField(null=True)
    periodRisingPercentage = models.FloatField(null=True)
    spectralType = models.CharField(max_length=17, null=True)

    bookmarks = GenericRelation('Bookmark')
    comments = GenericRelation('TextBlob')

    def getSkyCoords(self, dateTime=datetime.now()):
        return (self.ra, self.dec)

    def getMag(self, dateTime=datetime.now()):
        #TODO: Properly implement this function.
        return self.magMax

    def getBookmarkTypeString(self):
        return 'variableStar'

    def getUrl(self):
        return "/catalog/gcvs/" + str(self.pk)

    @property
    def getDisplayName(self):
        return self.identifier

    def getValueForTime(self, t):
        #TODO: Properly implement this function.
        return 3.0

    def getDifficultyForTime(self, t):
        #TODO: Properly implement this function.
        # Should be proprotional to the uncertainty in the brightness of the object at the given time.
        return 1.0

    def getUserDifficultyForTime(self, t, user, observatory=None):
        #TODO: Properly implement this function.
        if user.is_authenticated:
            return ScorableObject.limitingStellarMagnitudeDifficulty(self.getMag(t), user.profile.limitingMag)
        else:
            return ScorableObject.limitingStellarMagnitudeDifficulty(self.getMag(t), 16)

    @property
    def getLinks(self):
        links =  [
            ("https://www.aavso.org/apps/webobs/results/?star="+self.identifier+"&num_results=50", "AAVSO"),
            ("https://www.aavso.org/apps/vsp/chart/?star="+self.identifier+"&fov=60&maglimit=14.5&resolution=150&north=up&east=left&other=all", "VSP"),
            ("http://simbad.u-strasbg.fr/simbad/sim-id?Ident="+self.identifier, "SIMBAD")
            ]

        return links

class TwoMassXSCRecord(models.Model, BookmarkableItem, SkyObject, ScorableObject):
    """
    A record storing a single entry from the 2MASS Extended Source Catalog of "extended", i.e. non point source, objects.
    """
    identifier = models.CharField(max_length=24)
    ra = models.FloatField(db_index=True)
    dec = models.FloatField(db_index=True)
    #TODO: Should probably make this geometry field a polygon, or add a second geometry field for the polygon and leave this as a point.  Not sure which would be better.
    geometry = models.PolygonField(db_index=True, srid=40000, geography=False, dim=2, null=True)
    isophotalKSemiMajor = models.FloatField(db_index=True, null=True)
    isophotalKMinorMajor = models.FloatField(null=True)
    isophotalKAngle = models.FloatField(null=True)
    isophotalKMag = models.FloatField(null=True, db_index=True)
    isophotalKMagErr = models.FloatField(null=True)

    bookmarks = GenericRelation('Bookmark')
    comments = GenericRelation('TextBlob')

    def getSkyCoords(self, dateTime=datetime.now()):
        return (self.ra, self.dec)

    def getMag(self, dateTime=datetime.now()):
        return self.isophotalKMag

    def getBookmarkTypeString(self):
        return '2MassXSC'

    def getUrl(self):
        return "/catalog/2MassXSC/" + str(self.pk)

    @property
    def getDisplayName(self):
        return self.identifier

    def getValueForTime(self, t):
        #TODO: Properly implement this function.
        return pow(self.isophotalKSemiMajor/60.0, 2) * self.isophotalKMinorMajor

    def getDifficultyForTime(self, t):
        #TODO: Properly implement this function.
        return 1.0

    def getUserDifficultyForTime(self, t, user, observatory=None):
        #TODO: Allow fainter magnitudes for galaxies since the goal of observing them is mainly to check for supernovas which might be quite bright.
        #TODO: Properly implement this function.
        if user.is_authenticated:
            return ScorableObject.limitingDSOMagnitudeDifficulty(self.getMag(t), user.profile.limitingMag)
        else:
            return ScorableObject.limitingDSOMagnitudeDifficulty(self.getMag(t), 16)

    @property
    def getLinks(self):
        links =  [
            ("http://simbad.u-strasbg.fr/simbad/sim-id?Ident="+self.identifier, "SIMBAD")
            ]

        return links

class MessierRecord(models.Model, BookmarkableItem, SkyObject, ScorableObject):
    """
    A record storing a single entry from the Messier Catalog.
    """
    identifier = models.CharField(max_length=24)
    ra = models.FloatField()
    dec = models.FloatField()
    geometry = models.PointField(db_index=True, srid=40000, geography=False, dim=2, null=True)
    objectType = models.CharField(max_length=3)
    spectralType = models.CharField(max_length=10, null=True)
    magU = models.FloatField(db_index=True, null=True)
    magB = models.FloatField(db_index=True, null=True)
    magV = models.FloatField(db_index=True, null=True)
    magR = models.FloatField(db_index=True, null=True)
    magI = models.FloatField(db_index=True, null=True)
    numReferences = models.IntegerField()

    bookmarks = GenericRelation('Bookmark')
    comments = GenericRelation('TextBlob')

    def getSkyCoords(self, dateTime=datetime.now()):
        return (self.ra, self.dec)

    def getMag(self, dateTime=datetime.now()):
        return self.magV

    def getBookmarkTypeString(self):
        return 'messierObject'

    def getUrl(self):
        return "/catalog/messier/" + str(self.pk)

    @property
    def getDisplayName(self):
        return self.identifier

    def getValueForTime(self, t):
        typeValueDict = {
            'GlC': (8.0, 'cluster'),            # Globular Cluster
            'GiP': (3.0, 'galaxy'),             # Galaxy in Pair of Galaxies
            'HII': (1.4, 'nebula'),             # HII (ionized) region
            'AGN': (2.0, 'galaxy'),             # Active Galaxy Nucleus
            'Cl*': (7.0, 'cluster'),            # Cluster of Stars
            'As*': (1.8, 'cluster'),            # Association of Stars
            'Sy2': (2.0, 'galaxy'),             # Seyfert 2 Galaxy
            'OpC': (6.0, 'cluster'),            # Open (galactic) Cluster
            'PN': (2.8, 'stellarRemnant'),      # Planetary Nebula
            'H2G': (2.0, 'galaxy'),             # HII Galaxy
            'RNe': (2.5, 'nebula'),             # Reflection Nebula
            '**': (3.0, 'cluster'),             # Double or multiple star
            'IG': (5.0, 'galaxy'),              # Interacting Galaxies
            'SyG': (2.0, 'galaxy'),             # Seyfert Galaxy
            'SNR': (3.5, 'stellarRemnant'),     # SuperNova Remnant
            'GiG': (3.0, 'galaxy'),             # Galaxy in Group of Galaxies
            'LIN': (3.0, 'galaxy'),             # LINER-type Active Galaxy Nucleus
            'SBG': (5.0, 'galaxy'),             # Starburst Galaxy
            'G': (2.0, 'galaxy')                # Galaxy
            }

        valueList = typeValueDict[self.objectType]
        value = valueList[0]
        category = valueList[1]

        return value

    def getDifficultyForTime(self, t):
        typeDifficultyDict = {
            'GlC': (0.8, 'cluster'),            # Globular Cluster
            'GiP': (1.3, 'galaxy'),             # Galaxy in Pair of Galaxies
            'HII': (2.0, 'nebula'),             # HII (ionized) region
            'AGN': (1.3, 'galaxy'),             # Active Galaxy Nucleus
            'Cl*': (0.9, 'cluster'),            # Cluster of Stars
            'As*': (1.1, 'cluster'),            # Association of Stars
            'Sy2': (1.3, 'galaxy'),             # Seyfert 2 Galaxy
            'OpC': (1.0, 'cluster'),            # Open (galactic) Cluster
            'PN': (2.0, 'stellarRemnant'),      # Planetary Nebula
            'H2G': (1.3, 'galaxy'),             # HII Galaxy
            'RNe': (1.5, 'nebula'),             # Reflection Nebula
            '**': (0.8, 'cluster'),             # Double or multiple star
            'IG': (1.3, 'galaxy'),              # Interacting Galaxies
            'SyG': (1.3, 'galaxy'),             # Seyfert Galaxy
            'SNR': (2.0, 'stellarRemnant'),     # SuperNova Remnant
            'GiG': (1.3, 'galaxy'),             # Galaxy in Group of Galaxies
            'LIN': (1.3, 'galaxy'),             # LINER-type Active Galaxy Nucleus
            'SBG': (1.3, 'galaxy'),             # Starburst Galaxy
            'G': (1.3, 'galaxy')                # Galaxy
            }

        difficultyList = typeDifficultyDict[self.objectType]
        difficulty = difficultyList[0]
        category = difficultyList[1]

        return difficulty

    def getUserDifficultyForTime(self, t, user, observatory=None):
        #TODO: Properly implement this function.
        if user.is_authenticated:
            return ScorableObject.limitingDSOMagnitudeDifficulty(self.getMag(t), user.profile.limitingMag)
        else:
            return ScorableObject.limitingDSOMagnitudeDifficulty(self.getMag(t), 16)

    @property
    def getLinks(self):
        links =  [
            ("http://simbad.u-strasbg.fr/simbad/sim-id?Ident="+self.identifier, "SIMBAD")
            ]

        return links

class AstorbRecord(models.Model, BookmarkableItem, SkyObject, ScorableObject):
    """
    A record storing a the Keplerian orbital elements and physical properties for a single asteroid from the astorb database.
    """
    number = models.IntegerField(null=True)   # The asteroid's number, if it has been numbered, else None.
    name = models.CharField(max_length=18, null=True)   # The asteroid's name, if it has one, or a blank string.
    absMag = models.FloatField()   # The absolute magnitude parameter H (units: mag).
    slopeParam = models.FloatField()   # The slope magnitude parameter G.
    colorIndex = models.FloatField(null=True)   # The B-V magnitude color index of the asteroid (units: mag).
    diameter = models.FloatField(null=True)   # The asteroid's diameter (units: km).
    taxanomicClass = models.CharField(max_length=7)   # The IRAS taxanomic class of the asteroid.
    orbitCode = models.IntegerField()   # The planet crossing code.
    criticalCode = models.IntegerField()   # MPC critical-list code.
    astrometryNeededCode = models.IntegerField()   # The Flagstaff Station code.
    observationArc = models.IntegerField()   # The time between the first and last observations of the asteroid (units: days).
    numObservations = models.IntegerField()   # The number of observations actually used in computing the orbit.
    epoch = models.DateField()   # The epoch of the osculating orbit.
    meanAnomaly = models.FloatField()   # Orbital parameter (units: deg).
    argPerihelion = models.FloatField()   # Orbital parameter (units: deg).
    lonAscendingNode = models.FloatField()   # Orbital parameter (units: deg).
    inclination = models.FloatField()   # Orbital parameter (units: deg).
    eccentricity = models.FloatField()   # Orbital parameter (units: unitless).
    semiMajorAxis = models.FloatField()   # Orbital parameter (units: AU).
    ceu = models.FloatField()   # The current ephemeris uncertainty (units: arcsec).
    ceuRate = models.FloatField()  # The rate of change of the CEU (units: arcsec/d).
    ceuDate = models.DateField(null=True)   # The date for which the CEU is valid.
    nextPEU = models.FloatField()   # The next peak ephemeris uncertainty (units: arcsec).
    nextPEUDate = models.DateField(null=True)   # The date of the next peak.
    tenYearPEU = models.FloatField()   # The highest ephemeris uncertainty in the next 10 years. (units: arcsec)
    tenYearPEUDate = models.DateField(null=True)   # The date of the 10 year peak uncertainty.
    tenYearPEUIfObserved = models.FloatField()   # The new 10 year peak uncertainty if 2 observations were made at the next PEU (units: arcsec).
    tenYearPEUDateIfObserved = models.DateField(null=True)   # The new 10 year PEU date if the above observations were done.

    bookmarks = GenericRelation('Bookmark')
    comments = GenericRelation('TextBlob')

    def isMobile(self):
        return 2

    def getSkyCoords(self, dateTime=datetime.now()):
        ephemeris = computeSingleEphemeris(self, dateTime)
        return (ephemeris.ra*180/math.pi, ephemeris.dec*180/math.pi)

    def getMag(self, dateTime=datetime.now()):
        body = computeSingleEphemeris(self, dateTime)
        return body.mag

    def getBookmarkTypeString(self):
        return 'asteroid'

    def getUrl(self):
        return "/catalog/asteroid/" + str(self.pk)

    @property
    def getDisplayName(self):
        if self.number != None:
            ret = str(self.number) + ' - ' + self.name
        else:
            ret = self.name

        return ret

    def getCeuForTime(self, t):
        if self.ceuDate == None or self.ceuRate == None or self.ceu == None:
            # Asteroids without a ceuDate tend to be newly discovered asteroids with short observation arcs.  We use a
            # moderately high "fake" ceu for these objects to avoid returning a null value.
            return 500

        d = datetime(self.ceuDate.year, self.ceuDate.month, self.ceuDate.day, tzinfo=pytz.timezone('UTC'))
        deltaT = t - d
        value = self.ceu + self.ceuRate * (deltaT.total_seconds()/86400)
        return max(value, 0.0)

    def getValueForTime(self, t):
        #TODO: Properly implement this function.
        #TODO: Take into account the orbitCode, astrometryNeeded code, and criticalCode field.
        orbitCodeDict = {
            0: 1,      # 
            1: 6,    # Earth-crossing asteroid (ECA).
            2: 1.5,     # Orbit comes inside Earth's orbit but not specifically an ECA.
            4: 1.5,      # Amor type asteroids.
            8: 2,     # Mars crossers.
            16: 2      # Outer planet crossers.
            }

        criticalCodeDict = {
            0: 2,      # 
            1: 0.2,  # Lost asteroid.
            2: 10,    # Asteroids observed at only two apparitions.
            3: 5,     # Asteroids observed at only three apparitions.
            4: 5,     # Asteroids observed at four or more apparitions with the last more than 10 years ago.
            5: 5,     # Asteroids observed at four or more apparitions only one night in last 10 years.
            6: 2,     # Asteroids observed at four or more apparitions still poor data.
            7: 5      # Not critical asteroid, however absolute magnitude poorly known.
            }

        astrometryNeededCodeDict = {
            10: 4,   # Space mission targets and occultation candidates.
            9: 3,     # Asteroids useful for mass determination.
            8: 2,     # Asteroids for which a few observations would upgrade the orbital uncertainty.
            7: 1.5,      # MPC Critical list asteroids with future low uncertainties.
            6: 2,     # Planet crossers of type 6:5.
            5: 6,     # Asteroids for which a few more observations would lead to numbering them.
            4: 2,     # 
            3: 1.8,      # 
            2: 1.6,      # 
            1: 1.5,      # 
            0: 1.4       # 
            }

        #TODO: Some of these importance codes are bitwise anded together and need to be properly parsed that way.
        ocMultiplier = orbitCodeDict[self.orbitCode] if self.orbitCode in orbitCodeDict else 1.0
        ccMultiplier = criticalCodeDict[self.criticalCode] if self.criticalCode in criticalCodeDict else 1.0
        anMultiplier = astrometryNeededCodeDict[self.astrometryNeededCode] if self.astrometryNeededCode in astrometryNeededCodeDict else 1.0
        multiplier = ocMultiplier * ccMultiplier * anMultiplier / 5

        #TODO: Calculate an ephemeris and use angle from opposition as part of the score.
        #body = computeSingleEphemeris(self, dateTime)

        return multiplier

    def getAstrometryNeededCodeText(self):
        astrometryNeededCodeTextDict = {
            10: "Space mission targets and occultation candidates.",
            9: "Asteroids useful for mass determination.",
            8: "Asteroids for which a few observations would upgrade the orbital uncertainty.",
            7: "MPC Critical list asteroids with future low uncertainties.",
            6: "Planet crossers of type 6:5.",
            5: "Asteroids for which a few more observations would lead to numbering them.",
            4: "",
            3: "",
            2: "",
            1: "",
            0: ""
            }

        return astrometryNeededCodeTextDict[self.astrometryNeededCode]

    def getDifficultyForTime(self, t):
        #TODO: Properly implement this function.
        # Score increases with increasing error up until errorInDeg is reached and then it drops down from the peak
        # value for errors larger than this.
        errorInArcsec = 5
        ceu = self.getCeuForTime(t)
        if ceu < 2*errorInArcsec:
            return 1.0 + min(8.0, math.pow(1+ceu/errorInArcsec, 1.5))
        else:
            return max(2.5, 8.0 - 2.0 * math.pow(1+ceu-2*errorInArcsec/errorInArcsec, 1.2))

    def getUserDifficultyForTime(self, t, user, observatory=None):
        #TODO: Properly implement this function.
        if user.is_authenticated:
            return ScorableObject.limitingStellarMagnitudeDifficulty(self.getMag(t), user.profile.limitingMag)
        else:
            return ScorableObject.limitingStellarMagnitudeDifficulty(self.getMag(t), 16)

    @property
    def getLinks(self):
        #TODO: Link to (post only)   http://alcdef.org/alcdef_GenerateALCDEFPage.php
        #TODO: Link to (post only) http://www.minorplanet.info/PHP/GenerateLCDBHTMLPages.php
        links =  [
            ("https://www.minorplanetcenter.net/db_search/show_object?utf8=???&object_id="+self.name, "MPC"),
            ("https://ssd.jpl.nasa.gov/sbdb.cgi?sstr="+self.name, "JPL")
            ]

        if self.number is not None:
            links.append( ("http://astro.troja.mff.cuni.cz/projects/asteroids3D/web.php?page=db_asteroid_detail&asteroid_id="+str(self.number), "DAMIT") )

        return links

#TODO: This should probably inherit from SkyObject as well, need to add that and implement the function if it is deemed appropriate.
class AstorbEphemeris(models.Model):
    """
    A record containing a computed emphemeride path for an asteroid in the astorb database.  The AstorbRecord is read
    in from the database for the given asteroid, and pyephem is used to convert the Keplerian orbit into a series of
    RA-DEC ephemerides which is then stored in the AstorbEphemeris record.  In addition to the position on the sky
    (stored as a line geometry over the given time span), the min and max apparent magnitude over the interval is
    stored.
    """
    astorbRecord = models.ForeignKey(AstorbRecord, on_delete=models.CASCADE, related_name='ephemerides')
    startTime = models.DateTimeField(db_index=True, null=True)
    endTime = models.DateTimeField(db_index=True, null=True)
    dimMag = models.FloatField(db_index=True, null=True)
    brightMag = models.FloatField(db_index=True, null=True)
    geometry = models.LineStringField(db_index=True, srid=40000, geography=False, dim=2, null=True)

class ExoplanetRecord(models.Model, BookmarkableItem, SkyObject, ScorableObject):
    """
    A record storing a single entry from the Exoplanets Data Explorer database of curated exoplanet results.
    """
    identifier = models.CharField(max_length=32, null=True)
    identifier2 = models.CharField(max_length=32, null=True)
    starIdentifier = models.CharField(max_length=32, null=True)
    component = models.CharField(max_length=2, null=True)
    numComponents = models.IntegerField(null=True)
    ra = models.FloatField(db_index=True)
    dec = models.FloatField(db_index=True)
    geometry = models.PointField(srid=40000, db_index=True, geography=False, dim=2, null=True)
    dist = models.FloatField(null=True)

    magBMinusV = models.FloatField(null=True)
    magV = models.FloatField(null=True)
    magJ = models.FloatField(null=True)
    magH = models.FloatField(null=True)
    magKS = models.FloatField(null=True)

    thisPlanetDiscoveryMethod = models.CharField(max_length=32, null=True)
    firstPlanetDiscoveryMethod = models.CharField(max_length=32, null=True)
    discoveryMicrolensing = models.BooleanField()
    discoveryImaging = models.BooleanField()
    discoveryTiming = models.BooleanField()
    discoveryAstrometry = models.BooleanField()

    vSinI = models.FloatField(null=True)
    mSinI = models.FloatField(null=True)
    mass = models.FloatField(null=True)

    period = models.FloatField(null=True)
    velocitySemiAplitude = models.FloatField(null=True)
    velocitySlope = models.FloatField(null=True)

    timePeriastron = models.DateTimeField(null=True)
    eccentricity = models.FloatField(null=True)
    argPeriastron = models.FloatField(null=True)
    inclination = models.FloatField(null=True)
    semiMajorAxis = models.FloatField(null=True)

    transitDepth = models.FloatField(null=True)
    transitDuration = models.FloatField(null=True)
    transitEpoch = models.DateTimeField(null=True)

    planetRadius = models.FloatField(null=True)
    planetDensity = models.FloatField(null=True)
    planetSurfaceGravity = models.FloatField(null=True)

    firstPublicationDate = models.IntegerField(null=True)
    firstReference = models.TextField(null=True)
    orbitReference = models.TextField(null=True)

    epeLink = models.TextField(null=True)
    eaLink = models.TextField(null=True)
    etdLink = models.TextField(null=True)
    simbadLink = models.TextField(null=True)

    bookmarks = GenericRelation('Bookmark')
    comments = GenericRelation('TextBlob')

    def getTransitTime(self, transit='next', t=timezone.now()):
        """
        Returns a datetime object for the time of the 'next' or 'prev' transit starting from the given time t.
        """
        if self.transitEpoch is None:
            return None

        deltaT = t - self.transitEpoch
        periods = deltaT.total_seconds() / (86400*self.period)
        if transit == 'next':
            periodNumber = math.ceil(periods)
        elif transit == 'prev':
            periodNumber = math.floor(periods)
        else:
            return None

        transitTime = timedelta(days=periodNumber * self.period) + self.transitEpoch
        return transitTime

    def getSkyCoords(self, dateTime=datetime.now()):
        return (self.ra, self.dec)

    def getMag(self, dateTime=datetime.now()):
        return self.magV

    def getBookmarkTypeString(self):
        return 'exoplanet'

    def getUrl(self):
        return "/catalog/exoplanet/" + str(self.pk)

    @property
    def getDisplayName(self):
        return self.identifier

    def getValueForTime(self, t):
        #TODO: Properly implement this function.
        #TODO: Add an increase in score proportional to the period the planets orbit (for transiting exoplanets), since planets with long orbits only rarely transit, whereas short period planets transit all the time and are easier to study.
        if self.transitEpoch != None and self.transitDuration != None and self.period != None:
            deltaT = t - self.transitEpoch
            periods = deltaT.total_seconds() / (86400*self.period)
            periodFraction = periods - math.floor(periods)
            periodFloor = math.floor(periods)
            periodCeiling = math.ceil(periods)
            durationHalfFraction = (self.transitDuration / self.period) / 2.0
            durationHalfTimedelta = timedelta(days=self.transitDuration/2.0)
            windowSizeHours = 0.5
            windowSizeTimedelta = timedelta(hours=windowSizeHours)

            #print(deltaT, "\t", periods, "\t", periodFraction, "\t", durationHalfFraction)

            if periodFraction <= durationHalfFraction or periodFraction >= (1.0 - durationHalfFraction):
                # The exoplanet is currently in a transit.
                return 5
            else:
                # The exoplanet is not in a transit.
                transit1 = self.getTransitTime('next', t)
                transit2 = self.getTransitTime('prev', t)
                t1c1 = transit1 - durationHalfTimedelta
                t1c4 = transit1 + durationHalfTimedelta
                t2c1 = transit2 - durationHalfTimedelta
                t2c4 = transit2 + durationHalfTimedelta
                dt1c1 = abs((t - t1c1).total_seconds())
                dt1c4 = abs((t - t1c4).total_seconds())
                dt2c1 = abs((t - t2c1).total_seconds())
                dt2c4 = abs((t - t2c4).total_seconds())
                if dt1c1 < windowSizeTimedelta.total_seconds() or dt1c4 < windowSizeTimedelta.total_seconds() or \
                   dt2c1 < windowSizeTimedelta.total_seconds() or dt2c4 < windowSizeTimedelta.total_seconds():
                    # The exoplanet is ingressing or egressing from a transit, or near enough that we should be getting data.
                    return 10
                else:
                    # The exoplanet is not in a transit.
                    return 2.5

        return 3

    def getDifficultyForTime(self, t):
        #TODO: Properly implement this function.
        return 1.0

    def getUserDifficultyForTime(self, t, user, observatory=None):
        #TODO: Properly implement this function.
        if user.is_authenticated:
            return ScorableObject.limitingStellarMagnitudeDifficulty(self.getMag(t), user.profile.limitingMag)
        else:
            return ScorableObject.limitingStellarMagnitudeDifficulty(self.getMag(t), 16)

    @property
    def getLinks(self):
        links = [
            ("http://exoplanets.org/detail/"+self.identifier, "Exoplanet.org"),
            ("https://exoplanetarchive.ipac.caltech.edu/cgi-bin/DisplayOverview/nph-DisplayOverview?objname="+self.identifier, "NASA"),
            ("http://exoplanet.eu/catalog/"+self.identifier, "Exoplanet.eu"),
            ("http://simbad.u-strasbg.fr/simbad/sim-id?Ident="+self.identifier, "SIMBAD")
            ]

        if self.transitDepth is not None:
            links.append( ("http://var2.astro.cz/ETD/etd.php?STARNAME="+self.starIdentifier+"&PLANET="+self.component, "Transit") )

        return links


class GeoLiteLocation(models.Model):
    """
    A record storing a location (lat, lon, and city name) for an entry in the GeoLite Geolocation database.  The database
    is used for determining the approximate location of non-logged in users for things like the observation planning tool.
    The GeoLite database consists of two tables.  This one stores locations and city names, and then these entries are
    linked to from GeoLiteBlock records, which are IP block ranges.
    """
    id = models.IntegerField(db_index=True, primary_key=True)
    country = models.CharField(max_length=2)
    region = models.CharField(max_length=2)
    city = models.CharField(max_length=255)
    postalCode = models.CharField(max_length=8)
    lat = models.FloatField()
    lon = models.FloatField()
    metroCode = models.IntegerField(null=True)
    areaCode = models.CharField(max_length=3)

class GeoLiteBlock(models.Model):
    """
    A record storing a single IP block in the Geolite Geolocation database.  The block covers a range of IPs and contains a
    link to a GeoLiteLocation which contains the actual lat, lon, and city name info.
    """
    location = models.ForeignKey(GeoLiteLocation, on_delete=models.CASCADE)
    startIp = models.BigIntegerField(db_index=True)
    endIp = models.BigIntegerField(db_index=True)




#TODO: Make Question a ScorableObject.
class Question(models.Model):
    """
    A record containing a question to be asked to users of the site about uploaded images, files, observer notes, etc.
    This question record, forms the backbone of the question-answer system.  A fully implemented question consists of the
    following:

        * the text of the actual question itself
        * a list of response options and the input type for these options (checkbox, radiobutton, etc)
        * a short description of what the question is asking in more detail
        * a short description of what each response means if chosen
        * a list of questions that must be answered in a certain way for this question to be applicable

    Of all these different things, only some are stored in this record, with the others being stored in other record types.
    The question text and description are stored here, as well as the list of prerequisite questions.  See the record types
    below for more detailed descriptions of how the rest of the question system works.
    """
    #TODO: Should maybe include a FK to an image property or an image header entry to display to the user.  For example
    # 'frame type' could be displayed to check if it makes sense given the image.  I.E. does it look like a flat field, etc.
    text = models.TextField(null=True)
    descriptionText = models.TextField(null=True)
    titleText = models.TextField(null=True)
    aboutType = models.CharField(max_length=24)
    priority = models.IntegerField(db_index=True)
    previousVersion = models.ForeignKey('self', null=True, on_delete=models.CASCADE, related_name='laterVersion')
    prerequisites = models.ManyToManyField('self', symmetrical=False, through='AnswerPrecondition',
        through_fields=('firstQuestion', 'secondQuestion'))

    comments = GenericRelation('TextBlob')

class QuestionResponse(models.Model):
    """
    A record containing a single response option for a question.  The record contains the text to be shown for the response,
    as well as a short description of what the response means in more specific terms.  The index field is a running
    integer, counting up, which dictates the order in which the multiple responses for a given question will be displayed.
    The inputType field, which is a string interpreted by the question view, dictates what type of UI element to display
    with this response (checkbox, radiobutton, etc).  Lastly, the keyToSet and valueToSet fields describe the key-value
    components of an AnswerKV record which will be created and stored linking (indirectly) to the object the question was about.
    """
    question = models.ForeignKey(Question, db_index=True, on_delete=models.CASCADE)
    index = models.IntegerField()
    inputType = models.TextField(null=True)
    text = models.TextField(null=True)
    descriptionText = models.TextField(null=True)
    keyToSet = models.TextField(null=True)
    valueToSet = models.TextField(null=True)

class Answer(models.Model):
    """
    A record storing a submitted answer to a question in the question answer system.  The record links to the question
    that was asked, the user who answered it and the date and time it was answered.  A generic foreign key is used to
    link to the object the answer pertains to since the object could be any one of several types (image, observer
    notes, etc).  The three fields content_type, object_id, and content_object are all part of this generic foreign
    key.

    This record only stores the "metadata" that the question was answered and by who, the actual answer itself is
    stored as one or more AnswerKV records linking back to this answer.
    """
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    dateTime = models.DateTimeField()

    #Generic FK to image or whatever the question is about.
    #TODO: Add a reverse generic relation to the relevant classes this will link to (image, observer notes, etc).
    content_type = models.ForeignKey(ContentType, db_index=True, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')

class AnswerKV(models.Model):
    """
    A record storing a simple key-value pair containing the actual answer to a question submitted to the site by a user.
    The record links back to an Answer record containing the metadata for the answer.  Both the key and value fields are
    text fields of arbitrary length.
    """
    answer = models.ForeignKey(Answer, db_index=True, on_delete=models.CASCADE, related_name='kvs')
    key = models.TextField(null=True)
    value = models.TextField(null=True)

class AnswerPrecondition(models.Model):
    """
    A record representing a prerequisite question to another question.  The question linked in the firstQuestion field must
    be answered before the question linked in the secondQuestion field will be asked.  In addition to simple ordering of
    questions, in order for the secondQuestion to be asked at all each one of the AnswerPreconditionCondition records
    linking to this record must evaluate to true or the secondQuestion is not considered to be relevant and will therefore
    be skipped.  For example, it does not make sense to ask a question about the structure of galaxies present in an image
    if there are not actually any galaxies visible in the image.
    """
    descriptionText = models.TextField(null=True)
    firstQuestion = models.ForeignKey(Question, db_index=True, on_delete=models.CASCADE, related_name='dependantQuestions')
    secondQuestion = models.ForeignKey(Question, db_index=True, on_delete=models.CASCADE, related_name='dependsOnQuestions')

class AnswerPreconditionCondition(models.Model):
    """
    A record representing a true or false conditional test which must evaluate to true in order for a question to be
    considered relevant to be asked to a user.  The record links to an AnswerPrecondition which describes the firstQuestion
    these conditions are being applied to in order to determine if the secondQuestion should be asked.  If there are more
    than one conditions for a particular pair of questions then all of the conditions must be true (i.e. they are implicitely
    and'ed by the question system).  The pipe character "|" is used as the 'or' operator on the key and value fields and
    the number of items being or'ed together must be the same in both fields.  So for example it is wrong to write:

        a = b|c             (incorrect)

    but you should instead write:

        a|a = b|c           (correct)

    so that both fields have the same number of subentries.  The 'invert' field is used to invert the truth value of the
    condition so that a=b becomes a!=b.  Note that you need to properly apply De Morgan's Law yourself to make sure any
    preconditions utilizing the 'or' operator have the correct meaning when applied.
    """
    answerPrecondition = models.ForeignKey(AnswerPrecondition, db_index=True, on_delete=models.CASCADE)
    invert = models.BooleanField()
    key = models.TextField()
    value = models.TextField()

class TextBlob(models.Model):
    user = models.ForeignKey(User, null=True, db_index=True, on_delete=models.CASCADE)
    dateTime = models.DateTimeField(auto_now_add=True)
    markdownText = models.TextField()
    score = models.IntegerField(default=0)

    #Generic FK to the object this text blob is for.
    #TODO: Add a reverse generic relation to the relevant classes this will link to (Image, etc).
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    linkedObject = GenericForeignKey('content_type', 'object_id')

    # This reverse relation links back to the class itself to allow comments on other
    # comments (i.e. threaded comments).
    comments = GenericRelation('TextBlob')

    class Meta:
        ordering = ['-score', 'dateTime']

    def __str__(self):
        return markdown.markdown(self.markdownText, safe_mode='escape')

    def contextUrl(self):
        if self.linkedObject is None:
            return None

        # If this links to another text blob then is is a reply to a comment, so we recursively
        # call this function to return where that comment was made.
        if isinstance(self.linkedObject, TextBlob):
            return self.linkedObject.contextUrl()

        if isinstance(self.linkedObject, BookmarkableItem):
            return self.linkedObject.getUrl()

        return None

class CommentModeration(models.Model):
    user = models.ForeignKey(User, null=True, db_index=True, on_delete=models.CASCADE)
    modValue = models.TextField(db_index=True)
    comment = models.ForeignKey('TextBlob', on_delete=models.CASCADE, related_name='moderations')
    dateTime = models.DateTimeField(auto_now_add=True)

class CommentFlag(models.Model):
    user = models.ForeignKey(User, null=True, db_index=True, on_delete=models.CASCADE)
    flagValue = models.TextField(db_index=True)
    comment = models.ForeignKey('TextBlob', on_delete=models.CASCADE, related_name='flags')
    dateTime = models.DateTimeField(auto_now_add=True)

class CommentNeedsResponse(models.Model):
    user = models.ForeignKey(User, null=True, db_index=True, on_delete=models.CASCADE)
    responseValue = models.TextField(db_index=True)
    comment = models.ForeignKey('TextBlob', on_delete=models.CASCADE, related_name='needsResponses')
    dateTime = models.DateTimeField(auto_now_add=True)

class SavedQuery(models.Model):
    name = models.TextField(null=True, db_index=True, unique=True)
    user = models.ForeignKey(User, null=True, db_index=True, on_delete=models.CASCADE)
    dateTime = models.DateTimeField(auto_now_add=True)
    text = models.ForeignKey(TextBlob, on_delete=models.CASCADE)
    header = models.TextField()
    queryParams = models.TextField()

class SiteCost(models.Model):
    user = models.ForeignKey(User, null=True, db_index=True, on_delete=models.CASCADE)
    dateTime = models.DateTimeField()
    text = models.TextField()
    cost = models.FloatField(blank=True)

class SiteDonation(models.Model):
    user = models.ForeignKey(User, null=True, db_index=True, on_delete=models.CASCADE)
    dateTime = models.DateTimeField(auto_now_add=True)
    text = models.TextField()
    amount = models.FloatField(blank=True)

class CostTotal(models.Model):
    user = models.ForeignKey(User, null=True, db_index=True, on_delete=models.CASCADE)
    startDate = models.DateTimeField(null=False, db_index=True)
    endDate = models.DateTimeField(null=False, db_index=True)
    text = models.TextField()
    cost = models.FloatField(null=False, blank=True)

