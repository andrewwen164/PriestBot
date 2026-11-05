"""Read-only reporting for temporal vision candidates; no model deployment UI."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from .temporal_vision import HEADS
from .scene_vision import detect_red_nameplates
from PIL import Image, ImageTk, ImageDraw


def coverage_lines(coverage: dict) -> list[str]:
    rows = [f"Usable synchronized visual/control intervals: {coverage['usable_intervals']}",
            f"Sessions: {len(coverage['sessions'])}",
            f"PyTorch: {'installed' if coverage['torch_available']['installed'] else 'not installed'}",
            f"Device: {coverage['torch_available']['device']}",
            "", "Per-control evidence (multiple controls can be true at once):"]
    rows.extend(f"{name.replace('_',' ').title():<28} {coverage['action_counts'].get(name,0):>5}" for name in HEADS)
    rows.extend(['', coverage['guidance'], '',
                 'A press is an observed action, not proof that movement improved navigation.'])
    return rows


class VisionDashboard:
    def __init__(self, parent, coverage: dict, report: dict | None):
        win=tk.Toplevel(parent)
        win.title('PriestBot — Temporal vision & movement learning')
        win.geometry('1020x690')
        ttk.Label(win,text='Temporal vision: multiple simultaneous movement controls',
                  font=('Segoe UI',15,'bold')).pack(anchor='w',padx=14,pady=(12,3))
        ttk.Label(win,text='3 consecutive BEFORE frames • game telemetry • prior inputs • holdout by session • no learned game inputs',
                  wraplength=960).pack(anchor='w',padx=14,pady=(0,10))
        notebook=ttk.Notebook(win); notebook.pack(fill='both',expand=True,padx=12,pady=8)
        coverage_page=ttk.Frame(notebook);notebook.add(coverage_page,text='Data coverage')
        text=tk.Text(coverage_page,wrap='word',font=('Consolas',10),height=20)
        text.pack(fill='both',expand=True)
        text.insert('1.0','\n'.join(coverage_lines(coverage)));text.configure(state='disabled')
        result=ttk.Frame(notebook); notebook.add(result,text='Independent evaluation')
        if not report:
            ttk.Label(result,text='No temporal vision model yet. Record new v0.22 demonstrations and train a candidate.',
                      wraplength=900).pack(anchor='w',padx=16,pady=14)
        else:
            ev=report.get('evaluation',{})
            metrics=[('Candidate', report.get('candidate_id','')),
                    ('Model',report.get('model','')),
                    ('Training samples',ev.get('train_samples',0)),
                    ('Holdout samples',ev.get('holdout_samples',0)),
                    ('Evaluated on independent session?',ev.get('evaluated',False)),
                    ('Exact simultaneous-control accuracy',
                     f"{100*ev.get('exact_combo_accuracy',0):.1f}%" if ev.get('evaluated') else '—'),
                    ('Macro F1',f"{100*ev.get('macro_f1',0):.1f}%" if ev.get('evaluated') else '—'),
                    ('No-input baseline',f"{100*ev.get('idle_baseline',0):.1f}%" if ev.get('evaluated') else '—'),
                    ('Mouse drag MAE',f"{ev.get('mouse_error_px')} pixels" if ev.get('mouse_error_px') is not None else '—'),
                    ('Holdout range-error rate',str(ev.get('holdout_outcome_proxies',{}).get('range_error_rate','—'))),
                    ('Holdout target-HP progress fraction',str(ev.get('holdout_outcome_proxies',{}).get('target_hp_progress_rate','—'))),
                    ('Offline gate', 'Passed' if ev.get('offline_gate_passed') else 'Not passed'),
                    ('Deployment', 'DISABLED — candidate only')]
            for label,value in metrics:
                r=ttk.Frame(result);r.pack(fill='x',padx=14,pady=3)
                ttk.Label(r,text=label,width=39).pack(side='left')
                ttk.Label(r,text=str(value),wraplength=620).pack(side='left')
            ttk.Label(result,text=ev.get('explanation',''),wraplength=920).pack(anchor='w',padx=14,pady=12)
        detail=ttk.Frame(notebook);notebook.add(detail,text='Per-control holdout metrics')
        cols=('action','support','precision','recall','f1')
        tree=ttk.Treeview(detail,columns=cols,show='headings')
        for col in cols:
            tree.heading(col,text=col.replace('_',' ').title())
            tree.column(col,width=210 if col=='action' else 120)
        for row in (report or {}).get('evaluation',{}).get('per_action',[]):
            tree.insert('','end',values=[str(row.get(c,'')) for c in cols])
        tree.pack(fill='both',expand=True)
        audit=ttk.Frame(notebook); notebook.add(audit,text='Visual audit')
        from .temporal_vision import load_temporal_intervals
        # Build a visual false-positive audit from the latest locally recorded
        # game-only screenshot. No model predictions or controls occur here.
        latest_frame = None
        for item in load_temporal_intervals(coverage.get('_base'))[::-1] if coverage.get('_base') else []:
            latest_frame = item['frames'][-1]
            break
        if latest_frame is not None:
            with Image.open(latest_frame) as original:
                canvas_image=original.convert('RGB')
            candidates=detect_red_nameplates(canvas_image)
            marker=ImageDraw.Draw(canvas_image)
            w,h=canvas_image.size
            for plate in candidates:
                x1=int((plate.x-plate.width/2)*w);x2=int((plate.x+plate.width/2)*w)
                y1=int((plate.y-plate.height/2)*h);y2=int((plate.y+plate.height/2)*h)
                marker.rectangle((x1-2,y1-2,x2+2,y2+2),outline='#F3C04F',width=2)
            canvas_image.thumbnail((920,520),Image.Resampling.BILINEAR)
            view=ImageTk.PhotoImage(canvas_image)
            label=ttk.Label(audit,image=view)
            label.image=view
            label.pack(anchor='center',padx=5,pady=8)
            ttk.Label(audit,text=f'{len(candidates)} RED nameplate candidates — rectangles are NOT verified mobs. Inspect false positives before relying on vision.',
                      wraplength=930).pack(anchor='w',padx=12)
        else:
            ttk.Label(audit,text='No new v0.22 synchronized game frames yet. Record a demonstration first.').pack(padx=12,pady=12)
        ttk.Label(win,text='This is an offline diagnostic, not a controller. Existing Priest combat and safety rules remain authoritative.',
                  wraplength=970).pack(anchor='w',padx=14,pady=(0,12))
