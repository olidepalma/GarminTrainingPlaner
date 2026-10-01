import io
import json
import time
from datetime import date
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from test_coach import FakePro, plan, setup

from garmin_planner.app import create_app
from garmin_planner.coach import Accept, Coach, Generate
from garmin_planner.config import Settings
from garmin_planner.library import Library, LibraryError
from garmin_planner.pro import ProError
from garmin_planner.storage import Store


def epub(text="Triathlon training: recovery, swimming, cycling and running require balance."):
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as z:
        z.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="OEBPS/book.opf"/></rootfiles></container>',
        )
        z.writestr(
            "OEBPS/book.opf",
            '<package><manifest><item id="c" href="chapter.xhtml" '
            'media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="c"/></spine></package>',
        )
        z.writestr(
            "OEBPS/chapter.xhtml",
            "<html><head><title>Ignore head</title><script>UNTRUSTED_SCRIPT</script>"
            "</head><body><h1>Base training</h1><p>" + text + "</p></body></html>",
        )
    return stream.getvalue()


def test_explicit_processing_and_selection(tmp_path):
    store = Store(tmp_path)
    store.set("coach_calendar", [{"title": "Do not change"}])
    library = Library(store)
    identifier = library.upload(epub(), "book.epub", "My source", "Author")["document_id"]
    doc = library.listing()["documents"][0]
    assert doc["active"] is None and not doc["enabled"]
    assert library.retrieve(setup(date.today())) == []
    with pytest.raises(LibraryError, match="Procesa"):
        library.enable(identifier, True)
    library.process(identifier)
    assert library.retrieve(setup(date.today())) == []
    sample = library.preview(identifier)["fragments"][0]
    assert "Base training" in sample["locator"]
    assert "UNTRUSTED_SCRIPT" not in sample["text"]
    library.enable(identifier, True)
    sources = library.retrieve(setup(date.today()))
    assert sources[0]["version"] == 1 and sources[0]["title"] == "My source"
    assert store.get("coach_calendar") == [{"title": "Do not change"}]
    library.enable(identifier, False)
    assert library.retrieve(setup(date.today())) == []


def test_version_replacement_and_failed_update_preserve_active(tmp_path):
    library = Library(Store(tmp_path))
    identifier = library.upload(
        epub("Triathlon training ORIGINAL recovery swimming cycling running."), "old.epub"
    )["document_id"]
    library.process(identifier)
    library.enable(identifier, True)
    library.upload(
        epub("Triathlon training REPLACEMENT recovery swimming cycling running."),
        "new.epub",
        document_id=identifier,
    )
    assert library.retrieve(setup(date.today()))[0]["version"] == 1
    library.process(identifier)
    assert library.retrieve(setup(date.today()))[0]["version"] == 2
    assert "REPLACEMENT" in library.preview(identifier)["fragments"][0]["text"]
    library.upload(b"broken", "broken.epub", document_id=identifier)
    with pytest.raises(LibraryError):
        library.process(identifier)
    doc = library.listing()["documents"][0]
    assert doc["active"] == 2 and doc["enabled"]
    assert [v["status"] for v in doc["versions"]] == ["failed", "ready", "ready"]
    with library.store.connect() as db:
        assert db.execute("SELECT count(*) FROM library_chunks WHERE version=1").fetchone()[0] > 0


def test_formats_and_unreadable_documents(tmp_path):
    library = Library(Store(tmp_path))
    for kind in ("txt", "md"):
        identifier = library.upload(
            b"Endurance training and strength with adequate recovery.", "reference." + kind
        )["document_id"]
        library.process(identifier)
        assert library.preview(identifier)["fragments"]
    stream = io.BytesIO()
    with ZipFile(stream, "w") as z:
        z.writestr(
            "word/document.xml",
            "<document><body><p><r><t>Training and recovery recommendations from my coach."
            "</t></r></p></body></document>",
        )
    identifier = library.upload(stream.getvalue(), "coach.docx")["document_id"]
    library.process(identifier)
    assert "recommendations" in library.preview(identifier)["fragments"][0]["text"]
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    stream = io.BytesIO()
    writer.write(stream)
    identifier = library.upload(stream.getvalue(), "scan.pdf")["document_id"]
    with pytest.raises(LibraryError, match="OCR"):
        library.process(identifier)
    writer.encrypt("private")
    stream = io.BytesIO()
    writer.write(stream)
    identifier = library.upload(stream.getvalue(), "encrypted.pdf")["document_id"]
    with pytest.raises(LibraryError, match="cifrado"):
        library.process(identifier)


def test_bounded_retrieval_and_private_paths(tmp_path):
    library = Library(Store(tmp_path))
    identifier = library.upload(
        ("Swimming cycling running training recovery. " * 10000).encode(), "../../reference.txt"
    )["document_id"]
    library.process(identifier)
    library.enable(identifier, True)
    sources = library.retrieve(setup(date.today()))
    assert len(sources) <= 6
    assert sum(len(s["text"]) for s in sources) <= 7200
    assert all(p.parent == library.root for p in library.root.iterdir())
    with pytest.raises(LibraryError, match="Formato"):
        library.upload(b"code", "bad.exe")
    with pytest.raises(LibraryError):
        library.upload(b"", "empty.txt")
    with pytest.raises(LibraryError, match="encontrada"):
        library.upload(b"Text", "a.txt", document_id="../outside")


def test_archive_and_xml_limits(tmp_path, monkeypatch):
    library = Library(Store(tmp_path))
    stream = io.BytesIO()
    with ZipFile(stream, "w") as z:
        z.writestr("../escape", "x")
    identifier = library.upload(stream.getvalue(), "bad.epub")["document_id"]
    with pytest.raises(LibraryError, match="rutas"):
        library.process(identifier)
    monkeypatch.setattr("garmin_planner.library.MAX_EXPANDED", 10)
    identifier = library.upload(epub(), "large.epub")["document_id"]
    with pytest.raises(LibraryError, match="descomprimido"):
        library.process(identifier)


def test_draft_snapshots_and_unknown_citations(tmp_path):
    store = Store(tmp_path)
    today = date.today()
    store.set("coach_setup", setup(today))
    library = Library(store)
    identifier = library.upload(epub(), "source.epub")["document_id"]
    library.process(identifier)
    library.enable(identifier, True)
    sources = library.retrieve(setup(today))
    result_plan = plan(today)
    result_plan.citations = [sources[0]["id"]]
    pro = FakePro(result_plan)
    coach = Coach(store, pro, "Europe/Madrid", library)
    draft_id = coach.generate(Generate(start=today, mode="initial"))["draft_id"]
    payload = json.loads(pro.calls[0][1])
    assert payload["sources"][0]["id"] == sources[0]["id"]
    library.upload(
        epub("New training source for running and cycling."), "new.epub", document_id=identifier
    )
    library.process(identifier)
    assert store.get("coach_draft")["sources_snapshot"][0]["version"] == 1
    coach.accept(Accept(draft_id=draft_id, plan=result_plan))
    assert store.get("coach_accepted")["sources_snapshot"][0]["version"] == 1
    with store.connect() as db:
        archived = json.loads(
            db.execute("SELECT payload FROM coach_history WHERE id=?", (draft_id,)).fetchone()[0]
        )
    assert archived["sources_snapshot"][0]["version"] == 1
    result_plan.citations = ["fabricated-page"]
    with pytest.raises(ProError, match="referencia"):
        coach.generate(Generate(start=today, mode="weekly"))


def test_library_routes_private_csrf_and_manual_jobs(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, auto_sync=False))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/api/library").status_code == 401
        assert client.get("/api/coach/review").status_code == 401
        csrf = client.get("/api/session").json()["csrf"]
        login = client.post(
            "/api/session/login",
            json={"password": "test-library-password"},
            headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf},
        ).json()
        headers = {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": login["csrf"]}
        fake = FakePro(plan(date.today()))
        app.state.pro.respond = fake.respond
        assert client.post("/api/library/upload?filename=a.epub", content=epub()).status_code == 403
        result = client.post("/api/library/upload?filename=a.epub", content=epub(), headers=headers)
        assert result.status_code == 200
        identifier = result.json()["document_id"]
        assert client.get("/api/library").json()["documents"][0]["active"] is None
        job = client.post(f"/api/library/{identifier}/process", json={}, headers=headers).json()[
            "job_id"
        ]
        for _ in range(100):
            status = client.get(f"/api/jobs/{job}").json()
            if status["status"] != "running":
                break
            time.sleep(0.01)
        assert status["status"] == "completed"
        assert (
            client.post(
                f"/api/library/{identifier}/enabled", json={"enabled": True}, headers=headers
            ).status_code
            == 200
        )
        assert client.get(f"/api/library/{identifier}/preview").json()["fragments"]
        assert client.get("/api/coach").json()["calendar"] is None
        assert fake.calls == []
        review = client.get("/api/coach/review").json()
        assert (
            client.post(
                "/api/coach/feedback",
                json={"week_start": review["from"], "fatigue": 4, "notes": "Busy week"},
                headers=headers,
            ).status_code
            == 200
        )
        assert client.get("/api/coach/review").json()["feedback"]["fatigue"] == 4
        assert (
            client.post(
                "/api/coach/feedback",
                json={"week_start": review["from"], "fatigue": 99},
                headers=headers,
            ).status_code
            == 422
        )


def test_pdf_text_and_page_locator(tmp_path):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    content = DecodedStreamObject()
    content.set_data(
        b"BT /F1 12 Tf 20 200 Td (Training recovery and strength for endurance.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(content)
    stream = io.BytesIO()
    writer.write(stream)
    library = Library(Store(tmp_path))
    identifier = library.upload(stream.getvalue(), "reference.pdf")["document_id"]
    library.process(identifier)
    fragment = library.preview(identifier)["fragments"][0]
    assert fragment["locator"] == "Página 1"
    assert "Training recovery" in fragment["text"]


def test_xml_entities_and_epub_content_encryption(tmp_path):
    library = Library(Store(tmp_path))
    for encryption in (False, True):
        stream = io.BytesIO()
        with ZipFile(io.BytesIO(epub())) as original, ZipFile(stream, "w") as z:
            for name in original.namelist():
                raw = original.read(name)
                if not encryption and name.endswith("book.opf"):
                    raw = b'<!DOCTYPE package [<!ENTITY nested "attack">]>' + raw
                z.writestr(name, raw)
            if encryption:
                z.writestr(
                    "META-INF/encryption.xml",
                    "<encryption><EncryptedData><CipherData>"
                    '<CipherReference URI="OEBPS/chapter.xhtml"/>'
                    "</CipherData></EncryptedData></encryption>",
                )
        identifier = library.upload(stream.getvalue(), "unsafe.epub")["document_id"]
        with pytest.raises(LibraryError, match="protegido|XML"):
            library.process(identifier)


def test_generate_job_uses_selected_sources_and_accepts_snapshot(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, auto_sync=False))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        csrf = client.get("/api/session").json()["csrf"]
        login = client.post(
            "/api/session/login",
            json={"password": "test-planner-password"},
            headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf},
        ).json()
        headers = {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": login["csrf"]}
        today = date.today()
        client.post("/api/coach/setup", json=setup(today), headers=headers)
        library = app.state.library
        identifier = library.upload(epub(), "source.epub")["document_id"]
        library.process(identifier)
        library.enable(identifier, True)
        result = plan(today)
        result.citations = [library.retrieve(setup(today))[0]["id"]]
        fake = FakePro(result)
        app.state.pro.respond = fake.respond
        job = client.post(
            "/api/coach/generate", json={"start": str(today), "mode": "weekly"}, headers=headers
        ).json()["job_id"]
        for _ in range(100):
            status = client.get(f"/api/jobs/{job}").json()
            if status["status"] != "running":
                break
            time.sleep(0.01)
        assert status["status"] == "completed"
        assert len(fake.calls) == 1
        state = client.get("/api/coach").json()
        assert state["calendar"] is None
        assert state["draft"]["sources_snapshot"][0]["version"] == 1
        client.post(f"/api/library/{identifier}/enabled", json={"enabled": False}, headers=headers)
        response = client.post(
            "/api/coach/accept",
            json={"draft_id": state["draft"]["id"], "plan": state["draft"]["plan"]},
            headers=headers,
        )
        assert response.status_code == 200
        assert len(fake.calls) == 1
        accepted = client.get("/api/coach").json()
        assert len(accepted["calendar"]) == 3
        assert accepted["accepted"]["sources_snapshot"][0]["version"] == 1
