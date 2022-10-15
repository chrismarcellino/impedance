# TimeValueSample.py
from dataclasses import dataclass


# Common immutable sample data structure, for future extensibility (i.e. metadata, comments, etc.)
@dataclass(frozen=True)
class TimeValueSample:
    t: float
    v: float
