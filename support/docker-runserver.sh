#!/bin/bash

set -e

cd /home/appuser

sleep 6

if [ ! -f trackersite/settings.py ]; then
	# no config exists
	python3 /home/appuser/support/makesettings.py --db_backend=MySQL --db_host=mariadb --db_name tracker --db_user tracker --db_pass wikipassword --no-db-creation
	python3 trackersite/manage.py migrate
fi

python3 trackersite/manage.py runserver 0.0.0.0:8000