"""Privacy-conscious, uploadable PriestBot telemetry and decision report.

Tests are self-contained: no pytest, game client, keyboard/mouse automation,
internet or GPU required. An optional live *read-only* optical probe never
stores screenshots. This is not a substitute for a live gameplay trial.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import zipfile

from .config import Config
from .engine import Observation, PriestEngine


@dataclass(frozen=True)
class Step:
    seconds: float
    observation: Observation
    expected_action: str | None
    expected_stop: bool = False
    reason_contains: str | None = None


@dataclass(frozen=True)
class Scenario:
    name: str
    settings: dict[str, Any] = field(default_factory=dict)
    steps: tuple[Step, ...] = ()


def _ob(hp=1.0, mana=1.0, target=0.0, *, error=None, seq=0, target_seq=0,
        casting=False, shield_aura=None, pain_aura=None, success_spell=None,
        success_seq=None) -> Observation:
    return Observation(hp=hp, mana=mana, target_hp=target, error=error,
                       error_seq=seq, target_seq=target_seq, casting=casting,
                       shield_aura=shield_aura, pain_aura=pain_aura,
                       success_spell=success_spell, success_seq=success_seq)


def scenarios() -> tuple[Scenario, ...]:
    return (
        Scenario('Full health: never Renew between pulls',
                 {'use_renew': True, 'use_shield': False},
                 (Step(0, _ob(), 'next_target'),)),
        Scenario('Damaged Priest: casted Heal at 60 percent',
                 {'use_shield': False, 'use_pain': False},
                 (Step(0, _ob(hp=.59, target=.85), 'heal'),
                  Step(.5, _ob(hp=.59, target=.8, casting=True), None),)),
        Scenario('Between pulls: Renew at 75 percent',
                 {'use_renew': True, 'use_shield': False},
                 (Step(0, _ob(hp=.75), 'renew'),)),
        Scenario('Before pulls: Shield with sufficient mana',
                 {'use_shield': True, 'use_pain': False},
                 (Step(0, _ob(), 'shield'),)),
        Scenario('Do not replace active Shield',
                 {'use_shield': True, 'use_pain': False},
                 (Step(0, _ob(shield_aura='present'), 'next_target'),)),
        Scenario('Critical HP and no healing mana: stop',
                 {}, (Step(0, _ob(hp=.12, mana=.10, target=.9), None, True),)),
        Scenario('Stationary farmer: do not chase an out-of-range mob',
                 {'main_damage': 'smite', 'use_pain': False,
                  'enable_stationary_tracking': True, 'enable_movement': False},
                 (Step(0, _ob(target=.3), 'smite'),
                  Step(.3, _ob(target=.3, error='range', seq=1), 'clear_target'),)),
        Scenario('Fleeing mob: turn only on fresh facing error',
                 {'main_damage': 'smite', 'use_pain': False,
                  'enable_stationary_tracking': True, 'enable_movement': False},
                 (Step(0, _ob(target=.35), 'smite'),
                  Step(.3, _ob(target=.33, error='facing', seq=1), None),
                  Step(2, _ob(target=.33, error='facing', seq=1), 'turn_right'),
                  Step(2.1, _ob(target=.33, error='facing', seq=1), None),)),
        Scenario('Healthy target: no automatic turn when movement disabled',
                 {'main_damage': 'smite', 'use_pain': False,
                  'enable_stationary_tracking': True, 'enable_movement': False},
                 (Step(0, _ob(target=.8), 'smite'),
                  Step(.3, _ob(target=.8, error='facing', seq=1), 'clear_target'),)),
        Scenario('Fleeing mob: LoS waits in place, then retries',
                 {'main_damage': 'smite', 'use_pain': False,
                  'enable_stationary_tracking': True},
                 (Step(0, _ob(target=.3), 'smite'),
                  Step(.3, _ob(target=.3, error='los', seq=1), None,
                       reason_contains='waiting'),
                  Step(1.0, _ob(target=.3, error='los', seq=1), None),
                  Step(2.31, _ob(target=.3, error='los', seq=1), 'smite'),)),
        Scenario('LoS never recovers: give up without advancing',
                 {'main_damage': 'smite', 'use_pain': False,
                  'enable_stationary_tracking': True, 'los_wait_s': 4},
                 (Step(0, _ob(target=.3), 'smite'),
                  Step(.3, _ob(target=.3, error='los', seq=1), None),
                  Step(4.31, _ob(target=.3, error='los', seq=1), 'clear_target',
                       reason_contains='no pursuit'),)),
        Scenario('LoS waiting does not block emergency Heal',
                 {'main_damage': 'smite', 'use_pain': False,
                  'enable_stationary_tracking': True},
                 (Step(0, _ob(target=.3), 'smite'),
                  Step(.3, _ob(target=.3, error='los', seq=1), None),
                  Step(2, _ob(hp=.52, target=.3, error='los', seq=1), 'heal'),)),
        Scenario('Tracking off: retain legacy immediate LoS skip',
                 {'main_damage': 'smite', 'use_pain': False,
                  'enable_stationary_tracking': False},
                 (Step(0, _ob(target=.3), 'smite'),
                  Step(.3, _ob(target=.3, error='los', seq=1), 'clear_target'),)),
        Scenario('Lost target: cancel pending fleeing turn',
                 {'main_damage': 'smite', 'use_pain': False,
                  'enable_stationary_tracking': True},
                 (Step(0, _ob(target=.3), 'smite'),
                  Step(.3, _ob(target=.3, error='facing', seq=1), None),
                  Step(2, _ob(target=.3, error='facing', seq=1), 'turn_right'),
                  Step(3, _ob(target=.9, target_seq=1), 'smite'),)),
        Scenario('Malformed sensor values: stop without inputs',
                 {}, (Step(0, _ob(hp=1.2, target=.5), None, True),)),
        Scenario('Pain resisted: retry when its 1.5-second GCD ends',
                 {'main_damage': 'wand', 'use_shield': False},
                 (Step(0, _ob(target=.9, pain_aura='unknown', success_seq=0), 'pain'),
                  Step(.2, _ob(target=.9, pain_aura='estimated', error='pain_resist',
                               seq=1, success_spell='pain', success_seq=1), None),
                  Step(1.49, _ob(target=.9, pain_aura='estimated', error='pain_resist',
                                 seq=1, success_spell='pain', success_seq=1), None),
                  Step(1.5, _ob(target=.9, pain_aura='estimated', error='pain_resist',
                                seq=1, success_spell='pain', success_seq=1), 'pain'),)),
    )


def run_decision_tests() -> list[dict[str, Any]]:
    results = []
    for case in scenarios():
        cfg = Config(**case.settings)
        engine = PriestEngine(cfg)
        steps = []
        for step in case.steps:
            try:
                actual = engine.update(step.observation, step.seconds)
                passed = (actual.action == step.expected_action and
                          actual.stop == step.expected_stop and
                          (step.reason_contains is None or
                           step.reason_contains.lower() in actual.reason.lower()))
                result = {'time_s': step.seconds, 'observation': asdict(step.observation),
                          'expected_action': step.expected_action,
                          'actual_action': actual.action,
                          'expected_stop': step.expected_stop,
                          'actual_stop': actual.stop,
                          'decision_reason': actual.reason, 'passed': passed}
            except Exception as exc:
                result = {'time_s': step.seconds, 'observation': asdict(step.observation),
                          'expected_action': step.expected_action,
                          'passed': False, 'error': f'{type(exc).__name__}: {exc}'}
            steps.append(result)
        results.append({'name': case.name, 'settings': case.settings,
                        'passed': all(s['passed'] for s in steps), 'steps': steps})
    return results


def _make_optical_panel(*, compact: bool, corrupted: bool = False,
                        pain_resist: bool = False,
                        packet: bytes | None = None):
    """Generate synthetic native StatusBar pixels without importing tests."""
    import numpy as np

    height, width = (48, 350) if compact else (102, 270)
    p = np.full((height, width, 3), (27, 37, 48), dtype=np.uint8)
    for x, color in ((0, (255, 0, 255)), (16, (0, 255, 255)),
                     (32, (255, 255, 0))):
        p[0:12, x:x + 12] = color
    p[0:8, 48:56] = (0, 204, 102)
    p[0:10, 60:70] = (77, 77, 77)
    p[0:10, 76:86] = (255, 255, 0) if pain_resist else (77, 77, 77)
    for x in (96, 108, 120, 132):
        p[0:8, x:x + 8] = (64, 64, 64)
    if compact:
        p[0:8, 156:164] = (38, 230, 102)
        p[37:45, 0:8] = (0, 179, 179)
        for x in (16, 32, 48):
            p[37:47, x:x + 10] = (77, 77, 77)
        for x in (64, 76, 88, 100, 112, 124, 136, 148):
            p[37:45, x:x + 8] = (64, 64, 64)
        bar_rows, bar_height = (14, 21, 28), 4
        if packet is not None:
            p[0:8, 180:188] = (0, 191, 89)
            p[0:8, 196:204] = (191, 102, 0)
            for index in range(32):
                col, row = index % 16, index // 16
                x, y = 180 + col * 10, 14 + row * 10
                p[y:y + 8, x:x + 8] = tuple(packet[index * 3:index * 3 + 3])
    else:
        bar_rows, bar_height = (20, 40, 60), 12
        p[84:92, 0:8] = (0, 179, 179)
        for x in (16, 32, 48):
            p[84:94, x:x + 10] = (77, 77, 77)
        for x in (64, 76, 88, 100, 112, 124, 136, 148):
            p[84:92, x:x + 8] = (64, 64, 64)
    for y, fraction, color in zip(bar_rows, (.76, .48, .34),
                                  ((0, 255, 0), (0, 97, 255), (255, 0, 0))):
        p[y:y + bar_height, :160] = (25, 25, 25)
        p[y:y + bar_height, :round(fraction * 160)] = color
    if corrupted:
        p[bar_rows[1]:bar_rows[1] + bar_height, :160] = (130, 130, 130)
    canvas = np.full((160, 450, 3), (20, 40, 60), dtype=np.uint8)
    canvas[20:20 + height, 25:25 + width] = p
    return canvas


def run_telemetry_tests() -> list[dict[str, Any]]:
    from .bridge import BridgeNotFound, decode_bridge
    from .semantic_bridge import decode_pixels, encode_for_test

    checks = []
    for compact in (True, False):
        name = 'compact' if compact else 'normal'
        try:
            rd = decode_bridge(_make_optical_panel(compact=compact))
            correct = (rd.layout == name and abs(rd.observation.hp - .76) < .02 and
                       abs(rd.observation.mana - .48) < .02 and
                       abs(rd.observation.target_hp - .34) < .02)
            checks.append({'name': f'{name} RGB StatusBars decode', 'passed': correct,
                           'observation': asdict(rd.observation), 'layout': rd.layout})
        except Exception as exc:
            checks.append({'name': f'{name} RGB StatusBars decode', 'passed': False,
                           'error': f'{type(exc).__name__}: {exc}'})
        try:
            decode_bridge(_make_optical_panel(compact=compact, corrupted=True))
            rejected = False
        except BridgeNotFound:
            rejected = True
        except Exception:
            rejected = False
        checks.append({'name': f'{name} corrupted mana must fail closed', 'passed': rejected})
    packet = encode_for_test('B|3|2|ACTIONBUTTON2|spell|585|Smite', 47)
    frame = _make_optical_panel(compact=True, packet=packet)
    try:
        reading = decode_bridge(frame)
        actual = decode_pixels(frame, reading.marker_x, reading.marker_y,
                               reading.scale, layout=reading.layout)
        passed = actual is not None and actual.kind == 'B' and actual.sequence == 47
    except Exception:
        passed = False
    checks.append({'name': 'compact optical binding-packet checksum', 'passed': passed})
    bad = bytearray(packet)
    bad[10] ^= 1  # data bit flip must invalidate checksum
    frame = _make_optical_panel(compact=True, packet=bad)
    reading = decode_bridge(frame)
    checks.append({'name': 'bad optical binding packet is rejected',
                   'passed': decode_pixels(frame, reading.marker_x,
                                           reading.marker_y, reading.scale,
                                           layout=reading.layout) is None})
    try:
        reading = decode_bridge(_make_optical_panel(compact=True, pain_resist=True))
        passed = reading.observation.error == 'pain_resist'
    except Exception:
        passed = False
    checks.append({'name': 'compact Pain miss/resist pixel decodes', 'passed': passed})
    return checks


def read_live_telemetry() -> dict[str, Any]:
    """One optical read only; never save a screenshot or send inputs."""
    try:
        from mss import mss
        from .bridge import monitor_bridge
        with mss() as capture:
            reading = monitor_bridge(capture)
        return {'status': 'ok', 'layout': reading.layout,
                'scale': round(reading.scale, 3),
                'observation': asdict(reading.observation)}
    except Exception as exc:
        return {'status': 'unavailable', 'message': type(exc).__name__,
                'note': 'WoW must be visible with unobstructed PriestBridge telemetry.'}


def _markdown(report: dict[str, Any]) -> str:
    passed = report['summary']['passed']
    total = report['summary']['total']
    lines = [f"# PriestBot {report['version']} — diagnostic report", '',
             f"Generated: {report['generated_utc']}", '',
             f"**Offline checks: {passed}/{total} passed.**", '',
             'These are synthetic tests, not proof of live WoW behavior.', '',
             '## Telemetry decoder', '']
    for check in report['telemetry_tests']:
        lines.append(f"- {'PASS' if check['passed'] else 'FAIL'}: {check['name']}")
    lines.extend(['', '## Decisions (expected → actual)', ''])
    for case in report['decision_tests']:
        lines.append(f"### {'PASS' if case['passed'] else 'FAIL'} — {case['name']}")
        for step in case['steps']:
            lines.append(f"- {step['time_s']:.2f}s: {step['expected_action'] or 'wait'} → "
                         f"{step.get('actual_action') or 'wait'}; "
                         f"{step.get('decision_reason', step.get('error', 'unknown'))} "
                         f"({'PASS' if step['passed'] else 'FAIL'})")
        lines.append('')
    live = report.get('live_telemetry')
    settings = report['local_settings']
    lines.extend(['## Installed configuration (no secrets or local paths)', ''])
    for key, value in settings.items():
        lines.append(f'- {key}: {value}')
    lines.append('')
    lines.extend(['## Optional live optical snapshot', ''])
    if live is None:
        lines.append('Not requested. Offline checks never require the WoW client.')
    else:
        lines.append('Result: ' + live['status'])
        if live['status'] == 'ok':
            lines.append(f"Layout: {live['layout']}, UI scale: {live['scale']}")
            reading = live['observation']
            lines.append(f"HP: {reading['hp']:.1%}, Mana: {reading['mana']:.1%}, "
                         f"Target HP: {reading['target_hp']:.1%}, "
                         f"Error: {reading['error'] or 'none'}")
        else:
            lines.append(live['message'])
    lines.extend(['', '## Privacy / limitations', '',
                  '- No screenshots, keyboard history, names, chat, or absolute local paths are included.',
                  '- This report does not control WoW, send game inputs, or train a model.',
                  '- Stationary tracking is opt-in; fleeing mobs are turned toward only on confirmed facing errors.',
                  '- Line of sight is handled by waiting and bounded retries, never chasing blindly.',
                  '- Upload the ZIP or this Markdown file into PriestBot Chat 2 for review.', ''])
    return '\n'.join(lines)


def generate_report(output_dir: Path | None = None, *, include_live: bool = False,
                    current_config: Config | None = None) -> Path:
    """Write a report ZIP with human-readable Markdown and machine-readable JSON."""
    from .install_core import APP_VERSION

    root = output_dir or Path(__file__).resolve().parents[1] / 'diagnostic_reports'
    root.mkdir(parents=True, exist_ok=True)
    decision_tests = run_decision_tests()
    telemetry_tests = run_telemetry_tests()
    try:
        config = current_config if current_config is not None else Config.load()
        config_error = None
    except Exception as exc:
        config = Config()
        config_error = type(exc).__name__
    safe_fields = ('dry_run', 'main_damage', 'telemetry_source', 'input_mode',
                   'enable_stationary_tracking', 'enable_movement',
                   'use_heal', 'heal_below', 'use_renew', 'renew_below',
                   'use_shield', 'enable_drink', 'flee_target_hp_below',
                   'los_wait_s', 'los_retry_s', 'los_max_retries')
    n_total = len(decision_tests) + len(telemetry_tests)
    n_passed = sum(c['passed'] for c in decision_tests + telemetry_tests)
    report = {'schema_version': 1, 'version': APP_VERSION,
              'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'summary': {'total': n_total, 'passed': n_passed, 'failed': n_total - n_passed},
              'telemetry_tests': telemetry_tests, 'decision_tests': decision_tests,
              'local_settings': {key: getattr(config, key) for key in safe_fields},
              'config_load_error': config_error,
              'live_telemetry': read_live_telemetry() if include_live else None}
    basename = 'PriestBot-diagnostics-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    target = root / (basename + '.zip')
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('report.md', _markdown(report))
        bundle.writestr('report.json', json.dumps(report, indent=2) + '\n')
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description='Export offline PriestBot diagnostics for uploading to ChatGPT')
    parser.add_argument('--output-dir', type=Path, help='Optional report directory')
    parser.add_argument('--live', action='store_true', help='Try one read-only game telemetry snapshot')
    args = parser.parse_args()
    path = generate_report(args.output_dir, include_live=args.live)
    print('Report saved:', path)
    with zipfile.ZipFile(path) as bundle:
        summary = json.loads(bundle.read('report.json'))['summary']
    print(f"Offline checks: {summary['passed']}/{summary['total']} passed. Upload the ZIP to your chat.")
    if summary['failed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
