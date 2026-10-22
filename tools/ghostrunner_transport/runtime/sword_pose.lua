-- Retarget the player's actual sword sequence onto the proxy's arms. All calls
-- are made by the adapter on the game thread; source assets are never modified.
local M={}
local function valid(o) return o and o:IsValid() end
local function xyz(v) return {v.X,v.Y,v.Z} end
local unit={X=1,Y=1,Z=1}
local zero={X=0,Y=0,Z=0}
local root='/Game/Visual/Characters/FFP_View_Models/GhostRunner_VM_Hands/'
local function mul(a,b)
    return {W=a.W*b.W-a.X*b.X-a.Y*b.Y-a.Z*b.Z,
        X=a.W*b.X+a.X*b.W+a.Y*b.Z-a.Z*b.Y,
        Y=a.W*b.Y-a.X*b.Z+a.Y*b.W+a.Z*b.X,
        Z=a.W*b.Z+a.X*b.Y-a.Y*b.X+a.Z*b.W}
end
local function inverse(q) return {W=q.W,X=-q.X,Y=-q.Y,Z=-q.Z} end
local function rotate(q,v)
    local a=mul(mul(q,{W=0,X=v.X,Y=v.Y,Z=v.Z}),inverse(q))
    return {X=a.X,Y=a.Y,Z=a.Z}
end
local function rotator(q)
    local test=q.Z*q.X-q.W*q.Y
    local yaw=math.deg(math.atan(2*(q.W*q.Z+q.X*q.Y),1-2*(q.Y*q.Y+q.Z*q.Z)))
    if test<-.4999995 then
        return {Pitch=-90,Yaw=yaw,Roll=(-yaw-2*math.deg(math.atan(q.X,q.W)))%360}
    elseif test>.4999995 then
        return {Pitch=90,Yaw=yaw,Roll=(yaw-2*math.deg(math.atan(q.X,q.W)))%360}
    end
    return {Pitch=math.deg(math.asin(math.max(-1,math.min(1,2*test)))),Yaw=yaw,
        Roll=math.deg(math.atan(-2*(q.W*q.X+q.Y*q.Z),1-2*(q.X*q.X+q.Y*q.Y)))}
end
local katana_rotation={W=0,X=0,Y=-math.sqrt(.5),Z=-math.sqrt(.5)} -- (0,-180,-90)
function M.new(body,config)
    local self={body=body,actors={},nodes=nil,ready=false,active=false}
    local function sample(mesh)
        local a=body:GetWorld():SpawnActor(StaticFindObject('/Script/Engine.SkeletalMeshActor'),
            body:K2_GetActorLocation(),body:K2_GetActorRotation())
        assert(valid(a),'sword pose sampler spawn failed')
        self.actors[#self.actors+1]=a
        a:SetOwner(body);a:SetActorEnableCollision(false)
        local c=a.SkeletalMeshComponent
        c:SetMobility(2);c:SetSkeletalMesh(mesh,true)
        c.VisibilityBasedAnimTickOption=0
        a:K2_AttachToComponent(body.Mesh,FName('None'),2,2,2,false)
        c:K2_SetRelativeLocation(zero,false,{},true)
        c:K2_SetRelativeRotation({Pitch=0,Yaw=0,Roll=0},false,{},true)
        c:SetRelativeScale3D(unit)
        a:SetActorHiddenInGame(true)
        return c
    end
    function self:destroy()
        if valid(self.mesh) then self.mesh:K2_DestroyComponent(body) end
        for _,a in ipairs(self.actors) do if valid(a) then a:K2_DestroyActor() end end
        self.actors={};self.mesh=nil
    end
    local ok,problem=pcall(function()
        local fp=StaticFindObject(root..'SK_GhostRunner_VM_Hands.SK_GhostRunner_VM_Hands')
        assert(valid(fp),'player hands asset not loaded')
        self.source_bind=sample(fp)
        self.target_bind=sample(body.Mesh.SkeletalMesh)
        self.animated=sample(fp)
        self.idle=StaticFindObject(root..'Animations/H19_1hk_idle_02.H19_1hk_idle_02')
        assert(valid(self.idle),'sword idle not loaded')
        self.clips={}
        for _,name in ipairs({'H10_1hk_att_sword_R1','H10_1hk_att_sword_R2','H11_1hk_att_sword_R3',
            'H12_1hk_att_sword_L1','H12_1hk_att_sword_L2','H13_1hk_att_sword_L3',
            'H04_1hk_zipline_att_sword_L2','H04_1hk_zipline_att_sword_R1'}) do
            local path=root..'Animations/'..name..'.'..name
            local asset=StaticFindObject(path)
            if valid(asset) then self.clips[path]=asset end
        end
        -- This binding accepts the transform parameter but can initialize scale
        -- to zero. Explicit vector/rotator setters below are essential.
        local math_library=StaticFindObject('/Script/Engine.Default__KismetMathLibrary')
        local identity=math_library:MakeTransform(zero,{Pitch=0,Yaw=0,Roll=0},unit)
        self.mesh=body:AddComponentByClass(StaticFindObject('/Script/Engine.PoseableMeshComponent'),false,identity,false)
        assert(valid(self.mesh),'poseable component creation failed')
        body:FinishAddComponent(self.mesh,true,identity)
        self.mesh:SetSkeletalMesh(body.Mesh.SkeletalMesh,true)
        self.mesh:K2_AttachToComponent(body.Mesh,FName('None'),2,2,2,false)
        self.mesh:K2_SetRelativeLocation(zero,false,{},true)
        self.mesh:K2_SetRelativeRotation({Pitch=0,Yaw=0,Roll=0},false,{},true)
        self.mesh:SetRelativeScale3D(unit)
        self.mesh:SetWorldScale3D(unit)
        self.mesh:SetCollisionEnabled(0)
        self.mesh.VisibilityBasedAnimTickOption=0
        self.mesh:SetComponentTickEnabled(true)
        self.mesh:SetVisibility(false,false)
        self.mesh:CopyPoseFromSkeletalComponent(body.Mesh)
        self.animated:PlayAnimation(self.idle,true)
    end)
    if not ok then self:destroy();error(problem) end
    function self:calibrate()
        local nodes={}
        for _,side in ipairs({'l','r'}) do
            for _,bone in ipairs({'clavicle_','upperarm_','lowerarm_','hand_'}) do
                local name=FName(bone..side)
                local a=self.source_bind:GetSocketTransform(name,3)
                local b=self.target_bind:GetSocketTransform(name,3)
                local function initialized(t)
                    local p=t.Translation
                    return math.abs(p.X)+math.abs(p.Y)+math.abs(p.Z)>.01
                end
                if not initialized(a) or not initialized(b) then return false end
                nodes[#nodes+1]={name=name,parent=self.mesh:GetParentBone(name),
                    reference=b,correction=mul(b.Rotation,inverse(a.Rotation))}
            end
        end
        self.nodes=nodes;self.ready=true
        return true
    end
    function self:update(peer,weapons)
        local motion=peer.motion or {}
        local clip=type(motion.clip)=='string' and self.clips[motion.clip] or nil
        local phase=motion.phase
        self.active=motion.attacking==true and valid(clip) and type(phase)=='number'
            and phase==phase and phase>=0 and phase<=clip.SequenceLength
        local selected=self.active and clip or self.idle
        if selected~=self.selected or (self.active and motion.attack~=self.attack) then
            self.animated:PlayAnimation(selected,not self.active)
            self.selected=selected
        end
        local frozen=config and config.qa and config.mutation_freeze_sword
        self.animated:SetPlayRate(frozen and 0 or 1)
        if frozen then self.animated:SetPosition(0,false)
        elseif self.active and peer.tick~=self.peer_tick then self.animated:SetPosition(phase,false) end
        self.attack,self.peer_tick=motion.attack,peer.tick
        self.clip=self.active and motion.clip or self.idle:GetFullName():match('^AnimSequence (.+)$')
        if not self.nodes and not self:calibrate() then return false end
        self.mesh:CopyPoseFromSkeletalComponent(body.Mesh)
        for _,node in ipairs(self.nodes) do
            local source=self.animated:GetSocketTransform(node.name,3)
            local parent=self.mesh:GetBoneTransformByName(node.parent,1)
            local desired=mul(parent.Rotation,mul(node.correction,source.Rotation))
            local position=rotate(parent.Rotation,node.reference.Translation)
            for _,axis in ipairs({'X','Y','Z'}) do position[axis]=position[axis]+parent.Translation[axis] end
            -- Passing an FTransform back through this Lua binding zeroed its
            -- scale. These reflected FVector/FRotator calls preserve the pose.
            self.mesh:SetBoneLocationByName(node.name,position,1)
            self.mesh:SetBoneRotationByName(node.name,rotator(desired),1)
            self.mesh:SetBoneScaleByName(node.name,unit,1)
        end
        body.Mesh:SetVisibility(false,false)
        self.mesh:SetVisibility(true,false)
        local hand=self.animated:GetSocketTransform(FName('hand_r'),0)
        local socket=self.animated:GetSocketTransform(FName('Weapon_rSocket'),0)
        local delta={}
        for _,axis in ipairs({'X','Y','Z'}) do delta[axis]=socket.Translation[axis]-hand.Translation[axis] end
        local grip=mul(inverse(hand.Rotation),socket.Rotation)
        local offset=rotate(inverse(hand.Rotation),delta)
        local translated=rotate(grip,{X=0,Y=0,Z=3.19})
        for _,axis in ipairs({'X','Y','Z'}) do translated[axis]=translated[axis]+offset[axis] end
        self.grip_position,self.grip_rotation=translated,mul(grip,katana_rotation)
        for _,a in ipairs(weapons) do
            local c=a.SkeletalMeshComponent
            if c:GetAttachParent():GetFullName()~=self.mesh:GetFullName() then
                a:K2_AttachToComponent(self.mesh,FName('hand_r'),2,2,2,false)
                c:SetRelativeScale3D(unit)
            end
            c:K2_SetRelativeLocation(translated,false,{},true)
            c:K2_SetRelativeRotation(rotator(self.grip_rotation),false,{},true)
        end
        return true
    end
    function self:probe()
        local result={ready=self.ready,active=self.active,clip=self.clip or '',phase=self.animated:GetPosition()}
        if self.ready then
            -- Use the evaluated socket cache used by the renderer/attachments,
            -- rather than the newly edited pose awaiting the next component tick.
            local hand=self.mesh:GetSocketTransform(FName('hand_r'),0)
            local expected=rotate(hand.Rotation,self.grip_position)
            for _,axis in ipairs({'X','Y','Z'}) do expected[axis]=expected[axis]+hand.Translation[axis] end
            result.expected_grip=xyz(expected)
            result.hand=xyz(hand.Translation)
        end
        return result
    end
    return self
end
return M
