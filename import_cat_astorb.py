"""
This python scrupt is a standalone script which can be run to import the astorb.dat databse into the django database used
by the website cosmic.  It takes as input a the astorb.dat file downloaded from:

    ftp://ftp.lowell.edu/pub/elgb/astorb.html

and imports each data line as a record into the django database.


NOTE: This program clears the existing table before starting to read the new values in to avoid duplicating values.
"""

skip = True
skipFactor = 50

import os
import sys
import django
from django.db import transaction
from django.utils.dateparse import parse_date
from astropy import units as u
from astropy.coordinates import SkyCoord

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

usage = "\n\n\n\tUSAGE: " + sys.argv[0] + " </path/to/astorb.dat>\n\n\n"
if len(sys.argv) != 2:
    print(usage)
    sys.exit(1)

if os.path.basename(sys.argv[1]) != "astorb.dat":
    print(usage)
    sys.exit(1)

def parseInt(s):
    s = s.strip()
    return int(s) if s else None

def parseFloat(s):
    s = s.strip()
    return float(s) if s else None

def parseDate(s):
    year = s[0:4]
    month = s[4:6]
    day = s[6:8]
    return parse_date(year + '-' + month + '-' + day)

if skip:
    print("Skipping all but every " + str(skipFactor) + "th asteroid.\n")
else:
    print("Importing all asteroids in the specified file.\n")

print("Deleting all existing objects in the Astorb table from DB...")
sys.stdout.flush()
AstorbRecord.objects.all().delete()
print("Done.")
sys.stdout.write("\n\nReading in objects.\n|")
sys.stdout.flush()

with open(sys.argv[1], 'r') as f:
    with transaction.atomic():
        lineCounter = 0
        skipcounter = 0
        for line in f:
            lineCounter += 1
            if lineCounter % 10000 == 0:
                sys.stdout.write("-")
                sys.stdout.flush()

            skipcounter += 1
            if skip == True and skipcounter % skipFactor != 0:
                continue

            #NOTE: Epoch should have 0.5 added to it?
            record = AstorbRecord(
                number = parseInt(line[0:6]),
                name = line[7:26].strip(),
                absMag = parseFloat(line[42:48]),
                colorIndex = parseFloat(line[54:58]),
                diameter = parseFloat(line[59:64]),
                taxanomicClass = line[65:72].strip(),
                orbitCode = parseInt(line[73:74]),
                criticalCode = parseInt(line[84:86]),
                astrometryNeededCode = parseInt(line[92:94]),
                observationArc = parseInt(line[95:100]),
                numObservations = parseInt(line[101:105]),
                epoch = parseDate(line[106:114]),
                meanAnomaly = parseFloat(line[115:125]),
                argPerihelion = parseFloat(line[126:136]),
                lonAscendingNode = parseFloat(line[137:147]),
                inclination = parseFloat(line[148:157]),
                eccentricity = parseFloat(line[158:168]),
                semiMajorAxis = parseFloat(line[170:181]),
                ceu = parseFloat(line[191:198]),
                ceuRate = parseFloat(line[199:207]),
                ceuDate = parseDate(line[208:216]),
                nextPEU = parseFloat(line[217:224]),
                nextPEUDate = parseDate(line[225:233]),
                tenYearPEU = parseFloat(line[234:241]),
                tenYearPEUDate = parseDate(line[242:250]),
                tenYearPEUIfObserved = parseFloat(line[251:258]),
                tenYearPEUDateIfObserved = parseDate(line[259:267])
                )

            record.save()

sys.stdout.write("|")

print("\n\nUpdating catalog list.")
sys.stdout.flush()

Catalog.objects.filter(name="Astorb Database").delete()

catalogDescription = Catalog(
    name = "Astorb Database",
    fullName = "The Asteroid Orbital Elements Database ",
    objectTypes = "asteroids",
    numObjects = AstorbRecord.objects.count(),
    limMagnitude = None,
    attributionShort = "Astorb Database",
    attributionLong = "The research and computing needed to generate astorb.dat were funded principally by NASA grant NAG5-4741, and in part by the Lowell Observatory endowment. astorb.dat may be freely used, copied, and transmitted provided attribution to Dr. Edward Bowell and the aforementioned funding sources is made.",
    vizierID = "B/astorb",
    vizierUrl = "http://vizier.u-strasbg.fr/viz-bin/VizieR?-source%3DB/astorb",
    url = "ftp://ftp.lowell.edu/pub/elgb/astorb.html",
    cosmicNotes = "Several columns not imported."
    )

catalogDescription.save()

print("\n\nFinished.")
sys.stdout.flush()



