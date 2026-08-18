# Let's compare python step by step with node for seed="test", id=550
def int32(x):
    x = x & 0xFFFFFFFF
    if x >= 0x80000000:
        return x - 0x100000000
    return x

def uint32(x):
    return x & 0xFFFFFFFF

def imul(a, b):
    return (int32(a) * int32(b)) & 0xFFFFFFFF

def Mt(i, l):
    i = uint32(i)
    l = l & 31
    if l == 0:
        return i
    # in JS: (i << l | i >>> (32 - l)) >>> 0
    left = uint32(i << l)
    right = uint32(i >> (32 - l))
    return uint32(left | right)

def ue(i):
    i = uint32(i)
    i = uint32(i ^ (i >> 16))
    i = imul(i, 2246822507)
    i = uint32(i ^ (i >> 13))
    i = imul(i, 3266489909)
    return uint32(i ^ (i >> 16))

# Let's check tr("test", 550)
print("Mt(12345678, 5):", Mt(12345678, 5))
print("ue(12345678):", ue(12345678))
