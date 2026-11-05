"""Optional PyTorch temporal vision imitation learner, entirely offline.

Requires separately installed PyTorch. No trained policy is loaded by the game
engine, no actions are sent, and a held-out *session* is mandatory for metrics.
Inputs are only BEFORE frames; labels describe simultaneous controls applied
until AFTER frame. Controls don't imply successful or desirable navigation.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path
import uuid

import numpy as np
from PIL import Image

VISION_W, VISION_H = 320, 180
HEADS = ('move_forward', 'move_backward', 'turn_left', 'turn_right',
         'strafe_left', 'strafe_right', 'jump', 'auto_run',
         'mouse_left', 'mouse_right', 'camera_drag', 'character_drag')
MIN_INTERVALS = 48
HOLDOUT_MIN = 20
FRAME_PERIOD_MAX_MS = 1000


def _safe_frame(session: Path, path) -> Path | None:
    if not isinstance(path, str) or not path.startswith('frames/'):
        return None
    relative = Path(path)
    if '..' in relative.parts or relative.is_absolute() or len(relative.parts) != 2:
        return None
    p = session / relative
    return p if p.is_file() else None


def _state_features(interval: dict, previous: dict | None) -> np.ndarray:
    state = interval.get('before_state') or {}
    vals = [float(state.get(k) or 0) for k in ('hp', 'mana', 'target_hp')]
    vals += [float(state.get('error') == e) for e in ('range', 'los', 'facing')]
    vals += [float(state.get('casting') is True)]
    plates = interval.get('before_nameplates') or []
    # Closest visual candidate to center. This isn't a verified target.
    best = min(plates, key=lambda p: abs(p.get('x', .5)-.5) + abs(p.get('y',.4)-.4)) if plates else None
    vals.extend([min(1, len(plates)/8), *([float(best.get(k,0)) for k in
                 ('x','y','width','confidence')] if best else [0,0,0,0])])
    previous = previous or {}
    movement = previous.get('movement_occupancy') or {}
    buttons = previous.get('mouse_occupancy') or {}
    vals.extend([float(movement.get(k,0)) for k in HEADS[:8]])
    vals.extend([float(buttons.get(k,0)) for k in ('left','right')])
    vals.extend([float(np.clip(previous.get(k,0)/200,-2,2)) for k in ('mouse_dx','mouse_dy')])
    shift = (previous.get('scene_shift') or {})
    vals.extend([float(shift.get('dx',0))/8, float(shift.get('dy',0))/8,
                 float(shift.get('confidence',0))])
    return np.asarray(vals, np.float32)


def _labels(interval: dict) -> tuple[np.ndarray, np.ndarray, float]:
    movement = interval.get('movement_occupancy') or {}
    mouse = interval.get('mouse_occupancy') or {}
    dx, dy = float(interval.get('mouse_dx') or 0), float(interval.get('mouse_dy') or 0)
    both = min(float(mouse.get('left',0)), float(mouse.get('right',0)))
    labels = [float(movement.get(h,0) >= .28) for h in HEADS[:8]]
    if both >= .28:  # default WoW both-button movement, distinct from W key
        labels[0] = 1.0
    labels.extend([float(mouse.get('left',0) >= .25),
                   float(mouse.get('right',0) >= .25),
                   float(mouse.get('left',0) >= .25 and abs(dx)+abs(dy)>=7 and both < .28),
                   float(mouse.get('right',0) >= .25 and abs(dx)+abs(dy)>=7)])
    active_drag = float(mouse.get('left',0) >= .25 or mouse.get('right',0) >= .25)
    return np.asarray(labels, np.float32), np.asarray([np.clip(dx/200,-2,2),np.clip(dy/200,-2,2)],np.float32), active_drag


def _outcomes(interval):
    before, after = interval.get('before_state') or {}, interval.get('after_state') or {}
    same_target = before.get('target_seq') == after.get('target_seq')
    target_damage = (float(before.get('target_hp') or 0) - float(after.get('target_hp') or 0)) if same_target else None
    return {'target_hp_progress': round(target_damage,4) if target_damage is not None else None,
            'new_range_error': (before.get('error_seq') != after.get('error_seq') and after.get('error') == 'range'),
            'same_target': bool(same_target),
            'scene_shift': interval.get('scene_shift') or {}}


def load_temporal_intervals(base: Path) -> list[dict]:
    """Load valid game-only input intervals. Historical v0.21 recordings are
    preserved but lack synced intervals and cannot be retroactively upgraded."""
    result = []
    for session in sorted((base/'sessions').glob('*/events.jsonl')):
        try:
            with session.open('r',encoding='utf-8') as f:
                rows = [json.loads(line) for line in f]
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not any(r.get('event') == 'session_start' and r.get('kind') == 'demonstration' for r in rows):
            continue
        history = []
        previous = None
        last_end = None
        for r in rows:
            if r.get('event') != 'control_interval' or int(r.get('schema',0)) != 1:
                continue
            start = _safe_frame(session.parent, r.get('before_frame'))
            end = _safe_frame(session.parent, r.get('after_frame'))
            duration = int(r.get('duration_ms',0))
            if start is None or end is None or not 50 <= duration <= FRAME_PERIOD_MAX_MS:
                history.clear(); previous = None; last_end = None
                continue
            if history and last_end != start:
                history = []  # focus change / game screenshot break
                previous = None
            seq = ([history[-2] if len(history)>=2 else (history[-1] if history else start),
                    history[-1] if history else start, start])
            # For first two frames, repeating the first is preferable to
            # reading future frames and leaking action outcomes.
            y, motion, drag = _labels(r)
            result.append({'session': session.parent.name, 'frames': seq,
                           'features': _state_features(r, previous), 'actions': y,
                           'mouse': motion, 'drag_mask': drag,
                           'outcome': _outcomes(r),
                           'frame': r.get('before_frame')})
            history.append(start)
            last_end = end
            if len(history)>3:
                history.pop(0)
            previous = r
    return result


def temporal_coverage(base: Path) -> dict:
    data = load_temporal_intervals(base)
    action_counts = {h: sum(int(row['actions'][i]>0) for row in data) for i,h in enumerate(HEADS)}
    sessions = Counter(row['session'] for row in data)
    return {'usable_intervals': len(data), 'sessions': dict(sessions),
            'action_counts': action_counts,
            'guidance': ('Record at least two separate sessions. Practice simultaneous strafe + RMB camera turns; '
                         'include approaches from different angles, and ensure WoW remains foreground. '
                         'Each example is a before-frame action interval, not a completed navigation task.'),
            'torch_available': torch_status()}


def torch_status() -> dict:
    try:
        import torch
        return {'installed': True, 'cuda': bool(torch.cuda.is_available()),
                'device': torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}
    except (ImportError, OSError) as exc:
        return {'installed': False, 'cuda': False, 'device': 'not installed', 'reason': str(exc)}


@lru_cache(maxsize=384)
def _frame_tensor(path: str) -> np.ndarray:
    with Image.open(path) as im:
        im = im.convert('RGB').resize((VISION_W,VISION_H),Image.Resampling.BILINEAR)
        return np.asarray(im, dtype=np.uint8).transpose(2,0,1).copy()


def _images(row):
    return np.concatenate([_frame_tensor(str(f)) for f in row['frames']],axis=0).astype(np.float32)/255


def _build_model(torch, input_features):
    nn = torch.nn
    class TemporalConvNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(9, 16, 5, stride=2, padding=2), nn.ReLU(),
                nn.Conv2d(16, 32, 3, stride=2, padding=1), nn.ReLU(),
                nn.Conv2d(32, 48, 3, stride=2, padding=1), nn.ReLU(),
                nn.AdaptiveAvgPool2d((3,5)), nn.Flatten())
            self.head = nn.Sequential(nn.Linear(48*3*5+input_features, 128),
                                      nn.ReLU(), nn.Dropout(.15))
            self.actions = nn.Linear(128,len(HEADS))
            self.mouse = nn.Linear(128,2)
        def forward(self,frames,features):
            x = self.head(torch.cat((self.conv(frames),features),dim=1))
            return self.actions(x), self.mouse(x)
    return TemporalConvNet()


def train_temporal_candidate(base: Path, *, epochs: int=16, seed: int=22,
                             batch_size: int=16) -> dict:
    """Train an offline, session-held-out multi-output CNN if PyTorch available.

    A passing offline test NEVER enables movement. Promotion needs a separate
    supervised live outcome test, which v0.22 intentionally does not provide.
    """
    if not torch_status()['installed']:
        return {'status': 'missing_torch', 'message': 'PyTorch is optional and not installed. See README: GPU setup.'}
    import torch
    from torch.utils.data import Dataset, DataLoader
    torch.manual_seed(seed)
    np.random.seed(seed)
    all_data = load_temporal_intervals(base)
    if len(all_data) < MIN_INTERVALS:
        return {'status':'insufficient_data', 'message': f'Need {MIN_INTERVALS} v0.22 control intervals; have {len(all_data)}.'}
    sessions = sorted(set(r['session'] for r in all_data))
    # Hold out the entire most recent session from training.
    holdout = sessions[-1] if len(sessions)>1 else None
    train = [r for r in all_data if r['session'] != holdout] if holdout else all_data
    test = [r for r in all_data if r['session'] == holdout] if holdout else []
    evaluated = len(train) >= MIN_INTERVALS and len(test) >= HOLDOUT_MIN
    if len(train) < MIN_INTERVALS:
        # Do not mix holdout data into train to make a misleading evaluation.
        train=all_data
        test=[]
        evaluated=False
    class Frames(Dataset):
        def __init__(self,items): self.items=items
        def __len__(self):return len(self.items)
        def __getitem__(self,i):
            row=self.items[i]
            return (_images(row), row['features'], row['actions'], row['mouse'],
                    np.float32(row['drag_mask']))
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    model = _build_model(torch, len(train[0]['features'])).to(device)
    opt = torch.optim.AdamW(model.parameters(),lr=.0007,weight_decay=.01)
    targets = np.stack([r['actions'] for r in train])
    positive = targets.sum(axis=0)
    weights = np.clip((len(train)-positive) / np.maximum(1,positive),1,8)
    pos_weight=torch.tensor(weights,dtype=torch.float32,device=device)
    bce = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    loader = DataLoader(Frames(train),batch_size=batch_size,shuffle=True,num_workers=0)
    model.train()
    for epoch in range(max(1,epochs)):
        for frame,state,label,mouse,mask in loader:
            frame,state,label,mouse,mask=(v.to(device) for v in (frame,state,label,mouse,mask))
            logits, delta=model(frame,state)
            mloss = (((delta-mouse)**2).mean(dim=1)*mask).sum()/mask.sum().clamp(min=1)
            loss=bce(logits,label)+.12*mloss
            opt.zero_grad();loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
            opt.step()
    metrics = {'evaluated':False,'promotion_eligible':False,
               'holdout_samples':len(test),'train_samples':len(train),
               'explanation':'Need a separate session with 20+ intervals; no gameplay controls can be deployed.'}
    if evaluated:
        model.eval()
        logits_list=[];mouse_list=[]
        with torch.no_grad():
            for frame,state,labels,mouse,mask in DataLoader(Frames(test),batch_size=batch_size,shuffle=False,num_workers=0):
                logit,delta=model(frame.to(device),state.to(device))
                logits_list.append(logit.sigmoid().cpu().numpy())
                mouse_list.append(delta.cpu().numpy())
        probs=np.concatenate(logits_list,axis=0)
        pred=probs>=.5
        true=np.stack([r['actions'] for r in test])>0.5
        per=[]
        for i,h in enumerate(HEADS):
            tp=int((pred[:,i]&true[:,i]).sum()); fp=int((pred[:,i]&~true[:,i]).sum())
            fn=int((~pred[:,i]&true[:,i]).sum());support=int(true[:,i].sum())
            precision=tp/max(tp+fp,1);recall=tp/max(tp+fn,1)
            f1=2*precision*recall/max(precision+recall,1e-8)
            per.append({'action':h,'support':support,'precision':round(precision,3),
                        'recall':round(recall,3),'f1':round(f1,3)})
        supported=[x for x in per if x['support']>=3]
        macro_f1=float(np.mean([x['f1'] for x in supported])) if supported else 0.0
        exact=float(np.mean(np.all(pred==true,axis=1)))
        idle_baseline=float(np.mean(np.all(~true,axis=1)))
        drag_mask=np.array([r['drag_mask'] for r in test],bool)
        mae = (float(np.mean(np.abs(np.concatenate(mouse_list)[drag_mask] -
                                     np.stack([r['mouse'] for r in test])[drag_mask])))*200
               if drag_mask.any() else None)
        # Outcomes are descriptive proxies, not proof that a suggested action
        # will navigate safely. Holdout actions came from HUMAN demonstrations.
        range_error_rate=float(np.mean([r['outcome']['new_range_error'] for r in test]))
        damage_progress_rate=float(np.mean([r['outcome']['target_hp_progress'] is not None and
                                            r['outcome']['target_hp_progress'] > .001 for r in test]))
        scene_motion_rate=float(np.mean([r['outcome']['scene_shift'].get('confidence',0) > .12 for r in test]))
        # Read-only reports: offline numbers do NOT unlock input authority.
        offline_gate=bool(macro_f1>=.65 and exact>=max(.5,idle_baseline+.10)
                          and all(x['recall']>=.5 for x in supported))
        metrics.update({'evaluated':True, 'exact_combo_accuracy':round(exact,4),
                        'idle_baseline':round(idle_baseline,4),
                        'macro_f1':round(macro_f1,4),'per_action':per,
                        'mouse_error_px':round(mae,1) if mae is not None else None,
                        'holdout_outcome_proxies': {'range_error_rate':round(range_error_rate,3),
                            'target_hp_progress_rate':round(damage_progress_rate,3),
                            'scene_motion_rate':round(scene_motion_rate,3),
                            'warning':'These are descriptive game signals, not proof of successful learned navigation.'},
                        'offline_gate_passed':offline_gate,
                        'promotion_eligible':False,
                        'explanation':'Offline gate passed; a separate supervised navigation-outcome evaluation is still required before any model-controlled movement.'
                                      if offline_gate else 'Offline holdout below the vision safety thresholds. No model controls gameplay.'})
    candidate_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
    folder=base/'vision_candidates'/candidate_id
    folder.mkdir(parents=True,exist_ok=False)
    # State dictionaries only, never arbitrary executable deserialization from an external file.
    torch.save(model.cpu().state_dict(),folder/'temporal_model.pt')
    report={'candidate_id':candidate_id,'created_at':datetime.now(timezone.utc).isoformat(),
            'model':'temporal_rgb_3frame_multilabel_cnn_v1',
            'training':{'samples':len(train),'sessions':len(set(r['session'] for r in train)),
                        'epochs':epochs, 'source':'human_game_focused_control_intervals_only',
                        'hardware':str(device)},'heads':list(HEADS),
            'evaluation':metrics,'deployment':'candidate_only_NO_GAME_INPUTS',
            'limitations':['Nameplates are visual candidates, not verified enemies',
                           'Mouse deltas may be missing if the cursor is locked',
                           'Held controls are imitation labels, not proof of progress']}
    (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    (base/'latest_vision_candidate.json').write_text(json.dumps({'candidate_id':candidate_id})+'\n',encoding='utf8')
    return {'status':'candidate_created',**report}


def latest_vision_report(base: Path) -> dict | None:
    try:
        meta=json.loads((base/'latest_vision_candidate.json').read_text(encoding='utf8'))
        return json.loads((base/'vision_candidates'/meta['candidate_id']/'report.json').read_text(encoding='utf8'))
    except (ValueError,KeyError,OSError):
        return None
