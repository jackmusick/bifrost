"""
Password Generation Helpers

Generates human-friendly passphrases for temporary credentials.
"""

import secrets
import string


WORD_LIST = [
    "apple", "brave", "cloud", "delta", "eagle", "flame", "grace", "house",
    "ivory", "jewel", "kite", "light", "maple", "noble", "ocean", "piano",
    "quest", "river", "stone", "tiger", "ultra", "vivid", "water", "xenon",
    "yacht", "zebra", "amber", "blaze", "coral", "dream", "ember", "frost",
    "globe", "haven", "island", "joker", "karma", "lotus", "mango", "north",
    "orbit", "pearl", "quilt", "robin", "solar", "torch", "unity", "valor",
    "wheat", "pixel", "forge", "crown", "swift", "lunar", "cedar", "bloom",
    "cliff", "dune", "fern", "gold", "hawk", "jade", "lark", "mesa",
    "nova", "opal", "plum", "sage", "tide", "vine", "wolf", "aspen",
]


def generate_passphrase(word_count: int = 4) -> str:
    """Generate a random passphrase from the word list."""
    words = [secrets.choice(WORD_LIST) for _ in range(word_count)]
    # Capitalize first word, add a random digit at the end
    words[0] = words[0].capitalize()
    digit = secrets.choice(string.digits)
    return "-".join(words) + digit
