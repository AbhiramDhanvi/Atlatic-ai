"""Small-document synchronous ingestion, adapted from the ATLAS reference."""
import io
from pathlib import Path
from docx import Document
from pypdf import PdfReader
from fastapi import HTTPException
from app.backend import rpc, request
from app.config import settings
from app.models import embed

def parse(blob, suffix):
    if suffix == '.pdf':
        if not blob.startswith(b'%PDF'):
            raise ValueError('Invalid PDF file.')
        reader = PdfReader(io.BytesIO(blob))
        if len(reader.pages) > 100:
            raise ValueError('Use a document with at most 100 pages.')
        return [(i+1, page.extract_text() or '') for i, page in enumerate(reader.pages)]
    if suffix == '.docx':
        import zipfile
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            if sum(x.file_size for x in archive.infolist()) > 25 * 1024 * 1024:
                raise ValueError('Expanded document is too large.')
        doc = Document(io.BytesIO(blob))
        return [(1, '\n'.join([p.text for p in doc.paragraphs] +
                    [' '.join(c.text for c in row.cells) for t in doc.tables for row in t.rows]))]
    return [(1, blob.decode('utf-8'))]

def chunks(text, size=1200, overlap=180):
    text = ' '.join(text.split())
    for pos in range(0, len(text), size-overlap):
        yield text[pos:pos+size]
        if pos+size >= len(text):
            break

def ingest(p, blob, filename):
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.pdf', '.docx', '.txt', '.md'}:
        raise HTTPException(400, 'Allowed types: PDF, DOCX, TXT, MD.')
    if not blob or len(blob) > settings().max_upload_bytes:
        raise HTTPException(400, 'Upload must contain between 1 byte and 5 MB.')
    try:
        parts = []
        for page, text in parse(blob, suffix):
            for part in chunks(text):
                parts.append((page, part))
                if len(parts) > settings().max_chunks:
                    raise ValueError('Document too long for this free demo.')
    except Exception as exc:
        raise HTTPException(400, 'Unable to extract document text. Use a valid text document under the demo limits.') from exc
    if not parts:
        raise HTTPException(400, 'No extractable text. Scanned PDFs need OCR.')
    import uuid
    doc_id = str(uuid.uuid4())
    path = f'{p.subject}/{doc_id}{suffix}'
    records = [{'page': page, 'content': part, 'embedding': embed(part, 'RETRIEVAL_DOCUMENT')}
               for page, part in parts]
    request('POST', '/storage/v1/object/documents/' + path, p.token,
            content=blob, headers={'Content-Type': 'application/octet-stream', 'x-upsert': 'false'})
    try:
        rpc(p, 'commit_document', {'doc_id': doc_id, 'doc_title': filename[:180],
                                  'object_path': path, 'parts': records})
    except Exception:
        try:
            request('DELETE', '/storage/v1/object/documents', p.token, json={'prefixes': [path]})
        except Exception:
            pass
        raise
    return {'id': doc_id, 'title': filename, 'status': 'ready', 'chunks': len(records)}
