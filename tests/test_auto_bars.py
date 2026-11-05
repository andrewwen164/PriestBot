from PIL import Image,ImageDraw
from priestbot.auto_bars import suggest_bars


def _sample():
    im = Image.new("RGB", (1280, 720), (24, 24, 32))
    d = ImageDraw.Draw(im)
    d.rectangle((80, 70, 260, 82), fill=(12, 205, 34))
    d.rectangle((80, 91, 260, 102), fill=(20, 80, 215))
    d.rectangle((510, 70, 690, 82), fill=(210, 20, 20))
    return im


def test_detects_solid_player_bars_and_enemy_target():
    boxes=suggest_bars(_sample())
    assert set(boxes)=={"player_health", "player_mana", "target_health"}
    for key, x, y in [("player_health", 80, 70), ("player_mana",80,91),("target_health",510,70)]:
        b=boxes[key].box
        assert abs(b[0]-x)<=3, (key,b)
        assert abs(b[1]-y)<=3, (key,b)
        assert b[2]-b[0] >= 160, (key,b)


def test_returns_no_suggestions_for_unrecognizable_screenshot():
    im = Image.new("RGB", (1280,720), (31,31,31))
    assert suggest_bars(im)=={}
