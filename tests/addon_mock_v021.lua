-- Run: texlua tests/addon_mock_v021.lua
-- Simulates a WoW UI enough to load, tick, and decode the addon optical records.
local frames={}
UIParent={}
SlashCmdList={}
function CreateFrame(kind,name,parent)
  local self={kind=kind,name=name,children={}}
  if name then _G[name]=self end
  function self:SetSize(w,h) self.w=w;self.h=h end
  function self:SetPoint(...) self.point={...} end
  function self:SetFrameStrata(...) end
  function self:SetClampedToScreen(...) end
  function self:Show() end
  function self:Hide() end
  function self:RegisterEvent(ev) end
  function self:SetScript(name,callback) self[name]=callback end
  function self:CreateTexture()
    local t={}
    function t:SetSize(w,h) self.w=w;self.h=h end
    function t:SetPoint(...) self.point={...} end
    function t:SetColorTexture(r,g,b,a) self.rgb={r,g,b} end
    function t:SetAllPoints(...) end
    function t:SetShown(...) end
    table.insert(self.children,t)
    return t
  end
  function self:SetStatusBarTexture(...) end
  function self:SetStatusBarColor(...) end
  function self:SetMinMaxValues(...) end
  function self:SetValue(...) end
  table.insert(frames,self)
  return self
end
local clock=0
function GetTime() return clock end
function UnitExists(u) return u=='player' end
function UnitHealthMax() return 100 end
function UnitHealth() return 100 end
function UnitPowerMax() return 100 end
function UnitPower() return 70 end
function GetActionBarPage() return 1 end
function InCombatLockdown() return false end
function GetNumBindings() return 2 end
function GetBinding(i)
  if i==1 then return 'ACTIONBUTTON2','ACTIONBAR','2' end
  return 'MULTIACTIONBAR1BUTTON7','ACTIONBAR','SHIFT-G'
end
function GetActionInfo(slot)
  if slot==2 then return 'item',117 end
  if slot==67 then return 'macro',9 end
  return nil
end
function GetItemInfo(id)
  if id==117 then return 'Food' end
  return nil
end
function GetMacroInfo(id) return 'Bandage' end
function GetMacroItem(id) return 'Heavy Linen Bandage' end
function GetSpellInfo(id) if id==8092 then return 'Mind Blast' end end
function hooksecurefunc(...) end
function GetActionText(...) end
local f,e=loadfile('addons/PriestBridge/PriestBridge.lua')
assert(f,e)
f()
local sem
for _,frame in ipairs(frames) do
  if frame.kind=='Frame' and frame.name==nil and frame.OnUpdate and frame.OnEvent then sem=frame end
end
assert(sem,'semantic frame not found')
sem.OnEvent(sem,'PLAYER_ENTERING_WORLD')
local seen={}
for i=1,90 do
  clock=clock+.21
  if i==30 then sem.OnEvent(sem,'UNIT_SPELLCAST_SUCCEEDED','player','cast-guid',8092) end
  if i%5==0 then sem.OnEvent(sem,'ACTIONBAR_SLOT_CHANGED',2) end
  sem.OnUpdate(sem,.21)
  local bytes={}
  for _,tile in ipairs(PriestBridgeFrame.children) do
    local pp=tile.point
    if pp and pp[4] and pp[5] then
      local x=pp[4]
      local y=-pp[5]
      if x>=180 and x<=250 and y>=20 and y<=50 then
        local col=math.floor((x-180)/10)
        local row=math.floor((y-20)/10)
        local n=row*8+col
        bytes[3*n+1]=math.floor(tile.rgb[1]*255+.5)
        bytes[3*n+2]=math.floor(tile.rgb[2]*255+.5)
        bytes[3*n+3]=math.floor(tile.rgb[3]*255+.5)
      end
    end
  end
  assert(bytes[1]==166, 'optical magic missing')
  local seq=bytes[3]+bytes[4]*256
  local len=bytes[5]
  local checksum=bytes[6]+bytes[7]*256
  local sum=(seq+len)%65536
  local chars={}
  for j=1,len do
    local b=bytes[7+j]
    sum=(sum+b)%65536
    chars[#chars+1]=string.char(b)
  end
  assert(sum==checksum,'checksum mismatch')
  local msg=table.concat(chars)
  seen[msg]=true
end
assert(seen['B|1|2|ACTIONBUTTON2|item|117|Food'],'2 binding missing')
assert(seen['S|8092|Mind Blast'],'spell success event not encoded')
assert(seen['B|1|SHIFT-G|MULTIACTIONBAR1BUTTON7|macro|9|Bandage > Heavy Linen Bandage'],'macro binding missing')
print('LUA MOCK OK: bindings and optical checksums validated')
