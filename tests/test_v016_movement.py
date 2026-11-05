"""v0.16 small-step approach and facing, tests require no live WoW client."""
from __future__ import annotations
import pytest
from priestbot.config import Config
from priestbot.engine import Observation, PriestEngine
from priestbot.background_input import (
    GameWindow, post_game_hold, WM_KEYDOWN, WM_KEYUP,
)


def obs(tgt=1, hp=1, mana=1, error=None, seq=0, target_seq=0):
    return Observation(hp, mana, tgt, False, error, seq,
                       target_seq=target_seq)


def test_movement_off_by_default_range_skips():
    c = Config(main_damage='mind_blast_wand', use_pain=True)
    assert not c.enable_movement
    e = PriestEngine(c)
    assert e.update(obs(), 0).action == 'mind_blast'
    assert e.update(obs(error='range', seq=1), .5).action == 'clear_target'


def test_range_approaches_in_short_steps_and_retries_opener():
    c = Config(main_damage='mind_blast_wand', enable_movement=True, use_pain=True)
    e = PriestEngine(c)
    assert e.update(obs(), 0).action == 'mind_blast'
    # The original Mind Blast attempt must finish/time out before moving.
    assert e.update(obs(error='range', seq=1), .5).action is None
    a = e.update(obs(error='range', seq=1), 2.11)
    assert a.action == 'move_forward'
    assert e.approach_pulses == 1
    assert e.update(obs(error='range', seq=1), 2.4).action is None
    assert e.update(obs(error='range', seq=1), 2.9).action == 'mind_blast'


def test_range_moves_only_after_new_event_and_target():
    e = PriestEngine(Config(main_damage='mind_blast_wand', enable_movement=True))
    assert e.update(obs(tgt=0, error='range', seq=8), 0).action == 'next_target'
    assert e.update(obs(seq=8), 2).action == 'mind_blast'
    # Old range status is stale and should not cause movement.
    assert e.update(obs(error='range', seq=8), 2.3).action is None


def test_approach_limit_clears_target_not_endless_walking():
    c = Config(main_damage='mind_blast_wand', enable_movement=True,
               approach_max_pulses=1)
    e = PriestEngine(c)
    assert e.update(obs(), 0).action == 'mind_blast'
    assert e.update(obs(error='range', seq=1), 2.2).action == 'move_forward'
    assert e.update(obs(error='range', seq=1), 3).action == 'mind_blast'
    failure = e.update(obs(error='range', seq=2), 3.3)
    assert failure.action == 'clear_target'
    assert 'limit' in failure.reason.lower()


def test_facing_error_turns_then_retries():
    e = PriestEngine(Config(main_damage='mind_blast_wand',enable_movement=True))
    assert e.update(obs(), 0).action == 'mind_blast'
    r=e.update(obs(error='facing',seq=1),2.2)
    assert r.action=='turn_right'
    assert e.update(obs(error='facing',seq=1),2.3).action is None
    assert e.update(obs(error='facing',seq=1),2.75).action == 'mind_blast'


def test_los_still_skips_without_walking():
    e=PriestEngine(Config(main_damage='mind_blast_wand',enable_movement=True))
    assert e.update(obs(),0).action=='mind_blast'
    assert e.update(obs(error='los',seq=1),.5).action=='clear_target'


def test_low_hp_heal_before_walking():
    e=PriestEngine(Config(main_damage='mind_blast_wand',enable_movement=True))
    assert e.update(obs(),0).action=='mind_blast'
    r = e.update(obs(hp=.3, error='range', seq=1),2.2)
    assert r.action=='heal'  # no forward movement at low HP


def test_target_changed_drops_pending_movement():
    e=PriestEngine(Config(main_damage='mind_blast_wand',enable_movement=True))
    e.update(obs(),0)
    e.update(obs(error='range',seq=1),.5)
    r=e.update(obs(target_seq=1),2.2)
    assert r.action != 'move_forward'


class FakeApi:
    def __init__(self):
        self.game=GameWindow(0x12345,42,'wow.exe','WoW')
        self.events=[]
    def valid(self, target): return target==self.game
    def scan_code(self, vk): return vk & 0xFF
    def post(self, hwnd,msg,vk,lparam): self.events.append((hwnd,msg,vk))
    def vk_for_char(self,char):return -1


def test_background_hold_targets_game_only():
    api=FakeApi()
    post_game_hold('w',api.game,['wow.exe'],seconds=.05,api=api)
    assert api.events==[(api.game.hwnd,WM_KEYDOWN,ord('W')),
                        (api.game.hwnd,WM_KEYUP,ord('W'))]


def test_background_hold_cancellation_releases_key():
    api=FakeApi()
    times=[0]
    def cancelled():
        times[0]+=1
        return times[0] > 1
    with pytest.raises(RuntimeError, match='cancelled'):
        post_game_hold('right',api.game,['wow.exe'],seconds=.1,api=api,cancelled=cancelled)
    assert api.events[-1][1]==WM_KEYUP


def test_movement_key_config_preserved_with_old_keys():
    c=Config.from_dict({'keys':{'shield':'shift+e','wand':'r'}})
    assert c.keys['shield']=='shift+e'
    assert c.keys['move_forward']=='w'
    assert c.keys['turn_right']=='right'
    assert not c.enable_movement
