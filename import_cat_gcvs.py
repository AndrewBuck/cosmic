"""
This python scrupt is a standalone script which can be run to import the GCVS catalogue into the django database used
by the website cosmic.  It takes as input the ascii file downloaded from the GCVS website and imports each data line as
a record into the django database.

NOTE: This program clears the existing table before starting to read the new values in to avoid duplicating values.
"""

import os
import sys
import django
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

usage = "\n\n\n\tUSAGE: " + sys.argv[0] + " </path/to/gcvs5.txt>\n\n\n"
if len(sys.argv) != 2:
    print(usage)
    sys.exit(1)

if os.path.basename(sys.argv[1]) != "gcvs5.txt":
    print(usage)
    sys.exit(1)

def parseInt(s):
    s = s.strip()
    return int(s) if s else 0

def parseFloat(s):
    s = s.strip()
    return float(s) if s else 0

print("Deleting all existing stars in GCVSRecord table from DB...")
sys.stdout.flush()
GCVSRecord.objects.all().delete()
print("Done.")
sys.stdout.write("\n\nReading in objects.\n|")
sys.stdout.flush()

with open(sys.argv[1], 'r') as f:
    with transaction.atomic():
        readingData = False
        linecount = 0
        for line in f:
            if not readingData:
                if line.startswith("----------------------"):
                    readingData = True
                    continue
                else:
                    continue

            else:
                linecount += 1
                if linecount % 1000 == 0:
                    sys.stdout.write("-")
                    sys.stdout.flush()

                #TODO: Should convert this to astropy.
                raHours = parseFloat(line[20:22])
                raMin = parseFloat(line[22:24])
                raSec = parseFloat(line[24:29])
                decD = parseFloat(line[30:33])
                decM = parseFloat(line[33:35])
                decS = parseFloat(line[35:39])
                raDeg = 15*raHours + raMin/4.0 + raSec/240.0
                decDeg = decD + decM/60.0 + decS/3600.0

                catalogEntry = GCVSRecord(
                    constellationNumber = line[0:2],
                    starNumber = line[2:7],
                    identifier = ' '.join(line[8:18].split()),
                    ra = raDeg,
                    dec = decDeg,
                    geometry = 'POINT({} {})'.format(raDeg, decDeg),
                    pmRa = 1000.0 * parseFloat(line[179:185]),
                    pmDec = 1000.0 * parseFloat(line[186:192]),
                    variableType = line[41:51].strip(),
                    variableType2 = line[214:224].strip(),
                    magMax = parseFloat(line[53:58]),
                    magMaxFlag = line[52:53],
                    magMin = parseFloat(line[64:69]),
                    magMinFlag = line[62:63],
                    magMin2 = parseFloat(line[76:81]),
                    magMin2Flag = line[75:76],
                    epochMaxMag = parseFloat(line[91:102]),
                    outburstYear = parseInt(line[104:108]),
                    period = parseFloat(line[111:127]),
                    periodRisingPercentage = parseFloat(line[131:133]),
                    spectralType = line[137:154],
                    )

                catalogEntry.save()

sys.stdout.write("|")

print("\n\nUpdating catalog list.")
sys.stdout.flush()

Catalog.objects.filter(name="GCVS").delete()

catalogDescription = Catalog(
    name = "GCVS",
    fullName = "General Catalogue of Variable Stars",
    objectTypes = "stars (variable)",
    numObjects = GCVSRecord.objects.count(),
    limMagnitude = None,
    attributionShort = "Samus N.N., Kazarovets E.V., Durlevich O.V., Kireeva N.N., Pastukhova E.N., General Catalogue of Variable Stars: Version GCVS 5.1, Astronomy Reports, 2017, vol. 61, No. 1, pp. 80-88 {2017ARep...61...80S}",
    vizierID = "B/GCVS",
    vizierUrl = "http://vizier.u-strasbg.fr/viz-bin/VizieR-3?-source=B/gcvs/gcvs_cat",
    cosmicNotes = "Current import code ignores several 'flag' fields indicating uncertainty about various measurements in the catalog."
    )

catalogDescription.save()

print("\n\nFinished.")
sys.stdout.flush()

