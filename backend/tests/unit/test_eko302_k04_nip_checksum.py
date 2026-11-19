"""EKO-3-02 K-04, unit half (CUS-5): the NIP check digit is the sum of the first nine digits
weighted 6, 5, 7, 2, 3, 4, 5, 6, 7, modulo 11, and a remainder of 10 is no NIP at all.

Every NIP is synthetic and built at run time (G-7 A, `tests/support/eko302_nip.py`).
"""

import string

import pytest

from app.domain import customers as rules
from tests.support import eko302_nip as nips


def test_k04_each_weight_moves_the_check_digit_by_its_own_amount() -> None:
    # Nine digits with one 1 at position i have the weighted sum WEIGHTS[i], below 11: the check
    # digit is the weight itself, so a wrong weight at any position is a rejected NIP.
    for position, weight in enumerate(nips.WEIGHTS):
        nine = "0" * position + "1" + "0" * (8 - position)
        assert rules.polish_nip(nine + str(weight)) == nine + str(weight)
        with pytest.raises(ValueError):
            rules.polish_nip(nine + str((weight + 1) % 10))


def test_k04_the_sum_is_taken_modulo_11() -> None:
    # 9 * (6 + 5 + 7 + 2 + 3 + 4 + 5 + 6 + 7) = 405 = 36 * 11 + 9.
    nine = "9" * 9
    assert sum(9 * weight for weight in nips.WEIGHTS) % 11 == 9
    assert rules.polish_nip(nine + "9") == nine + "9"
    # 405 % 10 = 5 would be the check digit of a rule that drops the modulo 11.
    with pytest.raises(ValueError):
        rules.polish_nip(nine + "5")


def test_k04_remainder_ten_is_never_a_nip() -> None:
    ten = nips.remainder_ten_digits(0)
    assert nips.remainder(ten[:9]) == 10
    # Not one of the ten possible check digits makes it valid; `% 11 % 10` would accept "0".
    for digit in string.digits:
        with pytest.raises(ValueError):
            rules.polish_nip(ten[:9] + digit)


def test_k04_a_synthetic_valid_nip_is_accepted_and_its_neighbour_is_not() -> None:
    nip = nips.valid_nip(4242)
    assert rules.polish_nip(nip) == nip
    with pytest.raises(ValueError):
        rules.polish_nip(nips.wrong_check_digit(nip))
