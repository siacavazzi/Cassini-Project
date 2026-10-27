"""Synthetic check of a mosaic movie (obs_mosaic.rolling_layout): when a place's newest copy is not made yet or
SPICE could not place it, the copy before it stays up, so no place drops out of the mosaic and comes back.
Run: python web/test_rolling_places.py"""
import os, sys, json, tempfile, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))
import numpy as np
from PIL import Image
import obs_mosaic as om
cache = tempfile.mkdtemp()
offs=[(-400,-400),(400,-400),(-400,400),(400,400)]
fr=[(f"p{i}", f"N{1500000000+i}_1", "CB2", 1000.0+30*i, 600, 0,0,1e6) for i in range(12)]
u={"key":("JUPITER","OBS","N",0),"frames":fr,"z":1e6,"movie":False,"mosaic":True,"last":1400,"place":[i%4 for i in range(12)]}
u["place"][1] = u["place"][3] = None                       # two frames with no place: both stay up
d=om.folder(u,cache); TD = om._tiles(u, cache, {"blacks":{},"white":1,"gamma":3}); os.makedirs(TD, exist_ok=True)
for i,(_,fid,f,t,*_r) in enumerate(fr):
    im=np.zeros((1448,1448,4),np.uint8); c=(1448-1024)//2; im[c:c+1024,c:c+1024,3]=255; im[c:c+1024,c:c+1024,:3]=60+60*(i//4)
    Image.fromarray(im).save(f"{TD}/{i}.png")
    j={"n":i,"id":fid,"filter":f,"t":t,"offset":list(map(float,offs[i%4])),"box":[-724,-724,1448,1448]}
    if i==5: j={"n":i,"id":fid,"filter":f,"t":t,"why":"not placed"}   # lap 2 place 1: SPICE failed
    if i in (6,): continue                                          # lap 2 place 2: not made yet
    json.dump(j,open(f"{TD}/{i}.json","w"))
json.dump({"key":list(u["key"]),"display_scale":{"blacks":{},"white":1,"gamma":3},"angle":0,"footprint":[-1124,-1124,1124,1124],
 "fixed":True,"view":[2248,2248],"k":2048/2248,"colour":None,"grey":"CB2","whole":False},open(d+"/"+om.PLAN_FILE,"w"))
om.unit_of=lambda fid:(u,[x[1] for x in fr].index(fid))
om.tiles_ahead=lambda *a,**k:None
om.tile=lambda u_,j,c,s: json.load(open(f"{TD}/{j}.json")) if os.path.exists(f"{TD}/{j}.json") else {"n":j,"why":"not made"}
for n in (4,5,6,7):
    data,rep=om.rolling_webp(fr[n][1],512,cache,1)
    im=np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))
    q=[int(im[60:120,60:120,3].mean()>200), int(im[60:120,-120:-60,3].mean()>200), int(im[-120:-60,60:120,3].mean()>200), int(im[-120:-60,-120:-60,3].mean()>200)]
    print(n,q)
    assert all(q), (n,q)
print("no place drops out")
