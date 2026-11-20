"""EKO-3-02, G-7 A: synthetic Polish NIPs built at run time, never written as literals.

The K-07 personal-data guard flags any ten-digit run in an added line, so no test holds a NIP;
each one is built here from nine digits and a check digit computed by this module's own copy of
the CUS-5 rule (weights 6, 5, 7, 2, 3, 4, 5, 6, 7; the weighted sum modulo 11; remainder 10 is no
NIP), independent of `app.domain`. Every value starts with `000`, which is no tax office's prefix,
so none can be a real taxpayer's identifier (ADR-0005, "Synthetic customer data").
"""

WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)
SYNTHETIC_PREFIX = "000"


def remainder(nine: str) -> int:
    assert len(nine) == 9 and nine.isascii() and nine.isdigit(), "nine ASCII digits"
    return sum(int(digit) * weight for digit, weight in zip(nine, WEIGHTS, strict=True)) % 11


def _nine(seed: int) -> str:
    return SYNTHETIC_PREFIX + f"{seed:06d}"


def valid_nip(seed: int) -> str:
    """The first checksum-valid synthetic NIP at or after `seed` (0 to 999 999)."""
    for candidate in range(seed, 1_000_000):
        nine = _nine(candidate)
        check = remainder(nine)
        if check != 10:
            return nine + str(check)
    raise AssertionError("no valid synthetic NIP after the seed")


def remainder_ten_digits(seed: int) -> str:
    """Ten digits whose first nine have weighted remainder 10, so no check digit makes a NIP."""
    for candidate in range(seed, 1_000_000):
        nine = _nine(candidate)
        if remainder(nine) == 10:
            return nine + "0"
    raise AssertionError("no remainder-10 synthetic value after the seed")


def wrong_check_digit(nip: str) -> str:
    """The same NIP with only its check digit changed."""
    return nip[:9] + str((int(nip[9]) + 1) % 10)


def hyphenated(nip: str) -> str:
    """`XXX-XXX-XX-XX`, the usual written form."""
    return "-".join((nip[0:3], nip[3:6], nip[6:8], nip[8:10]))


def spaced(nip: str) -> str:
    return " ".join((nip[0:3], nip[3:6], nip[6:8], nip[8:10]))


def other_digits(nip: str, zero: int) -> str:
    """The same digits written from another Unicode digit block (`0xFF10` full-width, `0x0660`
    Arabic-Indic), which `str.isdigit()` and a regex digit class accept and CUS-5 does not."""
    return "".join(chr(zero + int(digit)) for digit in nip)
