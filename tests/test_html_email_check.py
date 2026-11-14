import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "skills" / "html-email-report" / "check.py"


def run_check(tmp_path, html, text=None, attachments=None):
    html_path = tmp_path / "email.html"
    html_path.write_text(html, encoding="utf-8")
    cmd = [sys.executable, str(CHECK), str(html_path)]
    if text is not None:
        text_path = tmp_path / "email.txt"
        text_path.write_text(text, encoding="utf-8")
        cmd.extend(["--text", str(text_path)])
    if attachments:
        cmd.append("--attachments")
        cmd.extend(str(path) for path in attachments)
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def passing_html():
    return (
        '<html><body><div style="max-width:640px">'
        '<img src="cid:chart.png" width="592" alt="Quarterly chart">'
        "</div></body></html>"
    )


def test_clean_message_passes(tmp_path):
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"png")
    proc = run_check(tmp_path, passing_html(), text="Hello from the report.", attachments=[chart])
    assert proc.returncode == 0
    assert "PASS" in proc.stdout
    assert "FAIL" not in proc.stdout
    assert "WARN" not in proc.stdout


def test_script_style_and_data_uri(tmp_path):
    html = passing_html().replace(
        "<div",
        '<script></script><style></style><img src="data:image/png;base64,aaaa" alt="x" width="1"><div',
    )
    proc = run_check(tmp_path, html, text="Hello")
    assert proc.returncode == 1
    assert "contains <script>" in proc.stdout
    assert "contains <style>" in proc.stdout
    assert "base64 data-URI image" in proc.stdout
    assert "FAILED" in proc.stdout


def test_image_without_alt_or_width(tmp_path):
    html = '<html><body style="max-width:640px"><img src="pic.png"></body></html>'
    proc = run_check(tmp_path, html, text="Hello")
    assert proc.returncode == 1
    assert "img without alt" in proc.stdout
    assert "img without width attribute" in proc.stdout


def test_cid_without_attachment(tmp_path):
    proc = run_check(tmp_path, passing_html(), text="Hello")
    assert proc.returncode == 1
    assert "cid:chart.png has no matching attachment" in proc.stdout


def test_near_gmail_limit_warns_without_failing(tmp_path):
    proc = run_check(tmp_path, "x" * 90_001, text="Hello")
    assert proc.returncode == 0
    assert "HTML is 90001 bytes" in proc.stdout
    assert "close to Gmail" in proc.stdout
    assert proc.stdout.strip().endswith("PASS")


def test_over_gmail_clip_fails(tmp_path):
    proc = run_check(tmp_path, "y" * 102_001, text="Hello")
    assert proc.returncode == 1
    assert "HTML is 102001 bytes" in proc.stdout
    assert "Gmail clips above about 102 KB" in proc.stdout


def test_dashes_and_empty_plain_text(tmp_path):
    html = passing_html().replace("Quarterly chart", "Q3\u2014result")
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"png")
    proc = run_check(tmp_path, html, text="A plain \u2013 line", attachments=[chart])
    assert proc.returncode == 1
    assert "HTML contains 1 en or em dashes" in proc.stdout
    assert "text contains 1 en or em dashes" in proc.stdout

    empty = run_check(tmp_path, passing_html(), text="  \n", attachments=[chart])
    assert empty.returncode == 1
    assert "plain-text alternative is empty" in empty.stdout


def test_missing_plain_text_and_max_width_warn_only(tmp_path):
    html = '<html><body><img src="pic.png" alt="chart" width="10"></body></html>'
    proc = run_check(tmp_path, html)
    assert proc.returncode == 0
    assert "no plain-text alternative checked" in proc.stdout
    assert "no 640px max-width container found" in proc.stdout
    assert proc.stdout.strip().endswith("PASS")


def test_encoded_attachment_over_25mb(tmp_path):
    html = passing_html()
    blob = tmp_path / "chart.png"
    blob.write_bytes(b"x")
    os.truncate(blob, 19_700_000)
    proc = run_check(tmp_path, html, text="Hello", attachments=[blob])
    assert proc.returncode == 1
    assert "message likely exceeds 25 MB once encoded" in proc.stdout
