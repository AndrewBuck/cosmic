Install Django:

sudo pip3 install Django



Install Celery and RabbitMQ to pass messages to it:

sudo pip3 install celery
sudo pip3 install django-celery-results
sudo apt-get install rabbitmq-server



Run the manage.py script to setup the database and run the django server:

python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py runserver 8080
celery -A cosmic worker -l info
python3 dispatcher.py




Commands needed installed on the system and in the path:
(Note these are mainly needed on the worker nodes running celery workers, not
necessarily on the webserver itself)

identify - part of imagemagick.  Calculates image statistics for an image.
	(width, height, bit depth, etc)

sextractor - Source Extractor: Finds stars and galaxies in an image.  Also must
	copy /usr/share/sextractor/default.* into the directory where it is being run
	or it will complain about missing configuration files.  This is a very
	powerful program, and we should look into using more of its functionality.

	One very useful feature would be to use the two image catalog matching
	mode to align partially overlapping images from a mosaic.

	See the "unofficial" documentation in "Sextractor for Dummies":

	http://mensa.ast.uct.ac.za/~holwerda/SE/Manual.html






NOTES:

The imwcs command line program does plate solving similar to atrometry.net

