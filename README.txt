Install Django:

sudo apt-get install python3-dev

sudo pip3 install Django django-extensions bokeh sqlparse dateparser lxml pytz markdown
imageio ccdproc

============== IMPORTANT ==============

On a production site you MUST, replace the django secret key that comes in the
config files by default from Git.  The SECRET_KEY parameter is found in the file
cosmic/settings.py and has the default value shown below when checked out from
Git.  Choose a long, randomly generated string like something from /dev/random
using the example command at the end of this section.

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'THIS_IS_NOT_SECRET____IN_GIT_REPO____MUST_CHANGE_FOR_PRODUCTION_SITE'

A good key could be generated using the following method, although you can use
whatever suits you as long as it is impossible to guess.  Note that the command
below may take a while to run as 512 bytes might empty the kernel entropy pool
and it will block until it refills.  You can use a lower value if you need, or
just wait it out.  On a development system with a user at the keyboard, starting
from a completely empty entropy pool this command took about 5 minutes to run.
It will take a bit longer on a server with less entropy generation, however it
is unlikely you will be starting from a completely empty entropy pool.

head -c 512 /dev/random | sha256sum -b







Install Celery and RabbitMQ to pass messages to it:

sudo pip3 install celery
sudo pip3 install django-celery-results
sudo apt-get install rabbitmq-server

Otional: In a development environment this module makes detecting code changes
more reliable when the 'manage.py runserver' development server is in use.  Not
needed for a production site:

sudo pip3 install pyinotify

# SortedContainers - does what it says on the tin
sudo pip3 install sortedcontainers

Astropy is used for various calculations and data reductions on the server and
on the celery worker nodes:

sudo pip3 install astropy photutils scipy scikit-image


PyEphem is used to compute ephemerides for asteroids, etc:

sudo pip3 install pyephem


Julian is a small library for converting datetime objects to/from julian dates:

sudo pip3 install julian


Install and setup Postgre SQL:

sudo apt-get install python-pip python-dev libpq-dev postgresql postgresql-contrib

sudo su - postgres

psql

CREATE DATABASE cosmic;

# Pick a proper password for a production site, the code in git uses the password below for development.
CREATE USER cosmicweb WITH PASSWORD 'password';

ALTER ROLE cosmicweb SET client_encoding TO 'utf8';
ALTER ROLE cosmicweb SET default_transaction_isolation TO 'read committed';
ALTER ROLE cosmicweb SET timezone TO 'UTC';

GRANT ALL PRIVILEGES ON DATABASE cosmic TO cosmicweb;

\q
exit

sudo pip3 install psycopg2

# Optional create a superuser on the cosmic website (a user who can access cosmic.science/admin).
python manage.py createsuperuser

# Optional install pgadmin, which is a gui to manage the postgre database, view tables, etc.
sudo apt-get install pgadmin3



At this point the base Postgre system is installed.  The next step is to install
and configure the PostGIS extensions and the GeoDjango framework which calls out
to the PostGIS backend.

We begin by installing the libraries needed for the system:

sudo apt-get install binutils libproj-dev gdal-bin

Next we install the base PostGIS system extensions into Postgre SQL (specific
version numbers may be different but version 9.3 or greater of Postgre is
required):

sudo apt-get install postgresql-9.3 postgresql-9.3-postgis-2.1 postgresql-server-dev-9.3 python-psycopg2

Finally we create the postgis extensions on the actual cosmic database:

sudo su postgres
psql cosmic
CREATE EXTENSION postgis;

Now that PostGIS is set up and ready to use, we need one final step to deal with
the fact that we are storing astronomical data rather than data for objects on
the surface of the Earth.  To do this we define our own "fake" Spatial Reference
System using the method outlined here (do not need to read this link just
included here for refernce) also note that we have modified the radius of the
sphere used so 1 unit along its surface corresponds to 1 degree:

https://gis.stackexchange.com/questions/2459/what-coordinate-system-should-be-used-to-store-geography-data-for-celestial-coor

The steps to actually create the fake SRS are to simply execute the following
SQL query to insert the fake SRS into the the spatial_ref_sys table.  The fake
SRS is simply spherical coordinate system using degrees for "lat" and "lon"
which will be our RA and DEC values, and it also uses a perfect sphere as its
reference ellipsoid (i.e. the celestial sphere).  The command to insert the SRS
is the following:

sudo su postgres
psql cosmic
insert into spatial_ref_sys values(40000, 'ME', 1, 'GEOGCS["Normal Sphere (r=57.295779513)",DATUM["unknown",SPHEROID["sphere",57.295779513,0]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]', '+proj=longlat +a=57.295779513 +b=57.295779513 +no_defs');






========== SKIP THIS SECTION ==========
As of now we the code has been refactored to no longer be dependant on IRAF.
This may change in the future, however for now this part of the setup can be
skipped over as it is not currently used.

Install pyraf library:

sudo pip3 install pyraf

For interfacing with IRAF we will use pyraf, which depends on Miniconda.  Get
and install Miniconda 3.

https://conda.io/miniconda.html

chmod +x Miniconda3-latest-Linux-x86_64.sh
./Miniconda3-latest-Linux-x86_64.sh

Close and reopen a terminal or source your ~/.bashrc to make sure 'conda' is in
your path.  Next, configure conda to use the astroconda channel.

conda config --add channels http://ssb.stsci.edu/astroconda

Install IRAF through conda.  (The instructions recommend the python 2.7 command
due to some incompatabilities, however we are running python3 for everything so
we will go with that for now and hope the incompatabilities are only in tasks
we won't be relying on right until they are fixed).

conda create -n iraf3 python=3 iraf-all pyraf-all stsci

After conda is set up and iraf is installed you should COMMENT OUT the lines
added to your .bashrc file as they are no longer needed and will break python
for the rest of the site.

# added by Miniconda3 4.3.21 installer
#export PATH="/home/buck/miniconda3/bin:$PATH"

========== END SKIP SECTION ==========


Make a directory to store uploaded files:

sudo mkdir /cosmicmedia
sudo chown username: /cosmicmedia

	(where username is the user running the webserver)

cp /usr/share/sextractor/default* /cosmicmedia/

	(this is temporary, will not be needed later on)



Run the manage.py script to setup the database:

python3 manage.py makemigrations
python3 manage.py migrate



Next, create the table of questions to ask the users in the database.  This
only needs to be run once, when the database is first created, or whenever new
questions are added to the system.  Running the script will also output a
picture showing a graph of the questions and what order they will be asked in,
this uses the python graphviz interface and the system program 'dot' which is
part of graphviz to actually render the image.  The image is saved to the static
directory so it is accesible on the website (note: make sure you run this
directly from the 'cosmic' root directory where the script is located so that
the rendered image is put in the correct place in the static directory):

sudo pip3 install graphviz pydot
sudo apt-get install graphviz

python3 createQuestions.py

There is also a script to clear all stored questions and answers from the
database.  Under normal circumstances you shouldn't need this, but it is useful
for developers working with a local copy of the database on their own system.

WARNING: ONLY FOR DEVELOPERS, DO NOT RUN ON A PRODUCTION SITE UNLESS YOU REALLY MEAN TO!

python3 clearQuestionsAndAnswers.py

Once dot is inslled it can optionally be used to generate a dependancy graph of
all of the database models in the django system, showing the relationships
between the tables.  This step is not necessary in production, but is useful to
developers who want to get a clearer picture of the database structure.  To
generate the graph, run the following manage.py command:

python3 manage.py graph_models -a -g -o models.png

Developers will also likely want to generate documentation for the codebase on
their local system.  To do this easily a Doxygen configuration file is included
in the doc/ directory which is set up for this project.  To build the html
documentation run the following:

cd doc
doxygen Doxyfile

The second command will create a doc/html directory.  You can browse the
documentation there by directing your web browser to the index.html file under
that directory.



Finally, populate the database tables containing the catalog data.  See below
for instructions on how to do that for individual catalogs if you only want specific
ones.  If you want to install all of the catalogs you can run the helper script:

./import_all.sh



Now that the database is set up and loaded with the necessary data, the server
can be launched with:

python3 manage.py runserver 8080
celery -A cosmic worker -l info
python3 dispatcher.py



Commands that need to be installed on the system and in the path:
(Note these are mainly needed on the worker nodes running celery workers, not
necessarily on the webserver itself)

sudo apt-get install sextractor astrometry.net

identify - part of imagemagick.  Calculates image statistics for an image.
	(width, height, bit depth, etc)

convert - the main tool from imagemagick.  Used to make thumbnails.

sextractor - Source Extractor: Finds stars and galaxies in an image.  Also must
	copy /usr/share/sextractor/default.* into the directory where it is being run
	or it will complain about missing configuration files.  This is a very
	powerful program, and we should look into using more of its functionality.

	One very useful feature would be to use the two image catalog matching
	mode to align partially overlapping images from a mosaic.

	See the "unofficial" documentation in "Sextractor for Dummies":

	http://mensa.ast.uct.ac.za/~holwerda/SE/Manual.html

solve-field - The main executable for astrometry.net.
	sudo apt-get install astrometry.net

image2xy - A source extraction tool that comes with astrometry.net (this is the
	default if you don't use sextractor).  Should be installed
	automatically with astrometry.net but good to double check.


Catalogs

The Cosmic website uses imported astronomical catalogs to aid in plate solving,
provide details on sources extracted from uploaded images, and to suggest
targets for people to observe.  These catalogs are freely available online, however
some are very large, both to download and in terms of the disk space they require.

Below is a listing of the catalogs that Cosmic has importers for.  Without
certain catalogs being imported, some site functionality may not work
correctly, and may break the site entirely, as runnning without the catalog is
not necessarily a supported, or even tested, option.

TODO:  Create files which are sample extracts of each catalog to allow a subset
of the full data to be distributed with Cosmic.  This way developers who want
to test the site or people who want to run local copies themselves can safely
use the site with reduced functionality, but without db queries failing due to
lack of data.



UCAC4 - U.S. Naval Observatory CCD Astrograph Catalog

	A catalog containing 114 million stars.  Coverage over the whole sky
	for all stars down to a limiting magnitude of 16.

	Attribution: "The fourth U.S. Naval Observatory CCD Astrograph Catalog
		(UCAC4) by Zacharias N., Finch C.T., Girard T.M., Henden A.,
		Bartlet J.L., Monet D.G., Zacharias M.I."

	Binary files are 8.6 gb, downloadable over ftp at:
		ftp://cdsarc.u-strasbg.fr/cats/I/322A/UCAC4/

	Also download the u4dump.f and u4sub.f from the 'access' folder.
	Compile them with:
		gfortran u4dump.f u4sub.f -o u4dump

	Then unpack the binary files into ascii files with u4dump
	The ascii files will take 26 gb on disk.

	Next run the import script in the cosmic directory to import the
	contents of the zXXX.asc files into the django database for the site.
	TODO: Determine DB size after import.
		python3 import_cat_ucac4_dump.py /path/to/ascii/files/*.asc

	After the import is complete and verified the ascii files can be
	deleted, freeing the 26 gb of disk space they used.  If you want to
	delete the binary files you can, but at 8.6 gb it is worth keeping them
	around in case a future import is needed.  They are not needed for the
	site to function correctly.



GCVS - General Catalogue of Variable Stars

	A catalog containing about 50,000 variable stars along with their
	minimum and maximum magnitudes, period, variability type, and spectral
	class.  No specific minimum magnitude and coverage is for the whole sky.

	Attribution: "Samus N.N., Kazarovets E.V., Durlevich O.V., Kireeva
		N.N., Pastukhova E.N., General Catalogue of Variable Stars:
		Version GCVS 5.1, Astronomy Reports, 2017, vol. 61, No. 1,
		pp.  80-88 {2017ARep...61...80S}"

	The catalog is distributed as an ascii text file downloadable from:
		http://www.sai.msu.su/gcvs/gcvs/

	The download is about 12 mb and consists of a single file: gcvs5.txt
	Once downloaded the import script can be run:
		python3 import_cat_gcvs.py /path/to/gcvs5.txt

	The import script expects version 5 of the catalog and will refuse to
	run unless the file is named gcvs5.txt.  Future versions of the catalog
	may work if they have the same format but at this time it is impossible
	to say if that will be true.  You can override this check by renaming
	your newer catalog to the expected name, or by commenting out the check
	in the python import script.

	After the script has finished importing the gcvs5.txt file could be
	deleted but it is not a big file anyway so you will probably want to
	keep it.  It is not necessary for the site to function correctly.



2MASS Extended Sources - Two Micron All Sky Survey (Only Extended Sources)

	The 2MASS survey covered the whole sky and created a huge catalog of
	stars as well as other sources.  As of right now the full 2MASS catalog
	is far to big for our purposes, so for the time being we only import the
	"extended sources" portion of the catalog.  Extended sources are
	galaxies, nebulae, etc; so we ignore the regular star portion of the
	catalog and only pull in "everything else".  The extended sources
	portion of 2MASS consists of about 1.6 million objects.

	Attribution:  "This publication makes use of data products from the Two
		Micron All Sky Survey, which is a joint project of the
		University of Massachusetts and the Infrared Processing and
		Analysis Center/California Institute of Technology, funded by
		the National Aeronautics and Space Administration and the
		National Science Foundation."

	The catalog is distributed as 2 ascii files (xsc_aaa.gz and xsc_baa.gz)
	downloadable from the following url:
		http://irsa.ipac.caltech.edu/2MASS/download/allsky/

	The download will be about 700 mb and after unziping the files require
	2.7 gb of disk space.  After unzipping the import script can be run:
		python3 import_cat_2mass_xsc.py /path/to/files/xsc_*

	After the script has finished importing the catalog the ascii files can
	be deleted to free up disk space or re-compressed.  The ascii files are
	not needed for Cosmic to work correctly after the import.



Messier Catalog - The Messier Objects

	The Messier objects are the famous list of 110 objects of varying
	types.  The data for the catalog was downloaded from Simbad and checked
	into the git repository along with code to import it.  To run the
	import simply execute:

		python3 import_cat_messier.py

	Attribution:  "1850CDT..1784..227M - Connaissance des Temps, 1784,
		227-269 (1850) - 01.01.86 20.07.15"



Astorb - The Asteroid Orbital Elements Database

    The Astorb database is the current list of orbital elements and basic data
    for all known asteroids.  It is updated daily from the Minor Planet Center
    and then some additional processing is done on it by the Lowell Observatory
    to add a few columns of data on ephemeris uncertainty for each asteroid.  As
    of 2017 the downloaded file is 54mb and it uncompresses to 200mb, containing
    data for about 700,000 asteroids.

    To import the data, first download and unzip the astorb.dat file from:

        ftp://ftp.lowell.edu/pub/elgb/astorb.html

    Then run the import python script:

        python3 import_cat_astorb.py /path/to/astorb.dat

    After the asteroid orbits themselves have been imported you need to load
    the pre-calculated AstorbEphemeride table with data by running the
    following script:

        python3 calculate_astorb_ephemerides.py

    The script will read the orbital data for each asteroid in the database and
    caluclate and store its position approximately once each month over the
    specified time period.

    Attribution: The research and computing needed to generate astorb.dat were
        funded principally by NASA grant NAG5-4741, and in part by the Lowell
        Observatory endowment. astorb.dat may be freely used, copied, and
        transmitted provided attribution to Dr. Edward Bowell and the
        aforementioned funding sources is made.



GeoLite City Database - GeoIP Database

    For certain tools on the site (such as the observing suggestions tool) we
    need to know the lat/lon of the observer.  For non-logged in users we can
    get approximate values from the GeoLite database, which is a free database
    produced by the MaxMind company.  The company offers more precise databases
    if you subscribe to the service, but the free "city level" database is good
    enough for our purposes.  The database can be downloaded from the following
    url (make sure to download the "city" version as this is what the importer
    expects and other versions have not been tested):

        https://dev.maxmind.com/geoip/legacy/geolite/

    Once downloaded and unzipped, the data can be imported in Django with:

        python3 import_cat_geoip_geolitecity.py

    Once the data has been imported with the script, you can delete the
    downloaded files as they are no-longer needed.

    Attribution: Copyright (c) 2012 MaxMind LLC.  All Rights Reserved.



Exoplanets Data Explorer Database

    The Exoplanets Data Explorer is a database of well vetted exoplanet
    discoveries and orbital information for these planets.  It contains fewer
    planets than some other databases, but the data is more carefully checked
    before inclusion in the database.  It can be downloaded from:

        http://exoplanets.org/

    After downloading the file can be imported with:

        python3 import_cat_exoplanets.py /path/to/exoplanets.csv

    After importing the csv file can be deleted as it is no longer needed.

    Attribution: This research has made use of the Exoplanet Orbit Database and
        the Exoplanet Data Explorer at exoplanets.org.

