from itertools import product
from math import comb, isclose
import pytest
from .core import SPEC, HYDROPATHY, chemistry_quadratic, evaluate_quadratic, bits_to_sequence, sequence_to_bits, hydrophobic_moment, sequence_properties, exact_reference

def test_constants_and_feasible_count():
    assert HYDROPATHY['L']==3.8 and HYDROPATHY['K']==-3.9
    assert exact_reference()['feasible_sequences']==comb(8,3)==56

def test_bits_roundtrip():
    for bits in product((0,1),repeat=8):
        assert sequence_to_bits(bits_to_sequence(bits))==bits

def test_order_sensitive_and_fixed_composition():
    a='KKKLLLLL'; b='KLKLKLLL'
    assert a.count('K')==b.count('K')==3
    assert not isclose(hydrophobic_moment(a)**2,hydrophobic_moment(b)**2,abs_tol=1e-10)
    assert isclose(sequence_properties(a)['approximate_net_charge'],sequence_properties(b)['approximate_net_charge'])

def test_quadratic_identity_for_all_256_states():
    q=chemistry_quadratic()
    for bits in product((0,1),repeat=8):
        seq=bits_to_sequence(bits)
        assert isclose(evaluate_quadratic(bits,q), -hydrophobic_moment(seq)**2, abs_tol=1e-11)

def test_feasible_and_rejections():
    assert sequence_properties('KKKLLLLL')['feasible']
    assert not sequence_properties('KLLLLLLL')['feasible']
    with pytest.raises(ValueError):
        sequence_properties('KKKLLXXX')
    with pytest.raises(ValueError):
        sequence_properties('KKKLLLL')
    with pytest.raises(ValueError):
        sequence_properties('KKKLLLLL',pH=-1)

def test_reference_matches_best_direct():
    d=exact_reference()
    assert d['all_binary_states']==256
    assert d['max_quadratic_identity_error']<1e-11
    assert d['best_feasible']['sequence'].count('K')==3
