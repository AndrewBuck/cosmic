from django.db.models import Func

class Epoch(Func):
    function = 'EXTRACT'
    template = "%(function)s('epoch' from %(expressions)s)"

