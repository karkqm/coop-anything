-- Small bounded JSON codec for the local file seam; never executes input text.
local M = { null = {} }
local escapes = {['"']='\\"', ['\\']='\\\\', ['\b']='\\b', ['\f']='\\f',
                 ['\n']='\\n', ['\r']='\\r', ['\t']='\\t'}
local function quote(s)
    return '"' .. s:gsub('[%z\1-\31\\"]', function(c)
        return escapes[c] or string.format('\\u%04x', c:byte())
    end) .. '"'
end
function M.encode(value, depth)
    depth = depth or 0
    assert(depth < 20, 'JSON depth limit')
    if value == M.null or value == nil then return 'null' end
    local kind = type(value)
    if kind == 'string' then return quote(value) end
    if kind == 'boolean' then return tostring(value) end
    if kind == 'number' then
        assert(value == value and math.abs(value) < math.huge, 'nonfinite number')
        return string.format('%.17g', value)
    end
    assert(kind == 'table', 'unsupported JSON type')
    local array, count = true, 0
    for k in pairs(value) do
        count = count + 1
        if type(k) ~= 'number' or k < 1 or k % 1 ~= 0 then array = false end
    end
    if array and count > 0 then
        assert(count == #value, 'sparse JSON array')
        local out = {}
        for i=1,count do out[i] = M.encode(value[i], depth+1) end
        return '[' .. table.concat(out, ',') .. ']'
    end
    local out = {}
    for k,v in pairs(value) do
        assert(type(k) == 'string', 'object key must be a string')
        out[#out+1] = quote(k) .. ':' .. M.encode(v, depth+1)
    end
    table.sort(out)
    return '{' .. table.concat(out, ',') .. '}'
end
function M.decode(text)
    assert(type(text) == 'string' and #text <= 8192, 'JSON size limit')
    local at = 1
    local parse
    local function skip()
        local _, last = text:find('^[ \n\r\t]*', at)
        at = (last or at-1)+1
    end
    local function hex4()
        local raw = text:sub(at, at+3)
        assert(#raw == 4 and raw:match('^%x%x%x%x$'), 'bad unicode escape')
        at = at + 4
        return tonumber(raw, 16)
    end
    local function string_value()
        at=at+1
        local out={}
        while at<=#text do
            local c=text:sub(at,at); at=at+1
            if c=='"' then return table.concat(out) end
            if c=='\\' then
                c=text:sub(at,at); at=at+1
                local unescape={['"']='"',['\\']='\\',['/']='/',b='\b',f='\f',n='\n',r='\r',t='\t'}
                if c=='u' then
                    local n=hex4()
                    if n>=0xd800 and n<=0xdbff then
                        assert(text:sub(at,at+1)=='\\u','missing low surrogate')
                        at=at+2
                        local low=hex4()
                        assert(low>=0xdc00 and low<=0xdfff,'bad low surrogate')
                        n=0x10000+(n-0xd800)*1024+(low-0xdc00)
                    else assert(n<0xdc00 or n>0xdfff,'unpaired low surrogate') end
                    out[#out+1]=utf8.char(n)
                else
                    assert(unescape[c], 'bad escape')
                    out[#out+1]=unescape[c]
                end
            else
                assert(c:byte()>=32,'control character in string')
                out[#out+1]=c
            end
        end
        error('unterminated string')
    end
    parse=function(depth)
        assert(depth<20,'JSON depth limit'); skip()
        local c=text:sub(at,at)
        if c=='"' then return string_value() end
        if c=='{' or c=='[' then
            local object=c=='{'; local close=object and '}' or ']'; at=at+1; skip()
            local out={}
            if text:sub(at,at)==close then at=at+1; return out end
            while true do
                skip()
                local key
                if object then
                    assert(text:sub(at,at)=='"','object key expected')
                    key=string_value(); skip(); assert(text:sub(at,at)==':','colon expected'); at=at+1
                    assert(out[key]==nil,'duplicate key')
                else key=#out+1 end
                out[key]=parse(depth+1); skip()
                c=text:sub(at,at); at=at+1
                if c==close then return out end
                assert(c==',','comma expected')
            end
        end
        for literal,value in pairs({['true']=true,['false']=false,['null']=M.null}) do
            if text:sub(at,at+#literal-1)==literal then at=at+#literal; return value end
        end
        local start=at
        if c=='-' then at=at+1 end
        c=text:sub(at,at)
        if c=='0' then at=at+1
        else
            assert(c:match('^[1-9]$'),'JSON value expected')
            repeat at=at+1 until not text:sub(at,at):match('^%d$')
        end
        if text:sub(at,at)=='.' then
            at=at+1; assert(text:sub(at,at):match('^%d$'),'bad fraction')
            repeat at=at+1 until not text:sub(at,at):match('^%d$')
        end
        c=text:sub(at,at)
        if c=='e' or c=='E' then
            at=at+1; c=text:sub(at,at)
            if c=='+' or c=='-' then at=at+1 end
            assert(text:sub(at,at):match('^%d$'),'bad exponent')
            repeat at=at+1 until not text:sub(at,at):match('^%d$')
        end
        local token=text:sub(start,at-1)
        local n=tonumber(token)
        assert(n and n==n and math.abs(n)<math.huge,'invalid number')
        return n
    end
    local result=parse(0); skip(); assert(at>#text,'trailing JSON data'); return result
end
return M
