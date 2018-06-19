#!/bin/bash

nohup python3 manage.py runserver 0.0.0.0:8080 > runserver.stdout.txt 2> runserver.stderr.txt &

nohup celery -A cosmic worker -l info > celery.stdout.txt 2> celery.stderr.txt &

nohup python3 dispatcher.py > dispatcher.py.stdout.txt 2> dispatcher.py.stderr.txt &

