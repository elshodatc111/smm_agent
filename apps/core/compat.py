"""Python 3.10 bilan moslik (enum.StrEnum faqat 3.11+ da bor)."""
try:
    from enum import StrEnum
except ImportError:  # Python 3.10
    from enum import Enum

    class StrEnum(str, Enum):
        def __str__(self):
            return str(self.value)

        @staticmethod
        def _generate_next_value_(name, start, count, last_values):
            return name.lower()
