from django import template
import math
import ephem
from datetime import timedelta

register = template.Library()

@register.filter
def concat(arg1, arg2):
    """concatenate arg1 & arg2"""
    return str(arg1) + str(arg2)

@register.filter
def formatRA(ra):
    """Format the ra given in degrees into hours, minutes, seconds."""
    return formatRA_rad((math.pi/180)*ra)

@register.filter
def formatDec(dec):
    """Format the dec given in degrees into degrees, minutes, seconds."""
    return formatDec_rad((math.pi/180)*dec)

@register.filter
def formatRA_rad(ra):
    """Format the ra given in degrees into hours, minutes, seconds."""
    angle = ephem.degrees(ra)
    return str(ephem.hours(angle))

@register.filter
def formatDec_rad(dec):
    """Format the dec given in degrees into degrees, minutes, seconds."""
    angle = ephem.degrees(dec)

    if angle >= 0:
        sign = '+'
    else:
        sign = ''

    return sign + str(angle)

@register.filter
def formatTime(time):
    if time == None:
        return '[time not entered]'

    timeString = '<div class=formattedTime style="display: inline-block">' + str(time).replace(' ', '<br>').replace('+', '<br>UTC +') + '</div>'

    return timeString

@register.filter
def multiply(value, arg):
    return value*arg

@register.filter
def divide(value, arg):
    return value/arg

@register.inclusion_tag('cosmicapp/tag_singleValue.html', takes_context=False)
def percentage(value, arg, rangeMin=0, rangeMax=100):
    if arg == 0:
        return { 'singleValue': rangeMax }

    tempDict = { 'singleValue': rangeMin + (rangeMax - rangeMin)*(value/arg) }
    return tempDict

@register.filter
def invert(value):
    return 1.0/value

@register.inclusion_tag('cosmicapp/bookmarkDiv.html', takes_context=True)
def bookmark(context, targetType, targetID, folderName, prefix=None, postfix=None):
    tempDict = context
    tempDict['targetType'] = targetType
    tempDict['targetID'] = targetID
    tempDict['folderName'] = folderName
    tempDict['prefix'] = prefix
    tempDict['postfix'] = postfix
    return tempDict

@register.inclusion_tag('cosmicapp/scoreForObject.html', takes_context=False)
def scoreForObject(obj, dateTime, user):
    tempDict = {}
    value = obj.getValueForTime(dateTime)
    difficulty = obj.getDifficultyForTime(dateTime)
    userDifficulty = obj.getUserDifficultyForTime(dateTime, user)
    tempDict['score'] = obj.getScoreForTime(dateTime, user)
    tempDict['peakScore'] = obj.getPeakScoreForInterval(dateTime, dateTime+timedelta(hours=24), user)
    tempDict['value'] = value
    tempDict['difficulty'] = difficulty
    tempDict['userDifficulty'] = userDifficulty
    return tempDict

