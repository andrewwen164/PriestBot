import numpy as np
from priestbot.vision import bar_fraction

def make_bar(pct=1.0,color=(45,187,52)):
    pixels=np.full((16,200,3),22,dtype=np.uint8)
    pixels[:,:int(200*pct),:]=color
    return pixels

def test_full():
    assert .97<=bar_fraction(make_bar(1))<=1.0

def test_half():
    assert abs(bar_fraction(make_bar(.5))-.5)<.025

def test_empty():
    assert bar_fraction(make_bar(0))==0

def test_blue():
    assert abs(bar_fraction(make_bar(.27,(45,80,200)))-.27)<.025

def test_red():
    assert abs(bar_fraction(make_bar(.65,(195,55,40)))-.65)<.025
