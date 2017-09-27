"""
This python script is a standalone script which can be run to import an ascii dump of the UCAC4 star catalogue into the
django database used by the website cosmic.  The script assumes you have already downloaded the relevant z001 through
z900 files containining the UCAC4 binary catalogue data and then "dumped" them to the ascii format using the u4dump
fortran program.  When runnning the program, leave the field delimeter blank (i.e. only spaces between fields).  This
program takes as input one or more of these ascii dump files which will be read in line by line and inserted into the
django database.  NOTE: This program clears the existing table before starting to read the new values in to avoid
duplicating values.

The dump program can be downloaded from:  ftp://cdsarc.u-strasbg.fr/cats/I/322A/UCAC4/access/
To compile it run the command:  gfortran u4dump.f u4sub.f -o u4dump
"""

skip = False
skipFactor = 1000

import sys

usage = "\n\n\n\tUSAGE: " + sys.argv[0] + " </path/to/ascii/files/*.asc>\n\n\n"
if len(sys.argv) < 2:
    print(usage)
    sys.exit(1)

print("\n\n\n---------- WARNING ----------")

print(      "This import will not contain proper motion values for\nthe 20 or so stars with the highest proper motion.")
print(      "---------- WARNING ----------")
print("\n\n\n")


if skip:
    print("Skipping all but every " + str(skipFactor) + "th star.\n")
else:
    print("Importing all stars in the specified zone files.\n")

sys.stdout.flush()


import os
import django
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *





#TODO: Need to read in file u4hpm.dat and fill in values in appropriate places.



print("Deleting all existing stars in UCAC4Record table from DB...")
sys.stdout.flush()
UCAC4Record.objects.all().delete()
print("Done.")
sys.stdout.flush()

skipcounter = 0
for filename in sys.argv[1:]:
    idZone = int(os.path.basename(filename)[1:4])    #filenames look like z550.asc
    idCounter = 0
    sys.stdout.write("\nReading zone " + os.path.basename(filename) + " |")
    sys.stdout.flush()
    with open(filename, 'r') as f:
        with transaction.atomic():
            for line in f:
                idCounter += 1
                if idCounter % 5000 == 0:
                    sys.stdout.write("-")
                    sys.stdout.flush()

                skipcounter += 1
                if skip == True and skipcounter % skipFactor != 0:
                    continue

                fields = line.split()

                record = UCAC4Record(
                    identifier = "%03i-%06i" % (idZone, idCounter),
                    ra = int(fields[0]) / float(3600*1000),
                    dec = (int(fields[1]) - 324000000) / float(3600*1000),
                    magFit = int(fields[2]) / 1000.0 if fields[2] != '20000' else None,
                    magAperture = int(fields[3]) / 1000.0 if fields[3] != '20000' else None,
                    magError = int(fields[4]) / 100.0 if fields[4] != '99' else None,
                    pmra = int(fields[14]) / 10.0 if fields[14] not in ['0', '32767'] else None,
                    pmdec = int(fields[15]) / 10.0 if fields[15] not in ['0', '32767'] else None,
                    id2mass = fields[18]
                    )

                record.save()

        sys.stdout.write("| Writing to DB...")
        sys.stdout.flush()

print("\n\nUpdating catalog list.")

Catalog.objects.filter(name="UCAC 4").delete()

catalogDescription = Catalog(
    name = "UCAC 4",
    fullName = "U.S. Naval Observatory CCD Astrograph Catalog",
    objectTypes = "stars",
    numObjects = UCAC4Record.objects.count(),
    limMagnitude = 16,
    attributionShort = "The fourth U.S. Naval Observatory CCD Astrograph Catalog (UCAC4) by Zacharias N., Finch C.T., Girard T.M., Henden A., Bartlet J.L., Monet D.G., Zacharias M.I.",
    vizierID = "I/322A",
    vizierUrl = "http://vizier.u-strasbg.fr/viz-bin/VizieR?-source=I/322",
    cosmicNotes = "Current import code does not crossmatch the 20 or so stars with the highest proper motion against "
                  "the hpm table provided as a supplement to the UCAC4 main files.  Future versions of the import script will do so."
    )

catalogDescription.save()

print("\n\nFinished.")

