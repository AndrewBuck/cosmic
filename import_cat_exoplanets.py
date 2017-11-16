"""
This python script is a standalone script which can be run to import the exoplanets.org database into the django database used
by the website cosmic.  It takes as input the csv file downloaded from the exoplanets.org website and imports each data line as
a record into the django database.

NOTE: This program clears the existing table before starting to read the new values in to avoid duplicating values.
"""

import os
import sys
import csv
import django
import julian
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

usage = "\n\n\n\tUSAGE: " + sys.argv[0] + " </path/to/exoplanets.csv>\n\n\n"
if len(sys.argv) != 2:
    print(usage)
    sys.exit(1)

if os.path.basename(sys.argv[1]) != "exoplanets.csv":
    print(usage)
    sys.exit(1)

def parseInt(s):
    s = s.strip()
    return int(s) if s else None

def parseFloat(s):
    s = s.strip()
    return float(s) if s else None

print("Deleting all existing entries in ExoplanetRecord table from DB...")
sys.stdout.flush()
ExoplanetRecord.objects.all().delete()
print("Done.")

sys.stdout.write("\n\nReading in exoplanets.\n")
sys.stdout.flush()

with transaction.atomic():
    with open(sys.argv[1], 'r') as f:
        linecount = 0
        skipped = 0
        csvreader = csv.DictReader(f, delimiter=',', quotechar='"')
        for row in csvreader:
            linecount += 1

            if linecount % 100 == 0:
                sys.stdout.write("-")
                sys.stdout.flush()

            timePeriastronJD = parseFloat(row['T0'])
            transitEpochJD = parseFloat(row['TT'])

            if timePeriastronJD != None:
                if timePeriastronJD < 2440000:
                    timePeriastronJD += 2440000

            if transitEpochJD != None:
                if transitEpochJD < 2440000:
                    transitEpochJD += 2440000

            if row['RA'] == '':
                skipped += 1
                continue

            ra = 15*parseFloat(row['RA'])
            dec = parseFloat(row['DEC'])

            exoplanet = ExoplanetRecord(
                identifier = row['NAME'],
                identifier2 = row['OTHERNAME'],
                starIdentifier = row['STAR'],
                component = row['COMP'],
                numComponents = parseInt(row['NCOMP']),
                ra = ra,
                dec = dec,
                geometry = 'POINT({} {})'.format(ra, dec),
                dist = parseFloat(row['DIST']),

                magBMinusV = parseFloat(row['BMV']),
                magV = parseFloat(row['V']),
                magJ = parseFloat(row['J']),
                magH = parseFloat(row['H']),
                magKS = parseFloat(row['KS']),

                thisPlanetDiscoveryMethod = row['PLANETDISCMETH'],
                firstPlanetDiscoveryMethod = row['STARDISCMETH'],
                discoveryMicrolensing = True if row['MICROLENSING'] == '1' else False,
                discoveryImaging = True if row['IMAGING'] == '1' else False,
                discoveryTiming = True if row['TIMING'] == '1' else False,
                discoveryAstrometry = True if row['ASTROMETRY'] == '1' else False,

                vSinI = parseFloat(row['VSINI']),
                mSinI = parseFloat(row['MSINI']),
                mass = parseFloat(row['MASS']),

                period = parseFloat(row['PER']),
                velocitySemiAplitude = parseFloat(row['K']),
                velocitySlope = parseFloat(row['DVDT']),

                timePeriastron = julian.from_jd(timePeriastronJD, fmt='jd') if timePeriastronJD != None else None,
                eccentricity = parseFloat(row['ECC']),
                argPeriastron = parseFloat(row['OM']),
                inclination = parseFloat(row['I']),
                semiMajorAxis = parseFloat(row['A']),

                transitDepth = parseFloat(row['DEPTH']),
                transitDuration = parseFloat(row['T14']),
                transitEpoch = julian.from_jd(transitEpochJD, fmt='jd') if transitEpochJD != None else None,

                planetRadius = parseFloat(row['R']),
                planetDensity = parseFloat(row['DENSITY']),
                planetSurfaceGravity = parseFloat(row['GRAVITY']),

                firstPublicationDate = parseInt(row['DATE']),
                firstReference = row['FIRSTREF'],
                orbitReference = row['ORBREF'],

                epeLink = row['JSNAME'],
                eaLink = row['EANAME'],
                etdLink = row['ETDNAME'],
                simbadLink = row['SIMBADNAME']
                )

            exoplanet.save()

print('Finished reading file.  Skipped {} entries with no right ascension (kepler candidate objects).'.format(skipped))

print("\n\nUpdating catalog list.")
sys.stdout.flush()

Catalog.objects.filter(name="Exoplanets.org").delete()

catalogDescription = Catalog(
    name = "Exoplanets.org",
    fullName = "Exoplanet.org Database",
    objectTypes = "Extrasolar planets",
    numObjects = ExoplanetRecord.objects.count(),
    limMagnitude = None,
    attributionShort = "This research has made use of the Exoplanet Orbit Database and the Exoplanet Data Explorer at exoplanets.org.",
    url = "http://exoplanets.org/",
    cosmicNotes = "Approximately half of the entries in the CSV file are Kepler candidate objects with no ra/dec.  The importer is skipping all of these for now until we can figure out how to handle them."
    )

catalogDescription.save()

print("\n\nFinished.")
sys.stdout.flush()

