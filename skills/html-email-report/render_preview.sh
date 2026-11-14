#!/bin/bash
# Render an HTML file full-page with headless Chrome and crop trailing background. Needs google-chrome and Pillow.
# usage: shot.sh in.html out.png width
google-chrome --headless=new --no-sandbox --disable-gpu --hide-scrollbars --allow-file-access-from-files --window-size=$3,30000 --screenshot=/tmp/full.png file://$1 >/dev/null 2>&1
python3 - "$2" <<'PY'
import sys
from PIL import Image
im=Image.open('/tmp/full.png').convert('RGB'); w,h=im.size
bg=im.getpixel((w-1,h-1)); px=im.load()
y=h-1
while y>0 and all(px[x,y]==bg for x in range(0,w,4)): y-=1
im.crop((0,0,w,min(h,y+24))).save(sys.argv[1]); print(im.size,'->',y+24)
PY
