import re,sys
s=open(sys.argv[1]).read()
for pat in [r'<!doctype html>\n', r'<html[^>]*>\n', r'<head>\n', r'<meta charset="utf-8">\n', r'<meta name="viewport"[^>]*>\n', r'</head>\n', r'<body[^>]*>\n', r'</body>\n?', r'</html>\n?']:
    s=re.sub(pat,'',s,count=1,flags=re.I)
open(sys.argv[2],'w').write(s)
