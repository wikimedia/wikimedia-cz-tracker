import os
import sys
import subprocess

import django
from django.template import Template, Context
from django.conf import settings
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
    print('Select your database provider')
    print('1) MySQL')
    print('2) SQLite')
    db_choice = int(input('Your choice: '))
    print("We'll ask you few questions now. Press enter if you want the defaults.")
    if db_choice == 1:
        options['backend'] = 'mysql'
        options['DB_NAME'] = input('Database name [tracer]: ') or 'tracker'
        options['DB_USER'] = input('Database username [root]: ') or 'root'
        options['DB_PASS'] = input('Database password [empty string]: ') or ''
        options['DB_HOST'] = input('Database hostname [localhost]: ') or ''
        options['DB_PORT'] = input('Database port [MySQL default]: ') or ''
        print('Creating your database')
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
        ])
    elif db_choice == 2:
        options['backend'] = 'sqlite3'
        default_path = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'deploy', 'tracker.db'))
        options['DB_NAME'] = input('Path to new database file [%s]: ' % default_path) or default_path
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
