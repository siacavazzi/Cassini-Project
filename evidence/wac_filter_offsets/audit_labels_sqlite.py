import json, os, sqlite3
d = json.load(open(os.path.expanduser("~/cassini-build/audit/out/labels.json")))
keys = d["keys"]
db = sqlite3.connect(os.path.expanduser("~/cassini-build/audit/out/labels.sqlite"))
db.execute("DROP TABLE IF EXISTS l")
db.execute("CREATE TABLE l (" + ", ".join(f'"{k}" TEXT' for k in keys) + ")")
db.executemany("INSERT INTO l VALUES (" + ",".join("?" * len(keys)) + ")", [r for r in d["rows"] if len(r) == len(keys)])
db.execute("CREATE INDEX lf ON l (frame)"); db.execute("CREATE INDEX lo ON l (OBSERVATION_ID)")
db.commit(); print("ok")
