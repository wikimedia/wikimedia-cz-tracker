from importlib import import_module
from importlib.util import find_spec

from django.conf import settings

from background_task.management.commands import process_tasks


def autodiscover():
    """
    Import the tasks module of each installed app.

    django-background-tasks 1.2.5 does this with the imp module. Python 3.12
    removes that module. This function does the same work with importlib.
    """
    for app in settings.INSTALLED_APPS:
        try:
            spec = find_spec('%s.tasks' % app)
        except ImportError:
            continue
        if spec is not None:
            import_module('%s.tasks' % app)


# The upstream command calls autodiscover() from its module namespace.
# Replace it there, so that the upstream run() uses this function.
process_tasks.autodiscover = autodiscover


class Command(process_tasks.Command):
    # The tracker app comes before background_task in INSTALLED_APPS.
    # Thus Django uses this command for "manage.py process_tasks".
    pass
