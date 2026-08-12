from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile,ZipFile
from io import BytesIO
from werkzeug.exceptions import RequestEntityTooLarge

DRAWING_MAX_BYTES=20*1024*1024
EXCEL_MAX_BYTES=25*1024*1024
ACTIVE_EXTENSIONS={'.svg','.html','.htm','.js'}
DRAWING_EXTENSIONS={'.pdf','.png','.jpg','.jpeg','.webp','.dxf','.dwg','.step','.stp','.iges','.igs','.zip'}

@dataclass(frozen=True)
class ValidatedUpload:
    original_name:str
    extension:str
    data:bytes

def _safe_display_name(filename:str)->str:
    name=Path(str(filename).replace('\\','/')).name.strip()
    if not name or name in {'.','..'}:raise ValueError('invalid filename')
    return name[:255]

def _read_limited(stream,limit:int)->bytes:
    data=stream.read(limit+1)
    if len(data)>limit:raise RequestUploadTooLarge(limit)
    if not data:raise ValueError('empty file')
    return data

class RequestUploadTooLarge(RequestEntityTooLarge):
    def __init__(self,limit:int):super().__init__(description=f'file exceeds {limit} bytes');self.limit=limit

def _verify_known_magic(ext:str,data:bytes)->None:
    valid={
      '.pdf':data.startswith(b'%PDF-'),
      '.png':data.startswith(b'\x89PNG\r\n\x1a\n'),
      '.jpg':data.startswith(b'\xff\xd8\xff'),'.jpeg':data.startswith(b'\xff\xd8\xff'),
      '.webp':len(data)>=12 and data[:4]==b'RIFF' and data[8:12]==b'WEBP',
      '.zip':data.startswith((b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08')),
    }
    if ext in valid and not valid[ext]:raise ValueError('file content does not match extension')

def validate_drawing_upload(file_storage)->ValidatedUpload:
    original=_safe_display_name(file_storage.filename)
    ext=Path(original).suffix.lower()
    if ext in ACTIVE_EXTENSIONS:raise ValueError('active document uploads are not supported')
    if ext not in DRAWING_EXTENSIONS:raise ValueError('unsupported drawing file type')
    data=_read_limited(file_storage.stream,DRAWING_MAX_BYTES);_verify_known_magic(ext,data)
    return ValidatedUpload(original,ext,data)

def validate_excel_upload(file_storage)->ValidatedUpload:
    original=_safe_display_name(file_storage.filename)
    if Path(original).suffix.lower()!='.xlsx':raise ValueError('only .xlsx files are supported')
    data=_read_limited(file_storage.stream,EXCEL_MAX_BYTES);_verify_known_magic('.zip',data)
    try:
        with ZipFile(BytesIO(data)) as archive:
            names=archive.namelist()
            if '[Content_Types].xml' not in names or not any(n.startswith('xl/') for n in names):raise ValueError('invalid XLSX structure')
    except BadZipFile as exc:raise ValueError('invalid XLSX archive') from exc
    return ValidatedUpload(original,'.xlsx',data)
