teh-tracker
===========
[![Build Status](https://integration.wikimedia.org/ci/job/wikimedia-cz-tracker-tox-docker/badge/icon)](https://integration.wikimedia.org/ci/view/WMF/job/wikimedia-cz-tracker-tox-docker/)

This is a Django app designed to track [Wikimedia CZ](https://www.wikimedia.cz/) projects and money. We kind of hope it might be useful for someone else too.

Issues can be reported at https://phabricator.wikimedia.org/project/board/3391/ or at tracker@wikimedia.cz.

# Run development environment

(all paths are from repository's root)

1. Clone the repository (preferably from [Gerrit](https://gerrit.wikimedia.org/r/admin/projects/wikimedia-cz/tracker)
2. Setup the repository for use with git review. You can use [this tutorial](https://www.mediawiki.org/wiki/Gerrit/Tutorial)
3. Create /deploy folder
4. Create Python2.7 virtual environment (venv) by running `virtualenv deploy/pyenv`
5. Activate the venv by running `source deploy/pyenv/bin/activate`
6. Install required packages by running `pip install -r support/requirements.txt`
7. Run `python support/makesettings.py` to get example settings.py
8. Run `python trackersite/manage.py runserver` to start the development server. It should listen on localhost:8000
