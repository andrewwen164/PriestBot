# PriestBot v0.25.1 — Streamlined Attended Farmer UI

The desktop window is now organized into **Farm**, **Record & Review**, and
**Setup & Tools** tabs. Core actions remain visible above the tabs at all
times: **Start/Pause (F8)**, **PANIC STOP (F9)**, **Verify addon (F6)**, and
**Export diagnostic ZIP**. The real-input checkbox remains prominent and OFF
each launch. F7 manual calibration is still available from the keyboard.

- **Farm:** main damage mode, spell bindings, Shield/Pain/Heal/Renew, melee,
  drinking, stationary fleeing-mob tracking, and input method.
- **Record & Review:** demonstration Start/Stop and input privacy pause.
  **Review data** combines the farming, action semantics, learning, and vision
  viewers; **Training tools** combines key configuration, candidate training,
  temporal vision, and read-only advisory approval. Recording switches remain
  available as before.
- **Setup & Tools:** ZIP upgrades, addon repair, source selection, game process
  list, background-input test, experimental walking, and a **More maintenance**
  menu for calibration, addon-folder changes, shortcut repair, and config.json.
- Shorter startup log and smaller window; no existing behavior, user settings,
  training files, or keybindings were intentionally removed or reset.

**Upgrade:** From the installed PriestBot shortcut, use **Update from ZIP** and
select the complete v0.25.1 release. The updater retains local state and
virtual environment. PriestBridge Lua is unchanged from v0.25.0; if that
version was already installed, no additional `/reload` is needed.

All offline GUI logic, decision, and telemetry tests still require **real
Windows GUI/live-WoW validation** before relying on unattended actions.

---

## Previous release notes

# PriestBot v0.25.0 — Attended Farmer Diagnostics (Live Validation Pending)

**Purpose:** assisted stationary farming in an open area while the owner
monitors the game. This is not autonomous navigation or an unattended leveler.
The v0.24.1 healing rotation and v0.24.0 compact telemetry are included.

## Export a test report to upload into PriestBot Chat 2

1. In the desktop app, select **Export diagnostic report (ZIP to upload into chat)**.
   The tests don't press keys, move the character, require a GPU, or need a
   running WoW client. The button also tries **one optional, read-only live
   optical sample** when PriestBridge is visible; failure to see it is marked
   `unavailable`, not a failed synthetic test.
2. Wait for the popup showing the complete ZIP path under
   `%LOCALAPPDATA%\PriestBot\diagnostic_reports`.
3. Upload that `.zip` here. It contains **report.md** (human-readable expected
   vs actual decisions) and **report.json** (all step observations/reasons),
   a minimal local configuration summary and decoder checks. No screenshot,
   chat, character name, keyboard log, or computer username is included.
4. Alternatively run from PowerShell without the GUI:

   ```powershell
   Push-Location "$env:LOCALAPPDATA\PriestBot"
   & "$env:LOCALAPPDATA\PriestBot\.venv\Scripts\python.exe" -m priestbot.diagnostics
   Pop-Location
   ```

   `--live` optionally requests a read-only visible PriestBridge sample.
   Diagnostics use installed runtime dependencies only, **not pytest**.

The included scenarios cover the 60% heal, pre-pull Shield/Renew, corrupted
normal/compact status bars, stale error counters, fleeing facing corrections,
LoS waiting/timeouts, and stopping on invalid sensor values. All results are
**synthetic regression evidence only**; real spells and real mob motion must
still be tested in WoW. The standard developer suite additionally uses pytest.

## Fleeing enemies and line of sight

**Stationary fleeing-mob tracking** is a separate checkbox, **OFF by default**
until you verify it in dry-run. With addon target-generation and fresh error
signals, it permits short, bounded **turn-in-place** corrections after a
facing error if the target is at or below 40% HP. It never guesses a target's
screen bearing. Turning right repeatedly may be slower than a real tracking
system but cannot make the bot walk into other mobs.

- On line-of-sight failure, stay planted and retry with a two-second interval.
  After eight seconds or three failed retries, clear and skip the target.
  **Never follow** a fleeing enemy around terrain.
- Turning is limited by the existing `turn_max_pulses` (10 by default), with
  explicit fresh game errors and delays between turn pulses. No free spinning.
- For a stationary farmer, leave **Experimental movement OFF**. Even if that
  box was previously on, stationary tracking takes priority when usable and
  disables forward movement on error recovery. Neither setting provides a
  world-space anchor, aggro-risk map, or verified mob-direction detector.
- When there is no reliable addon signal/target generation, retain legacy
  skip/stop behavior; do not infer the direction from a stale error tile.
- The F9 panic stop, rate limits, safety thresholds, and dry-run default remain.

**Suggested live validation:** open field, one fleeing mob, tracking checked
and real keys unchecked; inspect dry-run intent/reasons, verify `turn_right`
only on fresh facing errors, and verify no `move_forward` action during LoS.
Only then consider live-input trials while watching the character.

---

## Previous release notes

# PriestBot v0.24.1 — Priest Healing Rotation (Live Validation Pending)

This release tunes the **existing rule-based rotation** while preserving the
v0.24.0 compact telemetry mode, learning/data collection, and safety gates.

- **Heal / Lesser Heal:** cast when HP is **at or below 60%**, whether an enemy
  is selected or the Priest is between pulls. The old between-pull 74% shortcut
  is removed. Existing `config.json` files using the old default 45% value
  migrate to 60%; other deliberately tuned thresholds are preserved. A 3.2s
  fallback protects slow heal casts if the game's casting signal is missing.
- **Renew:** optional *between-pull-only* healing at **below 80% HP**, no more
  frequently than every 15 seconds, with at least 35% mana. It is never used
  at 90–100% HP and never inserted into the combat damage loop. The interval
  is a conservative time estimate, **not a verified Renew aura detector**.
- **Power Word: Shield:** if enabled, consider it immediately before the next
  pull (even at full HP), subject to the existing aura check, confirmed-cast
  estimate, retry and 15-second Weakened Soul protection. Pre-pull use now
  requires at least 50% mana to preserve resources for emergency healing.
- **Priority between pulls:** casted Heal under 60% → mana recovery → Renew if
  needed and enabled → Shield if needed and enabled → find next target. Buffs
  are not repeatedly cast during respawn waits or unsuccessful target searches.
- **New keybinding:** Renew defaults to `9` when available, with safe automatic
  selection of a free key for older custom configurations. Verify that the
  action-bar key self-casts before enabling the **Renew between pulls** checkbox.
  Renew remains OFF by default to avoid sending an unverified input.
- Casting in progress, F9 panic, foreground/dry-run protections, action-rate
  limits, and model advisory-only restrictions remain unchanged.

**Upgrade:** Permanent PriestBot desktop shortcut → **Update from ZIP** →
select the complete v0.24.1 ZIP → restart. Because this also includes the
v0.24.0 PriestBridge changes, install/repair the addon and `/reload` in-game.
Test the Heal/Renew/Shield decisions in **dry-run** before enabling real keys.
Actual WoW-client validation and the v0.23.2 binding test remain outstanding.

---

## Previous release notes

### v0.24.0 — Compact PriestBridge Telemetry

PriestBridge now has an optional **Compact Telemetry Mode**, designed to reduce
screen obstruction while preserving the native StatusBars required for restricted
combat health/power values and the existing optical action-semantics packets.

- `/pb compact`: a 350×48 UI-unit strip near the top-right of the game window.
- `/pb normal` (or `/pb full`): restore the original 270×102 panel in the
  original top-left position. Both modes keep all previous telemetry fields.
- Layout preference is saved in the addon's `PriestBridgeSettings` SavedVariables
  and restored after logging back in or reloading the UI.
- The Python bridge detects the compact-only marker automatically; there is no
  manual health-bar coordinate calibration. The old layout remains supported.
- **Not invisible:** the bars and packet tiles must remain unobscured and
  rendered on-screen. Hiding them or setting transparency to zero prevents
  optical decoding. The bars retain full 160-pixel fill resolution.
- Update from ZIP in the permanent app, install/repair the updated PriestBridge,
  then `/reload` in WoW. Test `/pb compact` and `/pb normal` with the app in
  dry-run mode before enabling any gameplay inputs.
- Synthetic Python and Lua mock tests cover layout and packet decoding; **live
  WoW-client behavior, UI scaling, and color fidelity have not yet been tested**.
  The pre-existing action-binding validation from v0.23.2 is still pending.

No combat decision, movement, looting, learning, or model-deployment behavior
was changed in this version.

---

## Previous release notes

### v0.23.3 — Windows Desktop Icon Cache Fix

- Uses a **new versioned Classic Priest icon filename** (`PriestBot.ClassicPriest.v2.ico`) under `%LOCALAPPDATA%\PriestBot`, avoiding stale Windows Explorer icon caching.
- Recreates the existing desktop shortcut and requests a shell icon refresh on successful updates or the **Recreate desktop shortcut** button.
- If the old image persists, check for duplicate shortcuts or taskbar pins. Refresh the desktop and, for pinned taskbar icons, unpin then pin the updated desktop shortcut again.
- This release changes no combat, telemetry, movement, recording, models, settings, or PriestBridge Lua code. No `/reload` needed.
- To update: permanent desktop PriestBot → **Update from ZIP** → choose this ZIP → restart. Verify the shortcut points to `%LOCALAPPDATA%\PriestBot\PriestBot.ClassicPriest.v2.ico,0` under Windows shortcut Properties → Shortcut → Change Icon.

---

# PriestBot v0.23.2 — Action Semantics Binding Reliability

**What changed:** PriestBridge now interleaves binding-catalog packets with gameplay events. Previously a continuous stream of spell/loot/target events could starve binding delivery for an entire recording, yielding `Resolved 0 bindings` and `Spell inputs: 0` despite confirmed spell casts. Action-bar bindings transmit first. This release also makes Lua binding enumeration safer when optional return values are nil, and adds `/pb bindings` diagnostics.

The desktop **Action Semantics** report now shows packet-type counts, declared bindings and binding packets received, plus a specific warning when zero bindings are resolved. The rule-based Priest rotation, movement, computer vision and learning/evaluation protections are unchanged. This upgrade does **not** retroactively invent labels for older demonstrations; existing recordings remain preserved for later analysis.

**How to update:** Use PriestBot desktop shortcut → Update from ZIP → select v0.23.2 → allow PriestBridge addon update, then `/reload` in WoW. Run `/pb bindings` outside combat and check `resolved` is above zero and `transmitted` increases. With WoW focused, record a new ~60-second demonstration: press two spell bindings and loot one corpse. Open Action Semantics to confirm resolved bindings and `B` packets. Open Farming Demonstrations and confirm `rotation_input` is now nonzero (subject to recorded bindings). If the catalog still reads zero, send `/pb bindings` output and new report packet-type counts.

**Testing:** Python regression suite and mock Lua frame tests; actual WoW client validation pending. The `R/B` optical packets remain read-only. `unknown`/`unmatched` means insufficient evidence, not a verified successful action. User recordings, settings and `.venv` remain untouched by the updater.

---

# PriestBot v0.23.1 — Classic Priest Desktop Icon + GitHub Source

- The permanent Windows desktop shortcut now uses the **Classic Priest class icon** (`classicon_priest`) instead of a generic Windows system icon.
- First-time installation creates the icon locally; installing via **Update from ZIP** also refreshes the existing shortcut automatically. **Recreate desktop shortcut** remains available in the app if Windows has cached the old icon.
- The `.ico` is generated from an embedded WoW Priest class icon resource. This avoids adding a new disallowed ZIP file path and keeps the release compatible with v0.23's strict updater.
- Existing combat, PriestBridge, learning data, settings and emergency-stop behavior are unchanged.
- **Repository hygiene:** `.gitignore` excludes local configurations, training screenshots, recordings, model candidates, virtual environments, logs, and backups. They are not required to run the application and should not be committed publicly.
- WoW icon asset is a Blizzard game asset; use is for local identification only, with no affiliation or endorsement implied.

**Upgrade:** Desktop PriestBot → Update from ZIP → select v0.23.1 → restart. No `/reload` needed because `PriestBridge.lua` is unchanged. If Windows still shows the old icon, right-click desktop and Refresh, then use the bot's **Recreate desktop shortcut** option.

---

# PriestBot v0.23.1 — Full Farming Demonstration Recording

**This version adds training-data collection, not a new autonomous looter or spell rotation.** The existing combat engine, user-selected keybinds, experimental walking, optical telemetry safety stop, and advisory-only model gate are unchanged.

## What's changed from v0.22.1

| Recording component | New evidence and output |
|---|---|
| Finding enemies | Tab/nearest-target key attempts, cursor and mouse gestures, camera scans from existing temporal intervals, game-only before/after frames |
| Selecting enemies | `PLAYER_TARGET_CHANGED` events with target generation, hostility and dead/alive status where readable; never claim a visual red rectangle is a confirmed mob |
| Spell rotations | The complete key/mouse timeline plus `UNIT_SPELLCAST_START`, `SUCCEEDED`, `FAILED`, `CHANNEL_START` when the client reports them; attempts remain separate from successful casts |
| Looting (highest priority) | Right-click/interact candidate coordinates and frames, `LOOT_OPENED`, `LOOT_READY`, `LOOT_SLOT_CLEARED`, `LOOT_CLOSED`; a loot-window opening alone is **not** credited as acquired loot |
| Combat phase | `PLAYER_REGEN_DISABLED` / `PLAYER_REGEN_ENABLED` when exposed; these do not independently prove a kill |
| Context and training examples | The nearest *previous* gameplay frame, the next valid gameplay frame, telemetry, input label, evidence source, phase, and uncertainty |
| Reporting | New **Farming demonstrations — targets / spells / loot** coverage and recent-evidence viewer |

Files created for each demonstration under `%LOCALAPPDATA%\PriestBot\learning_data\sessions\<session>`:

- `events.jsonl`: all game-only input events, video intervals, semantic confirmations, and new `farming_event` markers, time-stamped.
- `frames/*.jpg`: game-client-only screenshots (existing 800×450 recording at approximately 4 FPS).
- `farming_examples.jsonl`: training-ready *annotated observations* with `before_frame`, `after_frame`, `image_pair_complete`, and a defensible evidence status.
- `farming_report.json`: per-session coverage counts, recent events, potential missing examples, and observed loot-slot outcomes.
- `action_semantics.json` and `summary.json`: existing reports, preserved.

**Nothing learned from this new dataset can control the game yet.** Temporal vision training still uses simultaneous movement-control labels; combat/target/loot labels are collected for future separately evaluated multitask models. In particular, the current red-bar detector remains *unverified* and should not be used for automated enemy targeting.

## Upgrade from your permanent desktop shortcut

1. Close any running demonstration and stop PriestBot.
2. Launch PriestBot from the desktop shortcut → **Update from ZIP** → select the v0.23.1 ZIP (do not extract it first).
3. Allow **Install / repair PriestBridge** if Windows asks. PriestBridge is updated in `C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns` (your configured destination).
4. In WoW enter `/reload`. Keep the colored PriestBridge panel visible; select **Telemetry source: addon**.
5. Press **F6** to verify HP/mana/target and spell-signal telemetry.
6. Leave game inputs **off** and click **Start/stop demonstration**; play manually. This workflow does not need CUDA (PyTorch GPU may continue to report `False`).
7. Finish a 3–5 minute session, stop recording and open **Farming demonstrations — targets / spells / loot**.

## First recommended 3–5-minute demonstration

- **Find & select:** Starting with no target, look around with right-drag, left-drag, W, strafe, and Tab; choose different mobs. Include successful and abandoned selections. Avoid intentionally selecting other players.
- **Approach & face:** Show moving and turning simultaneously as you normally play. The old temporal movement intervals remain available, now with a `phase` field.
- **Spell rotation:** Cast Mind Blast → Shadow Word: Pain → wand on several mobs. Include healing/shield use when appropriate. Use your normal bindings and macros.
- **Loot:** Approach several corpses, right-click one, let the loot window open, loot items (including auto-loot if enabled), and close it. Also demonstrate at least one corpse that is too far away or already empty.
- **Review:** Inspect the counters for `target_selected`, `spell_success`, `loot_opened`, `loot_slot_cleared`, and `loot_closed`, and check evidence rows for plausible coordinates and frame links. The app will not fabricate a confirmed loot item based on a click alone.

## Limitations / what to watch out for

- The addon uses a **single shared optical packet strip** that rotates through event and binding data. Brief, busy interactions may cause events to arrive late or be missed. If a counter remains zero after real actions, report it with a short session log; don't assume the gameplay didn't happen.
- Target hostility and names are only supplied when the client allows them to be read. `unknown` is preferable to guessing. Target generation is modulo 16 and is **not** a persistent mob ID.
- `LOOT_SLOT_CLEARED` means a loot slot was cleared; it is not proof an item reached your bags. Auto-loot behavior varies by server/client. `LOOT_CLOSED` alone does not prove a successful loot.
- Native spell success events do **not** prove damage landed, nor does combat exit prove a kill.
- The recent click associated with `loot_opened` is only a **temporal candidate**. We will later review how reliably clicks correspond to loot windows, including camera turns.
- Screenshots, inputs and telemetry are captured only with WoW in the foreground during demonstrations; focus changes, chat entry and manual recording pauses break before/after pairs so outside-window activity is excluded.
- The v0.22.1 updater only accepts existing root files plus `.py` modules under `priestbot/` and tests. This release uses the same allowlist-compatible structure; **no new root-level installer file**.
- Models remain advisory-only and require held-out evaluation and explicit approval. Collect the data now; do not expect the new spell/loot dataset to improve an existing deployed model automatically.

## Existing instructions

---

# PriestBot v0.22.1 — Temporal Vision Learning Mode (legacy-updater compatible)

**Upgrade:** Use your permanent PriestBot shortcut → **Update from ZIP** → choose
`priest_foreground_bot_v0.22.1_updater_compatible.zip`. Existing `.venv`,
`config.json`, `learning_data`, keybindings and PriestBridge are preserved.
**PriestBridge is unchanged in v0.22; no WoW addon reload is needed.**

The **combat engine, addon telemetry, emergency stop, and manual movement
limits are unchanged**. All new vision models remain *offline candidates* and
**never send WoW keys or move the Priest**, regardless of holdout accuracy.

## What's new

- **Synchronized gameplay frames:** only while WoW is the foreground process,
  JPEG up to **800×450**, sampled about every **0.24 seconds** while demonstrating
  (~4 fps). Before/after frame paths and PriestBridge states are paired with
  mouse and keyboard actions. No browser or other monitor is captured.
- **Simultaneous inputs:** fractions of each frame interval spent strafing,
  running, turning, jumping, holding mouse buttons and using left/right mouse
  drags; horizontal/vertical mouse deltas. Camera-only LMB dragging and RMB
  character turning are represented independently; combos aren't collapsed
  into one movement class. Mouse movement may be missing if WoW locks its cursor.
- **Visual perception starter:** conservative **red hostile-nameplate candidate**
  boxes and screen-space track IDs, and before/after scene-shift estimates.
  These are unverified candidates, NOT general mob detection or obstacle
  avoidance. False positives are possible with red UI elements/spell effects.
  Use **Vision evaluation / coverage → Visual audit** to inspect detections.
- **Temporal vision candidate:** optional PyTorch CNN consuming **3 PRIOR RGB
  frames at 320×180** plus PriestBridge and preceding controls. It predicts independent
  binary movement/mouse controls plus drag magnitude. Training uses only human
  demonstrations, not automatic-bot actions. A separate *session* is held out.
- **Read-only visual evaluation:** exact simultaneous-control accuracy,
  per-control F1/recall, mouse-delta error, held-out-session data and observed
  scene/range/damage proxies. Outcome proxies are **not** proof of progress to
  a mob. No model deployment path is included.

## Do this first (the old v0.21 recordings are preserved)

1. Upgrade from ZIP and keep **Telemetry source = addon**. Press **F6** to check.
2. Open **Vision evaluation / coverage**; before new recordings the interval
   count will be zero. Previous v0.21 screenshots did not record synchronized
   simultaneous-control intervals; we do not fabricate them afterward.
3. Pause combat automation. Click **Start/stop demonstration**, focus WoW and
   record **3–5 minutes of normal approaching**, including W, Q/E strafing,
   left-drag camera looks, RMB turning, and simultaneous strafe + RMB dragging.
   Use the real bindings configured under **Demonstration keys**. Do not keep
   chat open or enter personal information while recording.
4. Stop and inspect **Vision evaluation / coverage → Data coverage & Visual
   audit**. Verify that red rectangles correspond to actual nameplates; ignore
   inaccurate candidate boxes. Inspect the simultaneous-control counts.
5. Record **another independent 3–5-minute session**, preferably in a different
   zone or camera position. The newest session is fully held out from training.
6. **Optional GPU setup (one time):** After v0.22.1 finishes installing, open
   PowerShell and run these commands (PyTorch is not bundled or installed by the
   normal ZIP updater):

   ```powershell
   & "$env:LOCALAPPDATA\PriestBot\.venv\Scripts\python.exe" -m pip install torch
   & "$env:LOCALAPPDATA\PriestBot\.venv\Scripts\python.exe" -c "import torch; print('CUDA available:', torch.cuda.is_available())"
   ```

   If CUDA is `False` and you want to use your NVIDIA GPU, select the appropriate
   **Windows / Pip / CUDA** command at https://pytorch.org/get-started/locally/.
   An appropriate CUDA build and NVIDIA driver are needed for GPU training;
   do not assume the default `pip install torch` will enable CUDA. PyTorch is
   optional and large; normal combat and recording work without it. Then click
   **Train temporal vision**, or leave **Auto-train candidates** enabled.
7. View **Vision evaluation / coverage → Independent evaluation**. Models never
   change combat or movement in v0.22. Any movement automation is still the
   previous rule-based engine. An offline score alone cannot approve new inputs.

**Data quality limitations:** raw OS mouse deltas can be distorted by cursor
re-centering, screenshots with chat are not anonymized, the old linear advisory
model is retained separately, and vision candidate tracking is not a calibrated
world-coordinate navigation system. This v0.22 foundation should be tested in
supervised game sessions before adding any learned navigation controller.

---

# PriestBot v0.21.0 — Action Semantics (read-only game-aware labeling)

This release extends the v0.20 learning and evaluation work. **Existing combat rules, Mind Blast → Pain → wand, recovery, modifier keybindings, movement and the advisory-only evaluation/deployment gate remain unchanged.** It adds optional *read-only* information from the WoW Addon API, sent through a small additional optical panel beside PriestBridge's existing health bars.

## Upgrade

1. Stop live automation and finish any active demonstration. Open PriestBot from your existing desktop shortcut → **Update from ZIP**. Select `priest_foreground_bot_v0.21_action_semantics.zip`.
2. Let the updater replace **both** Python and `PriestBridge.lua`. This release **requires the updated addon**; unlike v0.20, you must enter `/reload` in WoW. The addon remains under `C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\PriestBridge` using your saved path. Approve UAC if prompted.
3. Keep **Telemetry source = addon**. The old bars remain in the same positions; a small new colored pixel grid appears *to the right* of the existing PriestBridge bars. Keep the entire panel visible. `/pb show` if necessary.
4. Start a short demonstration in Learning Mode with WoW in the foreground. Press your food key `2` once, and (when appropriate) your bandage binding `Shift+G`. Stop the demonstration.
5. Click **Action semantics — bindings and confirmed uses** under Learning Mode. Review the **Bindings** and **Recent evidence** tabs. The report persists as `learning_data/sessions/<session>/action_semantics.json`; detailed events also go to `events.jsonl`.
6. Use a short 2–3 minute test before recording a long session. If the report says `0 optical packets`, check that you installed the **v0.21** PriestBridge Lua file, `/reload` succeeded, and the new grid is visible and unobstructed.

## What is automatically resolved

- `GetBinding()` enumerates key chords and commands, including `2`, `SHIFT-G`, `SHIFT-E`, when they are assigned. `GetActionInfo()` looks up slots on the standard and multiaction bars. `GetItemInfo` / `GetItemSpell`, spell APIs, and `GetMacroInfo` / `GetMacroItem` / `GetMacroSpell` provide a useful label for spells, items and macros **where these APIs are supported**.
- `UPDATE_BINDINGS`, `ACTIONBAR_SLOT_CHANGED`, `ACTIONBAR_PAGE_CHANGED`, `UPDATE_MACROS`, and item-info updates trigger a refreshed key/action snapshot. Refreshes are debounced and do not reset the data just because a cooldown updates.
- `UNIT_SPELLCAST_START`, `UNIT_SPELLCAST_CHANNEL_START`, `UNIT_SPELLCAST_SUCCEEDED`, `UNIT_SPELLCAST_FAILED` and interrupted casts provide attempted/started/confirmed/failed spell evidence, where available. The addon checks for **positive** readable Food/Drink/Recently Bandaged aura observations, never treating nil/secret aura results as proof of absence.
- Read-only `hooksecurefunc()` post-hooks may report action slot activations and bag item-use attempts if the client implements those entry points. **These do not prove the effect succeeded**. If the client doesn't expose them, semantic records simply remain unavailable/unknown.
- Python joins observed keyboard/mouse inputs to binding and game-event evidence. Mismatched cast events are *not* used as proof, macro conditions cannot be inferred from pressing a key, and unconfirmed attempts become **unknown** rather than false successes. A time-only association is marked `correlated_not_verified`.

## Important limitations

**A key's assigned action is not the same as a successful action.** For example, `2` might resolve to a named food item, but the report can only mark eating **confirmed** if the game emits matching positive aura/cast evidence. Depending on Forever's secret-value restrictions, eating/bandaging may remain unknown. `SHIFT-G` macros can have multiple conditional branches; simply pressing the macro never proves which branch executed. Actionbar/bag mouse-click hooking is best-effort; clicks elsewhere remain raw input events. The current visual protocol transmits a rotating binding catalog, so allow roughly 15–45 seconds after login or rebinding for all bindings to populate.

The extra optical grid uses error-checked packets, read from a fixed location relative to the already identified PriestBridge marker. It is **not** a server API, process-memory reader, network connection, or file writer from Lua. If packets are obscured, Action Semantics becomes unavailable but the original PriestBot telemetry still governs safety and automation. Screenshots, logs, and reports stay local to the permanent PriestBot installation. Recording still captures **only input while WoW is in the foreground**, and the conservative chat privacy guard remains; manually pause recording for other UI text fields.

Learning still trains only the existing movement-action classifier. Semantic labels are now recorded for later model work, but there is **no new learned combat policy, no learned input execution, and no bypass of the independent evaluation gate**.

## Suggested verification session

- Confirm `2` maps to the expected food item or food macro under **Bindings**.
- Press `2`, then inspect the timeline: `semantic_attempt` first; if readable `Food` aura or matching spell evidence appears, `semantic_outcome=confirmed`, otherwise it becomes `unknown` after eight seconds.
- Press `Shift+G`; verify its macro name and the attempt. A readable `Recently Bandaged` aura can confirm the effect; otherwise `unknown` is expected.
- Cast Mind Blast using its bound key and verify any matching `spell_succeeded` evidence. Change one actionbar slot out of combat and confirm the binding catalog eventually updates.
- View **Evaluation dashboard** / **Data coverage** as before. Nothing in this release automatically approves a model.

---

# PriestBot v0.20.0 — Learning Evaluation Dashboard & Data Coverage

This release extends v0.19.0; **combat rules, keybindings, telemetry, recording defaults, ZIP updater and manual advisory approval are unchanged**. It never allows a learned model to send game inputs. Existing `learning_data/` recordings and models are preserved by updates.

## Upgrade using your permanent desktop shortcut

1. Stop automation and close active demonstrations. Open PriestBot → **Update from ZIP** and select the complete `priest_foreground_bot_v0.20_learning_reports.zip`.
2. Allow the updater to restart the app. No addon update or `/reload` is needed (PriestBridge code is unchanged).
3. Click **Data coverage** to see exactly how many usable labeled movement examples you have for each action; the table shows how many are missing to reach the minimum (8) and recommended initial target (20).
4. Click **Evaluation dashboard** to see the evaluation gate, per-action precision/recall/F1 and representative correct/incorrect predictions on a *separate* holdout session.

### Your next demonstrations

- Your previous screenshot showed **2,025 raw input events, 61 saved correction labels and 50 training samples**, but **0 holdout samples**. Raw inputs are not ground-truth training examples; rarer action labels were excluded until they have 8 examples.
- Click **Data coverage** first and pick **two or three movement actions** with few examples, especially RMB turns and W+RMB turn combinations. Try to capture **20+ useful examples of each** from varied angles and distances, not just minutes of routine fighting.
- Make a **new, separately saved 5–10 minute session** containing at least **12 labeled examples of actions already present in your earlier training sessions**. Those are needed for a meaningful independent holdout. The latest session is held out if it meets all split checks.
- Stop the demonstration; auto-training runs if enabled. Otherwise click **Train candidate now**, then **Evaluation dashboard**. The Overview tab explicitly shows pass/fail conditions. The Per-action tab shows weak action classes. The Examples tab displays selected correctly and incorrectly predicted screenshots (new v0.20 candidates only). The Coverage tab recommends what to demonstrate next.
- Older v0.19 candidate reports remain readable, but **prediction examples and detailed split checks appear only after retraining** from your existing recordings in v0.20. You don't need to delete or re-record the old data.

### Evaluation gate (unchanged)

Evaluation must use a separate session with ≥12 holdout samples, ≥24 training samples and no classes in holdout absent from training. A candidate qualifies only if it has **accuracy ≥65% and ≥majority-class baseline +5 percentage points, macro-F1 ≥0.60 and recall ≥0.40 for each evaluated action**. All checks must pass. A passing model still requires explicit **Approve advisory**, and advisory models only generate suggestions; they never issue inputs or replace the existing combat or movement rules.

**Important:** An offline holdout measures imitation classification, not whether navigation is safe or improves XP/hour. Don't approve a candidate solely because one metric looks good. Inspect the most-confused classes and the screenshots, and keep using supervised live testing before contemplating a future movement controller.

---

# PriestBot v0.19.0 — Full gameplay input demonstrations

This release broadens v0.18's opt-in Learning Mode to **record all observed keyboard and standard mouse activity while WoW is the foreground game**, rather than only RMB turning and three movement keys. It preserves the v0.16+ combat rules, PriestBridge, existing permanent desktop shortcut/ZIP updater, dry-run defaults, and evaluation-gated advisory-only learning.

## Upgrade

1. Stop the combat bot and any demonstration, open PriestBot from your desktop shortcut and click **Update from ZIP**. Select the v0.19 ZIP.
2. Your `.venv`, `config.json`, spell bindings, existing learning sessions, candidate models and WoW addon installation path remain unchanged. **PriestBridge.lua is unchanged**, so no WoW `/reload` is needed if the addon is already working.
3. In **Learning Mode**, enable **Record manual movement corrections**, **Record all game-focused gameplay keys**, and **Record mouse clicks, drags and wheel** (defaults ON). Use **Demonstration keys** to match movement actions to your actual WoW bindings. Custom Q/E spell bindings should *not* be misidentified as strafing: change the demonstration bindings to match your layout.
4. Pause the combat bot, click **Start/stop demonstration**, then focus WoW and play naturally. Stop when finished. Candidate training still runs automatically, but deployment still requires separate-session evaluation and explicit approval; **no trained model controls gameplay**.

## Captured input and meaning

| Event | Stored | Trainable label? |
|---|---|---|
| W, S, configured movement/strafe/turn/jump/auto-run keys | Key down/up, hold duration, concurrent keys | Yes, for individually configured actions without ambiguous overlap |
| Spells, targeting, interacting, macros, Shift/Ctrl/Alt combinations | Key down/up, modifiers, chords; synchronized game screenshots/telemetry | Raw input only, until an action meaning is established |
| LMB dragging | Client-area positions, direction, duration and before/after frames | Tentative `camera_look_*` (not a character-facing command) |
| RMB dragging | Direction/distance, duration, simultaneous W | `mouse_turn_*`, `move_forward_mouse_turn_*` |
| Holding LMB and RMB together | Button state and timing, direction if visible | `mouse_both_forward`, or `mouse_both_forward_turn_*` |
| Normal left/right clicks, middle and side mouse buttons | Down/up times, client-relative coordinates and click/drag summary | Raw input only (could be target, loot, interact, UI drag or a bound ability) |
| Scrolling mouse wheel, including horizontal scroll | Wheel amounts, modifiers and mouse position | Raw input only (wheel may be zoom or rebound) |
| Hovering/moving cursor without buttons | Sampled game-only mouse positions | Raw input only (no inferred action) |

All raw events go into `learning_data/sessions/<session>/events.jsonl` as `event=input` with subtypes such as `key_down`, `mouse_down`, `mouse_drag_delta`, `cursor_move` and `scroll`. These are **input observations**, not proof that an in-game action succeeded. Confirmed game events are still recorded separately from PriestBridge. A `correction` record contains an advisory-model label and its before-frame; when captured, the next game frame becomes `frame_after`. Clicks and spell keys are deliberately *not* automatically turned into movement labels. The baseline trainer excludes classes with fewer than eight samples so rare interactions do not block unrelated movement training.

## Privacy and limitations

- Input listeners are active for demonstration events **only after you manually start a demonstration**. Each callback checks WoW is the foreground process, mouse positions must be within the WoW client rectangle, and focus loss cancels in-progress gestures. No browser/VS Code input or screenshots are recorded.
- **Chat privacy:** pressing Enter or `/` engages a conservative keyboard logging pause until Enter/Escape. The chat text itself is not written to the event log. For other game UI text fields (search boxes, whispers opened by other shortcuts, login dialogs), use **Pause / resume input logging** first. Do not record credentials or other private text. This is a precaution, not a comprehensive detection of all WoW text fields.
- **Windows OS cursor deltas are not guaranteed to equal WoW's raw relative mouse movement** when the game locks/recenters the pointer. If right/left turns yield zero or erratic deltas, this release cannot reconstruct accurate camera angles; do not train on them. Native Windows Raw Input capture would be a separate future feature.
- LMB drags over inventory/action bars can also be UI manipulation, not camera movement. LMB camera labels are **heuristic**, carry `ui_interaction_unverified=true`, and must be reviewed before trusting any learned camera advice.
- This records keyboard and ordinary mouse input, **not controller/XInput gamepads, hardware macro internals, or game-client hidden input streams**. It does not prove what spell a bound key represents without corroborating addon events.
- Screenshots can contain character names, chats and UI. Recordings stay local; delete unwanted sessions via **Open learning data**. Only keep recording while playing the private server where automation is permitted.

## Test focus

Test in manual demonstration mode with game foreground: LMB camera turn; RMB turn; holding both mouse buttons for forward; W+RMB; Shift+E; clicking/looting; mouse wheel; Enter-to-chat privacy pause; and switching focus to Codex. Confirm the saved `events.jsonl` contains appropriate inputs and no off-game events before collecting a large dataset. Lua add-on changes are not required.

---

# PriestBot v0.18.0 — Right-mouse turns in Learning Mode

**New:** Training demonstrations now capture RMB camera/character turning while WoW is foreground, including **W + RMB dragging** as a *combined* action rather than incorrectly labeling the move as W-only. This extends the v0.17 manual recording/CPU imitation model and does not change the existing Priest combat logic or add autonomous mouse control.

## Upgrade without reinstalling

1. Stop farming and end any ongoing demonstration session.
2. Open PriestBot from your existing desktop shortcut, click **Update from ZIP**, and select the v0.18 ZIP.
3. The updater preserves `config.json`, `.venv`, spell keybinds, the permanent desktop shortcut, all existing session recordings and models in `learning_data/`. The PriestBridge Lua addon is **unchanged**; no `/reload` is needed if already working.
4. In Learning Mode, enable **Record manual movement corrections** and **Record RMB mouse turns + W combinations** (both ON by default). Gameplay recording and candidate auto-training stay ON by default too.

## Record your natural movement

1. **Stop the combat bot**, then choose **Start/stop demonstration**.
2. Click into WoW. Hold **right mouse button and drag left or right** to turn; alternatively hold **W + RMB** and drag to run while turning. Release RMB after each turn. A quick RMB click without moving does not become a training label.
3. Continue recording until you have plenty of varied examples of turns and approaches, then stop the demonstration. The log reports total labels and `mouse turns` recorded.
4. For each usable RMB drag, the JSONL event stores the action (`mouse_turn_left`, `mouse_turn_right`, `move_forward_mouse_turn_left`, `move_forward_mouse_turn_right`), total `mouse_dx`, `mouse_dy`, pointer travel, length of drag, concurrently held movement keys, the scene **before** the drag and, if another frame was captured afterward, the scene **after**. Recordings are screenshots of the WoW client area and do not include other desktop windows.
5. Auto-training can now learn those **four new action categories**, alongside existing keyboard-only movement. The candidate report also lists typical displacement/duration for each mouse category as descriptive medians. The model **does not yet predict a continuous turn angle or directly control the mouse**.

## Important limits and troubleshooting

- **The RMB recorder listens only during a manually started demonstration, and accepts mouse motion only while WoW itself is the foreground program.** It discards an in-progress mouse drag when you switch to the browser or VS Code. It doesn't record other apps or ordinary mouse movement without RMB.
- Mouse movement is captured through Windows OS pointer events using `pynput`, **not through WoW's raw DirectInput/Raw Input stream**. Some WoW client configurations lock or recenter the cursor and expose no useful pointer deltas. If you make several visible turns but see `0 mouse turns` in the saved-session log, the OS isn't exposing motion; do not train on that missing data. That case requires a different raw-input capture approach, not tuning arbitrary model parameters.
- Pointer warps larger than 600 pixels per event, very tiny drags (under 12 net horizontal pixels), and abandoned/incomplete drags are rejected to avoid noisy training labels. Vertical-only turns aren't labeled yet.
- Samples use one snapshot shortly before the drag and, when available, one shortly after. Game orientation is **inferred from image differences, not measured as a ground-truth heading**. Avoid interpreting the number of pointer pixels as degrees rotated.
- Keep collecting examples across multiple independent sessions. Model training is still CPU-based and **candidate-only**; a held-out session evaluation and explicit approval are required even for read-only advice. Auto-training never deploys a model or changes PriestBot's movement/combat inputs.
- F9 emergency stop, dry-run-by-default, existing combat rules, foreground/background input modes, and telemetry safety gates are unchanged.

---

# PriestBot v0.17.0 — Learning Mode (local supervision + guarded evaluation)

**First release of learning infrastructure, not an autonomous self-improving navigation agent.** It preserves v0.16 targeting, movement limits, Mind Blast → Pain → wand, optional background PostMessage input, PriestBridge, and F9 stop. Trained models **do not replace the rule engine** and cannot control WoW in v0.17.

## Upgrade

1. Launch PriestBot using your existing permanent desktop shortcut. Stop the farming bot and any demonstration recording.
2. Click **Update from ZIP...** and choose the v0.17 release. Your existing `config.json`, `.venv`, spell keys, and desktop shortcut are retained. Your `learning_data` directory is also left untouched by subsequent ZIP upgrades.
3. PriestBridge is unchanged; no `/reload` is needed unless the installer reports it updated your AddOns folder.
4. The new **Learning Mode** section defaults to the requested toggles: gameplay recording ON, manual corrections ON, auto candidate training ON. All three are editable and saved. Existing live/dry-run protections remain unchanged.

## Record a supervised gameplay session

- Keep **Record game telemetry/screenshots** checked. Start PriestBot normally (dry-run first) and it automatically writes a timestamped session to `%LOCALAPPDATA%\PriestBot\learning_data\sessions\` if installed permanently.
- Each session contains `events.jsonl` (observations, bot decisions, reasons, cast/range/error signals), `summary.json` (counts and error totals), and compressed `frames/*.jpg` when WoW itself is the foreground application. The recorder samples **only the game client area** after verifying the foreground process is an allowed WoW executable. It never records the browser or Codex on another monitor. **While WoW is unfocused, numeric telemetry is recorded but screenshot recording pauses**; game must also be visible for PriestBridge.
- Screenshots may contain names, chat, and other game UI elements. The files stay local; no network uploads. You control retention: use **Open learning data** and delete sessions you don't want. Frequent recordings consume disk space; review the directory periodically.

## Teach it manually (imitation learning)

1. **Pause the combat bot**. Click **Demonstration keys** and match the movement keys to your actual WoW bindings. Defaults are `W` forward, `Left Arrow` turn left and `Right Arrow` turn right; the bot's own right-turn action binding is separate. Mouse turning is **not labeled** in this release.
2. Click **Start/stop demonstration** to start. Click back into WoW. Walk/turn to approach targets as you normally would, and correct mistakes; the app captures telemetry and small screenshots during gameplay and labels only the allowed movement keys while **WoW has focus**.
3. Click **Start/stop demonstration** again to stop and save. **Only manual correction key holds** become supervised training labels. Automated movement, attack decisions, and spell attempts are never treated as ground-truth demonstrations.
4. Create multiple sessions with varied terrain, lighting, mobs and camera positions. The first candidate needs at least **36 labeled key holds**, at least **8 of each learned action**, and at least **two distinct movement actions**. Try collecting 100+ examples across two or more sessions. Auto candidate training runs when a session ends; **Train candidate now** can also run it on demand.

## Evaluation and activation gate

- Candidates are small local CPU-trained image+telemetry **multiclass linear classifiers** (NumPy; no external service, no GPU or cloud dependency). This v0.17 baseline is intentionally inexpensive; it is not PPO, RL, world-model learning, or unsupervised learning.
- A candidate is evaluated only on **an entirely separate recording session** containing at least 12 labeled samples, with at least 24 training examples and classes represented. It must beat a majority-class baseline by at least five percentage points (and hit ≥65% accuracy), have macro-F1 ≥0.60, and ≥0.40 recall for each class appearing in the holdout. Training-set performance alone never qualifies.
- Click **View latest evaluation** for train/holdout size, per-class recall, accuracy, confusion matrix and eligibility. **Auto-training never activates a model**. Click **Approve advisory** and explicitly confirm *only if* it passes. Approved models emit occasional `ADVISORY ONLY: turn_left ...` log messages; **they never issue keyboard commands or alter combat decisions**.
- This evaluation measures imitation accuracy, **not actual XP/hour, collision avoidance, pathfinding, survival, or RL performance**. A later movement-controller release should require separate supervised in-game A/B tests before learned actions are enabled.

## Safety and troubleshooting

- All sessions start DRY RUN by default, and movement remains opt-in, bounded by the v0.16 limits. F9 still stops controls. A telemetry failure still pauses/halts keys according to the v0.14 guard.
- Capturing manual demonstrations requires working PriestBridge and WoW in the foreground. Because training uses screenshots, the bot must not be covered by other windows during demonstrations. If there aren't enough corrections, auto-training will log `Training skipped: Need ...`; no model is promoted.
- When the application closes during a demonstration, pending key holds are discarded; finish recordings using **Start/stop demonstration** so the session and auto-training complete cleanly.
- Models and sessions are local only. `learning_data/` is excluded from release ZIPs and retained by the updater. To reset learned advice, remove `learning_data/active_advisory.json` with the bot stopped; this does not erase recordings.

---

# PriestBot v0.16.0 — experimental walking and facing recovery

**This is a supervised, opt-in movement experiment for your permitted private server.** It retains v0.15 foreground/background modes, existing spell rotation, PriestBridge telemetry, ZIP updater, saved `.venv` and settings, and F9 panic stop.

### Upgrade through the existing desktop shortcut

1. Stop the bot, open **Update from ZIP**, and select the v0.16 ZIP. The existing `.venv`, `config.json`, spell assignments, WoW installation path and desktop shortcut are preserved.
2. The **PriestBridge addon changed** to recognize facing errors. Approve the AddOns update if prompted. In WoW run `/reload`. Type `/pb test facing`, then F6 to verify `spell_error=facing` and a changing event counter. Test a real wrong-facing Smite/Mind Blast if the private client permits it.
3. In **Configure spell keys**, set **Walk forward** to your real *Move Forward* key (normally `w`), and **Turn right** to your *Turn Right* key (normally right arrow). Set **Telemetry source = addon** and use **foreground input** for the initial walking tests. **Background movement has not been validated** and depends on whether your particular game client accepts held `PostMessage` keys.
4. Check **Experimental movement**; this feature is intentionally **OFF by default**. First test in **dry-run**: deliberately target a mob outside Mind Blast range and verify `WOULD move_forward`. For wrong facing, verify `WOULD turn_right`. Then supervise **one** real mob in live mode in a clear, safe area, with F9 ready.

### Behavior

- **New range error after an attempted spell** → hold the forward key for **0.45 seconds**, release, then probe with the normal attack. Maximum **six** forward steps per target (about 2.7 seconds of movement). If still out of range, **clear the target**. Do not assume movement succeeded from a sent key.
- **New facing error** → turn right **0.22 seconds**, release, retry casting. Maximum **ten** turning pulses per target. It is a bounded search, **not** directional navigation. Exact facing is unknown until the spell succeeds.
- **Line of sight blocked** → clear target; does **not** walk around obstacles or pathfind.
- **Low HP** → prioritize healing, not moving forward. Target changes, target death, the movement limits, telemetry loss, lost foreground focus, cancelled input or F9 all prevent further movement.
- Motion happens **only** on newly detected PriestBridge range/facing error events and only while an enemy target is alive. It does not chase after Tab targeting without a range error, blindly follow players, or navigate to spawn locations.

### Configuration (optional, edit `%LOCALAPPDATA%\PriestBot\config.json` with bot stopped)

```json
{
  "enable_movement": false,
  "approach_pulse_s": 0.45,
  "approach_max_pulses": 6,
  "turn_pulse_s": 0.22,
  "turn_max_pulses": 10,
  "movement_probe_delay_s": 0.25
}
```

These fields are examples, **not** the whole `config.json`. Existing values remain on upgrade. Keys are edited in the app, not in this snippet. Movement-key holds have a hard safety limit of 0.05–1.5 seconds each.

**Limitation:** Tab doesn't reveal the mob's actual bearing. If you are facing away from an out-of-range mob, short W steps can move you *farther away*. The bot stops after its limit rather than running indefinitely. Full reliable approach-and-face requires a directional source (e.g., trained nameplate/scene analysis or a permitted private-server telemetry extension). Avoid cliffs, water, other mobs, PvP zones and dangerous terrain for this first test. The addon and Python logic are not yet proven in-game for walking or facing.

---

# PriestBot v0.15.0 — optional background window input (private-server test build)

**New feature:** If WoW remains **visible and not minimized** on your main monitor, PriestBot can *attempt* to cast/target while you click VS Code or a browser on the second monitor. This is an experimental alternative to foreground-only `pydirectinput`.

### Upgrade using your permanent desktop shortcut

1. Pause the current bot. Open **PriestBot → Update from ZIP**, select this v0.15 ZIP, let the bot restart. It keeps `.venv`, `config.json`, spell bindings, and your existing PriestBridge addon. **No `/reload` needed** because Lua is unchanged.
2. Leave **Telemetry source = addon**. Set **Input method = background**. Save.
3. In WoW, keep the game in **windowed/borderless mode and fully visible** on the main monitor. Do not minimize it. PriestBridge must still be visible.
4. **Before live farming:** Click **Test background Tab (5s)** in PriestBot, immediately click your browser or VS Code on your second monitor, and watch the WoW target selection. The test posts **one** configured next-target key to the pinned WoW window after five seconds. If the target changes while the browser remains focused, this particular client has accepted the background key message. A log saying 'queued' alone is *not proof*.
5. If Tab works, enable live keys **only for a short supervised test**. F9 emergency-stops from either monitor. If Tab fails, switch **Input method = foreground**; background mode is not compatible with the client as currently configured.

### How the background mode works

- It uses the Win32 `PostMessageW` API with a **verified game HWND and process ID** and posts WM_KEYDOWN/WM_KEYUP messages, including Shift/Control/Alt combinations (e.g., `shift+e` for Shield). It does *not* use globally injected keys, automatically refocus WoW, modify the game client, or call private-server APIs.
- The existing PriestBridge → screen telemetry and v0.14 short-loss recovery remain in place. Because WoW stays visible, full-desktop `mss` capture can continue reading the marker while another monitor has focus. It will still fail closed if the game is obscured, hidden, minimized or telemetry is unreadable.
- Every action is logged as `POST ...` rather than `DO ...` because **successful Windows message posting is not confirmation the game executed it**. Successful spell telemetry is separate.
- It refuses ambiguous multiple WoW windows unless the intended one is currently focused when you start; binds to one window and rechecks HWND, PID and process name before commands. If the window changes/closes/minimizes, it stops rather than redirecting input.
- `foreground` remains the default for existing configurations. `background` requires addon telemetry and an operating F9 hotkey listener. Both input modes start in **dry-run** until you explicitly enable live keys for that session.
- Limitations: some WoW clients read keyboard state through DirectInput/Raw Input and ignore posted window messages when unfocused. It cannot be made reliable by changing `PostMessageW` alone. We have **not tested actual Win32 delivery inside your Forever client**; only simulations and code tests run here. Background rendering may also stop if the game is minimized or loses rendering while unfocused.

### Troubleshooting

- **`No visible WoW window found`**: keep the game window visible and not minimized; check the allowed `.exe` names.
- **`Multiple WoW windows`**: focus the intended WoW client and press F8 from inside it to select that instance.
- **`Window unavailable`**: reopen WoW and restart farming. The bot does not silently bind to a different process.
- **`Background Tab queued` but no target change**: verify Tab is actually bound to Target Nearest Enemy, targetable mobs are nearby, and retry with an unfocused browser. If still no action, your client probably ignores window messages while unfocused; use foreground mode.
- **Telemetry lost while using the browser**: ensure your second-monitor window does not cover the PriestBridge panel on the main monitor. The v0.14 failsafe still applies.

---

# PriestBot v0.14.0 — temporary telemetry recovery (Nov 5, 2026)

This update addresses a reported **live-input stop** shortly after a heal command:
`STOPPED: addon telemetry invalid: Found colored pixels but no valid PriestBridge marker.`
That error means **one screenshot could not be decoded**, not necessarily that the Lua addon failed or disappeared. The report by itself cannot establish whether a spell overlay, UI scaling, occlusion, or another transient render issue caused the failed screenshot.

### What changed

- **Marker search:** inspects every plausible magenta marker run, not every Nth magenta pixel. Large magenta spell effects can no longer cause the search to skip the real marker simply because the screenshot contains many magenta pixels.
- **Fail-closed short recovery:** at the *first* invalid addon frame, the program immediately **stops sending game inputs**. It tries capturing fresh frames; if two consecutive clean readings arrive within about **1.5 seconds**, it resumes and logs that recovery. Otherwise it stops, logs the last telemetry failure, and sounds an alarm. It never uses old HP, mana, or target values to choose new actions during the outage.
- This is deliberately conservative. It **does not** try to heal blindly or switch to manual screenshot telemetry during the outage. F9 emergency stop still works.
- Configuration fields (`config.json`), optional: `telemetry_grace_s` (default `1.5`) and `telemetry_recovery_frames` (default `2`). Do not increase the grace period for unattended play: longer delays mean longer periods without reliable health monitoring.
- PriestBridge addon Lua and spell rotation are unchanged from v0.13. The fix is in the Python application.

### Install and test

1. Pause PriestBot, click **Update from ZIP**, and select this v0.14 ZIP. Your permanent shortcut, virtual environment, settings and keybindings are preserved.
2. No `/reload` should be required because the addon code is unchanged.
3. With WoW visible, press F6 to verify telemetry. Run in **dry-run** first, then try one mob supervised in live mode.
4. If you see `Telemetry lost...` followed by `Telemetry restored...`, the transient recovery worked. If it remains invalid past the recovery window, expect `STOPPED: addon telemetry ...` and an alert; investigate whether the panel is obscured, WoW is in exclusive fullscreen, UI is hidden, or another window is covering it. The bot deliberately won't continue blind.

**Validation:** 439 Python tests passed, 2 graphical tests skipped, including a new test with bright-magenta noise and tests for consecutive recovery frames, timeouts and invalid markers. This change still requires live-client validation.

---

# PriestBot v0.13.0 — single-start wand, healing retry guard (Nov 5, 2026)

This release addresses a LIVE INPUT issue reported after four mobs: the bot logged two Shoot inputs on every pull (an immediate attempt during Pain's GCD, then an unconditional retry ~1.6 seconds later). Some wand macros can re-trigger or delay the first wand swing when pressed repeatedly. The bot now sends exactly **one Shoot keypress after the estimated Pain global cooldown**; it does not blindly issue a second press. This is a deliberate change from the v0.12 "immediate attempt + retry" behavior. It does **not** add extra waiting beyond the GCD (which already limits when Shoot can successfully start).

**Recommended wand macro** (bind this to the key configured for Wand):

```text
#showtooltip Shoot
/cast !Shoot
```

Avoid the user's former two-step `/castsequence reset=2 !Shoot, !Shoot` macro; we no longer need its cast-sequence state. If the simple macro behaves unexpectedly on your private client, try binding the Shoot spell directly and report the result.

**Other change:** between-mob healing attempts have a 4-second minimum spacing instead of spamming Heal every 1.7 seconds while HP is still below 74%. The bot still monitors health continuously and uses its existing in-combat healing logic. The extra interval is configurable as `between_heal_retry_s` in `config.json`.

### Update your permanent installation

1. Pause PriestBot and use **Update from ZIP** in your desktop application; select this v0.13 ZIP without extracting it.
2. The updater keeps your `.venv`, config, assigned spell keys, and permanent shortcut. PriestBridge is unchanged from v0.12; WoW `/reload` is only needed if the updater reports an addon change.
3. Replace the in-game wand macro with the simple `/cast !Shoot` version above. Ensure the bot's **Wand** keybind points to that slot.
4. Test one mob in dry-run, then one mob supervised in LIVE INPUT. Look for exactly **one** `DO wand - Starting wand once after Pain GCD` after each Pain. If no wand shot actually starts, disable live input and share the log, rather than letting it repeat indefinitely.

**Testing:** 433 Python automated tests passed, 2 display-dependent tests skipped. The Python+Lua client integration for this change has not yet been verified in-game. The addon and the targeting, buff, and error logic are otherwise unchanged.

---

# PriestBot v0.12.0 — reliable Pain aura fallback (Nov 5, 2026)

This release fixes repeated `WOULD pain` decisions when Shadow Word: Pain is visibly on the target but `/pb auras` reports `pain=absent`.

**Why it happened:** In modern combat-restricted WoW clients, `AuraUtil.FindAuraByName` can return `nil` even for an active aura. v0.11.2 treated `nil` as `absent`, causing the bot to retry Pain every ~2.6 seconds despite confirmed cast events.

**What changed:**
- PriestBridge now reports `unknown` when its name-based aura lookup returns `nil`. After a recognized successful Pain or Shield cast, it reports `estimated` while the respective timer is active; it does not claim to have verified the aura.
- Python honors a **confirmed Pain cast** for its configured approximate 18-second duration even if an older addon sends a misleading `absent` status. The timer resets on target change and does not imply the debuff cannot be resisted, dispelled, or fall off early.
- Shield keeps the existing early-absorption/Weakened Soul behavior for explicit `absent` readings from older addons. With the updated addon, restricted lookups instead produce `unknown`/`estimated`.
- New installations default to **Telemetry source: addon**. Existing saved selections remain intact.
- All keybindings, Mind Blast → Pain → wand rotation, windowed foreground control, updater and permanent shortcut remain as before.

## Update through your existing v0.11.2 desktop installation

1. Close or pause the bot. Click **Update from ZIP** and choose this release ZIP, without extracting it.
2. Allow the updater to install the new PriestBridge addon into the saved WoW AddOns folder, and then type `/reload` in WoW.
3. Cast Shadow Word: Pain on a fresh target **manually**, and while it is active, enter `/pb auras`. Expect `pain=estimated` (or `present` if your client returns readable aura data). `unknown` after the estimate expires is normal; `absent` from the new addon indicates the old file may still be installed.
4. Press F6 in PriestBot with WoW visible. In **dry-run** mode, verify `last_success=pain` and a changing success counter when you apply the spell. After confirmation, you should no longer see `WOULD pain` every 2–3 seconds on that same target. It may attempt again near the estimated 18-second expiration.
5. Keep dry-run enabled for the first test. This package has automated and simulated verification, **not a live-game validation**.

**Limitations:** The timer is an estimate, not a guaranteed aura reading. Target switches reset Pain tracking. A cast-success event may be missed, and repeated events can wrap a 4-bit counter; the existing retry and combat-stall safeguards still apply. False positives from casts onto unrelated units remain possible. No navigation or looting has been added.

---

# v0.11.2 – Telemetry counter parsing fix

This release makes v0.8 telemetry counter decoding more robust against mild render scaling and adjacent-pixel contamination. It samples an interior 3–7 pixel-wide patch rather than a single pixel for each success/target bit; it still stops safely if the colors are invalid. When it stops, the log now names the counter, bit, screen coordinate, RGB value and scale. The addon protocol is unchanged, so `/reload` is not required if v0.11.1 PriestBridge is already working. Install through **Update from ZIP**. If it still fails, press F6 while WoW is visible and share the exact new error, which will identify the bad bit.

## v0.11.1 hotfix: PriestBridge startup syntax error

Fixes the Lua parser error `line 175: end expected near return` that prevented the addon from loading in v0.11.0. No changes to spell rotations or keybinds. Use **Update from ZIP** in PriestBot, then **/reload** in WoW. If addon replacement requires administrator permission, approve UAC.

## v0.11: Modifier keybindings

The **Configure spell keys** window now accepts single keys (`e`, `3`, `tab`) and modifier combinations (`shift+e`, `ctrl+1`, `alt+q`, `ctrl+shift+r`). You can also type `shift - e`; the app normalizes it to `shift+e`. The configured binding must match the in-game spell or macro binding exactly. For example, bind Power Word: Shield to Shift+E in WoW, then enter `shift+e` for Shield in PriestBot. Every action sends a single keypress with modifiers held just for that action; no key is left held down. F6–F9 (with or without modifiers) and dangerous operating-system shortcuts are reserved. Test in DRY RUN, then with live input while observing your Priest.

**Upgrade:** Launch your existing desktop shortcut, choose **Update from ZIP**, and select `priest_foreground_bot_v0.11_modifier_keys.zip` without extracting it. Your `.venv`, configuration, keys, and shortcut are preserved. The ZIP includes a version-labeled PriestBridge, but its Lua behavior is unchanged, so there is no new addon calibration requirement. If the updater replaces it, use `/reload` inside WoW.

**Example:** In WoW, set Power Word: Shield (or its self-cast macro) to Shift+E. In PriestBot, click **Configure spell keys** and enter `shift+e` for **Power Word: Shield**. Save. In dry-run mode, confirm the action log; then test the new binding in one supervised live fight.

# PriestBot v0.10 — Mind Blast opener + fast wand rotation

**New rotation profile:** `mind_blast_wand` opens **each new target** with Mind Blast, then casts Shadow Word: Pain on the next scan after Mind Blast completes, then starts wanding on the next scan. There is **no arbitrary 1.7-second delay** inserted between these spells. The bot still respects actual cast-state telemetry and the game's global cooldown. Its `!Shoot` retry is scheduled approximately 1.6 seconds after Pain because Shoot can be ignored during GCD.

Mind Blast is a 1.5-second cast with an 8-second base cooldown in WoW Forever. The bot tracks successful Mind Blast casts and **waits for its cooldown before opening another target** (you can adjust `mind_blast_cooldown_s` in `config.json` if you have Improved Mind Blast). If mana is too low, it skips Mind Blast and falls through to Pain/wand instead. Healing and Shield, when enabled, have survival priority.

## Update your permanent v0.9 installation (no setup or batch files)

1. Download the new `priest_foreground_bot_v0.10_mind_blast_opener.zip` without extracting it.
2. Open PriestBot with the **existing desktop shortcut**, make sure it is paused, and select **Update from ZIP...**.
3. Select the v0.10 ZIP. The updater preserves `.venv`, your config/keybindings, and the desktop shortcut. It can replace `PriestBridge` in your configured Forever AddOns folder (Windows might request administrator approval).
4. Restart / reload WoW with `/reload` after the addon is replaced.
5. Open the updated bot: set **Main damage spell** to **`mind_blast_wand`** and leave **Shadow Word: Pain** enabled. Open **Configure spell keys** and confirm the Mind Blast, Pain and wand keys.
6. With the bot paused, test `/pb test mindblast` in WoW, then **F6** in the app: `last_success=mind_blast` should appear. Then test a **real Mind Blast** for an incremented `success_seq` before enabling live inputs.

**Default keybinds:** Mind Blast `8`, Pain `3`, Shoot / wand `7`, heal `2`, Shield `1` (all configurable). An older custom binding already using `8` is preserved; the upgrade assigns an unused default to Mind Blast instead. You do **not** need to replace Smite's existing binding.

### Recommended in-game macros

Mind Blast (assign to your configured Mind Blast key):

```text
#showtooltip Mind Blast
/cast [harm,nodead] Mind Blast
```

Pain:

```text
#showtooltip Shadow Word: Pain
/cast [harm,nodead] Shadow Word: Pain
```

Wand (important: use `!Shoot`):

```text
#showtooltip Shoot
/cast !Shoot
```

**Limitations:** This profile casts Mind Blast only once per target, not again as soon as its cooldown finishes while wanding. The bot uses confirmed casts from PriestBridge where available, with a conservative 2.1-second fallback if the event is missed. No UI automation is guaranteed to function unchanged on every private client. The initial live fight must be tested with supervision; the app still starts in dry-run mode.

---

# PriestBot v0.9 — permanent install and one-click local updates

**What's new:** a permanent Windows installation, an automatically created **PriestBot** desktop shortcut, updates from a local ZIP in the app, automatic PriestBridge installation (only when its files change), and preservation of existing spell bindings, `config.json`, and `.venv`. v0.8 game logic and addon telemetry remain unchanged. Designed for your private test server where automation is permitted; it has not been live-tested on your particular Windows machine.

## Install v0.9 ONCE (migrate from v0.8)

1. **Close the running v0.8 bot.** Download and extract this ZIP into a temporary folder.
2. Double-click **`install_windows.bat`** once. Python 3.10+ must already be available (as with previous versions).
3. If prompted about old settings, click **Yes**, then select the **`config.json` from your old v0.8 bot folder**. This is a one-time migration; it imports your spell keybindings, calibration, and rotation configuration. If you never customized settings, choose No.
4. The installer creates a permanent installation in **`%LOCALAPPDATA%\PriestBot`** (normally `C:\Users\<you>\AppData\Local\PriestBot`). It creates or reuses `.venv`; installs packages only if needed; and creates **PriestBot.lnk** on the actual Windows Desktop (including OneDrive-redirected desktops).
5. It installs/updates the bundled PriestBridge `.lua` and `.toc` in your WoW folder. The configured default is precisely:

   `C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns`

   If Windows protects `Program Files (x86)`, an administrator-permission **UAC** prompt may appear. Approval is only needed to update the addon, not to install the bot. If you decline, the Python app can still run, and **Install / repair PriestBridge** retries later.
6. The app opens automatically. Type **`/reload`** in WoW if the addon was updated. Begin in **dry-run mode** and press **F6** to verify your v0.8 aura, casting and health telemetry.

**After this initial install, use the PriestBot desktop shortcut every time.** You do not need to run setup or any BAT file for regular use.

## For ALL subsequent updates (v0.10 and later)

1. Download the ZIP of the new release; **do not extract it**.
2. Open **PriestBot** using the permanent desktop shortcut; pause the bot.
3. Click **Update from ZIP...** and choose the downloaded ZIP.
4. Confirm. PriestBot closes, applies the new files, preserves `.venv` and `config.json`, installs the addon if it changed (UAC only if needed), then **reopens automatically**.
5. If the addon changed, use **`/reload`** in WoW. The GUI shows the result of the update.

The update is **user-initiated and offline**. There is no network auto-download or unattended background installation. Install only release ZIPs you trust. The updater validates archive paths/sizes and saves backups in `backups/`, but it does **not** digitally authenticate third-party ZIP contents.

### Other new buttons

- **Install / repair PriestBridge:** Retry a blocked addon update without reinstalling Python; confirms your configured AddOns path.
- **Change WoW AddOns folder:** Choose the `Interface\AddOns` folder if you move the game later. This only changes saved settings; click Install / repair to apply it.
- **Recreate desktop shortcut:** Restores the desktop icon if it was moved or deleted.

### Files intentionally preserved across upgrades

`%LOCALAPPDATA%\PriestBot\config.json` (spells/keybindings, rotation and calibration), `.venv` (Python environment), `install_settings.json` (game addon path), `update.log`, previous backups, and your existing desktop shortcut. Addon updates replace **only** `PriestBridge.lua` and `PriestBridge.toc` within `PriestBridge`; other WoW addons and any other files in that directory remain untouched.

**Failure recovery:** If an upgrade fails, the updater attempts to restore any previously replaced program files, logs the failure in `update.log`, and relaunches the installed app when possible. A dependency installation failure may still require manual repair. If you declined addon UAC, the Python upgrade can complete independently and mark the addon update pending.

---

# Priest Foreground Farmer v0.8 — aura-aware rotation and decision dashboard

Windows prototype for **permitted, private-server automation**. Sends ordinary keystrokes only when the allowed WoW executable is the foreground application. No navigation, looting, background control, injection, or game-memory access. **v0.7 health/mana/target telemetry, range/LoS event and casting indicators were tested by the user on their private client. v0.8 aura and successful-cast features remain untested in their client.**



## NEW v0.8: confirmed spell casts, aura estimates and live dashboard

**This is a client + addon update.** Replace **both** `PriestBridge.lua` and `PriestBridge.toc` inside your existing `Interface/AddOns/PriestBridge/` folder with the v0.8 files, then `/reload`. Keep the entire telemetry panel unobstructed; v0.8 adds a *fourth, narrow status row* **underneath** the three existing bars. The original v0.7 bar coordinates and casting/error indicators have not moved.

1. Close the old Python bot and extract this ZIP to a new directory.
2. Copy your working **v0.7 `config.json`** into the new directory to keep keybindings, spells, calibration and telemetry source. The app always starts in **DRY RUN**, even if the copied config previously enabled live keys. `Config.from_dict` fills in new v0.8 defaults. Alternatively start fresh, select **addon** as the telemetry source, and configure bindings.
3. Install the included **v0.8** PriestBridge addon, reload WoW, and run `run_windows.bat`. If needed, run `setup_windows.bat` once in the extracted directory.
4. With the bot paused, press **F6** in WoW. Verify the log includes `Shield=...`, `Pain=...`, `last_success=...`, `success_seq=...`, and `target_seq=...`. If F6 says **no v0.8 aura/success telemetry**, you are still running an older addon or `/pb signals off` is active.
5. In WoW, `/pb test pain` simulates a successful Pain cast, and `/pb test shield` simulates a Shield cast. Press F6 immediately afterward: `success_seq` should advance and the last-success indicator change. `/pb test target` simulates a target change (also increments `target_seq`). These **test commands are synthetic signals**, not evidence of a real spell succeeding.
6. **Real-client test:** Cast Shadow Word: Pain manually on a real enemy, then quickly press F6. `last_success=pain` with an increased `success_seq` confirms `UNIT_SPELLCAST_SUCCEEDED` is usable for your Priest. Repeat with Smite and, once trained, Shield. Use `/pb auras` outside combat to inspect the aura reader's state.
7. Start with **DRY RUN**. Watch the **Live decision dashboard** and ensure Pain isn't reapplied unnecessarily and that a different target receives fresh treatment. Only enable live key presses once these signals behave correctly.

### New behavior

| Signal | Behavior |
|---|---|
| Shield present (verified) | Do not attempt another Shield |
| Pain present on current target (verified) | Do not recast Pain |
| Aura data restricted in combat | Track **estimated** state from confirmed `UNIT_SPELLCAST_SUCCEEDED`; do not pretend secret data was directly read |
| Confirmed Power Word: Shield | Estimate a maximum 30-second duration, and enforce a minimum 15-second reapplication lockout (Weakened Soul) after the confirmed cast |
| Confirmed Shadow Word: Pain | Estimate 18 seconds remaining; never carry that estimate over to a new target |
| Confirmed Smite | Permit the next Smite shortly after casting actually finishes, instead of always waiting the full fallback 2.7 seconds |
| Unknown spell status | Fall back to conservative v0.7 timers and health/error monitoring |
| Missing/restricted addon data | The original three bars are still required; corrupt telemetry stops the bot. Old addon versions can fall back to timers, but v0.8 signals are unavailable |

**Aura states:** `present` = name-based query returned a readable aura; `absent` = readable query found no matching aura; `estimated` = inferred from a successful cast with an assumed duration; `unknown` = unavailable/secret. With restricted auras, an early Shield absorption, dispel, mob death, or resist might not be reflected in an estimate. A name-based target Pain query may also detect another Priest's debuff; these are limitations of the bridge, **not proof** of your own active debuff. Spell-event counters are four bits and can wrap if more than 15 events happen between reads.

**Optional custom macros** (assign each to the configured action key; direct spell bindings also work):

Self-heal (key `2`):

```text
#showtooltip Lesser Heal
/cast [@player] Lesser Heal
```

Pain (key `3`):

```text
#showtooltip Shadow Word: Pain
/cast [harm,nodead] Shadow Word: Pain
```

Smite (key `4`):

```text
#showtooltip Smite
/cast [harm,nodead] Smite
```

Shield once learned (key `1`):

```text
#showtooltip Power Word: Shield
/cast [@player] Power Word: Shield
```

Wand when obtained (key `7`):

```text
#showtooltip Shoot
/cast !Shoot
```

Macros do **not** automatically chain casts; Python still sends each key. If your private client uses different conditionals or spell names, adjust the macro accordingly. All keys remain editable using **Configure spell keys** in the GUI.

**No guaranteed unattended farming:** This remains stationary Tab targeting with no pathfinding or looting. It may fail against the same unreachable target multiple times and eventually stop. F9 is an emergency stop; the app refuses to issue new keys when WoW is not the foreground process. No game-memory access or anti-detection mechanisms are used. Keep supervising initial live tests.

**Testing:** The pure decision logic and synthetic pixel telemetry decode are tested on the developer's machine, and the Tk UI was opened in a virtual display. The v0.8 Lua addon, aura visibility, and real spell-success events **have not** been tested on your actual private client. No Lua interpreter/client was available for an end-to-end run.

---

## v0.7: Spell casting and range/line-of-sight signals

The **same small PriestBridge status panel** now includes an optional top-row
status strip. Python reads this strip along with the existing health/mana/target
bars. **Do not overwrite v0.7 with your old addon folder:** copy the updated
`addons\PriestBridge` folder into the client's `Interface\AddOns` folder
(replace existing files) and type `/reload` in WoW. The `.toc` version is 0.7.

The new signals are intentionally conservative:

- **Casting:** Unit spellcast start/end events set a green/gray indicator. When
  casting is reported, Python avoids issuing a new spell key until the cast ends.
- **Out of range / line of sight:** A recognized `UI_ERROR_MESSAGE` flashes an
  orange or purple indicator, respectively. If the bot *just attempted an
  offensive spell* on a live target, it clears that target immediately instead
  of waiting 13 seconds. It stays stationary (no auto-navigation).
- **Other cast failed:** A red indicator and event counter are logged for
  diagnosis. Without a specific failure reason, the bot does not assume it
  should clear its current target.
- The original **13-second no-damage timeout remains a fallback** if the
  server does not produce the relevant events or the addon cannot read them.
- Signals are *events*, not proof that a specific keypress caused an error;
  only recent errors tied to attempted offensive actions prompt a target skip.
  Rapid sequences of 16 or more events between screenshot scans can overflow
  the four-bit counter; use these as hints, not guarantees.

### Verify the status strip before enabling live keys

1. Run `setup_windows.bat` once in the new folder if necessary. Copy your
   existing `config.json` from v0.6 to preserve spell keys and settings.
2. Replace the addon folder and type `/reload` in WoW. The health, mana, and
   target bars should look identical. New small squares appear above them.
3. Set telemetry source to `addon`. With bot **paused**, use `F6`; the log
   should now include `casting=False`, `spell_error=none`, and `event_seq=0`
   (or another number). If it says `legacy v0.6 addon`, WoW is still using
   the old Lua file, or `/pb signals off` is active.
4. While in WoW, type `/pb test range`, then immediately press `F6`: the log
   should report `spell_error=range`. `/pb test los` and `/pb test failed`
   exercise the other two categories. Each indication expires after ~2.5s.
   `/pb test cast` toggles the casting indicator for up to eight seconds.
5. Start the Python bot in **DRY RUN** to inspect state transitions. Then
   test an actual out-of-range Smite or Shadow Word: Pain and check whether
   the log reports the error. Only enable real inputs after you verify the
   response in your private client's build.

Use `/pb signals off` to disable the new strip if your client produces Lua
errors or unreliable spell events. The three native status bars continue to
work; Python automatically falls back to the old detection/timers. Use
`/pb signals on` to restore them.

**Limitations:** The Lua addon cannot call protected functions to cast or
navigate. This is *still a screen-pixel bridge*, not a backend/network API.
Private clients may rename, suppress, or restrict spell events, and API
behavior under combat secrecy may differ from test assumptions. The v0.7 spell signals were confirmed working by the user on their private
client; the new v0.8 confirmation and aura signals still require live tests.

## v0.6: client-side PriestBridge status bars (retained)

This release supports two sensor modes in the GUI: **addon** (recommended on compatible clients) and **manual** (previous v0.5 screenshot boxes). The addon is **display-only**; it does not issue game actions or access memory/files/network. WoW's native Lua functions update three standardized status bars, and Python measures their on-screen fill. This is still visual detection, but without repeated manual calibration. It does **not** provide a server API or raw character-state packets.

### Install the addon

1. In the extracted bot folder, find `addons\PriestBridge` with `PriestBridge.toc` and `PriestBridge.lua` inside.
2. Copy the entire **PriestBridge** folder to your *private server client's* `Interface\AddOns` directory. The actual client path varies; use the directory that already contains your other addon folders. Example: `...\World of Warcraft\_classic_beta_\Interface\AddOns\PriestBridge\PriestBridge.toc` (this beta path is only an example).
3. Relaunch or `/reload` in WoW; enable **PriestBridge** at the character screen if necessary. If it is marked out of date, check your private client's interface version. The supplied `.toc` targets the reported Forever beta interface `16001`; your client might be different.
4. A small three-color marker (magenta, cyan, yellow) above **green HP**, **blue mana**, and **red target HP** bars should appear near the upper-left of the WoW window. Keep that entire panel visible and unobstructed. Use `/pb show` to restore it or `/pb hide` to turn it off.
5. Run the Python app, select **Telemetry source → addon**, and save. With WoW visible, press **F6** to test the addon. Watch the displayed HP, mana, and target HP while these values actually change. **Do this in DRY RUN first**, with all input disabled.
6. If addon data fails to render or reads incorrectly, switch to `manual` and use the existing F7 box-calibration workflow instead. Do not enable live control on unverified telemetry.

### Technical limits

- WoW Forever inherits restricted/secret combat values from the modern addon API. The addon **never compares, formats, or performs math on secret health/mana**. It passes native values straight into `StatusBar:SetValue`/`SetMinMaxValues` in a protected `pcall`. Python measures their displayed fill.
- The bar protocol is **three 160×12 logical-pixel bars**, separated by 8 logical pixels, under colored marker squares. Python finds the signature anywhere on the full virtual desktop and accounts for Windows/UI scale in the pixel decoder. Overlays, gamma/contrast settings, special graphics filters, and unusual UI scales may still break detection.
- The v0.7 addon exports basic casting state and range/line-of-sight/failed hints, not complete cast-success, active buffs, or debuffs. The bot retains the old timers and 13-second no-damage recovery behavior. Those improvements require separate client-side compatibility tests.
- If Python cannot verify the marker or any of the three expected bars, the run **stops instead of issuing more keys**. Starting the app remains DRY RUN by default in a fresh folder.
- **F6** tests addon telemetry, **F7** opens manual screenshot calibration, **F8** starts/pauses, and **F9** stops. F6–F9 cannot be assigned to spells.
- The addon is not verified on your live private-client build. Tests use synthetic rendered panels at multiple display scales; the client could reject some Lua calls. No game executable patching, injection, network interception, or memory access is required.

## What's new in v0.4

- **Configure spell keys** button on the main window: map Shield, Heal/Lesser Heal, Shadow Word: Pain, Smite, wand, melee, drinking, next target, and clear target to any supported key or modifier combination. Saves directly to `config.json`. No Python editing needed.
- Keybinding validation: no duplicate bindings, unsupported combinations, unsafe OS shortcuts, or F6/F7/F8/F9 (reserved controls).
- **Auto suggest bars** button inside the screenshot calibrator, which searches for horizontal green/blue/red bars and proposes rectangles for player HP, player mana, and target HP. Detection is deliberately conservative and may return only 0–2 bars.
- **Preview screenshot readings** button to see estimated HP/mana/target percentages from your proposed boxes before saving.
- Automatic suggestions are **never saved automatically**. Inspect at 400% zoom, redraw or resize incorrect/partial boxes, and press **Save all 3 bars** yourself.
- Suggestions are most accurate when your character's HP, mana, and the selected hostile target's HP are close to **100%**. The algorithm detects colored *fill*, which may not span the full bar when HP is depleted. The resulting box must include the full track, including the unfilled region, to read percentages properly during gameplay.
- Previously saved boxes are preserved: auto suggestion fills only missing boxes and doesn't silently override manual work.

## Existing calibration improvements from v0.3

- **Zoomable calibration window**: scroll-wheel zoom centered on your pointer (up to 1600%), plus `+`, `−`, `Fit`, `100%`, and `400%` buttons. The screenshot is no longer shrunk to a fixed, blurry thumbnail.
- **Pan around a zoomed screenshot** with right- or middle-mouse drag; draw boxes with left-drag. Three individually selectable boxes are overlaid in different colors.
- **Pixel-accurate coordinates**: the boxes are stored in the *original screenshot* coordinate system, not scaled-up display pixels. Windows multi-monitor offsets (including negative coordinates) are preserved.
- **Fine-tuning**: select a box and use arrow keys to move it one source pixel or Shift+arrow to adjust its right/bottom edge. Undo with Ctrl+Z. You can redraw any box, clear it, and inspect all three before clicking Save.
- **Recalibration**: previously saved boxes are loaded onto the new screenshot (when they still fit), so you can refine them instead of redrawing all three.
- **Viewport-only rendering**: zooming into a 4K/multi-monitor image does not allocate a giant full-size enlarged screenshot.

## Other features retained from v0.2

- **Level 5 defaults**: cast Shadow Word: Pain once on each new target, repeat Smite, use Lesser Heal when below 45% HP, and begin melee attacks if mana falls below 30%.
- **Spell controls in the GUI**: select the main damage type (`smite`, `wand`, `melee`); enable/disable Shield, Pain, healing, or melee fallback. By default **Shield is OFF** until level 6.
- At low mana between pulls, wait for mana regeneration instead of stopping outright (optional water consumption can be enabled).
- Keys are configurable using **Configure spell keys** in the GUI (or manually in `config.json`); defaults are listed below.
- Includes automated tests for the new level-5 rotation and old-config migration.

## Upgrading from v0.3

Extract this ZIP to a **new** folder. If you want to keep your prior customizations, copy `config.json` from your old folder into the new folder, then use **Configure spell keys** to review the bindings. You can copy `.venv` from the earlier folder or run `setup_windows.bat` again to create a new virtual environment. The ZIP deliberately excludes `.venv` and personal config files.

## Setup

1. Install Python 3.10+ for Windows. Extract ZIP and run `setup_windows.bat`, then `run_windows.bat`.
2. In the game, create the macros below with `/macro`. Place each macro on an action-bar slot, then configure the corresponding key in the bot UI. Confirm the commands work **manually** on your private server before using the bot.
3. In either mode, click **Configure spell keys** and match the keys in WoW. For **addon** telemetry, follow the v0.6 instructions above and skip F7 box calibration. For **manual** telemetry, keep HP/mana/target bars visible, press **F7**, adjust the three boxes, preview the readings, and save them.
4. Select **smite** as Main damage spell; **enable Pain and Lesser Heal**, and **disable Shield** at level 5. Optionally enable melee fallback; it is ON by default.
5. Press **F8** to try the **DRY RUN** (doesn't press keys) first. Review detected HP, mana and target percentages. **Only after validating the readings** check *Enable real key presses* and press **F8** again.
6. **F9** emergency-stop requests immediate cessation of input. Changing the window focus also pauses inputs.


## Calibrating accurately (v0.4)

1. With WoW foreground, target a **living enemy with full health**, heal your character and refill mana if possible, then press **F7**. Avoid using the *Calibrate from screenshot* GUI button when WoW is behind other windows, because it captures whatever is currently visible.
2. Optionally click **Auto suggest bars**. Suggestions appear as colored rectangles. If any suggestion is missing, misplaced, or spans only the filled part, select that bar and redraw it using the mouse. Zoom to 200–400%, right-drag to pan, and draw a rectangle *inside* the bar track avoiding borders, icons, and text. Cover the **full width of the bar**, even when partially empty.
3. Repeat for **Your MANA bar** and **Enemy TARGET health bar**. Each selected bar remains visible in its own outline color. Use the radio buttons to redraw or adjust a previous selection.
4. At high zoom, **arrow keys** nudge the selected bar by one original pixel; **Shift+arrow** changes its width/height at the right/bottom edge. Ctrl+Z undoes the latest change.
5. Click **Preview screenshot readings** to check estimated percentages from the captured screenshot, then **Save all 3 bars**. Saved values refer to the *actual desktop pixel coordinates*, so zoom doesn't change the bot's readings. F8 dry-run should show reasonable HP, mana and target percentages.

Mouse wheel zooms around your pointer; `Fit` shows the entire capture; `100%` means one displayed pixel per screenshot pixel; `400%` provides pixel-level precision. Multi-monitor setups may have negative desktop X/Y values—this is expected. If you change UI scale, window placement, resolution, or move the bars, **press F7 and recalibrate**.

**Note:** Zoom improves where the detector reads. It doesn't fix the existing color-based filled-bar heuristic, and a screenshot with a partially filled bar may make the fill fraction misleading if you select only the filled part. Always select the full interior bar track.

## Configurable spell keys — level 5

| Action | Key | In-game macro / action bar |
| --- | --- | --- |
| Self-heal | `2` | `/cast [@player] Lesser Heal` |
| Shadow Word: Pain | `3` | `/cast [harm,nodead] Shadow Word: Pain` |
| Smite (filler) | `4` | `/cast [harm,nodead] Smite` |
| Melee fallback | `6` | `/startattack` |
| Target nearest enemy | `Tab` | Normal WoW keybind |
| Clear target | `Esc` | Normal WoW keybind |

Open **Configure spell keys** on the bot main screen to change any of these. Each action may use a single key (`e`) or one discrete modifier chord (`shift+e`, `ctrl+1`, `alt+q`, `ctrl+shift+r`) matching the in-game action-bar binding. F6, F7, F8 and F9 are reserved for addon test/calibration/start/stop, even with modifiers. Duplicate bindings are rejected. Pause the bot to edit bindings.

Other available keys for later levels:

| Action | Key | Macro / action bar |
| --- | --- | --- |
| Power Word: Shield (level 6+) | `1` | `/cast [@player] Power Word: Shield` |
| Water (optional) | `5` | Drag a stack of usable water to slot 5 |
| Wand (once obtained) | `7` | `/cast !Shoot` |

**Macro compatibility differs between private servers and client versions.** If `[@player]` or `[harm,nodead]` is not supported, adjust these macros for that server. You may also bind a direct spell instead of a macro when the target is correct; self-heal then needs a reliable self-cast binding.

## Customize the rotation

The GUI has a **Main damage spell** dropdown (`smite`, `wand`, `melee`) and checkboxes for Shield, Shadow Word: Pain, Lesser Heal, and Melee when OOM. Save changes before starting a new run. The optional water switch is OFF by default.

You can also edit `config.json` (generated on saving options). The key editor is recommended because it validates duplicate and reserved keys. Restart the application after editing it by hand. For example, these are the level-5 defaults:

```json
{
  "main_damage": "smite",
  "use_shield": false,
  "use_pain": true,
  "use_heal": true,
  "melee_when_oom": true,
  "heal_below": 0.45,
  "smite_interval_s": 2.7,
  "smite_mana_min": 0.30,
  "keys": {
    "heal": "2",
    "pain": "3",
    "smite": "4",
    "melee": "6"
  }
}
```

This is a *partial example*, not an additional file to place beside the program. The actual config contains other fields for health-bar calibration, process names, keys, and safety timers. If bringing an older v0.1 `config.json`, keys are merged and its old wand binding on `4` is remapped to `7` when Smite is introduced.

- **At level 6:** enable Shield in the GUI after training it and binding its macro to `1`.
- **Once you get a wand:** switch Main damage spell to `wand`, bind the Shoot macro to `7`, and optionally leave Pain/Shield/Heal enabled.
- **Healing spell changes:** update the macro on key `2` to the healing spell you actually know; the bot uses the same `heal` action.
- Timing and mana thresholds are heuristic. The program does **not** know actual spell costs, debuff duration, casting success, exact mana cost or cooldowns. Tune it after observing behavior in dry-run/live tests. You may change action keys and presets, but adding entirely new spell types to the decision engine still requires code changes.

## Bar detector: what to expect

- Detection is **assistive**, not a replacement for review. It doesn't recognize Blizzard UI frames semantically: it finds colored horizontal shapes and applies positional heuristics. Colored addons, UI skins and nameplates may be misidentified.
- Full bar **track** detection is not yet available. The tool often selects only the currently colored section. Check box width manually and calibrate while all three bars are near 100%.
- Screenshot preview reports readings from the **saved screenshot**, not live-game readings. After saving, use F8 **DRY RUN** and verify the continuously displayed percentages while your HP/mana/target HP actually change before enabling live input.
- Keep the manual zoom/pan editor as a fallback. No suggested boxes are applied to the main bot until you click **Save all 3 bars**.

## Known limitations

- Foreground game only. Switching to another application stops sending inputs. It cannot type in Codex simultaneously on the same desktop while controlling WoW.
- Stationary Tab-targeting only. A mob that spawns outside spell range may cause a target timeout; the bot has no pathfinding or movement.
- Screen bar detection is heuristic and vulnerable to UI changes/overlays; only use after validating measured percentages.
- The bot now has optional event-based spell failure/LoS and casting-state hints, but cannot reliably detect all failures, buffs/debuffs, trainer spells, or enemy identities. Pain and Shield refresh based on timers rather than confirmed effects.
- Early Smite casting is more mana-intensive than wanding; the bot may wait for natural regeneration often. It **does not loot or navigate**.
- All botting remains subject to the **actual server's** rules, even if your intended private server permits it. No anti-detection or bypass features are provided.

## Safety and testing

F6 = test addon, F7 = manual calibration, F8 = start/pause, F9 = immediate stop request. Dry-run enabled by default. Check actual Windows executable name if client process doesn't match the allowlist. Normal foreground-only controls don't guarantee compatibility with every WoW client.

To test decision logic without the game:

```
python -m pip install pytest
python -m pytest -q
```

Current tested scope: simulated observations, configuration migration, and bar-reading logic only. The app and keypresses have **not** been validated against live WoW.

## v0.5: Shadow Word: Pain → wand timing

When **Main damage spell** is set to `wand`, the bot no longer applies the general
`action_delay_s` (default 1.7s) after Shadow Word: Pain. It attempts `!Shoot`
on the very next scan (default 0.3s). Because Classic-style spells often
trigger a ~1.5s global cooldown, the first Shoot may be rejected by the game;
the bot automatically tries `!Shoot` again at approximately 1.6s after Pain.
This is deliberately **not** a promise of instant wand damage: the game
determines when Shoot can fire. Check this with your private server's actual
client. Use the macro below for the configured **wand** key:

```
#showtooltip Shoot
/cast !Shoot
```

Advanced timing in `config.json`:

```json
{
  "pain_to_wand_delay_s": 0.0,
  "wand_gcd_retry_s": 1.6
}
```

These are **individual fields in your existing config**, not a complete config
file. A v0.4 `config.json` remains compatible; new fields get defaults.
Smite mode retains the old action delay. Do not set the GCD retry to zero: if
Shoot is rejected during GCD, the bot could incorrectly believe wanding started.

## GitHub development notes

- This is the **source distribution**. Do not commit `.venv`, `config.json`, `learning_data`, local logs or trained models. Private recording data stays on your computer.
- Install on Windows using `install_windows.bat`; after first installation use the desktop shortcut and **Update from ZIP** for packaged releases.
- Clone the repository to work on code or run tests with `python -m pytest`. Optional GPU training is covered in earlier version notes.
- `priestbot/icon_asset.py` embeds the *Classic WoW Priest* class-icon image and generates `%LOCALAPPDATA%\PriestBot\PriestBot.ico` at installation. It is a third-party game asset; this project is unaffiliated with Blizzard.
- No open-source license has been assigned by the owner.
