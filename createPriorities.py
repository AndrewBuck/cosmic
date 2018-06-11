import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

#--------------------------------------------------------------------------------

#TODO: This table needs a constraint that name/priority is unique for all rows.

priority, created = ProcessPriority.objects.get_or_create(
    name = 'imagestats',
    priority = 10000,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'parseHeaders',
    priority = 10000,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'generateThumbnails',
    priority = 10000,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'sextractor',
    priority = 3010,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'sextractor',
    priority = 100000,
    priorityClass = 'interactive'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'image2xy',
    priority = 3008,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'image2xy',
    priority = 100000,
    priorityClass = 'interactive'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'daofind',
    priority = 3006,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'daofind',
    priority = 100000,
    priorityClass = 'interactive'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'starfind',
    priority = 3004,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'starfind',
    priority = 100000,
    priorityClass = 'interactive'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'flagSources',
    priority = 3002,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'starmatch',
    priority = 3000,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'starmatch',
    priority = 100000,
    priorityClass = 'interactive'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'flagSources',
    priority = 3000,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'flagSources',
    priority = 100000,
    priorityClass = 'interactive'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'astrometryNet',
    priority = 1000,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'astrometryNet',
    priority = 100000,
    priorityClass = 'interactive'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'imageCombine',
    priority = 1000,
    priorityClass = 'batch'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'imageCombine',
    priority = 100000,
    priorityClass = 'interactive'
    )

priority, created = ProcessPriority.objects.get_or_create(
    name = 'calculateUserCostTotals',
    priority = 9999999,
    priorityClass = 'batch'
    )

