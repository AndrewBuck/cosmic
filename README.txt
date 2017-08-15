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





Commands needed installed on the system and in the path:
(Note these are mainly needed on the worker nodes running celery workers, not necessarily on the webserver itself)

identify - part of imagemagick.

