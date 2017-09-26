"""
This python scrupt is a standalone script which can be run to import the Messier catalogue into the django database used
by the website cosmic.  It takes as input a csv file exported from a Simbad search query for the messier objects and
imports each data line as a record into the django database.  The file is not available for download anywhere, but
rather is included in the git repository for the website itself.

NOTE: This program clears the existing table before starting to read the new values in to avoid duplicating values.
"""

import os
import sys
import django
from django.db import transaction
from astropy import units as u
from astropy.coordinates import SkyCoord

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

def parseInt(s):
    s = s.strip()
    return int(s) if s else None

def parseFloat(s):
    s = s.strip()
    return float(s) if s else None

print("Deleting all existing objects in the MessierRecord table from DB...")
sys.stdout.flush()
MessierRecord.objects.all().delete()
print("Done.")
sys.stdout.write("\n\nReading in objects.\n|")
sys.stdout.flush()

with open('Catalogs/Messier_catalog.csv', 'r') as f:
    with transaction.atomic():
        for line in f:
            if line.startswith('#'):
                continue

            sys.stdout.write("-")
            sys.stdout.flush()

            fields = line.split(',')

            c = SkyCoord(fields[2] + '  ' + fields[3], frame='icrs', unit=(u.hourangle, u.deg))

            record = MessierRecord(
                identifier = fields[0],
                objectType = fields[1],
                ra = c.ra.deg,
                dec = c.dec.deg,
                magU = parseFloat(fields[4]),
                magB = parseFloat(fields[5]),
                magV = parseFloat(fields[6]),
                magR = parseFloat(fields[7]),
                magI = parseFloat(fields[8]),
                spectralType = fields[9],
                numReferences = parseInt(fields[10])
                )

            record.save()

sys.stdout.write("|")

print("\n\nUpdating catalog list.")
sys.stdout.flush()

Catalog.objects.filter(name="Messier Objects").delete()

catalogDescription = Catalog(
    name = "Messier Objects",
    fullName = "Catalogue des nebuleuses et des amas d'etoiles. (The Messier Catalog)",
    objectTypes = "globular clusters, open clusters, galaxies, nebulae",
    numObjects = MessierRecord.objects.count(),
    limMagnitude = None,
    attributionShort = "Messier Catalog - Simbad",
    attributionLong = "1850CDT..1784..227M - Connaissance des Temps, 1784, 227-269 (1850) - 01.01.86 20.07.15",
    vizierID = "",
    vizierUrl = "",
    cosmicNotes = "Taken from table of results via simbad query as no downloadable list of the catalog seems to exist online."
    )

catalogDescription.save()

print("\n\nFinished.")
sys.stdout.flush()


