-- PriestBridge v0.23.0. Client-side, display-only telemetry for a permitted private client.
-- No game-memory access, sockets, arbitrary filesystem access or protected game actions.
-- Modern combat secrets: never compare/calculate/display text from secret health values.
-- Health/mana/target bars use the native StatusBar widget, as in v0.6.
-- The optional top-line status strip is based solely on addon events and may be
-- unsupported/restricted on some clients; disable it with /pb signals off.

local FRAME_WIDTH, FRAME_HEIGHT = 270, 102
local ROOT = CreateFrame('Frame', 'PriestBridgeFrame', UIParent)
ROOT:SetSize(FRAME_WIDTH, FRAME_HEIGHT)
ROOT:SetPoint('TOPLEFT', UIParent, 'TOPLEFT', 20, -165)
ROOT:SetFrameStrata('HIGH')
ROOT:SetClampedToScreen(true)
ROOT:Show()

local function square(x, size, r, g, b)
    local t = ROOT:CreateTexture(nil, 'OVERLAY')
    t:SetSize(size, size)
    t:SetPoint('TOPLEFT', ROOT, 'TOPLEFT', x, 0)
    t:SetColorTexture(r, g, b, 1)
    return t
end
square(0, 12, 1, 0, 1)
square(16, 12, 0, 1, 1)
square(32, 12, 1, 1, 0)

local function makeBar(y, r, g, b)
    local bar = CreateFrame('StatusBar', nil, ROOT)
    bar:SetSize(160, 12)
    bar:SetPoint('TOPLEFT', ROOT, 'TOPLEFT', 0, -y)
    bar:SetStatusBarTexture('Interface\\Buttons\\WHITE8X8')
    bar:SetStatusBarColor(r, g, b, 1)
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    local bg = bar:CreateTexture(nil, 'BACKGROUND')
    bg:SetAllPoints(bar)
    bg:SetColorTexture(0.10, 0.10, 0.10, 1)
    return bar
end

local hp = makeBar(20, 0, 1, 0)
local mana = makeBar(40, 0, 0.38, 1)
local enemy = makeBar(60, 1, 0, 0)
local errors = 0
local function paint(bar, unit, isMana)
    local ok = pcall(function()
        if not UnitExists(unit) then
            bar:SetMinMaxValues(0, 1)
            bar:SetValue(0)
            return
        end
        if isMana then
            bar:SetMinMaxValues(0, UnitPowerMax(unit, 0))
            bar:SetValue(UnitPower(unit, 0))
        else
            bar:SetMinMaxValues(0, UnitHealthMax(unit))
            bar:SetValue(UnitHealth(unit))
        end
    end)
    if not ok then
        errors = errors + 1
        bar:SetMinMaxValues(0, 1)
        bar:SetValue(0)
        if errors == 1 then
            print('|cffff7777PriestBridge: a native bar failed to render.|r')
        end
    end
end
local function refresh()
    paint(hp, 'player', false)
    paint(mana, 'player', true)
    paint(enemy, 'target', false)
end

-- Protocol v0.7, y=0, all squares display-only, event-driven.
-- x48 = teal protocol marker. If missing, Python treats new signals as unavailable.
-- x60 = casting green/idle gray; x76 = range orange/LoS purple/facing blue/failed red/none gray.
-- x96,108,120,132 = event sequence counter bits (0..15); white = 1, gray = 0.
-- This counter prevents Python from re-applying stale errors on every screenshot.
local marker = square(48, 8, 0, 0.8, 0.4)
local castingPixel = square(60, 10, .3, .3, .3)
local errorPixel = square(76, 10, .3, .3, .3)
local bits = {}
for i=1,4 do bits[i] = square(96 + (i-1)*12, 8, .25, .25, .25) end

-- v0.8 additional row (y=84) is APPENDED; all v0.7 bar coordinates remain.
-- x0 teal version marker; x16 shield aura; x32 target SW:P aura.
-- Aura colors: green = API-verified present, red = API-verified missing,
-- amber = successful-cast timer estimate, gray = unknown/unreadable.
-- x48 last confirmed cast: shield green, Pain magenta, Smite white, Mind Blast orange,
-- heal cyan, none gray. x64..100 = success counter bits.
-- x112..148 = target-generation counter bits. All bits are 4-bit modulo 16.
local function squareOnRow(x, y, size, r, g, b)
    local t = ROOT:CreateTexture(nil, 'OVERLAY')
    t:SetSize(size, size)
    t:SetPoint('TOPLEFT', ROOT, 'TOPLEFT', x, -y)
    t:SetColorTexture(r, g, b, 1)
    return t
end
local marker08 = squareOnRow(0,84,8,0,.7,.7)
local shieldPixel = squareOnRow(16,84,10,.3,.3,.3)
local painPixel = squareOnRow(32,84,10,.3,.3,.3)
local successPixel = squareOnRow(48,84,10,.3,.3,.3)
local successBits, targetBits = {}, {}
for i=1,4 do
    successBits[i] = squareOnRow(64+(i-1)*12,84,8,.25,.25,.25)
    targetBits[i] = squareOnRow(112+(i-1)*12,84,8,.25,.25,.25)
end
local successSeq, targetSeq, recentSuccess = 0,0,'none'
local shieldEstimateUntil, painEstimateUntil = 0,0
local shieldState, painState = 'unknown','unknown'
local SHIELD_DURATION, PAIN_DURATION = 30,18 -- configurable estimates, not claimed to be verified
local function paintBits(bits, number)
    for i,t in ipairs(bits) do
        if number % 2^i >= 2^(i-1) then t:SetColorTexture(1,1,1,1)
        else t:SetColorTexture(.25,.25,.25,1) end
    end
end
local function paintAura(t,state)
    if state=='present' then t:SetColorTexture(0,1,0,1)
    elseif state=='absent' then t:SetColorTexture(1,0,0,1)
    elseif state=='estimated' then t:SetColorTexture(1,.7,0,1)
    else t:SetColorTexture(.3,.3,.3,1) end
end
local function redrawAuras()
    paintAura(shieldPixel,shieldState)
    paintAura(painPixel,painState)
    paintBits(successBits,successSeq)
    paintBits(targetBits,targetSeq)
    if recentSuccess=='shield' then successPixel:SetColorTexture(0,1,0,1)
    elseif recentSuccess=='pain' then successPixel:SetColorTexture(1,0,1,1)
    elseif recentSuccess=='smite' then successPixel:SetColorTexture(1,1,1,1)
    elseif recentSuccess=='mind_blast' then successPixel:SetColorTexture(1,.5,0,1)
    elseif recentSuccess=='heal' then successPixel:SetColorTexture(0,1,1,1)
    else successPixel:SetColorTexture(.3,.3,.3,1) end
end
-- Game APIs are permitted where available. In Forever combat, aura records
-- can be SECRET; do not access, compare or stringify a secret result.
-- In restricted combat APIs, AuraUtil.FindAuraByName can return nil for an
-- ACTIVE aura. A nil lookup is therefore UNKNOWN, never proof of absence.
-- Successful-cast event timers provide an estimate; unknown must not erase it.
-- Only a readable, non-secret matched aura may be marked present.
local function findAuraSafely(unit, spellName, filter)
    if not AuraUtil or not AuraUtil.FindAuraByName then return 'unknown' end
    local ok, result = pcall(function()
        local name = AuraUtil.FindAuraByName(spellName,unit,filter)
        if issecretvalue and issecretvalue(name) then return 'unknown' end
        if canaccessvalue and not canaccessvalue(name) then return 'unknown' end
        if name == nil then return 'unknown' end
        return 'present'
    end)
    if not ok then return 'unknown' end
    return result
end
local function evaluateAuras()
    local now = GetTime()
    local shield = findAuraSafely('player','Power Word: Shield','HELPFUL')
    local pain = 'unknown'
    local hasTargetOk, hasTarget = pcall(UnitExists,'target')
    if hasTargetOk and hasTarget then
        pain = findAuraSafely('target','Shadow Word: Pain','HARMFUL')
    end
    if shield=='unknown' and now < shieldEstimateUntil then shield='estimated' end
    if pain=='unknown' and now < painEstimateUntil then pain='estimated' end
    shieldState, painState = shield,pain
    redrawAuras()
end
local function spellName(spellId)
    if type(spellId)~='number' then return nil end
    local ok, result = pcall(function()
        local result
        if C_Spell and C_Spell.GetSpellName then result = C_Spell.GetSpellName(spellId)
        elseif GetSpellInfo then result = GetSpellInfo(spellId) end
        if issecretvalue and issecretvalue(result) then return nil end
        if canaccessvalue and not canaccessvalue(result) then return nil end
        return result
    end)
    if ok and type(result)=='string' then return result end
    return nil
end
local shieldRanks = {[17]=true,[592]=true,[600]=true,[3747]=true,[6065]=true,[6066]=true,[10898]=true,[10899]=true,[10900]=true,[10901]=true}
local painRanks = {[589]=true,[594]=true,[970]=true,[992]=true,[2767]=true,[10892]=true,[10893]=true,[10894]=true}
local mindBlastRanks = {[8092]=true,[8102]=true,[8103]=true,[8104]=true,[8105]=true,[8106]=true,[10945]=true,[10946]=true,[10947]=true}
local smiteRanks = {[585]=true,[591]=true,[598]=true,[984]=true,[1004]=true,[6060]=true,[10933]=true,[10934]=true}
local healRanks = {[2050]=true,[2052]=true,[2053]=true,[2054]=true,[2055]=true,[6063]=true,[6064]=true}
local function classSuccess(spellId)
    local name = spellName(spellId)
    if name == 'Power Word: Shield' then return 'shield' end
    if name == 'Shadow Word: Pain' then return 'pain' end
    if name == 'Smite' then return 'smite' end
    if name == 'Mind Blast' then return 'mind_blast' end
    if name == 'Heal' or name == 'Lesser Heal' or name == 'Flash Heal'
       or name == 'Greater Heal' or name == 'Renew' then return 'heal' end
    -- Known Classic/Forever ranks as a language-independent fallback.
    if shieldRanks[spellId] then return 'shield' end
    if painRanks[spellId] then return 'pain' end
    if smiteRanks[spellId] then return 'smite' end
    if mindBlastRanks[spellId] then return 'mind_blast' end
    if healRanks[spellId] then return 'heal' end
    return nil
end
local function recordSuccess(id)
    local kind = classSuccess(id)
    if not kind then return end
    successSeq=(successSeq+1)%16
    recentSuccess=kind
    local now=GetTime()
    if kind=='shield' then shieldEstimateUntil=now+SHIELD_DURATION end
    if kind=='pain' then painEstimateUntil=now+PAIN_DURATION end
    evaluateAuras()
end
local function newTarget()
    targetSeq=(targetSeq+1)%16
    painEstimateUntil=0
    evaluateAuras()
end
redrawAuras()

local signalsEnabled = true
local casting, castingAt = false, 0
local lastError, lastErrorAt, sequence = 'none', 0, 0

local function redrawSignals()
    marker:SetShown(signalsEnabled)
    castingPixel:SetShown(signalsEnabled)
    errorPixel:SetShown(signalsEnabled)
    for _, t in ipairs(bits) do t:SetShown(signalsEnabled) end
    marker08:SetShown(signalsEnabled)
    shieldPixel:SetShown(signalsEnabled)
    painPixel:SetShown(signalsEnabled)
    successPixel:SetShown(signalsEnabled)
    for _,t in ipairs(successBits) do t:SetShown(signalsEnabled) end
    for _,t in ipairs(targetBits) do t:SetShown(signalsEnabled) end
    if not signalsEnabled then return end
    if casting then castingPixel:SetColorTexture(0,1,0,1)
    else castingPixel:SetColorTexture(.3,.3,.3,1) end
    if lastError == 'range' then errorPixel:SetColorTexture(1,.5,0,1)
    elseif lastError == 'los' then errorPixel:SetColorTexture(.7,0,1,1)
    elseif lastError == 'facing' then errorPixel:SetColorTexture(0,.7,1,1)
    elseif lastError == 'failed' then errorPixel:SetColorTexture(1,0,0,1)
    else errorPixel:SetColorTexture(.3,.3,.3,1) end
    for i, t in ipairs(bits) do
        if sequence % (2^i) >= 2^(i-1) then t:SetColorTexture(1,1,1,1)
        else t:SetColorTexture(.25,.25,.25,1) end
    end
end
local function recordError(reason)
    -- UI_ERROR_MESSAGE often arrives alongside UNIT_SPELLCAST_FAILED.
    -- Keep the specific reason instead of overwriting it with generic failure.
    if reason == 'failed' and (lastError == 'range' or lastError == 'los' or lastError == 'facing')
       and GetTime() - lastErrorAt < .5 then return end
    lastError = reason
    lastErrorAt = GetTime()
    sequence = (sequence + 1) % 16
    redrawSignals()
end
local function classifyError(message)
    -- Global strings are locale-aware when supplied by the client.
    -- Check inside pcall: combat-secret message comparisons may be prohibited.
    if message == ERR_SPELL_OUT_OF_RANGE or message == ERR_OUT_OF_RANGE
       or message == SPELL_FAILED_OUT_OF_RANGE then return 'range' end
    if message == ERR_LINE_OF_SIGHT or message == SPELL_FAILED_LINE_OF_SIGHT
       or message == SPELL_FAILED_VISION_OBSCURED then return 'los' end
    if message == ERR_BADATTACKFACING or message == ERR_USE_BAD_ANGLE
       or message == SPELL_FAILED_UNIT_NOT_INFRONT or message == SPELL_FAILED_NOT_INFRONT
       or message == ERR_NOT_IN_FRONT_OF_TARGET then return 'facing' end
    -- Fallback for a client whose global constants differ (English UI only).
    local low = string.lower(message)
    if string.find(low, 'out of range', 1, true) or string.find(low, 'too far away', 1, true) then return 'range' end
    if string.find(low, 'line of sight', 1, true) or string.find(low, 'not in sight', 1, true) then return 'los' end
    if string.find(low, 'facing the wrong way', 1, true) or
       string.find(low, 'target needs to be in front', 1, true) or
       string.find(low, 'not in front', 1, true) or
       string.find(low, "aren't facing", 1, true) then return 'facing' end
    return nil
end
local signalErrorCount = 0
local function safeProcessSignal(event, ...)
    local arg1, arg2 = ...
    if event == 'UI_ERROR_MESSAGE' then
        local reason = classifyError(arg2)
        if reason then recordError(reason) end
        return
    end
    if arg1 ~= 'player' then return end
    if event == 'UNIT_SPELLCAST_START' or event == 'UNIT_SPELLCAST_CHANNEL_START' then
        casting = true
        castingAt = GetTime()
        redrawSignals()
    elseif event == 'UNIT_SPELLCAST_SUCCEEDED' then
        casting = false
        redrawSignals()
        -- Modern events: unit, castGUID, spellID. Only record known successes.
        recordSuccess(select(3,...))
    elseif event == 'UNIT_SPELLCAST_STOP' or event == 'UNIT_SPELLCAST_CHANNEL_STOP' then
        casting = false
        redrawSignals()
    elseif event == 'UNIT_SPELLCAST_FAILED' or event == 'UNIT_SPELLCAST_FAILED_QUIET'
        or event == 'UNIT_SPELLCAST_INTERRUPTED' then
        casting = false
        recordError('failed')
    end
end
local function signalEvent(event, ...)
    if not signalsEnabled then return end
    local ok = pcall(safeProcessSignal, event, ...)
    if not ok then
        signalErrorCount = signalErrorCount + 1
        if signalErrorCount == 1 then
            print('|cffffaa77PriestBridge: one or more spell event values are restricted on this client. The base bars still work.|r')
        end
    end
end

ROOT:RegisterEvent('PLAYER_ENTERING_WORLD')
ROOT:RegisterEvent('PLAYER_TARGET_CHANGED')
ROOT:RegisterEvent('UNIT_AURA')
ROOT:RegisterEvent('UNIT_HEALTH')
ROOT:RegisterEvent('UNIT_MAXHEALTH')
ROOT:RegisterEvent('UNIT_POWER_UPDATE')
ROOT:RegisterEvent('UNIT_MAXPOWER')
ROOT:SetScript('OnEvent', function(self, event, unit)
    if not unit or unit == 'player' or unit == 'target' then refresh() end
    if event=='PLAYER_TARGET_CHANGED' then newTarget() end
    if event=='UNIT_AURA' and (unit=='player' or unit=='target') then evaluateAuras() end
end)

local SIGNALS = CreateFrame('Frame')
local eventNames = {
    'UI_ERROR_MESSAGE', 'UNIT_SPELLCAST_START', 'UNIT_SPELLCAST_STOP',
    'UNIT_SPELLCAST_SUCCEEDED', 'UNIT_SPELLCAST_FAILED',
    'UNIT_SPELLCAST_INTERRUPTED', 'UNIT_SPELLCAST_FAILED_QUIET',
    'UNIT_SPELLCAST_CHANNEL_START', 'UNIT_SPELLCAST_CHANNEL_STOP'
}
for _, event in ipairs(eventNames) do
    -- Event availability varies across private-server clients.
    pcall(function() SIGNALS:RegisterEvent(event) end)
end
SIGNALS:SetScript('OnEvent', function(self, event, ...) signalEvent(event, ...) end)
local elapsed = 0
ROOT:SetScript('OnUpdate', function(self, dt)
    elapsed = elapsed + dt
    if elapsed >= .20 then
        elapsed = 0
        refresh()
        if casting and GetTime() - castingAt > 8 then casting = false; redrawSignals() end
        if lastError ~= 'none' and GetTime() - lastErrorAt > 2.5 then
            lastError = 'none'; redrawSignals()
        end
        evaluateAuras()
    end
end)
redrawSignals()
evaluateAuras()

SLASH_PRIESTBRIDGE1 = '/priestbridge'
SLASH_PRIESTBRIDGE2 = '/pb'
SlashCmdList.PRIESTBRIDGE = function(msg)
    if msg == 'hide' then ROOT:Hide()
    elseif msg == 'show' then ROOT:Show()
    elseif msg == 'signals off' then signalsEnabled = false; redrawSignals()
    elseif msg == 'signals on' then signalsEnabled = true; redrawSignals()
    elseif msg == 'test range' then recordError('range')
    elseif msg == 'test los' then recordError('los')
    elseif msg == 'test facing' then recordError('facing')
    elseif msg == 'test failed' then recordError('failed')
    elseif msg == 'test cast' then casting = not casting; castingAt = GetTime(); redrawSignals()
    elseif msg == 'test pain' then recordSuccess(589)
    elseif msg == 'test shield' then recordSuccess(17)
    elseif msg == 'test mindblast' then recordSuccess(8092)
    elseif msg == 'test target' then newTarget()
    elseif msg == 'auras' then evaluateAuras(); print('PriestBridge aura status: shield='..shieldState..', pain='..painState..' (estimated=cast timer; unknown=unreadable)')
    else
        print('PriestBridge v0.23: /pb show|hide|signals on/off|auras|test pain|test shield|test target|test range|test los|test facing|test cast')
    end
end


-- v0.23 Action Semantics + farming events: read-only optical metadata sidecar.
-- The first 160px of PriestBridge is unchanged, including all combat signals.
-- 32 8x8 tiles at x=180..250 y=20..58 encode 96 bytes as RGB values.
-- Header: 0xA6, version 1, seqLE16, length, sumLE16, UTF-8 payload.
-- A packet is repeated across four OnUpdate cycles to survive capture timing.
-- No filesystem/network calls, hooks that replace game functions, or protected inputs.
local SEM = CreateFrame('Frame')
local semTiles = {}
for i=1,32 do
    local col=(i-1)%8
    local row=math.floor((i-1)/8)
    semTiles[i]=squareOnRow(180 + col*10, 20 + row*10, 8, 0, 0, 0)
end
local semMarkerA = squareOnRow(180,0,8, 0,.75,.35)
local semMarkerB = squareOnRow(196,0,8, .75,.4,0)
local semSeq=0
local semGeneration=0
local semBindings={}
local semBindingIndex=1
local semEvents={}
local semCurrent=nil
local semRepeat=0
local semLastScan=0
local semDirty=true
local semFingerprint=nil
local function safeText(v)
    if type(v)~='string' and type(v)~='number' then return '' end
    if issecretvalue and issecretvalue(v) then return '' end
    if canaccessvalue and not canaccessvalue(v) then return '' end
    return tostring(v):gsub('[|\r\n\t]',' ')
end
local function emitSem(text)
    if #semEvents >= 70 then table.remove(semEvents, 1) end
    table.insert(semEvents, string.sub(text,1,89))
end
local function encodedPacket(msg)
    semSeq=(semSeq+1)%65536
    msg=string.sub(msg or '',1,89)
    local len=#msg
    local sum=0
    for i=1,len do sum=(sum+string.byte(msg,i))%65536 end
    sum=(sum+semSeq+len)%65536
    local bytes={166,1,semSeq%256, math.floor(semSeq/256),len,sum%256,math.floor(sum/256)}
    for i=1,len do bytes[#bytes+1]=string.byte(msg,i) end
    for i=1,32 do
        local k=3*(i-1)
        semTiles[i]:SetColorTexture((bytes[k+1] or 0)/255,
                                    (bytes[k+2] or 0)/255,
                                    (bytes[k+3] or 0)/255,1)
    end
end
local function slotFromCommand(cmd)
    local n=string.match(cmd,'^ACTIONBUTTON(%d+)$')
    if n then
        local page=1
        if GetActionBarPage then
            local ok,p=pcall(GetActionBarPage)
            if ok and type(p)=='number' then page=p end
        end
        return (page-1)*12+tonumber(n)
    end
    local bars={MULTIACTIONBAR1BUTTON=60, MULTIACTIONBAR2BUTTON=48,
                MULTIACTIONBAR3BUTTON=24, MULTIACTIONBAR4BUTTON=36,
                MULTIACTIONBAR5BUTTON=144, MULTIACTIONBAR6BUTTON=156,
                MULTIACTIONBAR7BUTTON=168}
    for prefix,offset in pairs(bars) do
        local index=string.match(cmd,'^'..prefix..'(%d+)$')
        if index then return offset+tonumber(index) end
    end
    return nil
end
local function resolveCommand(cmd)
    local slot=slotFromCommand(cmd)
    if not slot or not GetActionInfo then return 'binding',0,cmd end
    local ok,kind,id=pcall(GetActionInfo,slot)
    if not ok or type(kind)~='string' or type(id)~='number' then
        return 'slot',slot,'slot '..slot
    end
    local name=''
    if kind=='spell' then
        if C_Spell and C_Spell.GetSpellName then
            local o,v=pcall(C_Spell.GetSpellName,id); if o then name=safeText(v) end
        elseif GetSpellInfo then
            local o,v=pcall(GetSpellInfo,id); if o then name=safeText(v) end
        end
    elseif kind=='item' then
        if GetItemInfo then
            local o,v=pcall(GetItemInfo,id); if o then name=safeText(v) end
        end
        if GetItemSpell then
            local o,spell=pcall(GetItemSpell,id)
            if o and safeText(spell)~='' then name=name..' > '..safeText(spell) end
        end
    elseif kind=='macro' then
        if GetMacroInfo then
            local o,v=pcall(GetMacroInfo,id); if o then name=safeText(v) end
        end
        if GetMacroItem then
            local o,v=pcall(GetMacroItem,id)
            if o and safeText(v)~='' then name=name..' > '..safeText(v) end
        end
        if GetMacroSpell then
            local o,v=pcall(GetMacroSpell,id)
            if o and safeText(v)~='' then name=name..' > '..safeText(v) end
        end
    end
    if name=='' then name=kind..' '..id end
    return kind,id,name
end
local function rebuildSemBindings()
    if InCombatLockdown then
        local ok,combat=pcall(InCombatLockdown)
        if ok and combat then return end
    end
    local rows={}
    if type(GetNumBindings)=='function' and type(GetBinding)=='function' then
        local ok,count=pcall(GetNumBindings)
        if ok and type(count)=='number' then
            for i=1,math.min(count,350) do
                local r={pcall(GetBinding,i)}
                if r[1] and type(r[2])=='string' then
                    local cmd=r[2]
                    for j=4,#r do
                        local key=safeText(r[j])
                        if key~='' then
                            local kind,id,name=resolveCommand(cmd)
                            rows[#rows+1]=key..'|'..cmd..'|'..kind..'|'..id..'|'..name
                        end
                    end
                end
            end
        end
    end
    table.sort(rows)
    semDirty=false
    local fingerprint=table.concat(rows,'\n')
    if fingerprint==semFingerprint then return end
    semFingerprint=fingerprint
    semGeneration=(semGeneration+1)%256
    for i,msg in ipairs(rows) do rows[i]='B|'..semGeneration..'|'..msg end
    semBindings=rows
    semBindingIndex=1
    emitSem('R|'..semGeneration..'|'..#rows)
end
local function semanticEvent(event, ...)
    local first, second, third = ...
    local ok=pcall(function()
        if event=='UNIT_SPELLCAST_SUCCEEDED' or event=='UNIT_SPELLCAST_CHANNEL_START'
           or event=='UNIT_SPELLCAST_START' or event=='UNIT_SPELLCAST_FAILED'
           or event=='UNIT_SPELLCAST_INTERRUPTED' then
            local unit=first
            if unit~='player' then return end
            local spellId=third
            if type(spellId)~='number' then return end
            local name=spellName(spellId) or ''
            local tag=event=='UNIT_SPELLCAST_SUCCEEDED' and 'S'
                   or event=='UNIT_SPELLCAST_CHANNEL_START' and 'H'
                   or event=='UNIT_SPELLCAST_START' and 'T' or 'F'
            emitSem(tag..'|'..spellId..'|'..safeText(name))
        elseif event=='PLAYER_TARGET_CHANGED' then
            -- Describe a selection, not a successful attack. Combat-restricted
            -- values may be secret: leave identity/status unknown if unreadable.
            local kind, life, name='unknown','unknown',''
            local ok,exists=pcall(UnitExists,'target')
            local readableExists=ok and (not issecretvalue or not issecretvalue(exists))
            if readableExists and type(exists)=='boolean' and not exists then
                kind='none'; life='none'
            elseif readableExists and type(exists)=='boolean' and exists then
                local a,b=pcall(UnitCanAttack,'player','target')
                if a and (not issecretvalue or not issecretvalue(b)) and type(b)=='boolean' then
                    kind=b and 'hostile' or 'nonhostile'
                end
                local c,d=pcall(UnitIsDeadOrGhost,'target')
                if c and (not issecretvalue or not issecretvalue(d)) and type(d)=='boolean' then
                    life=d and 'dead' or 'alive'
                end
                local e,n=pcall(UnitName,'target')
                if e then name=string.sub(safeText(n),1,36) end
            end
            emitSem('G|'..targetSeq..'|'..kind..'|'..life..'|'..name)
        elseif event=='PLAYER_REGEN_DISABLED' then
            emitSem('D|combat_start')
        elseif event=='PLAYER_REGEN_ENABLED' then
            emitSem('D|combat_end')
        elseif event=='LOOT_OPENED' or event=='LOOT_READY' then
            local count=0
            if type(GetNumLootItems)=='function' then
                local ok,n=pcall(GetNumLootItems)
                if ok and type(n)=='number' then count=math.max(0,math.min(n,99)) end
            end
            emitSem('L|'..(event=='LOOT_OPENED' and 'opened' or 'ready')..'|'..count)
        elseif event=='LOOT_SLOT_CLEARED' then
            local slot=type(first)=='number' and first or 0
            emitSem('L|slot_cleared|'..slot)
        elseif event=='LOOT_CLOSED' then
            emitSem('L|closed|0')
        elseif event=='UPDATE_BINDINGS' or event=='ACTIONBAR_SLOT_CHANGED'
               or event=='ACTIONBAR_PAGE_CHANGED' or event=='GET_ITEM_INFO_RECEIVED'
               or event=='UPDATE_MACROS' or event=='PLAYER_ENTERING_WORLD' then
            semDirty=true
        elseif event=='UNIT_AURA' then
            if first~='player' then return end
            local foods={'Food','Drink','Recently Bandaged'}
            for _,aura in ipairs(foods) do
                if findAuraSafely('player',aura,'HELPFUL')=='present' or
                   findAuraSafely('player',aura,'HARMFUL')=='present' then
                    -- Positive aura evidence only; absence/secret is never a failure.
                    if not SEM['lastAura'..aura] or GetTime()-SEM['lastAura'..aura]>8 then
                        SEM['lastAura'..aura]=GetTime()
                        emitSem('A|'..aura..'|present')
                    end
                end
            end
        end
    end)
    if not ok then return end -- client restrictions must not break base telemetry
end
for _,ev in ipairs({'PLAYER_ENTERING_WORLD','UPDATE_BINDINGS','ACTIONBAR_SLOT_CHANGED',
    'ACTIONBAR_PAGE_CHANGED','GET_ITEM_INFO_RECEIVED','UPDATE_MACROS',
    'UNIT_SPELLCAST_SUCCEEDED','UNIT_SPELLCAST_START','UNIT_SPELLCAST_CHANNEL_START',
    'UNIT_SPELLCAST_FAILED','UNIT_SPELLCAST_INTERRUPTED','UNIT_AURA',
    'PLAYER_TARGET_CHANGED','PLAYER_REGEN_DISABLED','PLAYER_REGEN_ENABLED',
    'LOOT_OPENED','LOOT_READY','LOOT_SLOT_CLEARED','LOOT_CLOSED'}) do
    pcall(function() SEM:RegisterEvent(ev) end)
end
SEM:SetScript('OnEvent',function(_, event, ...) semanticEvent(event, ...) end)

-- Post-hooks are observational, do not replace protected game functionality.
if type(hooksecurefunc)=='function' then
    if type(UseAction)=='function' then
        pcall(function() hooksecurefunc('UseAction', function(slot)
            if type(slot)=='number' then
                local kind,id,name=resolveCommand('ACTIONBUTTON'..slot)
                -- UseAction reports the actual slot; GetActionInfo is more precise.
                local ok,k,i=pcall(GetActionInfo,slot)
                if ok and type(k)=='string' and type(i)=='number' then
                    kind,id=k,i
                    if k=='spell' then name=spellName(i) or name
                    elseif k=='item' and GetItemInfo then
                        local yes,n=pcall(GetItemInfo,i); if yes then name=safeText(n) end
                    end
                end
                emitSem('C|'..slot..'|'..safeText(kind)..'|'..safeText(id)..'|'..safeText(name))
            end
        end) end)
    end
    if C_Container and type(C_Container.UseContainerItem)=='function' then
        pcall(function() hooksecurefunc(C_Container,'UseContainerItem',function(bag,slot)
            local item=0
            if C_Container.GetContainerItemID then
                local ok,v=pcall(C_Container.GetContainerItemID,bag,slot)
                if ok and type(v)=='number' then item=v end
            end
            emitSem('I|'..item..'|'..bag..'|'..slot)
        end) end)
    end
end
local semTimer=0
SEM:SetScript('OnUpdate',function(_,dt)
    semTimer=semTimer+dt
    if semTimer<.20 then return end
    semTimer=0
    if semDirty and GetTime()-semLastScan >= 2 then
        semLastScan=GetTime()
        pcall(rebuildSemBindings)
    end
    if not semCurrent or semRepeat<=0 then
        local isEvent = #semEvents>0
        if isEvent then
            semCurrent=table.remove(semEvents,1)
        elseif #semBindings>0 then
            semCurrent=semBindings[semBindingIndex]
            semBindingIndex=semBindingIndex%#semBindings+1
        else
            semCurrent='P|0'
        end
        encodedPacket(semCurrent)
        semRepeat=isEvent and 4 or 3
    end
    semRepeat=semRepeat-1
end)
