"""Real race data wrapper.

The app now sources races from the normalized historical CSV instead of a sample
calendar file.
"""

from .data_sources import get_races


races = [race.model_dump() for race in get_races()]
