from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders

#TODO:  Need to review the on_delete behaviour of all foreign keys to guarantee references remain intact as needed.

#TODO:  Set a reated_name for all foreign keys and use that in the code where appropriate to make the code more readable.

"""
An Optical tube assembly that forms the core of the optical path of an instrument.
"""
class OTA(models.Model):
    make = models.CharField(max_length=64, null=True, blank=True)
    model = models.CharField(max_length=64, null=True, blank=True)
    focalLength = models.FloatField(null=True, blank=True)
    aperature = models.FloatField(null=True, blank=True)
    design = models.CharField(max_length=64, null=True, blank=True)

"""
A port for a camera or eyepiece to be attached to an OTA.
"""
class OTAPort(models.Model):
    ota = models.ForeignKey(OTA, on_delete=models.CASCADE)
    diameter = models.FloatField(null=True, blank=True)
    location = models.CharField(max_length=64, null=True, blank=True)
    extraOptics = models.CharField(max_length=64, null=True, blank=True)

"""
An eyepiece to be inserted into a telescope for visual observations.
"""
class Eyepiece(models.Model):
    diameter = models.FloatField(null=True, blank=True)
    focalLength = models.FloatField(null=True, blank=True)
    apparentFOV = models.FloatField(null=True, blank=True)

"""
A camera to be inserted into a telescope for recording observations.
"""
class Camera(models.Model):
    make = models.CharField(max_length=64, null=True, blank=True)
    model = models.CharField(max_length=64, null=True, blank=True)
    dimX = models.FloatField(null=True, blank=True)
    dimY = models.FloatField(null=True, blank=True)
    pixelDimX = models.FloatField(null=True, blank=True)
    pixelDimY = models.FloatField(null=True, blank=True)
    readNoise = models.FloatField(null=True, blank=True)
    ePerADU = models.FloatField(null=True, blank=True)
    exposureMin = models.FloatField(null=True, blank=True)
    exposureMax = models.FloatField(null=True, blank=True)
    coolingCapacity = models.FloatField(null=True, blank=True)

"""
The moving mount that a telescope OTA and all connected components ride on.
"""
class Mount(models.Model):
    make = models.CharField(max_length=64, null=True, blank=True)
    model = models.CharField(max_length=64, null=True, blank=True)
    mountType = models.CharField(max_length=64, null=True, blank=True)
    mountedOn = models.CharField(max_length=64, null=True, blank=True)

"""
An entire assembled telescope optical path.  A single telescope may consist of multiple instruments which have common
optical paths for some portion of the setup.
"""
class Instrument(models.Model):
    mount = models.ForeignKey(Mount, on_delete=models.CASCADE)
    ota = models.ForeignKey(OTA, on_delete=models.CASCADE)
    #TODO: Camera and eyepiece should probably be subclassed and then turn this to a single foreign key
    eyepiece = models.ForeignKey(Eyepiece, on_delete=models.CASCADE)
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE)





class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    homeLat = models.FloatField(null=True, blank=True)
    homeLon = models.FloatField(null=True, blank=True)
    birthDate = models.DateField(null=True, blank=True)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()




class UploadedFileRecord(models.Model):
    uploadingUser = models.ForeignKey(User, on_delete=models.CASCADE)
    unpackedFromFile = models.ForeignKey('self', null=True)
    originalFileName = models.CharField(max_length=256)
    onDiskFileName = models.CharField(max_length=256)
    fileSha256 = models.CharField(max_length=64)
    uploadDateTime = models.DateTimeField()
    uploadSize = models.IntegerField()

class Image(models.Model):
    fileRecord = models.ForeignKey(UploadedFileRecord, on_delete=models.PROTECT)
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, null=True)
    dimX = models.IntegerField(null=True)
    dimY = models.IntegerField(null=True)
    dimZ = models.IntegerField(null=True)
    bitDepth = models.IntegerField(null=True)
    frameType = models.CharField(max_length=32)
    centerRA = models.FloatField(null=True)
    centerDEC = models.FloatField(null=True)
    centerROT = models.FloatField(null=True)
    resolutionX = models.FloatField(null=True)
    resolutionY = models.FloatField(null=True)
    thumbnailFullName = models.CharField(max_length=256, null=True)
    thumbnailSmallName = models.CharField(max_length=256, null=True)

    def getThumbnail(self, sizeString):
        if sizeString == 'full':
            thumbBaseName = self.thumbnailFullName
        elif sizeString == 'small':
            thumbBaseName = self.thumbnailSmallName

        if finders.find("cosmicapp/images/" + thumbBaseName):
            url = staticfiles_storage.url("cosmicapp/images/" + thumbBaseName)
            return '<a href=/image/' + str(self.pk) + '><img src="' + url + '"></a>'
        else:
            filename = thumbBaseName[:-len(".png")]
            filename += "-0.png"
            url = staticfiles_storage.url("cosmicapp/images/" + filename)
            #TODO: Add javascript here to flip between different thumbnails.
            return '<a href=/image/' + str(self.pk) + '><img src="' + url + '"></a>'

    def getThumbnailFull(self):
        return self.getThumbnail("full")

    def getThumbnailSmall(self):
        return self.getThumbnail("small")

class ImageHeaderField(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    index = models.IntegerField(null=True)
    key = models.TextField(null=True)
    value = models.TextField(null=True)

class ImageChannelInfo(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    index = models.IntegerField()
    channelType = models.CharField(max_length=16)




class ProcessInput(models.Model):
    prerequisite = models.ManyToManyField('self', symmetrical=False)
    process = models.CharField(max_length=32)
    requestor = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    submittedDateTime = models.DateTimeField()
    startedDateTime = models.DateTimeField(null=True)
    priority = models.FloatField(null=True)
    estCostCPU = models.FloatField(null=True)
    estCostBandwidth = models.FloatField(null=True)
    estCostStorage = models.FloatField(null=True)
    estCostIO = models.FloatField(null=True)
    completed = models.BooleanField(default=False)
    #NOTE: We may want to add a field or an auto computed field for whether the process can be run now or not.  I.E.
    # whether it has any unmet prerequisites.

    class Meta:
        ordering = ['-priority', 'submittedDateTime']

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
    processInput = models.ForeignKey(ProcessInput, on_delete=models.CASCADE)
    argIndex = models.IntegerField()
    arg = models.CharField(max_length=256)

class ProcessOutputFile(models.Model):
    processInput = models.ForeignKey(ProcessInput, on_delete=models.CASCADE)
    onDiskFileName = models.CharField(max_length=256)
    fileSha256 = models.CharField(max_length=64)
    size = models.IntegerField()





class SextractorResult(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    pixelX = models.FloatField(null=True)
    pixelY = models.FloatField(null=True)
    pixelZ = models.FloatField(null=True)
    fluxAuto = models.FloatField(null=True)
    fluxAutoErr = models.FloatField(null=True)
    flags = models.IntegerField(null=True)



class Catalog(models.Model):
    name = models.CharField(max_length=64, null=True)
    fullName = models.CharField(max_length=64, null=True)
    objectTypes = models.TextField(null=True)
    numObjects = models.TextField(null=True)
    limMagnitude = models.FloatField(null=True)
    attributionShort = models.TextField(null=True)
    attributionLong = models.TextField(null=True)
    vizierID = models.TextField(null=True)
    vizierUrl = models.TextField(null=True)

class UCAC4Record(models.Model):
    identifier = models.CharField(max_length=10, null=True)
    ra = models.FloatField(null=True)
    dec = models.FloatField(null=True)
    pmra = models.FloatField(null=True)
    pmdec = models.FloatField(null=True)
    magFit = models.FloatField(null=True)
    magAperture = models.FloatField(null=True)
    magError = models.FloatField(null=True)
    id2mass = models.CharField(max_length=32, null=True)

