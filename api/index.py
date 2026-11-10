"""Vercel ASGI entry point. Cloud configuration must be explicit."""
import os

os.environ['NEWS_BACKGROUND_ENABLED'] = '0'
os.environ['PUBLIC_FORECAST_BACKGROUND_ENABLED'] = '0'

from server.deployment import validate
validate()
from server.app import app
