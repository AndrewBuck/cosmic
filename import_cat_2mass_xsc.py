"""
This python script is a standalone script which can be run to import the 2MASS Extended Sources catalogue into the
django database used by the website cosmic.  It takes as input the 2 ascii files downloaded from the 2MASS ftp site and
imports each data line as a record into the django database.

NOTE: This program clears the existing table before starting to read the new values in to avoid duplicating values.
"""

skip = False
skipFactor = 100

import os
import sys
import django
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

usage = "\n\n\n\tUSAGE: " + sys.argv[0] + " </path/to/2massXSC/xsc_*>\n\n\n"
if len(sys.argv) == 1:
    print(usage)
    sys.exit(1)

if skip:
    print("Skipping all but every " + str(skipFactor) + "th source.\n")
else:
    print("Importing all sources in the specified files.\n")

def parseFloat(s):
    if s == r'\N':
        return None
    else:
        return float(s)

print("Deleting all existing stars in TwoMassXSCRecord table from DB...")
sys.stdout.flush()
TwoMassXSCRecord.objects.all().delete()
print("Done.")

skipcounter = 0
for filename in sys.argv[1:]:
    sys.stdout.write("\n\nReading in objects from " + filename + "\n|")
    sys.stdout.flush()
    with open(filename, 'r') as f:
        with transaction.atomic():
            linecount = 0
            for line in f:
                linecount += 1
                if linecount % 20000 == 0:
                    sys.stdout.write("-")
                    sys.stdout.flush()

                skipcounter += 1
                if skip == True and skipcounter % skipFactor != 0:
                    continue

                fields = line.split('|')

                tempRA = parseFloat(fields[2])
                tempDec = parseFloat(fields[3])

                record = TwoMassXSCRecord(
                    identifier = '2MASX J' + fields[1].strip(),
                    ra = tempRA,
                    dec = tempDec,
                    geometry = 'POINT({} {})'.format(tempRA, tempDec),
                    isophotalKSemiMajor = parseFloat(fields[9]),
                    isophotalKMinorMajor = parseFloat(fields[24]),
                    isophotalKAngle = parseFloat(fields[25]),
                    isophotalKMag = parseFloat(fields[16]),
                    isophotalKMagErr = parseFloat(fields[17])
                    )

                record.save()

    sys.stdout.write("|")

print("\n\nUpdating catalog list.")
sys.stdout.flush()

Catalog.objects.filter(name="2MASS XSC").delete()

catalogDescription = Catalog(
    name = "2MASS XSC",
    fullName = "2MASS Extended Source Catalog",
    objectTypes = "galaxies, nebulae, clusters",
    numObjects = TwoMassXSCRecord.objects.count(),
    limMagnitude = None,
    attributionShort = "This publication makes use of data products from the Two Micron All Sky Survey, which is a joint project of the University of Massachusetts and the Infrared Processing and Analysis Center/California Institute of Technology, funded by the National Aeronautics and Space Administration and the National Science Foundation.",
    vizierID = "VII/233",
    vizierUrl = "http://vizier.u-strasbg.fr/viz-bin/VizieR?-source=VII%2F233",
    cosmicNotes = "The full catalog has over 300 columns, only the basic size, shape, and magnitude in the K-band were read in to the database."
    )

catalogDescription.save()

print("\n\nFinished.")
sys.stdout.flush()

