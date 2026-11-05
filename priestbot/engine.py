"""Pure deterministic decision engine: no game IO, testable with fake health bars.

Time is monotonic seconds. Produces at most one intent per tick. Scheduler enforces
minimum gap between intents and a maximum rate; no infinite fast loops.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import deque


@dataclass(frozen=True)
class Observation:
    hp: float
    mana: float
    target_hp: float
    casting: bool | None = None  # Optional addon event signal; None in manual mode.
    error: str | None = None  # range | los | facing | failed | None
    error_seq: int | None = None  # 4-bit counter; only changes matter.
    # v0.8 extension: None means an older addon or manual mode.
    shield_aura: str | None = None  # present | absent | estimated | unknown
    pain_aura: str | None = None
    success_spell: str | None = None  # shield | pain | smite | mind_blast | heal
    success_seq: int | None = None
    target_seq: int | None = None


@dataclass(frozen=True)
class Decision:
    action: str | None
    reason: str
    stop: bool = False


class PriestEngine:
    def __init__(self, config):
        self.cfg = config
        self.reset()

    def reset(self):
        self.ready_at = 0.0
        self.observed_error_seq = None
        self.observed_success_seq = None
        self.observed_target_seq = None
        self.confirmed_shield_until = float('-inf')
        self.confirmed_pain_until = float('-inf')
        self.last_confirmed_spell = None
        self.last_confirmed_at = None
        self.last_shield_confirmed_at = float('-inf')
        self.last_offensive_at = float("-inf")
        self.last_offensive_kind = None
        self.pending_skip_reason = None
        self.last_shield = float('-inf')
        self.last_renew = float('-inf')
        self.last_pain = float('-inf')
        self.last_smite = float('-inf')
        self.mb_opener_state = 'pending'  # pending | casting | done (per target)
        self.mb_attempted_at = None
        self.mb_next_attempt_at = float('-inf')
        self.mb_cooldown_until = float('-inf')  # persists across target changes
        self.mb_attempts = 0
        self.last_drink = float('-inf')
        self.last_between_heal_at = float('-inf')
        self.last_target_at = float('-inf')
        self.target_since = None
        self.last_progress_at = None
        self.last_target_hp = None
        self.failed_targets = 0
        self.no_target_attempts = 0
        self.no_target_since = None
        self.next_search_at = 0.0
        self.wand_active = False
        self.melee_active = False
        self.wand_start_at = None  # one wand activation after the Pain GCD
        self.drinking = False
        self.resting = False
        self.action_times = deque()
        self.status = "READY"
        self.pending_movement = None
        self.approach_pulses = 0
        self.turn_pulses = 0
        self.los_blocked_since = None
        self.los_retry_at = None
        self.los_retries = 0

    def _clear_los_wait(self):
        self.los_blocked_since = None
        self.los_retry_at = None
        self.los_retries = 0

    def _act(self, kind, reason, now):
        self.ready_at = now + self.cfg.action_delay_s
        self.action_times.append(now)
        if kind == "pain" and self.cfg.main_damage in ("wand", "mind_blast_wand"):
            # Do not press Shoot while Pain's GCD is still active: that
            # produces a failed attempt followed by an unconditional second
            # press, which can restart/cancel wand autos on some clients.
            # Instead, perform exactly ONE wand activation after the GCD.
            self.wand_start_at = now + max(0.0, self.cfg.wand_gcd_retry_s,
                                           self.cfg.pain_to_wand_delay_s)
            # Other decisions (such as emergency healing) may still run;
            # the wand branch itself waits for wand_start_at.
            self.ready_at = now + max(0.0, self.cfg.pain_to_wand_delay_s)
        elif kind in ("shield", "renew", "smite", "mind_blast", "heal", "melee", "next_target", "clear_target"):
            self.wand_start_at = None
        if kind in ("pain", "smite", "mind_blast", "wand", "melee"):
            self.last_offensive_at = now
            self.last_offensive_kind = kind
        if kind == "shield":
            self.last_shield = now
        if kind == "renew":
            self.last_renew = now
        if kind == "heal":
            # Heal ranks can be longer than the generic 1.7s action interval.
            # Avoid cancelling our own cast if the addon casting flag is lost.
            self.ready_at = max(self.ready_at, now + self.cfg.heal_cast_fallback_s)
        if kind == "pain":
            self.last_pain = now
        if kind == "smite":
            self.last_smite = now
        if kind == "mind_blast":
            self.mb_opener_state = 'casting'
            self.mb_attempted_at = now
            self.mb_attempts += 1
            # A completed Mind Blast cast (or a conservative timeout) is needed
            # before Pain. Do not apply the generic inter-spell delay.
            self.ready_at = now + self.cfg.mind_blast_cast_fallback_s
        if kind in ("shield", "renew", "pain", "smite", "mind_blast", "heal"):
            # Casting interrupts previous wand/melee auto-attacks in some clients.
            self.wand_active = False
            self.melee_active = False
        if kind == "wand":
            self.wand_active = True
            self.melee_active = False
            self.wand_start_at = None
        if kind == "melee":
            self.melee_active = True
            self.wand_active = False
        if kind == "drink":
            self.last_drink = now
            self.drinking = True
        if kind in ("next_target", "clear_target"):
            self.wand_active = False
            self.melee_active = False
        if kind in ("move_forward", "turn_right"):
            duration = (self.cfg.approach_pulse_s if kind == "move_forward"
                        else self.cfg.turn_pulse_s)
            # The caller holds the key for this duration. Once released, allow
            # game position and range results to update before probing again.
            self.ready_at = now + duration + self.cfg.movement_probe_delay_s
            self.pending_movement = None
            if kind == "move_forward":
                self.approach_pulses += 1
            else:
                self.turn_pulses += 1
            # A previous out-of-range/facing attempt cannot be assumed to land.
            # Give the opener a fresh chance after this short motor action.
            if self.mb_opener_state == 'casting':
                self.mb_opener_state = 'pending'
                self.mb_attempted_at = None
                self.mb_next_attempt_at = float('-inf')
            self.wand_active = False
            self.melee_active = False
        self.status = reason
        return Decision(kind, reason)

    def update(self, obs: Observation, now: float) -> Decision:
        hp, mana, target = obs.hp, obs.mana, obs.target_hp
        # Explicit client target-change events keep per-target DoT estimates from
        # leaking onto a different mob (even when both have full health).
        if obs.target_seq is not None:
            if self.observed_target_seq is None:
                self.observed_target_seq = obs.target_seq
            elif obs.target_seq != self.observed_target_seq:
                self.observed_target_seq = obs.target_seq
                self._clear_current_target()
                self.last_pain = float('-inf')
                self.confirmed_pain_until = float('-inf')
                if target > .055 and self.cfg.main_damage == 'mind_blast_wand':
                    self.ready_at = min(self.ready_at, now)
        # A successful spell event is stronger evidence than an attempted key.
        # Don't count a stale strip repeatedly, or infer spell success from
        # UNIT_SPELLCAST_START/STOP. Four-bit counters can overflow between scans.
        if obs.success_seq is not None:
            if self.observed_success_seq is None:
                self.observed_success_seq = obs.success_seq
            elif obs.success_seq != self.observed_success_seq:
                self.observed_success_seq = obs.success_seq
                self.last_confirmed_spell = obs.success_spell
                self.last_confirmed_at = now
                if obs.success_spell in ('pain', 'smite', 'mind_blast'):
                    self._clear_los_wait()
                if obs.success_spell == 'shield':
                    self.last_shield_confirmed_at = now
                    self.last_shield = now
                    self.confirmed_shield_until = now + self.cfg.shield_duration_s
                elif obs.success_spell == 'pain' and target > .055:
                    self.last_pain = now
                    self.confirmed_pain_until = now + self.cfg.pain_duration_s
                elif (obs.success_spell == 'mind_blast' and target > .055 and
                      self.cfg.main_damage == 'mind_blast_wand' and
                      self.mb_opener_state == 'casting'):
                    # Mind Blast's confirmed completion releases Pain at the
                    # next scan, without an artificial 1.7-second gap.
                    self.mb_opener_state = 'done'
                    self.mb_cooldown_until = now + self.cfg.mind_blast_cooldown_s
                    self.ready_at = min(self.ready_at, now)
                elif obs.success_spell == 'smite':
                    # The game confirmed completion. Allow another Smite after
                    # a small configurable network/GCD margin instead of always
                    # waiting the conservative rank-independent 2.7-second timer.
                    # The casting flag is checked before any action is issued.
                    self.last_smite = now - self.cfg.smite_interval_s + self.cfg.smite_post_success_s
        # If a recent related cast failed, do not treat the attempt timer as
        # proof that Pain or Shield actually landed. A GCD-safe retry follows.
        if not (0 <= hp <= 1 and 0 <= mana <= 1 and 0 <= target <= 1):
            return Decision(None, "Sensor readings out of range; paused", stop=True)
        if hp <= .02:
            return Decision(None, "DEAD or health bar not visible; stopped", stop=True)
        if hp <= self.cfg.danger_below and mana <= self.cfg.heal_mana_min:
            return Decision(None, "Critical health and insufficient mana; stopped", stop=True)
        # Only react to NEW event counters, never a stale on-screen error.
        # Tie range/LoS to an offensive action issued in the last four seconds;
        # unrelated UI errors must not cause unwanted target changes.
        if obs.error_seq is not None:
            if self.observed_error_seq is None:
                self.observed_error_seq = obs.error_seq
            elif obs.error_seq != self.observed_error_seq:
                self.observed_error_seq = obs.error_seq
                if obs.error == 'failed' and now - self.last_offensive_at <= 4:
                    if self.last_offensive_kind == 'pain':
                        self.last_pain = float('-inf')
                    elif (self.last_offensive_kind == 'mind_blast' and
                          self.mb_opener_state == 'casting'):
                        self.mb_opener_state = 'pending'
                        self.mb_next_attempt_at = now + self.cfg.mind_blast_retry_delay_s
                        self.ready_at = min(self.ready_at, self.mb_next_attempt_at)
                        if self.mb_attempts >= self.cfg.mind_blast_max_attempts:
                            self.pending_skip_reason = 'Repeated Mind Blast failures'
                if (obs.error in ("range", "los", "facing") and target > .055 and
                    self.target_since is not None and
                    0 <= now - self.last_offensive_at <= 4.0):
                    # Movement is ONLY triggered by a new game-reported error.
                    # Tab targeting alone gives no directional/distance fix.
                    reliable = self.cfg.telemetry_source == 'addon' and obs.target_seq is not None
                    fleeing = target <= self.cfg.flee_target_hp_below
                    stationary = self.cfg.enable_stationary_tracking and reliable
                    if obs.error == 'los' and stationary:
                        if self.los_blocked_since is None:
                            self.los_blocked_since = now
                        self.los_retries += 1
                        self.los_retry_at = now + self.cfg.los_retry_s
                        self.pending_movement = None
                        # A failed attempt is not a successful wand hit/cast.
                        self.wand_active = False
                        self.melee_active = False
                        if self.last_offensive_kind == 'smite':
                            self.last_smite = float('-inf')
                        elif self.last_offensive_kind == 'pain':
                            self.last_pain = float('-inf')
                        elif (self.last_offensive_kind == 'mind_blast' and
                              self.mb_opener_state == 'casting'):
                            self.mb_opener_state = 'pending'
                            self.mb_next_attempt_at = now + self.cfg.los_retry_s
                        if (now - self.los_blocked_since >= self.cfg.los_wait_s or
                                self.los_retries > self.cfg.los_max_retries):
                            self.pending_skip_reason = 'Line of sight never recovered'
                    elif (obs.error == 'facing' and stationary and fleeing and
                          self.turn_pulses < self.cfg.turn_max_pulses):
                        self.pending_movement = 'turn_right'
                    elif (obs.error == 'facing' and stationary and fleeing):
                        self.pending_skip_reason = 'Fleeing target facing correction limit reached'
                    elif self.cfg.enable_movement and reliable and not stationary:
                        if obs.error == 'range' and self.approach_pulses < self.cfg.approach_max_pulses:
                            self.pending_movement = 'move_forward'
                        elif obs.error == 'facing' and self.turn_pulses < self.cfg.turn_max_pulses:
                            self.pending_movement = 'turn_right'
                        else:
                            self.pending_skip_reason = {'range': 'Approach limit reached',
                                                        'facing': 'Facing search limit reached',
                                                        'los': 'Line of sight blocked'}[obs.error]
                    else:
                        self.pending_skip_reason = {'range': 'Out of range',
                                                    'los': 'Line of sight blocked',
                                                    'facing': 'Not facing target'}[obs.error]
        if self.pending_skip_reason is not None:
            self.pending_movement = None
            reason = self.pending_skip_reason
            self.pending_skip_reason = None
            self.failed_targets += 1
            self._clear_current_target()
            if self.failed_targets >= self.cfg.max_failed_targets:
                return Decision(None, "Repeated unreachable targets; stopped", stop=True)
            # Clear immediately, ignoring the regular spell action delay.
            return self._act("clear_target", reason + "; clearing target", now)
        if self.target_since is not None:
            if target <= .025:
                self._clear_current_target()
                # corpse can stay targeted; next_target targets enemies via tab
            elif self.last_target_hp is not None:
                if target < self.last_target_hp - .015:
                    self.last_progress_at = now
                    self.last_target_hp = target
                    self.failed_targets = 0
                    self._clear_los_wait()
                if (self.last_progress_at is not None and
                        now - self.last_progress_at >= self.cfg.stuck_timeout_s):
                    self._clear_current_target()
                    self.failed_targets += 1
                    self.status = "Target not losing HP; skipping"
                    if self.failed_targets >= self.cfg.max_failed_targets:
                        return Decision(None, "Too many stuck targets; stopped", stop=True)
                    # explicit clear to avoid repeatedly wanding same target
                    if now >= self.ready_at:
                        return self._act("clear_target", "Clearing unreachable/immune target", now)
                elif now - self.target_since >= self.cfg.target_timeout_s:
                    return Decision(None, "Target combat exceeded safety timeout", stop=True)
        # A player spell already being cast should not be interrupted by
        # attack/pain/shield key presses. Health sensor emergencies still stop above.
        if obs.casting is True:
            return Decision(None, "Casting; waiting for completion")
        if self.los_blocked_since is not None:
            # No chase: the bot is planted in its field. Wait for the fleeing
            # mob to become castable, then issue a bounded offensive probe.
            # Defensive self-healing is still allowed during LoS recovery.
            if (self.cfg.use_heal and hp <= self.cfg.heal_below and
                    mana > self.cfg.heal_mana_min and now >= self.ready_at):
                return self._act('heal', 'Healing while waiting for line of sight', now)
            if now - self.los_blocked_since >= self.cfg.los_wait_s:
                self.failed_targets += 1
                self._clear_current_target()
                return self._act('clear_target', 'Line of sight timeout; no pursuit', now)
            if now < self.los_retry_at:
                return Decision(None, 'Line of sight blocked; waiting in place')
            self.los_retry_at = now + self.cfg.los_retry_s
            self.wand_active = False
            self.melee_active = False
        # Move only when safe and only while target remains selected.  The
        # engine does not know the target bearing and cannot path around walls.
        if self.pending_movement is not None:
            if target <= .055:
                self.pending_movement = None
            elif (self.cfg.use_heal and hp <= self.cfg.heal_below and
                  mana > self.cfg.heal_mana_min):
                return self._act('heal', 'Healing before movement: HP low', now)
            elif hp <= self.cfg.danger_below:
                return Decision(None, 'Low health: movement stopped', stop=True)
            elif now >= self.ready_at:
                kind = self.pending_movement
                reason = ('Approaching target in one bounded forward step' if kind == 'move_forward'
                          else 'Turning right slightly to face target')
                return self._act(kind, reason, now)
            else:
                return Decision(None, 'Waiting before safe movement pulse')
        if now < self.ready_at:
            return Decision(None, self.status)
        while self.action_times and now-self.action_times[0] > 60:
            self.action_times.popleft()
        if len(self.action_times) >= self.cfg.max_cast_per_minute:
            return Decision(None, "Action-rate safety limit; stopped", stop=True)
        # Consider >= ~5% target bar to indicate a target that is alive.
        has_target = target > .055
        if not has_target:
            self._clear_current_target()
            if self.no_target_since is None:
                self.no_target_since = now
            if now - self.no_target_since > self.cfg.max_no_target_s:
                return Decision(None, "No reachable mobs for too long; stopped", stop=True)
            if self.cfg.use_heal and hp <= self.cfg.heal_below and mana > self.cfg.heal_mana_min:
                if now - self.last_between_heal_at >= self.cfg.between_heal_retry_s:
                    self.last_between_heal_at = now
                    return self._act("heal", "Healing between mobs", now)
                return Decision(None, "Waiting after between-mob healing attempt")
            if mana < self.cfg.drink_below:
                self.resting = True
            if self.resting:
                if mana >= self.cfg.resume_mana:
                    self.resting = False
                    self.drinking = False
                elif self.cfg.enable_drink:
                    if now - self.last_drink >= 24:
                        return self._act("drink", "Drinking between mobs", now)
                    return Decision(None, "Recovering mana with water")
                else:
                    return Decision(None, "Waiting for natural mana regeneration")
            if now < self.next_search_at:
                return Decision(None, "Waiting for nearby mob respawns")
            if self.no_target_attempts >= self.cfg.max_failed_targets:
                self.no_target_attempts = 0
                self.next_search_at = now + self.cfg.respawn_wait_s
                return Decision(None, "Waiting for mob respawns before searching again")
            # Preparation belongs immediately before a new pull, not during
            # repeated unsuccessful Tab searches or respawn waits.
            if self.no_target_attempts == 0:
                if (self.cfg.use_renew and hp < self.cfg.renew_below and
                        mana >= self.cfg.renew_mana_min and
                        now - self.last_renew >= self.cfg.renew_interval_s):
                    # Time-based, not claimed as confirmed aura uptime. Do not
                    # refresh every tick while the HoT is still healing.
                    return self._act('renew', 'Renew between pulls: HP below threshold', now)
                if (mana >= self.cfg.prepull_shield_mana_min and
                        self._should_shield(obs, now, mana)):
                    return self._act('shield', 'Power Word: Shield before next pull', now)
            self.no_target_attempts += 1
            return self._act("next_target", "Searching for a hostile target", now)
        # Existing target may be acquired by tab (or manually).
        if self.target_since is None:
            self.target_since = now
            self.last_progress_at = now
            self.last_target_hp = target
            self.wand_active = False
            self.melee_active = False
            self.last_smite = float('-inf')
            if self.cfg.main_damage == 'mind_blast_wand':
                # A newly acquired live target can be opened immediately, even
                # if the preceding Tab input used the generic action delay.
                self.ready_at = min(self.ready_at, now)
            self.last_pain = float('-inf')
            self.confirmed_pain_until = float('-inf')
            # Retain failures across consecutive unreachable pulls; reset on damage.
            self.no_target_attempts = 0
            self.no_target_since = None
            self.next_search_at = 0.0
        # Survival always outranks attack.
        if self.cfg.use_heal and hp <= self.cfg.heal_below and mana > self.cfg.heal_mana_min:
            return self._act("heal", "Casting heal: HP low", now)
        if hp <= self.cfg.danger_below and mana < self.cfg.heal_mana_min:
            return Decision(None, "Unable to heal at critical health", stop=True)
        # Restricted aura APIs can report a false "absent" for an active aura.
        # A confirmed successful cast on this target is more reliable than a
        # nil-by-name query. Never let a false absence erase the cast estimate.
        # Estimates are intentionally time-limited and reset on target change.
        # Shield can be absorbed before its nominal duration; retain the
        # existing conservative 15s Weakened Soul rule for an explicit absent
        # reading from an older addon. The updated addon reports unknown when
        # lookup cannot be trusted, preserving the full confirmed estimate.
        pain_present = (obs.pain_aura in ('present', 'estimated') or
                        now < self.confirmed_pain_until)
        pain_gap = (self.cfg.aura_retry_s if obs.pain_aura == 'absent' else self.cfg.pain_interval_s)
        if self._should_shield(obs, now, mana):
            return self._act("shield", "Shield missing/expired; attempting Power Word: Shield", now)
        if self.cfg.main_damage == 'mind_blast_wand' and self.mb_opener_state != 'done':
            if self.mb_opener_state == 'casting':
                # v0.8+ addons identify confirmed completions above. If the
                # success event is lost, fall back after the cast + margin.
                # A known failed cast instead sets this state back to pending.
                if now < self.mb_attempted_at + self.cfg.mind_blast_cast_fallback_s:
                    return Decision(None, 'Waiting for Mind Blast to finish')
                self.mb_opener_state = 'done'
                self.mb_cooldown_until = now + self.cfg.mind_blast_cooldown_s
                self.ready_at = min(self.ready_at, now)
            else:
                if mana < self.cfg.mind_blast_mana_min:
                    # If mana is too low for MB, keep fighting with wand instead
                    # of stalling indefinitely on a target.
                    self.mb_opener_state = 'done'
                elif now < self.mb_cooldown_until:
                    return Decision(None, 'Waiting for Mind Blast cooldown before opening')
                elif now < self.mb_next_attempt_at:
                    return Decision(None, 'Retrying Mind Blast after failed cast')
                else:
                    return self._act('mind_blast', 'Opening target with Mind Blast', now)
        if (self.cfg.use_pain and not pain_present and now - self.last_pain >= pain_gap and
                mana >= self.cfg.dot_mana_min):
            return self._act("pain", "Pain missing/expired; attempting Shadow Word: Pain", now)
        if self.cfg.main_damage == "smite":
            if mana >= self.cfg.smite_mana_min:
                if now - self.last_smite >= self.cfg.smite_interval_s:
                    return self._act("smite", "Casting Smite", now)
                return Decision(None, "Waiting for next Smite")
            if self.cfg.melee_when_oom:
                if not self.melee_active:
                    return self._act("melee", "Low mana; switching to melee auto-attack", now)
                return Decision(None, "Low mana; melee auto-attacking")
            return Decision(None, "Mana too low for Smite; monitoring")
        if self.cfg.main_damage in ("wand", "mind_blast_wand"):
            if not self.wand_active:
                if self.wand_start_at is not None and now < self.wand_start_at:
                    return Decision(None, "Waiting for Pain GCD before wanding")
                reason = ("Starting wand once after Pain GCD" if self.wand_start_at is not None
                          else "Starting wand auto-attack")
                return self._act("wand", reason, now)
            return Decision(None, "Wanding; watching target HP")
        if self.cfg.main_damage == "melee":
            if not self.melee_active:
                return self._act("melee", "Starting melee auto-attack", now)
            return Decision(None, "Melee auto-attacking")
        return Decision(None, "Unknown damage mode; stopped", stop=True)

    def _should_shield(self, obs: Observation, now: float, mana: float) -> bool:
        """Shared in-combat and pre-pull protection with Weakened Soul guard."""
        shield_present = obs.shield_aura in ('present', 'estimated') or (
            obs.shield_aura in (None, 'unknown') and now < self.confirmed_shield_until)
        shield_gap = (self.cfg.aura_retry_s if obs.shield_aura == 'absent'
                      else self.cfg.shield_interval_s)
        return (self.cfg.use_shield and not shield_present and
                now - self.last_shield >= shield_gap and
                now - self.last_shield_confirmed_at >= self.cfg.shield_lockout_s and
                mana >= self.cfg.shield_mana_min)

    def _clear_current_target(self):
        self._clear_los_wait()
        self.pending_movement = None
        self.approach_pulses = 0
        self.turn_pulses = 0
        self.mb_opener_state = 'pending'
        self.mb_attempted_at = None
        self.mb_next_attempt_at = float('-inf')
        self.mb_attempts = 0
        self.wand_start_at = None
        self.target_since = None
        self.last_progress_at = None
        self.last_target_hp = None
        self.wand_active = False
        self.melee_active = False
