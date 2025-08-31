import os
import polib


def find_pot_files(base_path):
    """
    Recursively finds all .pot files within a given directory.
    """
    pot_files = []
    for root, _, files in os.walk(base_path):
        for file in files:
            if file.endswith('.pot'):
                pot_files.append(os.path.join(root, file))
    return pot_files


def test_no_trailing_whitespace_in_messages():
    """
    Tests that no message strings in .pot files have trailing whitespace.
    """
    project_root = os.path.join(os.path.dirname(__file__), '..', '..')

    pot_files = find_pot_files(project_root)

    if not pot_files:
        raise AssertionError("No .pot files found to test.")

    for file_path in pot_files:
        try:
            po = polib.pofile(file_path)
        except Exception as e:
            raise AssertionError(f"Could not parse file: {file_path}. Error: {e}")

        for entry in po:
            if entry.msgid and entry.msgid.rstrip() != entry.msgid:
                raise AssertionError(
                    f"Found trailing whitespace in a message ID ('msgid') "
                    f"in file: {file_path}, line {entry.linenum}.\n"
                    f"Message ID: '{entry.msgid}'"
                )

            if entry.msgstr and entry.msgstr.rstrip() != entry.msgstr:
                raise AssertionError(
                    f"Found trailing whitespace in a message string ('msgstr') "
                    f"in file: {file_path}, line {entry.linenum}.\n"
                    f"Message ID: '{entry.msgid}'\n"
                    f"Message String: '{entry.msgstr}'"
                )
