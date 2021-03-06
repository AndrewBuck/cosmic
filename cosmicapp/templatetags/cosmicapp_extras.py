import math
import ephem
import markdown
from datetime import timedelta

from django import template
from django.db.models import Count

register = template.Library()

from cosmicapp import models

@register.filter
def doubleEscape(arg1, arg2):
    """Search through arg1 and replace all instances of arg2 with 2 copies of arg2."""
    output = ''
    for c in arg1:
        if c == arg2:
            output += arg2 + arg2
        else:
            output += c

    return output

@register.filter
def concat(arg1, arg2):
    """concatenate arg1 & arg2"""
    return str(arg1) + str(arg2)

@register.filter
def formatRA(ra):
    """Format the ra given in degrees into hours, minutes, seconds."""
    if ra is None:
        return None

    return formatRA_rad((math.pi/180)*ra)

@register.filter
def formatDec(dec):
    """Format the dec given in degrees into degrees, minutes, seconds."""
    if dec is None:
        return None

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

@register.inclusion_tag('cosmicapp/raDec.html', takes_context=True)
def formatRADec(context, ra, dec, prefix=None, postfix=None):
    tempDict = context
    tempDict['ra'] = formatRA(ra)
    tempDict['dec'] = formatDec(dec)
    tempDict['raDecimal'] = 1.0*ephem.degrees(ra)
    tempDict['decDecimal'] = 1.0*ephem.degrees(dec)
    tempDict['prefix'] = prefix
    tempDict['postfix'] = postfix
    return tempDict

@register.inclusion_tag('cosmicapp/raDec.html', takes_context=True)
def formatRADec_rad(context, ra, dec, prefix=None, postfix=None):
    return formatRADec(context, ra*(180/math.pi), dec*(180/math.pi), prefix, postfix)

@register.filter
def formatTime(time):
    if time == None:
        return '[time not entered]'

    timeString = '<div class=formattedTime style="display: inline-block">' + str(time).replace(' ', '<br>').replace('+', '<br>UTC +') + '</div>'

    return timeString

@register.filter
def typeOf(value):
    return str(type(value))

@register.filter
def subtract(value, arg):
    return value-arg

@register.filter
def multiply(value, arg):
    return value*arg

@register.filter
def average(value, arg):
    return (float(value)+float(arg))/2.0

@register.filter
def divide(value, arg):
    return value/arg

@register.inclusion_tag('cosmicapp/tag_singleValue.html', takes_context=False)
def percentage(value, arg, rangeMin=0, rangeMax=100, decimalPlaces=1):
    if arg == 0:
        return { 'singleValue': 'Undefined' }

    tempDict = { 'singleValue': round(rangeMin + (rangeMax - rangeMin)*(value/arg), decimalPlaces) }
    return tempDict

@register.filter
def invert(value):
    return 1.0/value

@register.filter
def markdownParse(value):
    return markdown.markdown(value)

@register.filter
def sha256summary(value):
    return value[0:6] + "..." + value[-6:]

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

@register.inclusion_tag('cosmicapp/newCommentDiv.html', takes_context=True)
def newComment(context, targetType, targetID, buttonText, prefix=None, postfix=None):
    tempDict = context
    tempDict['targetType'] = targetType
    tempDict['targetID'] = targetID
    tempDict['buttonText'] = buttonText
    tempDict['prefix'] = prefix
    tempDict['postfix'] = postfix
    return tempDict

@register.inclusion_tag('cosmicapp/displayComment.html', takes_context=True)
def displayComment(context, comment, prefix=None, postfix=None):
    tempDict = context
    tempDict['comment'] = comment
    tempDict['prefix'] = prefix
    tempDict['postfix'] = postfix
    if context['user'].is_authenticated:
        tempDict['previousMods'] = models.CommentModeration.objects.filter(user=context['user'], comment=comment)
        tempDict['previousFlags'] = models.CommentFlag.objects.filter(user=context['user'], comment=comment)
        tempDict['previousFlagsCounts'] = models.CommentFlag.objects.filter(comment=comment)\
            .values('flagValue').annotate(count=Count('id'))
        tempDict['previousResponses'] = models.CommentNeedsResponse.objects.filter(user=context['user'], comment=comment)
        tempDict['previousResponsesCounts'] = models.CommentNeedsResponse.objects.filter(comment=comment)\
            .values('responseValue').annotate(count=Count('id'))
    return tempDict

@register.inclusion_tag('cosmicapp/displayCommentsFor.html', takes_context=True)
def displayCommentsFor(context, objectForComments, messageForComments='Comments:', prefix=None, postfix=None):
    tempDict = context
    tempDict['objectForComments'] = objectForComments
    tempDict['messageForComments'] = messageForComments
    tempDict['prefix'] = prefix
    tempDict['postfix'] = postfix
    return tempDict

