import urllib.parse

segment_path = "https://embed18.streamc.xyz/RwL87gn3GuqYl3pxgH6rzT/9P3GoCJHdRlu8as+b+79eeqCHXM3bTgqFexYiy2x4Q"

# Default quote
default_quoted = urllib.parse.quote(segment_path)
print("Default quoted:", default_quoted)
# Notice '+' is still '+'!

# Safe quote (quote everything except scheme)
safe_quoted = urllib.parse.quote(segment_path, safe=':/?=')
print("Safe quoted:", safe_quoted)
# Notice '+' is still '+'!

# Strict quote for query param
strict_quoted = urllib.parse.quote(segment_path, safe='')
print("Strict quoted:", strict_quoted)
# Notice '+' becomes '%2B'!

# Test unquoting strict_quoted
unquoted = urllib.parse.unquote(strict_quoted)
print("Unquoted:", unquoted)
assert unquoted == segment_path
print("TEST PASSED!")
