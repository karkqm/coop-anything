-- Opt-in local bot. This file is never read from a network snapshot.
local M={}
local function triple(v)
    if type(v)~='table' or #v~=3 then return false end
    for _,n in ipairs(v) do
        if type(n)~='number' or n~=n or math.abs(n)>1e8 then return false end
    end
    return true
end
function M.new(json,directory)
    local self={id=0,hold=nil}
    local function validate(pawn,p)
        local k=StaticFindObject('/Script/Engine.Default__KismetSystemLibrary')
        local ignore={pawn}
        if _G.GhostrunnerSync and _G.GhostrunnerSync.body and _G.GhostrunnerSync.body:IsValid() then
            ignore[#ignore+1]=_G.GhostrunnerSync.body
        end
        local red,green={R=1,G=0,B=0,A=1},{R=0,G=1,B=0,A=1}
        local floor={}
        local found=k:LineTraceSingle(pawn,{X=p[1],Y=p[2],Z=p[3]+10},
              {X=p[1],Y=p[2],Z=p[3]-400},0,false,ignore,0,floor,true,red,green,0)
        assert(found and floor.ImpactNormal.Z>.7,'QA target has no walkable floor')
        local height=p[3]-floor.ImpactPoint.Z
        local half=pawn.CapsuleComponent:GetScaledCapsuleHalfHeight()
        local radius=pawn.CapsuleComponent:GetScaledCapsuleRadius()
        assert(height>=half and height<=half+4,'QA target is not at player standing height')
        local blocked={}
        local overlaps=k:CapsuleTraceSingle(pawn,{X=p[1],Y=p[2],Z=p[3]},
              {X=p[1],Y=p[2],Z=p[3]+.5},radius,half,0,false,ignore,0,blocked,true,red,green,0)
        assert(not overlaps,'QA target capsule overlaps world geometry')
        return {floor_z=floor.ImpactPoint.Z,height=height,capsule_half_height=half,
                capsule_radius=radius,capsule_clear=true}
    end
    function self:update(pc,pawn,config)
        local f=io.open(directory..'/qa.json','rb')
        local command=nil
        if f then
            local raw=f:read(8193); f:close()
            local ok,value=pcall(json.decode,raw)
            if ok then command=value end
        end
        if type(command)=='table' and type(command.id)=='number' and command.id%1==0 and command.id>self.id then
            if command.action=='hold' and triple(command.position) and triple(command.rotation) then
                self.validation=validate(pawn,command.position)
                self.hold=command
                self.walk=nil
                self.id=command.id
            elseif command.action=='walk' and triple(command.direction) then
                self.hold=nil; self.walk=command; self.id=command.id
                pawn.CharacterMovement:SetMovementMode(1,0)
            elseif command.action=='attack' then
                pawn['Melee Attack'](pawn)
                self.id=command.id
            elseif command.action=='release' then
                self.hold=nil; self.walk=nil; self.id=command.id
                pawn.CharacterMovement:SetMovementMode(1,0)
                pawn:EnableInput(pc)
            elseif command.action=='mutation' and type(command.drop_receive)=='boolean' then
                config.mutation_drop_receive=command.drop_receive
                self.id=command.id
            elseif command.action=='mutation' and type(command.freeze_sword)=='boolean' then
                config.mutation_freeze_sword=command.freeze_sword
                self.id=command.id
            end
        end
        if self.hold then
            local p,r=self.hold.position,self.hold.rotation
            pawn:DisableInput(pc)
            pawn.CharacterMovement:DisableMovement()
            pawn.CharacterMovement:StopMovementImmediately()
            assert(pawn:K2_SetActorLocation({X=p[1],Y=p[2],Z=p[3]},false,{},true),'QA source teleport failed')
            pc:SetControlRotation({Pitch=r[1],Yaw=r[2],Roll=r[3]})
            pawn:K2_SetActorRotation({Pitch=r[1],Yaw=r[2],Roll=r[3]},true)
        elseif self.walk then
            local d=self.walk.direction
            pawn:DisableInput(pc)
            pawn:AddMovementInput({X=d[1],Y=d[2],Z=d[3]},1,true)
        end
    end
    return self
end
return M
