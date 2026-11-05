"""Opt-in, game-window-only farming demonstration annotation.

Records attempts and *separate* evidence for search, target acquisition, spell
rotations, and looting. No autonomous inputs and no training-model promotion.
Actual controls/images remain in SessionRecorder's existing files. Training
examples include a PRE-action frame and the first subsequently captured frame.
"""
from __future__ import annotations

from collections import Counter, deque
import json
import time


SUPPORTED_GAME_KINDS = {'G', 'L', 'D', 'S', 'T', 'H', 'F', 'C', 'I'}


class FarmingDemonstrations:
    def __init__(self, session_path, *, emit=None):
        self.path = session_path
        self.emit = emit or (lambda _name, **_fields: None)
        self.examples_file = (session_path / 'farming_examples.jsonl').open('w', encoding='utf-8')
        self.counters = Counter()
        self.recent = deque(maxlen=120)
        self.recent_interactions = deque(maxlen=24)
        self.phase = 'search'
        self.active_loot = None
        self.finished_loots = []
        self.pending = []
        self.last_packet_sequence = None
        self.target_observed = False
        self.last_target_generation = None
        self.last_frame = None
        self.last_state = {}
        self.events_written = 0
        self.closed = False

    def _event(self, label, mono, *, evidence='attempted', source='input', **fields):
        if self.closed:
            return
        row = {'category': label, 'evidence': evidence, 'source': source,
               'observed_at_mono': round(float(mono), 4),
               'phase': self.phase, 'before_frame': self.last_frame,
               'before_state': dict(self.last_state), **fields}
        self.counters[label] += 1
        self.recent.append({k: v for k, v in row.items()
                            if k not in ('before_state',)})
        self.emit('farming_event', **row)
        self.pending.append(row)
        if len(self.pending) > 1000:  # bounded during unusually event-heavy sessions
            self._flush(None, None, limit=500)

    def _flush(self, after_frame, after_state, *, limit=None):
        batch = self.pending if limit is None else self.pending[:limit]
        for row in batch:
            record = dict(row, after_frame=after_frame,
                          after_state=dict(after_state or {}) if after_frame else None,
                          image_pair_complete=bool(row.get('before_frame') and after_frame))
            self.examples_file.write(json.dumps(record, separators=(',', ':'), allow_nan=False) + '\n')
            self.events_written += 1
        if batch:
            self.examples_file.flush()
        del self.pending[:len(batch)]

    def observe(self, frame, state, mono):
        """Call only on a valid new WoW screenshot, after it has been saved."""
        if self.closed:
            return
        # A screenshot is AFTER an event only if it arrived later than the event.
        ready = [x for x in self.pending if mono > x['observed_at_mono'] + .001]
        if ready:
            for row in ready:
                record = dict(row, after_frame=frame, after_state=dict(state or {}),
                              image_pair_complete=bool(row.get('before_frame')))
                self.examples_file.write(json.dumps(record, separators=(',', ':'), allow_nan=False) + '\n')
                self.events_written += 1
            self.examples_file.flush()
            self.pending = [x for x in self.pending if x not in ready]
        self.last_frame = frame
        self.last_state = dict(state or {})
        target_seq = self.last_state.get('target_seq')
        if (target_seq is not None and self.last_target_generation is not None
                and target_seq != self.last_target_generation):
            # Game telem is only 4-bit, so treat as a change hint, not identity.
            self._event('target_change_hint', mono, evidence='telemetry_generation_changed',
                        source='PriestBridge_bars', generation=target_seq)
        self.last_target_generation = target_seq
        if self.active_loot is None:
            target_health = self.last_state.get('target_hp')
            if target_health is not None and float(target_health) > 0:
                if self.phase == 'search':
                    self.phase = 'engage'
            elif self.phase == 'engage':
                self.phase = 'search'

    def input(self, kind, mono, *, data=None, binding=None):
        if self.closed:
            return
        d = data or {}
        name = str(d.get('key') or '').lower()
        command = str(getattr(binding, 'command', '') or '').upper()
        action_type = str(getattr(binding, 'action_type', '') or '')
        action_name = str(getattr(binding, 'action_name', '') or '')
        key = str(d.get('chord') or name).upper()
        if kind == 'key_down':
            if name in ('tab',) or any(tag in command for tag in ('TARGETNEAREST', 'TARGETLAST', 'TARGETENEMY')):
                self.phase = 'search'
                self._event('target_search_attempt', mono, key=key, command=command)
            elif action_type in ('spell', 'macro', 'item'):
                label = 'rotation_input' if action_type in ('spell', 'macro') else 'item_input'
                self._event(label, mono, key=key, action_type=action_type,
                            action_name=action_name, action_id=getattr(binding,'action_id',0),
                            binding_generation=getattr(binding,'generation',None))
            elif 'INTERACT' in command:
                self.recent_interactions.append({'time': mono, 'input': key,
                                                 'frame': self.last_frame, 'kind': 'keybind'})
                self._event('interact_attempt', mono, key=key, command=command)
        elif kind == 'mouse_down':
            # No claim that a click selected a unit or interacted with a corpse.
            button = str(d.get('button') or '')
            if button in ('left', 'right'):
                self.recent_interactions.append({'time': mono, 'input': button,
                                                 'x': d.get('x'), 'y': d.get('y'),
                                                 'frame': self.last_frame, 'kind': 'mouse_down'})
                self._event('mouse_click_candidate', mono, button=button,
                            x=d.get('x'), y=d.get('y'))
        elif kind == 'scroll':
            # Raw timeline already contains scroll. It is not a verified target action.
            return

    def packet(self, packet, mono):
        if self.closed or packet is None or packet.sequence == self.last_packet_sequence:
            return
        self.last_packet_sequence = packet.sequence
        kind, fields = packet.kind, packet.fields
        if kind not in SUPPORTED_GAME_KINDS:
            return
        if kind == 'G' and len(fields) >= 3:
            # Native selection event. Hostility and living state may be unknown.
            self.target_observed = fields[1] != 'none'
            self.phase = 'engage' if fields[1] == 'hostile' and fields[2] != 'dead' else 'search'
            self._event('target_selected' if self.target_observed else 'target_cleared', mono,
                        evidence='native_target_changed', source='PriestBridge',
                        target_generation=fields[0], kind=fields[1], life=fields[2],
                        display_name='|'.join(fields[3:]) if len(fields) > 3 else '')
            return
        if kind == 'L' and len(fields) >= 1:
            event = fields[0]
            if event in ('opened', 'ready'):
                if self.active_loot is None:
                    self.active_loot = {'started': mono, 'slots_cleared': 0, 'opened': False,
                                        'ready': False}
                self.active_loot['ready' if event == 'ready' else 'opened'] = True
                self.phase = 'loot'
                # This is a *possible* preceding interaction, not a verified
                # linkage. Optical packets can arrive later than their input.
                last = next((x for x in reversed(self.recent_interactions)
                             if 0 <= mono-x['time'] <= 7), None)
                candidate = None if last is None else {
                    'input': last['input'], 'x': last.get('x'), 'y': last.get('y'),
                    'frame': last.get('frame'), 'age_ms': round((mono-last['time'])*1000),
                    'association': 'temporal_candidate_unverified'}
                self._event('loot_' + event, mono, evidence='native_loot_window_event',
                            source='PriestBridge', reported_count=fields[1] if len(fields)>1 else '',
                            candidate_interaction=candidate)
            elif event == 'slot_cleared':
                if self.active_loot is not None:
                    self.active_loot['slots_cleared'] += 1
                self._event('loot_slot_cleared', mono, evidence='native_slot_cleared',
                            source='PriestBridge', slot=fields[1] if len(fields)>1 else '')
            elif event == 'closed':
                cleared = self.active_loot['slots_cleared'] if self.active_loot else 0
                self._event('loot_closed', mono, evidence='native_loot_window_closed',
                            source='PriestBridge', cleared_slots=cleared)
                self.finished_loots.append({'cleared_slots': cleared,
                                            'outcome': 'slot_cleared_observed' if cleared else 'unknown'})
                self.active_loot = None
                self.phase = 'search'
            return
        if kind == 'D' and fields:
            event = fields[0]
            if event == 'combat_start':
                self.phase = 'engage'
            elif event == 'combat_end' and self.active_loot is None:
                self.phase = 'search'
            self._event(event, mono, evidence='native_combat_flag', source='PriestBridge')
            return
        if kind in ('S','T','H','F'):
            event = {'S':'spell_success','T':'spell_start','H':'channel_start','F':'spell_failure'}[kind]
            evidence = {'S':'native_cast_succeeded','T':'native_cast_started',
                        'H':'native_channel_started','F':'native_cast_failed'}[kind]
            self._event(event, mono, evidence=evidence, source='PriestBridge',
                        spell_id=fields[0] if fields else '',
                        spell_name='|'.join(fields[1:]) if len(fields)>1 else '')
            return
        if kind in ('C','I'):
            self._event('actionbar_trigger' if kind == 'C' else 'bag_item_attempt', mono,
                        evidence='native_action_attempt', source='PriestBridge', fields=list(fields))

    def snapshot(self):
        tips = []
        if not self.counters['target_selected']:
            tips.append('Demonstrate finding and selecting mobs; verify target change events in PriestBridge.')
        if not self.counters['spell_success']:
            tips.append('Demonstrate full spell rotations and verify successful casts in the action timeline.')
        if not self.counters['loot_opened']:
            tips.append('Demonstrate approaching and opening loot on corpses, including an empty corpse.')
        if not self.counters['loot_slot_cleared']:
            tips.append('Record a loot session with at least one cleared slot; window opening alone is not item acquisition.')
        return {'schema': 1, 'counts': dict(self.counters), 'phase': self.phase,
                'examples_saved': self.events_written, 'pending_examples': len(self.pending),
                'loot_sessions': list(self.finished_loots[-30:]),
                'recent': list(self.recent)[-60:],
                'recommendations': tips,
                'limitations': ('Outcome events are not proof of XP earned or a mob killed. '
                                'A slot-cleared event is evidence of loot-slot interaction, not confirmed inventory gain. '
                                'Screenshots and inputs remain game-focused, opt-in only. '
                                'These records are training data; they do not enable autonomous looting/combat.')}

    def interrupt(self, reason='focus_or_privacy_pause'):
        """Never bridge an example from a WoW frame to another window/time."""
        if self.closed:
            return
        self._flush(None, None)
        self.last_frame = None
        self.last_state = {}
        self.emit('farming_capture_break', reason=reason)

    def close(self):
        if self.closed:
            return
        self._flush(None, None)
        self.closed = True
        self.examples_file.close()
        (self.path / 'farming_report.json').write_text(json.dumps(self.snapshot(), indent=2),
                                                       encoding='utf-8')
