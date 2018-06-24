from django.apps import AppConfig

class CosmicappConfig(AppConfig):
    name = 'cosmicapp'
    runAlready = False

    def ready(self):
        #TODO: Add a file lock to prevent this method from running twice in a development environment.
        print('Config "ready" method called.')
        import cosmicapp.hooks

