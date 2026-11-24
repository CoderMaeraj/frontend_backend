import os
import sys

# Make the backend modules (app, models, config ...) importable from the tests folder.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
