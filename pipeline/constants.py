"""pipeline/constants.py — shared enums for pipeline string constants.

str 믹스인을 사용해 Python 3.10+에서 문자열로 직접 비교 가능.
"""

from enum import Enum


class BeatFunction(str, Enum):
    HOOK = "hook"
    EMPATHY = "empathy"
    TIP = "tip"
    REVEAL = "reveal"
    PRODUCT_FOCUS = "product_focus"
    CTA = "cta"


class SceneType(str, Enum):
    HOOK = "hook"
    REACTION = "reaction"
    EMPATHY = "empathy"
    TIP = "tip"
    PRODUCT_FOCUS = "product_focus"
    CTA = "cta"


class SubtitleDensity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
