import os
import subprocess
import sys

import django
import questionary
from django.conf import settings
from django.template import Template, Context
from django.utils.crypto import get_random_string

MY_PATH = os.path.abspath(os.path.dirname(__file__))


def main():
    target_path = os.path.abspath(os.path.join(MY_PATH, '..', 'trackersite', 'settings.py'))
    if os.path.exists(target_path):
        print('Don\'t want to overwrite %s.\nIf you\'re sure, delete it and try again.' % target_path)
        sys.exit(1)

    # make a template instance
    settings.configure(TEMPLATES=[
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates'
        }
    ], TEMPLATE_DEBUG=False)
    django.setup()
    template_file = open(os.path.join(MY_PATH, 'settings.py.template'))
    template = Template(template_file.read())
    template_file.close()

    # set up the options we want
    options = {}
    chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
    options['secret_key'] = get_random_string(50, chars)

    # DB provider
    # TODO: Add Oracle and postgresql_psycopg2
    db_choice = questionary.select(
        "Select your database provider",
        choices=[
            "MySQL",
            "SQLite"
        ]
    ).ask()
    if db_choice == "MySQL":
        options['backend'] = 'mysql'
        options['DB_NAME'] = questionary.text("Database name", default="tracker").ask()
        options['DB_USER'] = questionary.text("Database username", default="root").ask()
        options['DB_PASS'] = questionary.password("Database password").ask()
        options['DB_HOST'] = questionary.text("Database hostname [localhost]").ask()
        options['DB_PORT'] = questionary.text("Database port").ask()
        print('INFO: Creating your database')
        subprocess.call([
            'mysql',
            # Pass username
            '-u', options['DB_USER'],
            # Pass password
            '-p' + options['DB_PASS'],
            # Pass -h and hostname, but only if db_host is non-empty string
            '-h ' + options['DB_HOST'] if options['DB_HOST'] else '',
            # Same for db_port
            '-P ' + options['DB_PORT'] if options['DB_PORT'] else '',
            '-e',
            'CREATE DATABASE %s' % options['DB_NAME']
        ], stdout=subprocess.DEVNULL)
    elif db_choice == "SQLite":
        options['backend'] = 'sqlite3'
        default_path = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'deploy', 'tracker.db'))
        options['DB_NAME'] = questionary.text("Path to new database file", default=default_path).ask()
        options['DB_USER'] = ''
        options['DB_PASS'] = ''
        options['DB_HOST'] = ''
        options['DB_PORT'] = ''

    context = Context(options)
    target = open(target_path, 'wb')
    target.write(template.render(context).encode('utf-8'))
    target.close()


if __name__ == '__main__':
    main()
