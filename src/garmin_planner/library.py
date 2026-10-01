"""Biblioteca privada, extracción local y búsqueda sin llamadas a modelos."""

import hashlib
import json
import posixpath
import re
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from garmin_planner.pro import ProError
from garmin_planner.storage import atomic_write, private_dir

MAX_UPLOAD = 40 * 1024 * 1024
MAX_EXPANDED = 80 * 1024 * 1024
FORMATS = {".epub", ".pdf", ".docx", ".txt", ".md"}


class LibraryError(ProError):
    pass


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0
        self.heading, self.in_heading = "", False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.hidden += 1
        if tag in ("p", "div", "br", "li", "h1", "h2", "h3"):
            self.parts.append("\n")
        if tag in ("h1", "h2") and not self.heading:
            self.in_heading = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("h1", "h2"):
            self.in_heading = False
        if tag in ("p", "div", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.in_heading:
                self.heading += data


def xml(raw):
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", raw, re.I):
        raise LibraryError("El documento contiene XML no admitido.")
    return ET.fromstring(raw)


def archive(path):
    z = ZipFile(path)
    infos = z.infolist()
    if len(infos) > 10000 or sum(i.file_size for i in infos) > MAX_EXPANDED:
        z.close()
        raise LibraryError("El documento descomprimido supera el límite de 80 MB.")
    if any(
        i.flag_bits & 1
        or i.filename.startswith(("/", "\\"))
        or ".." in i.filename.replace("\\", "/").split("/")
        for i in infos
    ):
        z.close()
        raise LibraryError("Archivo cifrado o con rutas no admitidas.")
    return z


def extract(path, kind):
    sections, warnings = [], []
    if kind == ".epub":
        with archive(path) as z:
            container = xml(z.read("META-INF/container.xml"))
            rootfile = container.find(".//{*}rootfile")
            if rootfile is None:
                raise LibraryError("No se encuentra el contenido del EPUB.")
            opf_path = rootfile.attrib["full-path"]
            opf = xml(z.read(opf_path))
            manifest = {i.attrib["id"]: i.attrib for i in opf.findall(".//{*}manifest/{*}item")}
            spine = opf.findall(".//{*}spine/{*}itemref")
            names = []
            for item in spine:
                entry = manifest.get(item.attrib.get("idref"), {})
                href = unquote(entry.get("href", "").split("#")[0])
                name = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), href))
                if name.startswith("../") or name.startswith("/"):
                    raise LibraryError("Ruta de capítulo no admitida.")
                if entry.get("media-type") in ("application/xhtml+xml", "text/html"):
                    names.append(name)
            if "META-INF/encryption.xml" in z.namelist():
                encrypted = xml(z.read("META-INF/encryption.xml"))
                paths = {
                    unquote(i.attrib.get("URI", ""))
                    for i in encrypted.findall(".//{*}CipherReference")
                }
                if paths.intersection(names):
                    raise LibraryError("El EPUB tiene contenido protegido. Usa una copia sin DRM.")
            for number, name in enumerate(names, 1):
                parser = PlainHTML()
                parser.feed(z.read(name).decode("utf-8-sig"))
                locator = (parser.heading.strip()[:160] or f"Sección {number}") + " · " + name
                sections.append((locator, "".join(parser.parts)))
            warnings.append(
                "EPUB: localizadores de sección, sin números de página; imágenes y tablas "
                "complejas pueden perder información."
            )
    elif kind == ".docx":
        with archive(path) as z:
            root = xml(z.read("word/document.xml"))
            paragraphs = [
                "".join(t.text or "" for t in p.findall(".//{*}t")) for p in root.findall(".//{*}p")
            ]
            sections = [("Documento · párrafos", "\n".join(paragraphs))]
            warnings.append("DOCX: se extrae texto; no se conservan maquetación ni páginas.")
    elif kind == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        if reader.is_encrypted:
            raise LibraryError("Usa un PDF sin contraseña ni cifrado.")
        if len(reader.pages) > 1000:
            raise LibraryError("El PDF supera el límite de 1.000 páginas.")
        for number, page in enumerate(reader.pages, 1):
            content = page.get_contents()
            if content and len(content.get_data()) > 10 * 1024 * 1024:
                raise LibraryError("Una página PDF es demasiado compleja para extraerla.")
            sections.append((f"Página {number}", page.extract_text() or ""))
        warnings.append(
            "PDF: sin OCR; las páginas escaneadas y los gráficos pueden no aportar texto."
        )
    else:
        sections = [("Texto", path.read_text(encoding="utf-8-sig"))]
    chunks = []
    for locator, text in sections:
        text = re.sub(r"[ \t]+", " ", text).strip()
        for offset in range(0, len(text), 1040):
            fragment = text[offset : offset + 1200].strip()
            if len(fragment) >= 30:
                chunks.append({"locator": locator, "text": fragment})
    if not chunks:
        raise LibraryError("No hay texto utilizable. En PDF escaneado aplica OCR antes de subirlo.")
    if len(chunks) > 16000:
        raise LibraryError("El documento contiene demasiado texto.")
    return chunks, warnings


class Library:
    def __init__(self, store):
        self.store, self.root = store, store.path.parent / "library"
        private_dir(self.root)
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS library_documents (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0, active INTEGER,
                    latest INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS library_versions (
                    document_id TEXT NOT NULL, version INTEGER NOT NULL, filename TEXT NOT NULL,
                    kind TEXT NOT NULL, sha256 TEXT NOT NULL, created TEXT NOT NULL,
                    status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
                    warnings TEXT NOT NULL DEFAULT '[]',
                    PRIMARY KEY(document_id, version)
                );
                CREATE TABLE IF NOT EXISTS library_chunks (
                    document_id TEXT NOT NULL, version INTEGER NOT NULL, number INTEGER NOT NULL,
                    locator TEXT NOT NULL, text TEXT NOT NULL,
                    PRIMARY KEY(document_id, version, number)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS library_search USING fts5(
                    document_id UNINDEXED, version UNINDEXED, number UNINDEXED, text,
                    tokenize='unicode61 remove_diacritics 2'
                );
            """)

    def upload(self, content, filename, title="", author="", document_id=None):
        kind = Path(filename).suffix.lower()
        if kind not in FORMATS:
            raise LibraryError("Formatos admitidos: EPUB, PDF, DOCX, TXT y Markdown.")
        if not content or len(content) > MAX_UPLOAD:
            raise LibraryError("Sube un archivo de entre 1 byte y 40 MB.")
        identifier = document_id or uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            doc = db.execute("SELECT * FROM library_documents WHERE id=?", (identifier,)).fetchone()
            if document_id and not doc:
                raise LibraryError("Fuente no encontrada.")
            version = doc["latest"] + 1 if doc else 1
            # La ruta depende únicamente de un UUID interno y una versión entera.
            path = self.root / f"{identifier}-{version}{kind}"
            atomic_write(path, content)
            try:
                if not doc:
                    db.execute(
                        "INSERT INTO library_documents(id,title,author) VALUES(?,?,?)",
                        (identifier, title.strip() or Path(filename).stem[:200], author.strip()),
                    )
                db.execute(
                    "UPDATE library_documents SET latest=? WHERE id=?", (version, identifier)
                )
                db.execute(
                    "INSERT INTO "
                    "library_versions(document_id,version,filename,kind,sha256,created,status) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (
                        identifier,
                        version,
                        filename[:250],
                        kind,
                        hashlib.sha256(content).hexdigest(),
                        datetime.now(UTC).isoformat(),
                        "pending",
                    ),
                )
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return {"document_id": identifier, "version": version}

    def listing(self):
        with self.store.connect() as db:
            documents = [
                dict(r) for r in db.execute("SELECT * FROM library_documents ORDER BY title")
            ]
            for doc in documents:
                doc["enabled"] = bool(doc["enabled"])
                doc["versions"] = []
                for row in db.execute(
                    "SELECT v.*, (SELECT count(*) FROM library_chunks c WHERE "
                    "c.document_id=v.document_id AND c.version=v.version) AS chunks FROM "
                    "library_versions v WHERE document_id=? ORDER BY version DESC",
                    (doc["id"],),
                ):
                    v = dict(row)
                    v["warnings"] = json.loads(v["warnings"])
                    doc["versions"].append(v)
        return {"documents": documents}

    def process(self, identifier):
        with self.store.connect() as db:
            doc = db.execute("SELECT * FROM library_documents WHERE id=?", (identifier,)).fetchone()
            if not doc:
                raise LibraryError("Fuente no encontrada.")
            version = doc["latest"]
            v = db.execute(
                "SELECT * FROM library_versions WHERE document_id=? AND version=?",
                (identifier, version),
            ).fetchone()
            if v["status"] == "ready":
                return {"document_id": identifier, "version": version}
        try:
            chunks, warnings = extract(self.root / f"{identifier}-{version}{v['kind']}", v["kind"])
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                latest = db.execute(
                    "SELECT latest FROM library_documents WHERE id=?", (identifier,)
                ).fetchone()[0]
                if latest != version:
                    raise LibraryError(
                        "Se ha subido otra versión. Procesa la actualización más reciente."
                    )
                db.executemany(
                    "INSERT INTO library_chunks VALUES(?,?,?,?,?)",
                    [
                        (identifier, version, i, c["locator"], c["text"])
                        for i, c in enumerate(chunks)
                    ],
                )
                db.executemany(
                    "INSERT INTO library_search VALUES(?,?,?,?)",
                    [(identifier, version, i, c["text"]) for i, c in enumerate(chunks)],
                )
                db.execute(
                    "UPDATE library_versions SET status='ready',detail='',warnings=? WHERE "
                    "document_id=? AND version=?",
                    (json.dumps(warnings), identifier, version),
                )
                db.execute(
                    "UPDATE library_documents SET active=? WHERE id=?", (version, identifier)
                )
        except Exception as exc:
            message = (
                str(exc)
                if isinstance(exc, LibraryError)
                else "No se pudo leer el documento. Comprueba su formato y que no tenga protección."
            )
            with self.store.connect() as db:
                db.execute(
                    "UPDATE library_versions SET status='failed',detail=? WHERE document_id=? AND "
                    "version=?",
                    (message, identifier, version),
                )
            raise LibraryError(message) from exc
        return {"document_id": identifier, "version": version, "chunks": len(chunks)}

    def enable(self, identifier, enabled):
        with self.store.connect() as db:
            doc = db.execute(
                "SELECT active FROM library_documents WHERE id=?", (identifier,)
            ).fetchone()
            if not doc:
                raise LibraryError("Fuente no encontrada.")
            if enabled and doc["active"] is None:
                raise LibraryError(
                    "Procesa primero el documento antes de seleccionarlo para el coach."
                )
            db.execute(
                "UPDATE library_documents SET enabled=? WHERE id=?", (int(enabled), identifier)
            )
        return {"ok": True}

    def preview(self, identifier):
        with self.store.connect() as db:
            doc = db.execute(
                "SELECT active FROM library_documents WHERE id=?", (identifier,)
            ).fetchone()
            if not doc:
                raise LibraryError("Fuente no encontrada.")
            rows = db.execute(
                "SELECT locator,text FROM library_chunks WHERE document_id=? AND version=? "
                "ORDER BY number LIMIT 3",
                (identifier, doc["active"]),
            ).fetchall()
        return {"version": doc["active"], "fragments": [dict(r) for r in rows]}

    def retrieve(self, setup):
        # Búsquedas por tema evitan que una disciplina monopolice todos los extractos.
        aliases = {
            "triathlon": ["triathlon", "triatlón", "brick", "transition"],
            "running": ["running", "run", "carrera"],
            "trail": ["trail", "hill", "desnivel"],
            "cycling": ["cycling", "bike", "ciclismo"],
            "swimming": ["swimming", "swim", "natación"],
            "strength": ["strength", "fuerza"],
        }
        primary = next(e for e in setup["events"] if e["priority"] == "primary")
        groups = [aliases.get(primary["sport"], []) + ["periodization", "periodización"]]
        groups += [aliases[s] for s in setup["profile"]["sports"] if s in aliases]
        if setup["profile"].get("strength"):
            groups.append(aliases["strength"])
        groups.append(["recovery", "recuperación", "training", "entrenamiento"])
        candidates = []
        with self.store.connect() as db:
            for terms in groups:
                query = " OR ".join('"' + t + '"' for t in dict.fromkeys(terms))
                candidates.append(
                    db.execute(
                        """SELECT c.*, d.title,d.author FROM library_search s
                    JOIN library_documents d ON d.id=s.document_id
                        AND d.enabled=1 AND d.active=s.version
                    JOIN library_chunks c ON c.document_id=s.document_id
                        AND c.version=s.version AND c.number=s.number
                    WHERE library_search MATCH ? ORDER BY bm25(library_search) LIMIT 12""",
                        (query,),
                    ).fetchall()
                )
        chosen, seen = [], set()
        for depth in range(12):
            for rows in candidates:
                if depth >= len(rows):
                    continue
                row = rows[depth]
                identifier = f"{row['document_id']}:{row['version']}:{row['number']}"
                if identifier in seen:
                    continue
                seen.add(identifier)
                chosen.append(
                    {
                        "id": identifier,
                        "title": row["title"],
                        "author": row["author"],
                        "version": row["version"],
                        "locator": row["locator"],
                        "text": row["text"],
                    }
                )
                if len(chosen) == 6:
                    return chosen
        return chosen
