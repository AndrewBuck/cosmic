import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cosmic.settings")
django.setup()

from cosmicapp.models import *

print("\n\n\nWARNING: Running this command will clear all stored questions and answers from your database.  Type 'yes' if you want to continue.\n\n\n")

if input("Continue and clear data:  ") == 'yes':
    Question.objects.all().delete()
    QuestionResponse.objects.all().delete()
    Answer.objects.all().delete()
    AnswerKV.objects.all().delete()
    AnswerPrecondition.objects.all().delete()
    AnswerPreconditionCondition.objects.all().delete()

    os.remove('./cosmicapp/static/cosmicapp/QuestionGraph.svg')
    print("\n\n\nDone.\n")

