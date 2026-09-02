from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from core import checks  # noqa: F401 — import registers the checks via @register()

        # `manage.py runserver` with no port arg defaults to 8000. Django resolves
        # the `runserver` command to whichever INSTALLED_APPS entry defines it that
        # sits earliest in the list (django.contrib.staticfiles, here) — an app-local
        # management/commands/runserver.py in `core` would silently lose to it since
        # `core` is listed after staticfiles. Patching the class attribute here runs
        # before command dispatch and affects the actual class Django will use.
        from django.contrib.staticfiles.management.commands.runserver import Command as RunserverCommand
        RunserverCommand.default_port = '8002'
