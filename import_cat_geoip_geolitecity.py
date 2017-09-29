
"""
This python script is a standalone script which can be run to import the GeoLite City CSV geoip database into the django database used
by the website cosmic.  It takes as input the ascii file downloaded from the GeoLite website and imports each data line as
a record into the django database.

NOTE: This program clears the existing table before starting to read the new values in to avoid duplicating values.
"""

import os
import sys
import csv
import django
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

usage = "\n\n\n\tUSAGE: " + sys.argv[0] + " </path/to/GeoLiteCity-Location.csv> </path/to/GeoLiteCity-Blocks.csv>\n\n\n"
if len(sys.argv) != 3:
    print(usage)
    sys.exit(1)

if os.path.basename(sys.argv[1]) != "GeoLiteCity-Location.csv" and os.path.basename(sys.argv[2]) != "GeoLiteCity-Blocks.csv":
    print(usage)
    sys.exit(1)

def parseInt(s):
    s = s.strip()
    return int(s) if s else None

def parseFloat(s):
    s = s.strip()
    return float(s) if s else None

print("Deleting all existing entries in GeoLiteBlock table from DB...")
sys.stdout.flush()
GeoLiteBlock.objects.all().delete()
print("Done.")

print("Deleting all existing entries in GeoLiteLocation table from DB...")
sys.stdout.flush()
GeoLiteLocation.objects.all().delete()
print("Done.")

sys.stdout.write("\n\nReading in locations.\n")
sys.stdout.flush()

with transaction.atomic():
    with open(sys.argv[1], 'r', encoding='latin-1') as f:
        # Discard the first line of the file so it doesn't confuse the csv reader.
        print(f.readline())

        linecount = 0
        csvreader = csv.DictReader(f, delimiter=',', quotechar='"')
        for row in csvreader:
            linecount += 1

            if linecount % 1000 == 0:
                sys.stdout.write("-")
                sys.stdout.flush()

            location = GeoLiteLocation(
                id = row['locId'],
                country = row['country'],
                region = row['region'],
                city = row['city'],
                postalCode = row['postalCode'],
                lat = row['latitude'],
                lon = row['longitude'],
                metroCode = parseInt(row['metroCode']),
                areaCode = row['areaCode']
                )

            location.save()

sys.stdout.write("\n\nReading in blocks.\n")
sys.stdout.flush()

with transaction.atomic():
    with open(sys.argv[2], 'r', encoding='latin-1') as f:
        # Discard the first line of the file so it doesn't confuse the csv reader.
        print(f.readline())

        linecount = 0
        csvreader = csv.DictReader(f, delimiter=',', quotechar='"')
        for row in csvreader:
            linecount += 1

            if linecount % 1000 == 0:
                sys.stdout.write("-")
                sys.stdout.flush()

            locId = row['locId']
            location = GeoLiteLocation.objects.get(pk=locId)

            block = GeoLiteBlock(
                location = location,
                startIp = row['startIpNum'],
                endIp = row['endIpNum']
                )

            block.save()

print("\n\nUpdating catalog list.")
sys.stdout.flush()

Catalog.objects.filter(name="GeoLite").delete()

catalogDescription = Catalog(
    name = "GeoLite",
    fullName = "GeoLite City GeoIP Database",
    objectTypes = "IP Addresses",
    numObjects = GeoLiteLocation.objects.count() + GeoLiteBlock.objects.count(),
    limMagnitude = None,
    attributionShort = "Copyright (c) 2012 MaxMind LLC.  All Rights Reserved.",
    url = "https://dev.maxmind.com/geoip/legacy/geolite/",
    cosmicNotes = "This is not an astronomical database, it is a database which maps IP addresses to Lat/Lon on the Earth.  It is used to set default locations for non-logged in users for things like Observation Suggestions and other tools which need a location to work."
    )

catalogDescription.save()

print("\n\nFinished.")
sys.stdout.flush()

