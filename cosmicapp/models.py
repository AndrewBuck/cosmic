from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType

#TODO:  Need to review the on_delete behaviour of all foreign keys to guarantee references remain intact as needed.

#TODO:  Set a reated_name for all foreign keys and use that in the code where appropriate to make the code more readable.

"""
An Optical tube assembly that forms the core of the optical path of an instrument.
"""
class OTA(models.Model):
    make = models.CharField(max_length=64, null=True, blank=True)
    model = models.CharField(max_length=64, null=True, blank=True)
    focalLength = models.FloatField(null=True, blank=True)
    aperture = models.FloatField(null=True, blank=True)
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
    elevation = models.FloatField(null=True, blank=True)
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
    fileRecord = models.ForeignKey(UploadedFileRecord, on_delete=models.PROTECT, null=True)
    parentImages = models.ManyToManyField('self', symmetrical=False, related_name='childImages')
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, null=True)
    dimX = models.IntegerField(null=True)
    dimY = models.IntegerField(null=True)
    dimZ = models.IntegerField(null=True)
    bitDepth = models.IntegerField(null=True)
    frameType = models.CharField(max_length=32)
    centerRA = models.FloatField(null=True)
    centerDec = models.FloatField(null=True)
    centerRot = models.FloatField(null=True)
    resolutionX = models.FloatField(null=True)
    resolutionY = models.FloatField(null=True)
    answers = GenericRelation('Answer')

    def getThumbnailUrl(self, sizeString, hintWidth=-1, hintHeight=-1, stretch='false'):
        #TODO: Specify an image with something like "thumbnail not found" to display in place of this thumbnail.
        thumbnailNotFound = ""

        try:
            records = ImageThumbnail.objects.filter(image__pk=self.pk).order_by('width')
        except:
            return thumbnailNotFound

        if len(records) == 0:
            return thumbnailNotFound

        if hintWidth != -1 and hintHeight != -1:
            for i in range(len(records)):
                if records[i].size == sizeString:
                    record = records[i]
                    break

                if records[i].width >= hintWidth and records[i].height >= hintHeight:
                    if stretch == 'true' and i > 0:
                        record = records[i-1]
                    else:
                        record = records[i]
                    break;
            else:
                record = records[len(records)-1]
        else:
            for i in range(len(records)):
                if records[i].size == sizeString:
                    record = records[i]
                    break
            else:
                return thumbnailNotFound

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

class ImageThumbnail(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    size = models.CharField(max_length=10)
    width = models.IntegerField()
    height = models.IntegerField()
    channel = models.IntegerField()
    filename = models.CharField(max_length=256)

class ImageHeaderField(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    index = models.IntegerField(null=True)
    key = models.TextField(null=True)
    value = models.TextField(null=True)

class ImageChannelInfo(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    index = models.IntegerField()
    channelType = models.CharField(max_length=16)
    mean = models.FloatField(null=True)
    median = models.FloatField(null=True)
    stdDev = models.FloatField(null=True)
    bgMean = models.FloatField(null=True)
    bgMedian = models.FloatField(null=True)
    bgStdDev = models.FloatField(null=True)

class ImageProperty(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name='properties')
    header = models.ForeignKey(ImageHeaderField, on_delete=models.CASCADE, null=True)
    key = models.TextField()
    value = models.TextField()

class ImageTransform(models.Model):
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
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    wcsHeader = models.TextField()
    source = models.CharField(max_length=32)




class ProcessInput(models.Model):
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
                arg = arg
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
    processInput = models.ForeignKey(ProcessInput, on_delete=models.CASCADE)
    argIndex = models.IntegerField()
    arg = models.CharField(max_length=256)

class ProcessOutputFile(models.Model):
    processInput = models.ForeignKey(ProcessInput, on_delete=models.CASCADE)
    onDiskFileName = models.CharField(max_length=256)
    fileSha256 = models.CharField(max_length=64)
    size = models.IntegerField()





class SourceFindResult(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE)
    pixelX = models.FloatField(null=True)
    pixelY = models.FloatField(null=True)
    pixelZ = models.FloatField(null=True)
    confidence = models.FloatField(null=True)

    class Meta:
        abstract = True

class SextractorResult(SourceFindResult):
    fluxAuto = models.FloatField(null=True)
    fluxAutoErr = models.FloatField(null=True)
    flags = models.IntegerField(null=True)

class Image2xyResult(SourceFindResult):
    flux = models.FloatField(null=True)
    background = models.FloatField(null=True)

class DaofindResult(SourceFindResult):
    mag = models.FloatField(null=True)
    flux = models.FloatField(null=True)
    peak = models.FloatField(null=True)
    sharpness = models.FloatField(null=True)
    sround = models.FloatField(null=True)
    ground = models.FloatField(null=True)

class StarfindResult(SourceFindResult):
    mag = models.FloatField(null=True)
    peak = models.FloatField(null=True)
    flux = models.FloatField(null=True)
    fwhm = models.FloatField(null=True)
    roundness = models.FloatField(null=True)
    pa = models.FloatField(null=True)
    sharpness = models.FloatField(null=True)

class SourceFindMatch(SourceFindResult):
    numMatches = models.IntegerField()
    sextractorResult = models.ForeignKey(SextractorResult, null=True, on_delete=models.CASCADE)
    image2xyResult = models.ForeignKey(Image2xyResult, null=True, on_delete=models.CASCADE)
    daofindResult = models.ForeignKey(DaofindResult, null=True, on_delete=models.CASCADE)
    starfindResult = models.ForeignKey(StarfindResult, null=True, on_delete=models.CASCADE)



#TODO: Create a base class for catalog object entries with some standard params in it to make querying more uniform.
class Catalog(models.Model):
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
    identifier = models.CharField(max_length=10, null=True)
    ra = models.FloatField(null=True)
    dec = models.FloatField(null=True)
    pmra = models.FloatField(null=True)
    pmdec = models.FloatField(null=True)
    magFit = models.FloatField(null=True)
    magAperture = models.FloatField(null=True)
    magError = models.FloatField(null=True)
    id2mass = models.CharField(max_length=10, null=True)

class GCVSRecord(models.Model):
    constellationNumber = models.CharField(max_length=2, null=True)
    starNumber = models.CharField(max_length=5, null=True)
    identifier = models.CharField(max_length=10, null=True)
    ra = models.FloatField(null=True, db_index=True)
    dec = models.FloatField(null=True, db_index=True)
    pmRa = models.FloatField(null=True)
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

class TwoMassXSCRecord(models.Model):
    identifier = models.CharField(max_length=24)
    ra = models.FloatField(db_index=True)
    dec = models.FloatField(db_index=True)
    isophotalKSemiMajor = models.FloatField(null=True)
    isophotalKMinorMajor = models.FloatField(null=True)
    isophotalKAngle = models.FloatField(null=True)
    isophotalKMag = models.FloatField(null=True, db_index=True)
    isophotalKMagErr = models.FloatField(null=True)

class MessierRecord(models.Model):
    identifier = models.CharField(max_length=24)
    ra = models.FloatField()
    dec = models.FloatField()
    objectType = models.CharField(max_length=3)
    spectralType = models.CharField(max_length=10, null=True)
    magU = models.FloatField(null=True)
    magB = models.FloatField(null=True)
    magV = models.FloatField(null=True)
    magR = models.FloatField(null=True)
    magI = models.FloatField(null=True)
    numReferences = models.IntegerField()

class AstorbRecord(models.Model):
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

class AstorbEphemeris(models.Model):
    astorbRecord = models.ForeignKey(AstorbRecord, on_delete=models.CASCADE)
    dateTime = models.DateTimeField()
    ra = models.FloatField(db_index=True)
    dec = models.FloatField(db_index=True)
    earthDist = models.FloatField()
    sunDist = models.FloatField()
    mag = models.FloatField(db_index=True)
    elong = models.FloatField()

class ExoplanetRecord(models.Model):
    identifier = models.CharField(max_length=32, null=True)
    identifier2 = models.CharField(max_length=32, null=True)
    starIdentifier = models.CharField(max_length=32, null=True)
    component = models.CharField(max_length=2, null=True)
    numComponents = models.IntegerField(null=True)
    ra = models.FloatField(db_index=True)
    dec = models.FloatField(db_index=True)
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




class GeoLiteLocation(models.Model):
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
    location = models.ForeignKey(GeoLiteLocation, on_delete=models.CASCADE)
    startIp = models.BigIntegerField(db_index=True)
    endIp = models.BigIntegerField(db_index=True)




class Question(models.Model):
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
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    index = models.IntegerField()
    inputType = models.TextField(null=True)
    text = models.TextField(null=True)
    descriptionText = models.TextField(null=True)
    keyToSet = models.TextField(null=True)
    valueToSet = models.TextField(null=True)

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    dateTime = models.DateTimeField()

    #Generic FK to image or whatever the question is about.
    #TODO: Add a reverse generic relation to the relevant classes this will link to (image, observer notes, etc).
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

class AnswerKV(models.Model):
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name='kvs')
    key = models.TextField(null=True)
    value = models.TextField(null=True)

class AnswerPrecondition(models.Model):
    descriptionText = models.TextField(null=True)
    firstQuestion = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='dependantQuestions')
    secondQuestion = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='dependsOnQuestions')

class AnswerPreconditionCondition(models.Model):
    answerPrecondition = models.ForeignKey(AnswerPrecondition, on_delete=models.CASCADE)
    invert = models.BooleanField()
    key = models.TextField()
    value = models.TextField()

