import math

from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType

from .tasks import computeSingleEphemeris

#TODO:  Need to review the on_delete behaviour of all foreign keys to guarantee references remain intact as needed.

#TODO:  Set a related_name for all foreign keys and use that in the code where appropriate to make the code more readable.

#TODO:  Need to review the null constraint for all fields and try to minimize use of null=True, this is best done after the database is in a more stable state.

class InstrumentComponent(models.Model):
    """
    An abstract base class containing the fields common to all hardware that makes up an instrument.  I.E. a mounting
    pier, a mount, and OTA, a camera, etc.

    Records of this type cannot be created directly and there is no actual table for this type in the database.  Rather one
    of the child classes derived from this is actually created and stored in the corresponding table.  Having this base
    class avoids duplicating code for the common fields in each derived child record type, but it also allows code
    manipulating those results to have a guarantee that certain fields are present on any of the found sources.
    """
    make = models.CharField(max_length=64, null=True, blank=True)
    model = models.CharField(max_length=64, null=True, blank=True)

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

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    attachedTo = models.ForeignKey("ComponentInstance", on_delete=models.CASCADE)
    serialNumber = models.TextField(null=True)
    dateOnline = models.DateField(null=True, blank=True)
    dateOffline = models.DateField(null=True, blank=True)

class OTA(InstrumentComponent):
    """
    An Optical tube assembly that forms the core of the optical path of an instrument.
    """
    focalLength = models.FloatField(null=True, blank=True)
    aperture = models.FloatField(null=True, blank=True)
    design = models.CharField(max_length=64, null=True, blank=True)

class OTAPort(models.Model):
    """
    A port for a camera or eyepiece to be attached to an OTA.
    """
    ota = models.ForeignKey(OTA, on_delete=models.CASCADE)
    diameter = models.FloatField(null=True, blank=True)
    location = models.CharField(max_length=64, null=True, blank=True)
    extraOptics = models.CharField(max_length=64, null=True, blank=True)

class Eyepiece(models.Model):
    """
    An eyepiece to be inserted into a telescope for visual observations.
    """
    diameter = models.FloatField(null=True, blank=True)
    focalLength = models.FloatField(null=True, blank=True)
    apparentFOV = models.FloatField(null=True, blank=True)

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

class Mount(models.Model):
    """
    The moving mount that a telescope OTA and all connected components ride on.
    """
    make = models.CharField(max_length=64, null=True, blank=True)
    model = models.CharField(max_length=64, null=True, blank=True)
    mountType = models.CharField(max_length=64, null=True, blank=True)
    mountedOn = models.CharField(max_length=64, null=True, blank=True)

#TODO: Delete this class.
class Instrument(models.Model):
    """
    An entire assembled telescope optical path.  A single telescope may consist of multiple instruments which have common
    optical paths for some portion of the setup.
    """
    mount = models.ForeignKey(Mount, on_delete=models.CASCADE)
    ota = models.ForeignKey(OTA, on_delete=models.CASCADE)
    #TODO: Camera and eyepiece should probably be subclassed and then turn this to a single foreign key
    eyepiece = models.ForeignKey(Eyepiece, on_delete=models.CASCADE)
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE)



#TODO: Add a class for an observing session storing details about equipment used, weather, seeing, goals, etc.


class Profile(models.Model):
    """
    Extra user profile information not stored by the default Django User record.  The two 'reciever' functions below hook
    into updates to the User table and automatically create/update the Profile table as needed.  Care needs to be taken to
    make sure User updates are done through the standard Django methods to ensure that these receiver functions get called
    and the tables are kept in sync.  I.E. no raw sql queries to the User table, etc.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    defaultObservatory = models.ForeignKey('Observatory', on_delete=models.CASCADE, null=True)
    birthDate = models.DateField(null=True, blank=True)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

class Bookmark(models.Model):
    """
    A class storing a GenericForeignKey relation to an object to act as a bookmark.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    folders = models.ManyToManyField('BookmarkFolder', symmetrical=False, related_name='folderItems', through='BookmarkFolderLink')

    #Generic FK to image or object or whatever the bookmark is linking to.
    #TODO: Add a reverse generic relation to the relevant classes this will link to (image, asteroid, star, etc).
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    @property
    def getObjectTypeString(self):
        stringDict = {
            'astorbrecord': 'asteroid',
            'exoplanetrecord': 'exoplanet',
            'gcvsrecord': 'variableStar',
            'messierrecord': 'messierObject',
            'twomassxscrecord': '2MassXSC'
            }

        t = ContentType.objects.get(pk=self.content_type.pk)

        return stringDict[t.model]

    @property
    def getObjectTypeCommonName(self):
        stringDict = {
            'astorbrecord': 'Asteroid',
            'exoplanetrecord': 'Exoplanet',
            'gcvsrecord': 'Variable Star',
            'messierrecord': 'Messier Object',
            'twomassxscrecord': 'Deep Sky Object'
            }

        t = ContentType.objects.get(pk=self.content_type.pk)

        return stringDict[t.model]

class BookmarkFolder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=256, null=True)
    dateTime = models.DateTimeField(auto_now=True)

class BookmarkFolderLink(models.Model):
    bookmark = models.ForeignKey(Bookmark, on_delete=models.CASCADE)
    folder = models.ForeignKey(BookmarkFolder, on_delete=models.CASCADE)
    dateTime = models.DateTimeField(auto_now=True)

class BookmarkableItem:
    """
    A base class that any models defined from on this page should also inherit from (in addition to models.Model).
    This contains common base functionality required for displaying lists of bookmarks when the items in the list are
    of differing types.  I.E. it normalizes the display so that differing types can be displayed in a common format.
    """
    @property
    def getDisplayName(self):
        return "getDisplayName uniplemented"

class SkyObject:
    """
    A base class to inherit from for any object that has a presense in the sky that can be derived at a given time.
    This could be a fixed object like a star, or could be a moving object like a planet or asteroid, or something like
    an image with known sky coordinates.
    """
    def getSkyCoords(self, dateTime):
        return (None, None)

class Observatory(models.Model):
    """
    A record storing the location and other basic information for an observing location.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=256, null=True)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    elevation = models.FloatField(null=True, blank=True)



class UploadedFileRecord(models.Model):
    """
    A record storing information about any type of file uploaded by a user to the site.  The original file name, size,
    hash, etc are stored here as well as onDiskFileName which is the name django assigns to our copy of the file (to handle
    multiple uploads of the same file, etc).
    """
    uploadingUser = models.ForeignKey(User, on_delete=models.CASCADE)
    unpackedFromFile = models.ForeignKey('self', null=True, on_delete=models.CASCADE)
    originalFileName = models.CharField(max_length=256)
    onDiskFileName = models.CharField(max_length=256)
    fileSha256 = models.CharField(max_length=64)
    uploadDateTime = models.DateTimeField()
    uploadSize = models.IntegerField()

class Image(models.Model, SkyObject):
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
    fileRecord = models.ForeignKey(UploadedFileRecord, on_delete=models.PROTECT, null=True)
    parentImages = models.ManyToManyField('self', symmetrical=False, related_name='childImages')
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, null=True)
    observatory = models.ForeignKey(Observatory, on_delete=models.PROTECT, null=True)
    dimX = models.IntegerField(null=True)
    dimY = models.IntegerField(null=True)
    dimZ = models.IntegerField(null=True)
    bitDepth = models.IntegerField(null=True)
    frameType = models.CharField(max_length=32)
    dateTime = models.DateTimeField(null=True)
    answers = GenericRelation('Answer')

    def getSkyCoords(self, dateTime):
        ps = self.getBestPlateSolution()
        return (ps.centerRA, ps.centerDec)

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
    #TODO: Include image channel in the thumbnail selection.  Make this a pipe char separated list to allow multiple
    # channels to be returned at once to save on requests.
    def getThumbnailUrl(self, sizeString, hintWidth=-1, hintHeight=-1, stretch='false'):
        #TODO: Specify an image with something like "thumbnail not found" to display in place of this thumbnail.
        thumbnailNotFound = ""

        # Select a list of all the thumbnails for this image and return the error image if no thumbnails have been generated yet.
        try:
            records = ImageThumbnail.objects.filter(image__pk=self.pk).order_by('width')
        except:
            return thumbnailNotFound

        #TODO: Delete this?  Should be covered by the try-except block above, not sure why it is still here.
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
        return '/static/cosmicapp/images/' + record.filename

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
        return self.plateSolutions.first()

class ImageThumbnail(models.Model):
    """
    A record containing details about an individual thumbnail for an image on the site.  Each uploaded image gets multiple
    size thumbnails made of it, each with its own ImageThumbnail record.
    """
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
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

    For most uses on the site (queries, sorting, etc) you should not use thes records directly, but should instead use
    ImageProperty records, which are sanitized versions of these headers.  Each image property record links back to the
    ImageHeaderField it was derived from in case you need the exact data after you query.

    The 'index' field of the record stores a running number counting up from 0 in the order the header fields were read in.
    The idea here is that we may be able to identify particular software packages by the order in which the header fields
    are stored in the file.

    #TODO:  Some checking needs to be done on the index field.  I am storing them in the order that image magic spits them
    out, however the order it gives (at least for fits files) differs from other tools to list headers.  So this index
    number may not be trustworthy without changing to a different tool for the actual reading of the headers.
    """
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    index = models.IntegerField(null=True)
    key = models.TextField(null=True)
    value = models.TextField(null=True)

class ImageProperty(models.Model):
    """
    A record storing sanitized and normalized image metadata key value pairs.  Most of these records will be derived from
    one or possibly several ImageHeaderField records and the 'header' field will link back to the source field.  For some,
    it may be the case that there is no source header field in which case this field will be null (for example in the case
    of metadata added by the site itself or by a user on the site for information that was not present in the uploaded
    file, e.g. frame type, seeing conditions, etc).
    """
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name='properties')
    header = models.ForeignKey(ImageHeaderField, on_delete=models.CASCADE, null=True)  #TODO: Make this many to many?
    key = models.TextField()
    value = models.TextField()

class ImageChannelInfo(models.Model):
    """
    A record representing the statistical measurements of a single channel of an image.  The channelType field represents
    what color channel the image represents (if it was taken from a color image with known red-green-blue channels, or will
    be grey for most other channels where the colorspace is not known.  Additionally we store the standard statistics
    (mean, median, and standard deviation) of the channel as well as the same statistics for just the background (i.e.
    after source removal by sigma clipping or other methods).
    """
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    index = models.IntegerField()
    channelType = models.CharField(max_length=16)
    mean = models.FloatField(null=True)
    median = models.FloatField(null=True)
    stdDev = models.FloatField(null=True)
    bgMean = models.FloatField(null=True)
    bgMedian = models.FloatField(null=True)
    bgStdDev = models.FloatField(null=True)

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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    referenceImage = models.ForeignKey(Image, on_delete=models.CASCADE, related_name='transformReferences')
    subjectImage = models.ForeignKey(Image, on_delete=models.CASCADE, related_name='transformSubjects')
    m00 = models.FloatField()
    m01 = models.FloatField()
    m02 = models.FloatField()
    m10 = models.FloatField()
    m11 = models.FloatField()
    m12 = models.FloatField()

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
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name='plateSolutions')
    wcsHeader = models.TextField()
    source = models.CharField(max_length=32)
    centerRA = models.FloatField(null=True)
    centerDec = models.FloatField(null=True)
    centerRot = models.FloatField(null=True)
    resolutionX = models.FloatField(null=True)
    resolutionY = models.FloatField(null=True)
    geometry = models.PolygonField(srid=40000, geography=False, dim=2, null=True)
    area = models.FloatField(null=True)




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
    prerequisites = models.ManyToManyField('self', symmetrical=False)
    process = models.CharField(max_length=32)
    requestor = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    submittedDateTime = models.DateTimeField()
    startedDateTime = models.DateTimeField(null=True)
    priority = models.FloatField(null=True)
    estCostCPU = models.FloatField(null=True)
    estCostBandwidth = models.BigIntegerField(null=True)
    estCostStorage = models.BigIntegerField(null=True)
    estCostIO = models.BigIntegerField(null=True)
    completed = models.TextField(null=True, default=None)
    #NOTE: We may want to add a field or an auto computed field for whether the process can be run now or not.  I.E.
    # whether it has any unmet prerequisites.

    class Meta:
        ordering = ['-priority', 'submittedDateTime']

    def addArguments(self, argList):
        for arg in argList:
            i = 1
            pa = ProcessArgument(
                processInput = self,
                argIndex = i,
                arg = str(arg)
                )

            pa.save()
            i += 1

class ProcessOutput(models.Model):
    processInput = models.ForeignKey(ProcessInput, on_delete=models.CASCADE)
    finishedDateTime = models.DateTimeField(null=True)
    actualCostCPU = models.FloatField(null=True)
    actualCostBandwidth = models.FloatField(null=True)
    actualCostStorage = models.FloatField(null=True)
    actualCostIO = models.FloatField(null=True)
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
    processInput = models.ForeignKey(ProcessInput, on_delete=models.CASCADE)
    argIndex = models.IntegerField()
    arg = models.CharField(max_length=256)

class ProcessOutputFile(models.Model):
    processInput = models.ForeignKey(ProcessInput, on_delete=models.CASCADE)
    onDiskFileName = models.CharField(max_length=256)
    fileSha256 = models.CharField(max_length=64)
    size = models.IntegerField()





class SourceFindResult(models.Model):
    """
    An abstract base class containing the fields common to all source finding methods, such as position and confidence.
    Records of this type cannot be created directly and there is no actual table for this type in the database.  Rather one
    of the child classes derived from this is actually created and stored in the corresponding table.  Having this base
    class avoids duplicating code for the common fields in each derived child record type, but it also allows code
    manipulating those results to have a guarantee that certain fields are present on any of the found sources, no matter
    the algorithm used to detect them.
    """
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    pixelX = models.FloatField(null=True)
    pixelY = models.FloatField(null=True)
    pixelZ = models.FloatField(null=True)
    confidence = models.FloatField(null=True)

    class Meta:
        abstract = True

class SextractorResult(SourceFindResult):
    """
    A record storing a single source detected in an image by the Source Extractor program.
    """
    fluxAuto = models.FloatField(null=True)
    fluxAutoErr = models.FloatField(null=True)
    flags = models.IntegerField(null=True)

class Image2xyResult(SourceFindResult):
    """
    A record storing a single source detected in an image by the image2xy program.
    """
    flux = models.FloatField(null=True)
    background = models.FloatField(null=True)

class DaofindResult(SourceFindResult):
    """
    A record storing a single source detected in an image by the daofind algorithm (part of astropy).
    """
    mag = models.FloatField(null=True)
    flux = models.FloatField(null=True)
    peak = models.FloatField(null=True)
    sharpness = models.FloatField(null=True)
    sround = models.FloatField(null=True)
    ground = models.FloatField(null=True)

class StarfindResult(SourceFindResult):
    """
    A record storing a single source detected in an image by the starfind algorithm (part of astropy).
    """
    mag = models.FloatField(null=True)
    peak = models.FloatField(null=True)
    flux = models.FloatField(null=True)
    fwhm = models.FloatField(null=True)
    roundness = models.FloatField(null=True)
    pa = models.FloatField(null=True)
    sharpness = models.FloatField(null=True)

class SourceFindMatch(SourceFindResult):
    """
    A record storing links to the individual SourceFindResult records for sources which are found at the same location in
    an image by two or more individual source find methods.  The confidence of the match is taken to be the "geometric mean"
    of the confidence values of the individual matched results.
    """
    numMatches = models.IntegerField()
    sextractorResult = models.ForeignKey(SextractorResult, null=True, on_delete=models.CASCADE)
    image2xyResult = models.ForeignKey(Image2xyResult, null=True, on_delete=models.CASCADE)
    daofindResult = models.ForeignKey(DaofindResult, null=True, on_delete=models.CASCADE)
    starfindResult = models.ForeignKey(StarfindResult, null=True, on_delete=models.CASCADE)



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

class UCAC4Record(models.Model):
    """
    A record storing a single entry from the UCAC4 catalog of stars.
    """
    identifier = models.CharField(max_length=10, null=True)
    ra = models.FloatField(null=True)
    dec = models.FloatField(null=True)
    geometry = models.PointField(srid=40000, geography=False, dim=2, null=True)
    pmra = models.FloatField(null=True)
    pmdec = models.FloatField(null=True)
    magFit = models.FloatField(null=True)
    magAperture = models.FloatField(null=True)
    magError = models.FloatField(null=True)
    id2mass = models.CharField(max_length=10, null=True)

class GCVSRecord(models.Model, BookmarkableItem, SkyObject):
    """
    A record storing a single entry from the General Catalog of Variable Stars.
    """
    constellationNumber = models.CharField(max_length=2, null=True)
    starNumber = models.CharField(max_length=5, null=True)
    identifier = models.CharField(max_length=10, null=True)
    ra = models.FloatField(null=True, db_index=True)
    dec = models.FloatField(null=True, db_index=True)
    geometry = models.PointField(srid=40000, geography=False, dim=2, null=True)
    pmRA = models.FloatField(null=True)
    pmDec = models.FloatField(null=True)
    variableType = models.CharField(max_length=10, null=True)
    variableType2 = models.CharField(max_length=10, null=True)
    magMax = models.FloatField(null=True)
    magMaxFlag = models.CharField(max_length=1, null=True)
    magMin = models.FloatField(null=True)
    magMinFlag = models.CharField(max_length=1, null=True)
    magMin2 = models.FloatField(null=True)
    magMin2Flag = models.CharField(max_length=1, null=True)
    epochMaxMag = models.FloatField(null=True)  #NOTE: This can be a max or a min depending on the variable type.
    outburstYear = models.FloatField(null=True)
    period = models.FloatField(null=True)
    periodRisingPercentage = models.FloatField(null=True)
    spectralType = models.CharField(max_length=17, null=True)
    bookmarks = GenericRelation('Bookmark')

    def getSkyCoords(self, dateTime):
        return (self.ra, self.dec)

    @property
    def getDisplayName(self):
        return self.identifier

class TwoMassXSCRecord(models.Model, BookmarkableItem, SkyObject):
    """
    A record storing a single entry from the 2MASS Extended Source Catalog of "extended", i.e. non point source, objects.
    """
    identifier = models.CharField(max_length=24)
    ra = models.FloatField(db_index=True)
    dec = models.FloatField(db_index=True)
    #TODO: Should probably make this geometry field a polygon, or add a second geometry field for the polygon and leave this as a point.  Not sure which would be better.
    geometry = models.PointField(srid=40000, geography=False, dim=2, null=True)
    isophotalKSemiMajor = models.FloatField(null=True)
    isophotalKMinorMajor = models.FloatField(null=True)
    isophotalKAngle = models.FloatField(null=True)
    isophotalKMag = models.FloatField(null=True, db_index=True)
    isophotalKMagErr = models.FloatField(null=True)
    bookmarks = GenericRelation('Bookmark')

    def getSkyCoords(self, dateTime):
        return (self.ra, self.dec)

    @property
    def getDisplayName(self):
        return self.identifier

class MessierRecord(models.Model, BookmarkableItem, SkyObject):
    """
    A record storing a single entry from the Messier Catalog.
    """
    identifier = models.CharField(max_length=24)
    ra = models.FloatField()
    dec = models.FloatField()
    geometry = models.PointField(srid=40000, geography=False, dim=2, null=True)
    objectType = models.CharField(max_length=3)
    spectralType = models.CharField(max_length=10, null=True)
    magU = models.FloatField(null=True)
    magB = models.FloatField(null=True)
    magV = models.FloatField(null=True)
    magR = models.FloatField(null=True)
    magI = models.FloatField(null=True)
    numReferences = models.IntegerField()
    bookmarks = GenericRelation('Bookmark')

    def getSkyCoords(self, dateTime):
        return (self.ra, self.dec)

    @property
    def getDisplayName(self):
        return self.identifier

class AstorbRecord(models.Model, BookmarkableItem, SkyObject):
    """
    A record storing a the Keplerian orbital elements and physical properties for a single asteroid from the astorb database.
    """
    number = models.IntegerField(null=True)
    name = models.CharField(max_length=18)
    absMag = models.FloatField()
    slopeParam = models.FloatField()
    colorIndex = models.FloatField(null=True)
    diameter = models.FloatField(null=True)
    taxanomicClass = models.CharField(max_length=7)
    orbitCode = models.IntegerField()
    criticalCode = models.IntegerField()
    astrometryNeededCode = models.IntegerField()
    observationArc = models.IntegerField()
    numObservations = models.IntegerField()
    epoch = models.DateField()
    meanAnomaly = models.FloatField()
    argPerihelion = models.FloatField()
    lonAscendingNode = models.FloatField()
    inclination = models.FloatField()
    eccentricity = models.FloatField()
    semiMajorAxis = models.FloatField()
    ceu = models.FloatField()
    ceuRate = models.FloatField()
    ceuDate = models.DateField(null=True)
    nextPEU = models.FloatField()
    nextPEUDate = models.DateField(null=True)
    tenYearPEU = models.FloatField()
    tenYearPEUDate = models.DateField(null=True)
    tenYearPEUIfObserved = models.FloatField()
    tenYearPEUDateIfObserved = models.DateField(null=True)
    bookmarks = GenericRelation('Bookmark')

    def getSkyCoords(self, dateTime):
        ephemeris = computeSingleEphemeris(self, dateTime)
        return (ephemeris.ra*180/math.pi, ephemeris.dec*180/math.pi)

    @property
    def getDisplayName(self):
        if self.number != None:
            ret = str(self.number) + ' - ' + self.name
        else:
            ret = self.name

        return ret

#TODO: This should probably inherit from SkyObject as well, need to add that and implement the function if it is deemed appropriate.
class AstorbEphemeris(models.Model):
    """
    A record containing a computed emphemeride path for an asteroid in the astorb database.  The AstorbRecord is read
    in from the database for the given asteroid, and pyephem is used to convert the Keplerian orbit into a series of
    RA-DEC ephemerides which is then stored in the AstorbEphemeris record.  In addition to the position on the sky
    (stored as a line geometry over the given time span), the min and max apparent magnitude over the interval is
    stored.
    """
    astorbRecord = models.ForeignKey(AstorbRecord, on_delete=models.CASCADE)
    startTime = models.DateTimeField(null=True)
    endTime = models.DateTimeField(null=True)
    dimMag = models.FloatField(db_index=True, null=True)
    brightMag = models.FloatField(db_index=True, null=True)
    geometry = models.LineStringField(srid=40000, geography=False, dim=2, null=True)

class ExoplanetRecord(models.Model, BookmarkableItem, SkyObject):
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
    geometry = models.PointField(srid=40000, geography=False, dim=2, null=True)
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

    def getSkyCoords(self, dateTime):
        return (self.ra, self.dec)

    @property
    def getDisplayName(self):
        return self.identifier



class GeoLiteLocation(models.Model):
    """
    A record storing a location (lat, lon, and city name) for an entry in the GeoLite Geolocation database.  The database
    is used for determining the approximate location of non-logged in users for things like the observation planning tool.
    The GeoLite database consists of two tables.  This one stores locations and city names, and then these entries are
    linked to from GeoLiteBlock records, which are IP block ranges.
    """
    id = models.IntegerField(primary_key=True)
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
    priority = models.IntegerField()
    previousVersion = models.ForeignKey('self', null=True, on_delete=models.CASCADE, related_name='laterVersion')
    prerequisites = models.ManyToManyField('self', symmetrical=False, through='AnswerPrecondition',
        through_fields=('firstQuestion', 'secondQuestion'))

class QuestionResponse(models.Model):
    """
    A record containing a single response option for a question.  The record contains the text to be shown for the response,
    as well as a short description of what the response means in more specific terms.  The index field is a running
    integer, counting up, which dictates the order in which the multiple responses for a given question will be displayed.
    The inputType field, which is a string interpreted by the question view, dictates what type of UI element to display
    with this response (checkbox, radiobutton, etc).  Lastly, the keyToSet and valueToSet fields describe the key-value
    components of an AnswerKV record which will be created and stored linking (indirectly) to the object the question was about.
    """
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
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
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

class AnswerKV(models.Model):
    """
    A record storing a simple key-value pair containing the actual answer to a question submitted to the site by a user.
    The record links back to an Answer record containing the metadata for the answer.  Both the key and value fields are
    text fields of arbitrary length.
    """
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name='kvs')
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
    firstQuestion = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='dependantQuestions')
    secondQuestion = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='dependsOnQuestions')

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
    answerPrecondition = models.ForeignKey(AnswerPrecondition, on_delete=models.CASCADE)
    invert = models.BooleanField()
    key = models.TextField()
    value = models.TextField()

