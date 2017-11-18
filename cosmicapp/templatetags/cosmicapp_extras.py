from django import template
import math
import ephem

register = template.Library()

@register.filter
def concat(arg1, arg2):
    """concatenate arg1 & arg2"""
    return str(arg1) + str(arg2)

@register.filter
def formatRA(ra):
    """Format the ra given in degrees into hours, minutes, seconds."""
    angle = ephem.degrees((math.pi/180)*ra)
    return str(ephem.hours(angle))

@register.filter
def formatDec(dec):
    """Format the dec given in degrees into degrees, minutes, seconds."""
    angle = ephem.degrees((math.pi/180)*dec)

    if angle >= 0:
        sign = '+'
    else:
        sign = ''

    return sign + str(angle)

@register.filter
def multiply(value, arg):
    return value*arg

@register.filter
def divide(value, arg):
    return value/arg

@register.filter
def invert(value):
    return 1.0/value

