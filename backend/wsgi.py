"""WSGI entry point; never start the development server on PythonAnywhere."""
from app import create_app

application = create_app()

