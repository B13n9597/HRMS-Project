from django.apps import AppConfig


class HrConfig(AppConfig):
    name = 'hr'

    def ready(self):
        import hr.signals  
