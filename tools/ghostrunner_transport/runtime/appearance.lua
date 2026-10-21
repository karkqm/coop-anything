-- Runtime-only visual representation using assets already loaded by the game.
local M={}
local function valid(o) return o and o:IsValid() end
local function xyz(v) return {v.X,v.Y,v.Z} end
local sequence_root='/Game/Visual/Characters/Enemy_Pistol_01/Animations/'
local sequences={idle='ESP_12_pst_Idle',walk='ESP01_pst_Walk_Fwd',run='ESP01_pst_Sprint_Fwd',
                 air='ESP07_pst_jump_away_R',attack='ESP_12_pst_Attack1'}
local blade_path='/Game/Visual/Characters/Hero_Swords/Parts/SK_Katana_Blade.SK_Katana_Blade'
local handle_path='/Game/Visual/Characters/Hero_Swords/Parts/SK_Katana_Handle.SK_Katana_Handle'
local source={attack=0}
local function montage_clip(montage,position)
    -- Export the actual sequence segment and its phase. A montage name containing
    -- "att" alone says nothing about which sword swing or pose is playing.
    if source.clip_montage~=montage:GetFullName() then
        source.clip_montage=montage:GetFullName()
        source.segments={}
        montage.SlotAnimTracks:ForEach(function(_,slot)
            slot:get().AnimTrack.AnimSegments:ForEach(function(_,entry)
                local segment=entry:get()
                local asset=segment.AnimReference
                if valid(asset) then
                    local path=asset:GetFullName():match('^AnimSequence (.+)$')
                    if path and path:find('/Game/Visual/Characters/FFP_View_Models/',1,true)==1 then
                        local rate=segment.AnimPlayRate
                        local first,last=segment.AnimStartTime,segment.AnimEndTime
                        if rate>0 and last>first then
                            source.segments[#source.segments+1]={clip=path,start=segment.StartPos,
                                first=first,last=last,rate=rate,loops=segment.LoopingCount}
                        end
                    end
                end
            end)
        end)
    end
    for _,segment in ipairs(source.segments) do
        local length=segment.last-segment.first
        local elapsed=(position-segment.start)*segment.rate
        if elapsed>=0 and elapsed<length*segment.loops then
            return segment.clip,segment.first+(elapsed%length),length
        end
    end
end
function M.capture(pawn)
    local name=pawn:GetFullName()
    if source.name~=name then
        source={name=name,attack=0}
        local prefix=name:match('^[^ ]+ (.+)$')..'.'
        for _,component in ipairs(FindAllOf('SkeletalMeshComponent') or {}) do
            local cn=component:GetFullName()
            if cn:find(prefix,1,true) and valid(component.SkeletalMesh) then
                local asset=component.SkeletalMesh:GetFullName()
                if asset:find('VM_Hands',1,true) then source.hands=component end
                if asset:find('Hero_Swords',1,true) then source.sword=true end
            end
        end
    end
    local current,position='',0
    local clip,phase,duration=nil,nil,nil
    if valid(source.hands) then
        pcall(function()
            local instance=source.hands:GetAnimInstance()
            local montage=instance:GetCurrentActiveMontage()
            if valid(montage) then
                current=montage:GetFullName()
                position=instance:Montage_GetPosition(montage)
                clip,phase,duration=montage_clip(montage,position)
            end
        end)
    end
    local attacking=current:lower():find('att',1,true)~=nil
    if attacking and (source.montage~=current or position+0.05<(source.montage_position or 0)) then
        source.attack=source.attack+1
    end
    source.montage,source.montage_position=current,position
    return {mode=pawn.CharacterMovement.MovementMode,attack=source.attack,
            attacking=attacking,weapon=source.sword and 'katana' or 'none',montage=current,
            clip=clip,phase=phase,duration=duration}
end
function M.new(body)
    local self={body=body,weapons={},group=nil,attack=-1,assets={}}
    for group,name in pairs(sequences) do
        local asset=StaticFindObject(sequence_root..name..'.'..name)
        if valid(asset) then self.assets[group]=asset end
    end
    assert(self.assets.idle and self.assets.walk and self.assets.run,'avatar animation assets missing')
    local function weapon(path)
        local mesh=StaticFindObject(path)
        assert(valid(mesh),'katana asset missing')
        local actor=body:GetWorld():SpawnActor(StaticFindObject('/Script/Engine.SkeletalMeshActor'),
                body:K2_GetActorLocation(),body:K2_GetActorRotation())
        assert(valid(actor),'weapon SpawnActor failed')
        self.weapons[#self.weapons+1]=actor
        actor:SetOwner(body)
        actor:SetActorEnableCollision(false)
        actor.SkeletalMeshComponent:SetMobility(2)
        actor.SkeletalMeshComponent:SetSimulatePhysics(false)
        actor.SkeletalMeshComponent:SetSkeletalMesh(mesh,true)
        actor:K2_AttachToComponent(body.Mesh,FName('hand_r'),2,2,2,false)
        local parent=actor.SkeletalMeshComponent:GetAttachParent()
        assert(valid(parent) and parent:GetFullName()==body.Mesh:GetFullName(),'weapon attach failed')
        actor.SkeletalMeshComponent:K2_SetRelativeLocation({X=0,Y=0,Z=3.19},false,{},true)
        actor.SkeletalMeshComponent:K2_SetRelativeRotation({Pitch=0,Yaw=-180,Roll=-90},false,{},true)
        return actor
    end
    local ok,problem=pcall(function() weapon(handle_path); weapon(blade_path) end)
    if not ok then
        for _,actor in ipairs(self.weapons) do if valid(actor) then actor:K2_DestroyActor() end end
        error(problem)
    end
    function self:hide(hidden)
        for _,actor in ipairs(self.weapons) do
            if valid(actor) then actor:SetActorHiddenInGame(hidden) end
        end
    end
    function self:destroy()
        for _,actor in ipairs(self.weapons) do
            if valid(actor) then actor:K2_DestroyActor() end
        end
        self.weapons={}
    end
    function self:update(peer)
        local height=peer.half_height or 96
        if height~=self.height then
            body.Mesh:K2_SetRelativeLocation({X=0,Y=0,Z=-height-12},false,{},true)
            self.height=height
        end
        local motion=peer.motion or {mode=1,attack=0,weapon='katana'}
        local speed=math.sqrt(peer.velocity[1]^2+peer.velocity[2]^2)
        local group=speed>550 and 'run' or speed>20 and 'walk' or 'idle'
        if motion.mode==3 and self.assets.air then group='air' end
        if motion.attacking and self.assets.attack then group='attack' end
        if group~=self.group or (group=='attack' and motion.attack~=self.attack) then
            body.Mesh:PlayAnimation(self.assets[group],group~='attack')
            self.group=group
        end
        local rate=1
        if group=='walk' then rate=math.max(0.5,math.min(2,speed/200)) end
        if group=='run' then rate=math.max(0.5,math.min(2.5,speed/600)) end
        body.Mesh:SetPlayRate(rate)
        self.attack=motion.attack
        self:hide(motion.weapon=='none')
        self.weapon_visible=motion.weapon~='none'
    end
    function self:probe()
        local result={group=self.group or 'none',playing=body.Mesh:IsPlaying(),position=body.Mesh:GetPosition(),
            weapon_visible=self.weapon_visible==true,weapon_count=#self.weapons,
            hand=xyz(body.Mesh:GetSocketLocation(FName('hand_r'))),bones={}}
        for _,bone in ipairs({'pelvis','upperarm_l','hand_l','upperarm_r','hand_r','foot_l','foot_r'}) do
            result.bones[bone]=xyz(body.Mesh:GetSocketLocation(FName(bone)))
        end
        result.weapons={}
        for _,actor in ipairs(self.weapons) do
            result.weapons[#result.weapons+1]={mesh=actor.SkeletalMeshComponent.SkeletalMesh:GetFullName(),
                position=xyz(actor:K2_GetActorLocation()),hidden=actor.bHidden,
                socket=actor.SkeletalMeshComponent:GetAttachSocketName():ToString(),
                parent=actor.SkeletalMeshComponent:GetAttachParent():GetFullName()}
        end
        return result
    end
    return self
end
return M
