#!/usr/bin/env python3
"""Pre-send checks for an HTML email report. Usage:
python3 check.py email.html [--text email.txt] [--attachments a.png b.png ...]"""
import argparse, os, re, sys
ap = argparse.ArgumentParser()
ap.add_argument("html"); ap.add_argument("--text"); ap.add_argument("--attachments", nargs="*", default=[])
a = ap.parse_args()
h = open(a.html, encoding="utf-8").read()
fails, warns = [], []
size = len(h.encode("utf-8"))
if size > 102_000: fails.append(f"HTML is {size} bytes; Gmail clips above about 102 KB")
elif size > 90_000: warns.append(f"HTML is {size} bytes; close to Gmail's ~102 KB clipping limit")
if re.search(r"<script", h, re.I): fails.append("contains <script>")
if re.search(r"<style", h, re.I): warns.append("contains <style>; Gmail may drop it, keep styles inline")
if "data:image" in h: fails.append("base64 data-URI image; Gmail does not render these")
imgs = re.findall(r"<img\b[^>]*>", h, re.I)
for tag in imgs:
    if "alt=" not in tag: fails.append(f"img without alt: {tag[:80]}")
    if not re.search(r'\bwidth="\d+"', tag): fails.append(f"img without width attribute: {tag[:80]}")
cids = set(re.findall(r'src="cid:([^"]+)"', h))
names = {os.path.basename(p) for p in a.attachments}
for c in cids - names: fails.append(f"cid:{c} has no matching attachment")
total = sum(os.path.getsize(p) for p in a.attachments)
if total * 4 / 3 + size > 25 * 1024 * 1024: fails.append("message likely exceeds 25 MB once encoded")
for label, text in [("HTML", h)] + ([("text", open(a.text, encoding="utf-8").read())] if a.text else []):
    n = len(re.findall("[\u2013\u2014]", text))
    if n: fails.append(f"{label} contains {n} en or em dashes")
if a.text and not open(a.text, encoding="utf-8").read().strip(): fails.append("plain-text alternative is empty")
if not a.text: warns.append("no plain-text alternative checked")
if 'max-width:640px' not in h.replace(" ", ""): warns.append("no 640px max-width container found")
print(f"HTML {size} bytes, {len(imgs)} images, {len(cids)} cid refs, attachments {total} bytes")
for w in warns: print("WARN", w)
for f in fails: print("FAIL", f)
print("PASS" if not fails else "FAILED")
sys.exit(1 if fails else 0)
