"""Join foreground WoW input demonstrations with native addon binding/cast hints.

Read-only labeling: keypress is only an ATTEMPT; a matching spellcast or readable
positive aura is separate evidence. Macro conditionals are never assumed to
have executed just because the macro key was pressed.
"""
from __future__ import annotations
from collections import Counter, deque
from dataclasses import dataclass, asdict
import time

MODIFIERS = {'alt', 'ctrl', 'shift', 'meta', 'win'}


def wow_binding(chord: str) -> str:
    """Normalize pynput chords to Blizzard GetBinding() key notation."""
    words = str(chord).lower().replace('-', '+').split('+')
    names = {'control': 'ctrl', 'control_l': 'ctrl', 'control_r': 'ctrl',
             'ctrl_l': 'ctrl', 'ctrl_r': 'ctrl', 'shift_l': 'shift',
             'shift_r': 'shift', 'alt_l': 'alt', 'alt_r': 'alt',
             'esc': 'escape', 'return': 'enter', 'space': 'space',
             'page_up': 'pageup', 'page_down': 'pagedown'}
    words = [names.get(w.strip(), w.strip()) for w in words if w.strip()]
    if not words or all(w in MODIFIERS for w in words):
        return ''
    mods = [k.upper() for k in ('ctrl', 'shift', 'alt', 'meta') if k in words]
    key = next((w.upper() for w in reversed(words) if w not in MODIFIERS), '')
    return '-'.join(mods + [key]) if key else ''


@dataclass(frozen=True)
class Binding:
    key: str
    command: str
    action_type: str
    action_id: int
    action_name: str
    generation: int

    @property
    def ambiguous(self):
        return self.action_type in ('macro', 'binding', 'slot')


class ActionSemanticTracker:
    def __init__(self, emit=None):
        self.emit = emit or (lambda *_a, **_kw: None)
        self.bindings: dict[str, Binding] = {}
        self.generation = None
        self.last_sequence = None
        self.attempts = deque(maxlen=120)
        self.recent = deque(maxlen=80)
        self.counts = Counter()
        self.packets = 0
        self.packet_types = Counter()
        self.declared_bindings = None
        self.binding_records_seen = 0
        self.last_seen = None
        self.packet_errors = 0

    def _log(self, event, **fields):
        self.emit(event, **fields)
        if event in ('semantic_attempt', 'semantic_outcome', 'semantic_event'):
            self.recent.append({'event': event, **fields})

    def input(self, kind: str, mono: float, *, key=None, chord=None, button=None, **_kwargs):
        if kind == 'key_down' and key not in MODIFIERS:
            normalized = wow_binding(chord or key or '')
            if not normalized:
                return
            binding = self.bindings.get(normalized)
            attempt = {'time_mono': mono, 'input': normalized, 'source': 'keyboard',
                       'action': binding.action_name if binding else '',
                       'action_type': binding.action_type if binding else 'unresolved',
                       'action_id': binding.action_id if binding else 0,
                       'command': binding.command if binding else '',
                       'status': 'attempted', 'matched': False}
            self.attempts.append(attempt)
            self.counts['attempts'] += 1
            self._log('semantic_attempt', **{k:v for k,v in attempt.items() if k!='matched'})
        elif kind == 'mouse_down' and button in ('left', 'right'):
            # A click alone is not an actionbar click. Await addon UseAction
            # / bag-use hook for actual semantic context.
            self.attempts.append({'time_mono':mono, 'input': button+' click',
                                  'source':'mouse', 'action':'', 'action_type':'unresolved',
                                  'action_id':0, 'command':'', 'status':'attempted',
                                  'matched':False})

    def _match(self, mono, *, action_id=0, action_name='', allow_fallback=False):
        candidates = [a for a in self.attempts if not a['matched']
                      and 0 <= mono-a['time_mono'] <= 5.0
                      and (a['source']=='keyboard' or (allow_fallback and a['source']=='mouse'))]
        if not candidates:
            return None
        if action_id:
            exact = [a for a in candidates if a['action_id'] == action_id
                     and a['action_type'] in ('spell','item')]
            if exact:
                exact[-1]['match_method']='exact_id'
                return exact[-1]
        if action_name:
            lname = action_name.lower()
            named = [a for a in candidates if a['action'] and
                     (lname in a['action'].lower() or a['action'].lower() in lname)]
            if named:
                named[-1]['match_method']='name'
                return named[-1]
        if allow_fallback:
            # Only fall back when one action was attempted in the correlation
            # window, to avoid inventing a relationship between unrelated casts.
            if len(candidates)==1 and candidates[0]['action_type'] in ('macro','item'):
                candidates[0]['match_method']='temporal_only'
                return candidates[0]
            return None
        return None

    def _outcome(self, attempt, status, mono, *, event, evidence):
        if attempt is None:
            self.counts['unmatched_events'] += 1
            self._log('semantic_event', game_event=event, evidence=evidence,
                      status='unmatched', time_mono=mono)
            return
        # A temporally adjacent spell does not prove which branch of a macro
        # ran or whether an item was responsible for the cast.
        method = attempt.get('match_method', 'aura_evidence')
        if method == 'temporal_only' and status == 'confirmed':
            status = 'correlated_not_verified'
        attempt['matched'] = True
        attempt['status'] = status
        self.counts[status] += 1
        self._log('semantic_outcome', input=attempt['input'],
                  action=attempt['action'], action_type=attempt['action_type'],
                  status=status, game_event=event, evidence=evidence,
                  match_method=method,
                  latency_ms=round((mono-attempt['time_mono'])*1000),
                  time_mono=mono)

    def expire(self, mono: float):
        """No telemetry confirmation within eight seconds means UNKNOWN, not failed."""
        for attempt in self.attempts:
            if attempt['matched'] or mono-attempt['time_mono'] < 8:
                continue
            attempt['matched'] = True
            attempt['status'] = 'unknown'
            self.counts['unknown'] += 1
            self._log('semantic_outcome', input=attempt['input'],
                      action=attempt['action'], action_type=attempt['action_type'],
                      status='unknown', evidence='no_correlated_success_observed',
                      game_event='', latency_ms=round((mono-attempt['time_mono'])*1000),
                      time_mono=mono)

    def ingest(self, packet, mono: float | None=None):
        mono = time.monotonic() if mono is None else mono
        self.expire(mono)
        if packet is None or packet.sequence == self.last_sequence:
            return
        self.last_sequence = packet.sequence
        self.last_seen = mono
        self.packets += 1
        self.packet_types[packet.kind] += 1
        fields = packet.fields
        kind = packet.kind
        if kind == 'R' and len(fields)>=1:
            try:
                generation = int(fields[0])
            except ValueError:
                return
            if len(fields)>1:
                try:
                    self.declared_bindings = int(fields[1])
                except (ValueError, TypeError):
                    pass
            if generation != self.generation:
                self.generation = generation
                self.bindings.clear()
                self._log('binding_snapshot', generation=generation,
                          declared_bindings=self.declared_bindings)
            return
        if kind == 'B' and len(fields)>=6:
            self.binding_records_seen += 1
            try:
                generation = int(fields[0]); key = fields[1].upper()
                ident = int(fields[4])
            except (ValueError, TypeError):
                return
            if generation != self.generation:
                self.generation = generation
                self.bindings.clear()
            binding = Binding(key, fields[2], fields[3], ident,
                              '|'.join(fields[5:]).strip(), generation)
            if self.bindings.get(key) != binding:
                self.bindings[key] = binding
                self._log('semantic_binding', **asdict(binding), ambiguous=binding.ambiguous)
            return
        if kind in ('S','T','H','F') and len(fields)>=1:
            try:
                spell_id = int(fields[0])
            except ValueError:
                spell_id = 0
            name = '|'.join(fields[1:]) if len(fields)>1 else ''
            event = {'S':'spell_succeeded','T':'cast_started',
                     'H':'channel_started','F':'spell_failed'}[kind]
            match = self._match(mono, action_id=spell_id, action_name=name,
                                allow_fallback=(kind in ('S','H','F')))
            if kind == 'S':
                self._outcome(match, 'confirmed', mono, event=event, evidence=name or str(spell_id))
            elif kind == 'F':
                self._outcome(match, 'failed', mono, event=event, evidence=name or str(spell_id))
            else:
                # Starting a cast/channel is not completion.
                self._log('semantic_event', game_event=event, spell_id=spell_id,
                          spell=name, status='started', time_mono=mono)
            return
        if kind == 'A' and len(fields)>=2 and fields[-1]=='present':
            aura = fields[0]
            candidates = [a for a in self.attempts if not a['matched']
                          and 0 <= mono-a['time_mono'] <= 8
                          and ((aura.lower() in a['action'].lower()) or
                               (aura.lower()=='food' and 'eat' in a['action'].lower()) or
                               (aura.lower()=='recently bandaged' and 'bandage' in a['action'].lower()))]
            # A readable positive aura can verify that a recent *item* initiated
            # eating even when the item is named 'Conjured Bread', not 'Food'.
            if not candidates:
                items=[a for a in self.attempts if not a['matched'] and
                       a['action_type']=='item' and 0 <= mono-a['time_mono'] <= 5]
                if len(items)==1:
                    candidates=items
            if candidates:
                candidates[-1]['match_method']='aura_evidence'
            self._outcome(candidates[-1] if candidates else None, 'confirmed', mono,
                          event='aura_present', evidence=aura)
            return
        if kind == 'C' and len(fields)>=4:
            slot, action_type, ident, name = fields[:4]
            match = self._match(mono, action_id=int(ident) if ident.isdigit() else 0,
                                action_name=name, allow_fallback=True)
            self._log('semantic_event', game_event='action_slot_triggered',
                      slot=slot, action_type=action_type, action_id=ident,
                      action=name, source_input=match['input'] if match else '',
                      status='observed_trigger_not_confirmed', time_mono=mono)
            return
        if kind == 'I' and len(fields)>=3:
            match = self._match(mono, action_id=int(fields[0]) if fields[0].isdigit() else 0,
                                allow_fallback=True)
            self._log('semantic_event', game_event='bag_item_use_attempt',
                      item_id=fields[0], bag=fields[1], slot=fields[2],
                      source_input=match['input'] if match else '',
                      status='attempted_not_confirmed', time_mono=mono)

    def snapshot(self):
        return {'bindings': [asdict(b) | {'ambiguous':b.ambiguous}
                             for b in sorted(self.bindings.values(),key=lambda b:b.key)],
                'recent':list(self.recent), 'counts':dict(self.counts),
                'generation':self.generation, 'packets':self.packets,
                'packet_types':dict(self.packet_types),
                'declared_bindings':self.declared_bindings,
                'binding_records_seen':self.binding_records_seen,
                'protocol':'PriestBridge semantic v1',
                'limitations':'Macro branches and unobserved food/bandage auras remain unknown; '
                              'item-use hook is an attempt, not confirmation.'}
