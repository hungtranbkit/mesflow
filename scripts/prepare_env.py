from pathlib import Path
import secrets, re, urllib.parse
p=Path('.env')
s=p.read_text()
def setv(k,v):
    global s
    if re.search(rf'^{re.escape(k)}=',s,re.M):
        s=re.sub(rf'^{re.escape(k)}=.*$',f'{k}={v}',s,flags=re.M)
    else:
        s+=f'\n{k}={v}'
def vals():
    out={}
    for line in s.splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1); out[k]=v
    return out
v=vals()
if v.get('MESFLOW_SECRET_KEY') in ('','CHANGE_ME',None): setv('MESFLOW_SECRET_KEY',secrets.token_hex(32))
if v.get('POSTGRES_PASSWORD') in ('','CHANGE_ME',None): setv('POSTGRES_PASSWORD',secrets.token_hex(32))
v=vals()
url=f"postgresql://{urllib.parse.quote(v.get('POSTGRES_USER','mesflow_v65'))}:{urllib.parse.quote(v['POSTGRES_PASSWORD'])}@postgres:5432/{urllib.parse.quote(v.get('POSTGRES_DB','mesflow_v65'))}"
setv('DATABASE_URL',url)
p.write_text(s.strip()+'\n')
