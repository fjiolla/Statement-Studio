import time

from fastapi.testclient import TestClient

from conftest import SAMPLES
from app.main import app


def _wait(c, sid, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = c.get(f"/api/statements/{sid}").json()
        if s["status"] in ("done", "failed", "needs_password"):
            return s
        time.sleep(0.3)
    raise AssertionError("timeout")


def test_upload_password_correct_export():
    import io
    import openpyxl

    with TestClient(app) as c:
        r = c.post("/api/statements", files={"file": ("n.pdf", (SAMPLES / "nimbus_protected.pdf").read_bytes(), "application/pdf")}).json()
        s = _wait(c, r["id"])
        assert s["status"] == "needs_password"
        c.post(f"/api/statements/{r['id']}/password", json={"password": "demo1234"})
        s = _wait(c, r["id"])
        assert s["status"] == "done" and len(s["transactions"]) == 47
        assert s["insights"]["totals"]["count"] == 47

        t = s["transactions"][0]
        u = c.patch(f"/api/transactions/{t['id']}", json={"category": "rent", "apply_to_similar": True, "remember": True}).json()
        assert all(x["category"] == "rent" for x in u["updated"])

        x = c.get(f"/api/export?ids={r['id']}&format=xlsx")
        assert x.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(x.content))
        assert wb.sheetnames[:2] == ["Summary", "Transactions"]
        assert wb["Transactions"].max_row == 48
        csv = c.get(f"/api/export?ids={r['id']}&format=csv")
        assert csv.content.startswith(b"\xef\xbb\xbf") and csv.text.count("\n") == 48


def test_rejects_non_pdf():
    with TestClient(app) as c:
        r = c.post("/api/statements", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
        assert r.status_code == 422 and r.json()["error"]["code"] == "not_a_pdf"
