"""Headless UI construction: make sure cleanup retains every legacy tool."""
from priestbot import app as ui


class FakeWidget:
    widgets = []

    def __init__(self, parent=None, kind='Widget', **options):
        self.parent = parent
        self.kind = kind
        self.options = options
        self.commands = []
        self.tab_items = []
        self.layout = None
        self.widgets.append(self)

    def pack(self, **options):
        self.layout = ('pack', options)
        return self

    def grid(self, **options):
        self.layout = ('grid', options)
        return self

    def bind(self, *_args, **_kwargs):
        return None

    def configure(self, **options):
        self.options.update(options)

    def add(self, child, **options):
        self.tab_items.append((child, options))

    def add_command(self, **options):
        self.commands.append(options)


def _no_display_app(monkeypatch):
    FakeWidget.widgets = []

    def make(kind):
        return lambda parent=None, **opts: FakeWidget(parent, kind, **opts)

    for widget in ('Frame', 'Label', 'LabelFrame', 'Button', 'Checkbutton',
                   'Combobox', 'Entry', 'Separator', 'Notebook', 'Menubutton'):
        monkeypatch.setattr(ui.ttk, widget, make(widget))
    monkeypatch.setattr(ui.tk, 'Menu', make('Menu'))
    monkeypatch.setattr(ui.tk, 'Text', make('Text'))

    app = object.__new__(ui.App)
    app.root = FakeWidget(kind='Root')
    fields = ('state_text', 'values_text', 'aura_text', 'target_text', 'decision_text',
              'live', 'damage_mode', 'shield', 'pain', 'heal', 'renew', 'melee_oom',
              'drink', 'stationary_tracking', 'movement', 'telemetry_source',
              'input_mode', 'processes', 'calibration_text', 'learn_record',
              'learn_corrections', 'learn_mouse', 'learn_all_keys', 'learn_auto')
    for name in fields:
        setattr(app, name, object())
    messages = []
    app.log = messages.append
    app.build()
    return app, messages, list(FakeWidget.widgets)


def _ancestors(widget):
    parent = widget.parent
    while parent is not None:
        yield parent
        parent = parent.parent


def test_three_tabs_and_primary_safety_actions_always_visible(monkeypatch):
    _, messages, widgets = _no_display_app(monkeypatch)
    notebook, = [w for w in widgets if w.kind == 'Notebook']
    assert [item['text'] for _, item in notebook.tab_items] == [
        'Farm', 'Record & Review', 'Setup & Tools']

    buttons = [w for w in widgets if w.kind == 'Button']
    top = [w.options['text'] for w in buttons
           if not any(a.kind == 'Notebook' for a in _ancestors(w))]
    assert top == ['Start / Pause (F8)', 'PANIC STOP (F9)',
                   'Verify addon (F6)', 'Export diagnostic ZIP']
    assert len([w for w in widgets if w.kind == 'Checkbutton' and
                'REAL key presses' in w.options.get('text', '')]) == 1
    assert any('DRY RUN' in message for message in messages)


def test_advanced_commands_combined_not_deleted(monkeypatch):
    _, _, widgets = _no_display_app(monkeypatch)
    menus = [w for w in widgets if w.kind == 'Menubutton']
    assert {w.options['text'] for w in menus} == {
        'More maintenance ▾', 'Review data ▾', 'Training tools ▾'}
    assert [len(w.options['menu'].commands) for w in menus] == [4, 6, 4]

    callbacks = []
    for w in widgets:
        callback = w.options.get('command')
        if callback is not None:
            callbacks.append(callback.__func__.__name__)
        if w.kind == 'Menu':
            callbacks.extend(c['command'].__func__.__name__ for c in w.commands)
    assert set(callbacks) >= {
        'toggle', 'panic', 'verify_addon', 'export_diagnostics',
        'configure_keys', 'update_from_zip', 'reinstall_addon', 'capture',
        'show_config', 'change_addon_folder', 'recreate_shortcut',
        'toggle_demonstration', 'pause_demo_input', 'configure_demo_keys',
        'view_farming', 'view_semantics', 'view_evaluation', 'view_coverage',
        'view_vision', 'train_now', 'train_temporal', 'approve_advisory',
        'open_learning_data', 'test_background_tab', 'store_flags',
    }
    # No long row of seven independent model-training and review buttons.
    visible_buttons = [w.options['text'] for w in widgets if w.kind == 'Button']
    assert 'Train temporal vision' not in visible_buttons
    assert 'Approve advisory' not in visible_buttons
    assert 'Action semantics — bindings and confirmed uses' not in visible_buttons
