import subprocess
import sys


def main():
    with open("trackersite/locale/django.pot", "rb") as fd:
        entries = fd.read().count(b"msgid")

    subprocess.run("cd trackersite; python3 manage.py makemessages --keep-pot", shell=True, check=True,
                   stdout=subprocess.DEVNULL)

    with open("trackersite/locale/django.pot", "rb") as fd:
        updated_entries = fd.read().count(b"msgid")

    if entries != updated_entries:
        sys.exit(1)


if __name__ == '__main__':
    main()
