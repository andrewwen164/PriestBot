"""Counter reading remains strict but tolerates isolated rendering artifacts."""
from __future__ import annotations
import numpy as np
import pytest
from PIL import Image
from priestbot.bridge import BridgeNotFound, decode_bridge
from test_v08_aura_success import panel_v08


@pytest.mark.parametrize("scale", [1.0, 1.0833, 1.17, 1.25, 1.3333, 1.5, 2.0])
@pytest.mark.parametrize("resampler", [Image.Resampling.NEAREST,
                                      Image.Resampling.BILINEAR])
@pytest.mark.parametrize("sseq,tseq", [(0,0),(1,8),(5,10),(15,15)])
def test_fractional_scale_roundtrip(scale, resampler, sseq, tseq):
    orig = panel_v08(seq=sseq,target_seq=tseq)[60:162,70:230]
    scaled = np.asarray(Image.fromarray(orig).resize(
        (round(160*scale), round(102*scale)), resample=resampler))
    full = np.zeros((420,560,3),dtype=np.uint8)
    full[:]=(20,25,30)
    full[60:60+scaled.shape[0],70:70+scaled.shape[1]]=scaled
    o = decode_bridge(full).observation
    assert (o.success_seq,o.target_seq) == (sseq,tseq)


def test_single_pixel_color_damage_is_tolerated():
    image=panel_v08(seq=5,target_seq=10)
    # Corrupt exactly the middle pixel where older decoder sampled.
    image[60+88,70+68] = (240,0,240)
    o=decode_bridge(image).observation
    assert (o.success_seq,o.target_seq)==(5,10)


def test_corrupt_tile_still_stops_with_diagnostics():
    image=panel_v08(seq=5,target_seq=10)
    image[60+84:60+92,70+112:70+120] = (2,180,210)
    with pytest.raises(BridgeNotFound,match=r"target counter bit 1.*RGB=.*scale="):
        decode_bridge(image)
