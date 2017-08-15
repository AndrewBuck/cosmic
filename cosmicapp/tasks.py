from __future__ import absolute_import, unicode_literals
from celery import shared_task

import subprocess
import json
import sys

from .models import *

storageDirectory = '/cosmicmedia/'

@shared_task
def imagestats(filename):
    formatString = '{"width" : %w, "height" : %h, "depth" : %z}'
    proc = subprocess.Popen(['identify', '-format', formatString, storageDirectory + filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

    output, error = proc.communicate()
    output = output.decode('utf-8')
    error = error.decode('utf-8')

    print("imagestats: " + output)
    sys.stdout.flush()

    jsonObject = json.loads(output)

    image = Image.objects.get(fileRecord__onDiskFileName=filename)
    image.dimX = jsonObject['width']
    image.dimY = jsonObject['height']
    image.bitDepth = jsonObject['depth']
    image.save()

