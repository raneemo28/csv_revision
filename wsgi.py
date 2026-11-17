# WSGI entry point for PythonAnywhere.
#
# Paste this into the WSGI configuration file on the Web tab (it is
# /var/www/<username>_pythonanywhere_com_wsgi.py). You do not need to edit
# anything: the project path is derived from your home directory, so this
# works as long as the project folder is named "csv_revision" and sits in
# /home/<your-username>/csv_revision.
import os
import sys

PROJECT_HOME = os.path.join(os.path.expanduser("~"), "csv_revision")
if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)
os.chdir(PROJECT_HOME)

from app import app as application  # noqa: E402
