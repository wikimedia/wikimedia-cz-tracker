import os
import subprocess
import sys

import django
import click
from django.conf import settings
from django.template import Template, Context
from django.utils.crypto import get_random_string

MY_PATH = os.path.abspath(os.path.dirname(__file__))


@click.command()
@click.option('--db_backend', type=click.Choice(['MySQL', 'SQLite']), default='MySQL')
@click.option('--db_name', type=str)
@click.option('--db_user', type=str)
@click.option('--db_pass', type=str)
@click.option('--db_host', type=str, default='')
@click.option('--db_port', type=str, default='')
@click.option('--db-creation/--no-db-creation', is_flag=True, default=True)
def main(db_backend, db_name, db_user, db_pass, db_host, db_port, db_creation):
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

    if db_backend == "MySQL":
        options['backend'] = 'mysql'
        options['DB_NAME'] = db_name if db_name else click.prompt('Database name', default='tracker')
        options['DB_USER'] = db_user if db_user else click.prompt('Database user', default='root')
        options['DB_PASS'] = db_pass if db_pass else click.prompt('Database password', default='')
        options['DB_HOST'] = db_host
        options['DB_PORT'] = db_port

        if db_creation:
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
    elif db_backend == "SQLite":
        options['backend'] = 'sqlite3'
        default_path = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'deploy', 'tracker.db'))
        options['DB_NAME'] = questionary.text("Path to new database file", default=default_path).ask()
        options['DB_USER'] = ''
        options['DB_PASS'] = ''
        options['DB_HOST'] = ''
        options['DB_PORT'] = ''
    else:
        raise Exception('Invalid DB backend')

    context = Context(options)
    target = open(target_path, 'wb')
    target.write(template.render(context).encode('utf-8'))
    target.close()


if __name__ == '__main__':
    main()
