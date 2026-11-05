"""Readable, local-only evaluation and training coverage UI.

This module displays reports; it never trains a model, promotes one or sends
WoW inputs. All pictures resolve under learning_data/sessions only.
"""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


def pretty_action(name: str) -> str:
    return str(name).replace("_", " ").title()


def as_percent(value) -> str:
    try:
        return f"{float(value)*100:.1f}%"
    except (ValueError, TypeError):
        return "—"


def gate_summary(report: dict | None) -> dict:
    """Read-only explanation of existing independent holdout promotion gate."""
    if not report:
        return {"state": "No candidate", "headline": "No model has been trained yet.",
                "checks": [], "metrics": [], "reason": "Collect demonstrations, then train a candidate."}
    ev = report.get("evaluation", {})
    trained = report.get("training", {})
    metrics = [
        ("Training samples", str(ev.get("train_samples", trained.get("samples", 0)))),
        ("Holdout samples", str(ev.get("holdout_samples", 0))),
        ("Accuracy", as_percent(ev.get("accuracy"))),
        ("Majority baseline", as_percent(ev.get("baseline_accuracy"))),
        ("Macro F1", as_percent(ev.get("macro_f1"))),
    ]
    if not ev.get("evaluated"):
        split_names = {
            "separate_session": "A separate demonstration session exists",
            "holdout_at_least_12": "The most recent session has at least 12 usable labels",
            "train_at_least_24": "Earlier sessions have at least 24 usable labels",
            "holdout_classes_in_training": "Holdout actions were demonstrated in earlier sessions",
            "all_classes_in_training": "Every candidate action appears in training sessions",
        }
        checks = []
        for key, label in split_names.items():
            found = ev.get("split_checks", {}).get(key)
            if found is not None:
                checks.append((label, bool(found)))
        return {"state": "NOT EVALUATED", "headline": "Independent holdout requirements aren't met.",
                "checks": checks, "metrics": metrics,
                "reason": ev.get("explanation", "Use a later, separate recording as the evaluation session.")}
    threshold = max(.65, float(ev.get("baseline_accuracy", 0)) + .05)
    checks = [
        (f"Accuracy ≥ {threshold*100:.0f}% (65% minimum and baseline + 5 points)",
         ev.get("accuracy", 0) >= threshold),
        ("Macro F1 ≥ 60%", ev.get("macro_f1", 0) >= .60),
    ]
    row_scores = ev.get("recall_by_class", [])
    cm = ev.get("confusion_matrix", [])
    tested = [i for i, row in enumerate(cm) if sum(row) > 0]
    checks.append(("Recall ≥ 40% for every action in the holdout",
                   all(i < len(row_scores) and row_scores[i] >= .40 for i in tested)
                   if cm else False))
    eligible = bool(ev.get("promotion_eligible"))
    return {"state": "ELIGIBLE — ADVISORY ONLY" if eligible else "EVALUATED — DID NOT PASS",
            "headline": "Candidate meets the offline gate." if eligible else
                        "Candidate did not meet every offline criterion.",
            "checks": checks, "metrics": metrics,
            "reason": "Even a passing model cannot control gameplay; only explicit advisory approval is allowed."
                      if eligible else ev.get("explanation", "Needs more diverse demonstrations.")}


def per_action_rows(report: dict | None) -> list[dict]:
    if not report:
        return []
    ev = report.get("evaluation", {})
    classes = report.get("classes", [])
    cm = ev.get("confusion_matrix")
    if not cm:
        return [{"action": c, "holdout_samples": 0, "correct": 0, "wrong": 0,
                 "precision": None, "recall": None, "f1": None, "confused_with": ""} for c in classes]
    rows = []
    for i, c in enumerate(classes):
        row = cm[i]
        n = int(sum(row))
        correct = int(row[i])
        predicted = int(sum(r[i] for r in cm))
        precision = correct / predicted if predicted else 0
        recall = correct / n if n else 0
        f1 = 2*precision*recall/(precision+recall) if precision+recall else 0
        wrong = sorted(((cnt, classes[j]) for j, cnt in enumerate(row) if j != i and cnt), reverse=True)
        rows.append({"action": c, "holdout_samples": n, "correct": correct,
                     "wrong": n-correct, "precision": precision if n else None,
                     "recall": recall if n else None,
                     "f1": f1 if n else None,
                     "confused_with": pretty_action(wrong[0][1]) if wrong else "—"})
    return rows


def safely_resolve_frame(base: Path, relative: str | None) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    parts = Path(relative).parts
    if len(parts) < 4 or parts[0] != 'sessions' or parts[2] != 'frames':
        return None
    try:
        resolved = (base / relative).resolve(strict=True)
        if resolved.is_relative_to((base / 'sessions').resolve()) and resolved.suffix.lower() in ('.jpg','.jpeg','.png'):
            return resolved
    except (OSError, ValueError):
        pass
    return None


class LearningDashboard:
    def __init__(self, master, report: dict | None, coverage: dict, *, base: Path,
                 starting_tab="evaluation"):
        self.report, self.coverage, self.base = report, coverage, base
        self.window = tk.Toplevel(master)
        self.window.title("PriestBot — Learning evaluation & data coverage")
        self.window.geometry('1030x740')
        self.window.minsize(790, 540)
        self.window.transient(master)
        self.window.resizable(True, True)
        self.photo = None
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text="Learning Mode: evaluate before deploying",
                  font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(outer, text="Read-only reports · models remain advisory-only · recorded input does not equal a training label",
                  foreground='#555').pack(anchor='w', pady=(2, 9))
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill='both', expand=True)
        self.overview = ttk.Frame(self.tabs, padding=12)
        self.actions = ttk.Frame(self.tabs, padding=12)
        self.examples = ttk.Frame(self.tabs, padding=12)
        self.coverage_frame = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.overview, text='Evaluation summary')
        self.tabs.add(self.actions, text='Per-action results')
        self.tabs.add(self.examples, text='Example predictions')
        self.tabs.add(self.coverage_frame, text='Training data coverage')
        self.render_overview()
        self.render_actions()
        self.render_examples()
        self.render_coverage()
        if starting_tab == 'coverage':
            self.tabs.select(self.coverage_frame)
        ttk.Button(outer, text="Close", command=self.window.destroy).pack(anchor='e', pady=(8,0))

    def render_overview(self):
        data = gate_summary(self.report)
        ttk.Label(self.overview, text=data['state'], font=('Segoe UI', 17, 'bold')).pack(anchor='w')
        ttk.Label(self.overview, text=data['headline'], font=('Segoe UI', 11)).pack(anchor='w', pady=(3,10))
        if self.report:
            ttk.Label(self.overview, text=f"Candidate: {self.report.get('candidate_id', 'unknown')}",
                      foreground='#555').pack(anchor='w', pady=(0,6))
        metrics = ttk.LabelFrame(self.overview, text="Measured data", padding=10)
        metrics.pack(fill='x', pady=5)
        for i,(title,value) in enumerate(data['metrics']):
            ttk.Label(metrics, text=title).grid(row=i,column=0,sticky='w',padx=7,pady=3)
            ttk.Label(metrics, text=value,font=('Segoe UI',10,'bold')).grid(row=i,column=1,sticky='w',padx=7,pady=3)
        gate = ttk.LabelFrame(self.overview, text="Why the model did / didn't pass", padding=10)
        gate.pack(fill='x', pady=8)
        if not data['checks']:
            ttk.Label(gate, text="Evaluation checks will appear after a candidate is trained.").pack(anchor='w')
        for text,passed in data['checks']:
            ttk.Label(gate, text=('PASS  ' if passed else 'NEEDS WORK  ') + text,
                      foreground='#196b37' if passed else '#9e411c', wraplength=880).pack(anchor='w', pady=2)
        ttk.Label(self.overview, text=data['reason'], wraplength=880,
                  font=('Segoe UI',10)).pack(anchor='w', pady=9)
        ttk.Label(self.overview, text="Passing this offline test is NOT proof of safe navigation or better farming. "
                  "No learned actions are sent to WoW.", wraplength=880,
                  foreground='#555').pack(anchor='w')

    def _tree(self, parent, columns, headings, widths, *, height=15):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, pady=6)
        table = ttk.Treeview(frame, columns=columns, show='headings', height=height)
        for key in columns:
            table.heading(key, text=headings.get(key, key))
            table.column(key, width=widths.get(key,110), minwidth=70, stretch=(key == columns[0]))
        vs = ttk.Scrollbar(frame, orient='vertical', command=table.yview)
        table.configure(yscrollcommand=vs.set)
        table.pack(side='left', fill='both', expand=True)
        vs.pack(side='right', fill='y')
        return table

    def render_actions(self):
        ttk.Label(self.actions, text="Class-by-class performance on held-out gameplay",
                  font=('Segoe UI',12,'bold')).pack(anchor='w')
        ttk.Label(self.actions, text="Precision: when the model predicts an action, how often it is right. "
                  "Recall: how often it recognizes that action. — means the holdout had no examples.",
                  wraplength=900).pack(anchor='w', pady=(3,8))
        cols = ('action','held','correct','wrong','precision','recall','f1','mistaken')
        tbl = self._tree(self.actions, cols,
                         {'action':'Action','held':'Holdout','correct':'Correct','wrong':'Wrong',
                          'precision':'Precision','recall':'Recall','f1':'F1', 'mistaken':'Most confused with'},
                         {'action':220,'held':75,'correct':70,'wrong':70,
                          'precision':90,'recall':90,'f1':85,'mistaken':180},height=18)
        rows=per_action_rows(self.report)
        for row in rows:
            tbl.insert('', 'end',values=(pretty_action(row['action']), row['holdout_samples'],
                       row['correct'],row['wrong'], as_percent(row['precision']),
                       as_percent(row['recall']),as_percent(row['f1']),row['confused_with']))
        if not self.report or not self.report.get('evaluation',{}).get('evaluated'):
            ttk.Label(self.actions, text="No held-out action metrics yet. Record a new demonstration session and retrain.",
                      foreground='#9e411c').pack(anchor='w',pady=5)

    def render_examples(self):
        ttk.Label(self.examples, text="Representative predictions on unseen holdout frames",
                  font=('Segoe UI',12,'bold')).pack(anchor='w')
        ev=(self.report or {}).get('evaluation', {})
        samples=ev.get('examples', [])
        ttk.Label(self.examples, text=f"Showing {len(samples)} saved examples from "
                  f"{ev.get('examples_total', 0)} holdout predictions. "
                  "Misclassified examples are shown first.", wraplength=880).pack(anchor='w',pady=(4,8))
        frame=ttk.Frame(self.examples)
        frame.pack(fill='both',expand=True)
        left=ttk.Frame(frame)
        left.pack(side='left',fill='both',expand=True)
        cols=('result','actual','predicted','confidence','session')
        table=self._tree(left,cols,
                         {'result':'Result','actual':'Actual','predicted':'Predicted','confidence':'Confidence','session':'Session'},
                         {'result':75,'actual':180,'predicted':180,'confidence':90,'session':140},height=15)
        right=ttk.Frame(frame, width=340)
        right.pack(side='right',fill='y',padx=(12,0))
        self.example_image=ttk.Label(right,text="Select an example to preview the game frame",wraplength=310)
        self.example_image.pack(anchor='center',pady=(12,8))
        self.example_details=ttk.Label(right,text='',wraplength=320)
        self.example_details.pack(anchor='w')
        for i,ex in enumerate(samples):
            table.insert('', 'end',iid=str(i),values=("Correct" if ex.get('correct') else "Wrong",
                  pretty_action(ex.get('truth','')),
                  pretty_action(ex.get('predicted','')),
                  as_percent(ex.get('confidence')),
                  ex.get('session','')[:16]))
        def chosen(_event=None):
            if not table.selection(): return
            ex=samples[int(table.selection()[0])]
            path=safely_resolve_frame(self.base, ex.get('frame'))
            self.photo=None
            if path:
                try:
                    with Image.open(path) as src:
                        image=src.convert('RGB')
                        image.thumbnail((320,260))
                    self.photo=ImageTk.PhotoImage(image,master=self.window)
                    self.example_image.configure(image=self.photo,text='')
                except (OSError, ValueError, tk.TclError):
                    self.example_image.configure(image='',text="Screenshot could not be loaded")
            else:
                self.example_image.configure(image='',text='Screenshot no longer available')
            self.example_details.configure(text=(f"Actual: {pretty_action(ex.get('truth',''))}\n"
                 f"Predicted: {pretty_action(ex.get('predicted',''))}\n"
                 f"Confidence: {as_percent(ex.get('confidence'))}\n"
                 f"Session: {ex.get('session','')}"))
        table.bind('<<TreeviewSelect>>', chosen)
        if not samples:
            ttk.Label(self.examples,text="No saved holdout examples yet. Retrain after recording a separate "
                      "evaluation session. Older v0.19 reports also lack example predictions.",
                      foreground='#9e411c',wraplength=840).pack(anchor='w',pady=6)

    def render_coverage(self):
        cover=self.coverage
        ttk.Label(self.coverage_frame, text="What demonstrations should you record next?",
                  font=('Segoe UI',12,'bold')).pack(anchor='w')
        ttk.Label(self.coverage_frame, text=(f"{cover['total_labels']} valid labeled actions across "
                  f"{cover['sessions']} sessions. {cover['action_count']} classes have at least 8 examples. "
                  f"{cover['usable_for_training']} labels meet the class-minimum rule."),
                  wraplength=960).pack(anchor='w',pady=(3,7))
        guidance=ttk.LabelFrame(self.coverage_frame,text='Next recording goals',padding=8)
        guidance.pack(fill='x',pady=(0,7))
        for n,text in enumerate(cover.get('next_steps',[]),1):
            ttk.Label(guidance,text=f"{n}. {text}",wraplength=940).pack(anchor='w',pady=2)
        ttk.Label(self.coverage_frame, text="8 per action is the minimum for training; aim for ~20+ across "
                  "different angles/areas to improve robustness. Raw keystrokes are not automatically training examples.",
                  wraplength=930).pack(anchor='w',pady=(0,7))
        cols=('action','count','sessions','min','to20','status')
        tree=self._tree(self.coverage_frame,cols,
                        {'action':'Action','count':'Labels','sessions':'Sessions','min':'Need for min (8)',
                         'to20':'Need for 20','status':'Training coverage'},
                        {'action':300,'count':75,'sessions':75,'min':115,'to20':105,'status':140},height=15)
        for row in cover['actions']:
            tree.insert('','end',values=(pretty_action(row['action']),row['samples'],row['sessions'],
                row['training_shortfall'], row['recommended_shortfall'],
                'Training eligible' if row['training_supported'] else 'Collect more'))
