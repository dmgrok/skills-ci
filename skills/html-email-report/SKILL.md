---
name: html-email-report
description: >-
  Use when a written report or brief must be delivered as an HTML email that
  renders well in Gmail on desktop and mobile, with figures, tables and a
  plain-text alternative.
---
# HTML email report

Restructure first, then code. An email report is read on a phone in a client that strips half of CSS, so the layout must survive with inline styles only. Start from `template.html` in this skill's folder and run `check.py` before sending.

## 1. Verified constraints (checked October 2026)

| Constraint | What to do | Source |
|---|---|---|
| Gmail supports `<style>` in the head only partly: not for non-Google accounts in the Gmail apps, and the block is capped at 16 KB | Put every style inline. Treat any head `<style>` as optional enhancement | caniemail.com/features/html-style |
| Gmail supports a listed subset of CSS properties and only width, orientation and resolution media queries | Stick to colour, font, padding, border, width, text-align, line-height | developers.google.com/workspace/gmail/design/css |
| Gmail clips messages whose HTML exceeds about 102 KB, hiding the rest behind "View entire message" | Keep HTML under about 90 KB. Put the font family once on the wrapper cell and let it inherit | emailonacid.com, Gmail clipping |
| Gmail does not render base64 data-URI images | Use CID inline attachments or HTML-native figures, never `data:` images | caniemail.com/features/image-base64 |
| Gmail ignores `@media (prefers-color-scheme)`. The Gmail iOS app fully inverts colours, the Android app partially inverts, Gmail on desktop leaves the email unchanged | Design for light mode with mid-tone accents that survive inversion, avoid pure white on pure black, test both | caniemail.com, Litmus dark mode guide, Feb 2025 |
| `<script>` never runs in email | No scripts, no forms, no web fonts you depend on | general |

## 2. Layout rules

- Outer table 100% wide with a light neutral background, inner table `width="640"` plus `style="width:100%;max-width:640px"`. Single column.
- Tables use `role="presentation"`, `cellpadding="0"`, `cellspacing="0"`, `border="0"`.
- Web-safe fonts: Arial or Helvetica for text, Georgia for headings. Body 15px with 22 to 23px line height; never below 12px.
- High contrast: text at 4.5:1 or better against its background. One accent colour, used on one or two elements per section.
- Data tables: three columns at most, percentage widths, text that wraps. Keep long single words out of narrow columns.
- Add a hidden preheader sentence right after `<body>`.
- Links keep their full URL in `href`, with descriptive link text.

## 3. Figures

Choose per figure:
1. **HTML-native figure** for simple bar comparisons and short flows. Bars are table cells with a percentage width and a background colour; flows are bordered boxes with arrows. These always render, invert sensibly and cost no attachment.
2. **CID inline image** for anything richer. Attach the PNG with `inline=true` and a filename, reference it as `<img src="cid:FILENAME" width="592" alt="..." style="display:block;width:100%;max-width:592px;height:auto">`.

For every image: width attribute, descriptive alt text that states the finding, a source line under it, rendered at 2x for sharpness.

**Verify CID wiring before sending.** Some mail connectors refuse inline attachments or attach files without a Content-ID, which leaves broken images. Create a draft, fetch it in raw MIME, and confirm each image part has `Content-ID: <FILENAME>` and `Content-Disposition: inline`. If not, switch those figures to HTML-native versions and attach the PNGs as ordinary attachments for full-size viewing.

## 4. Plain-text alternative

Always send one. Generate it from the same content: headings on their own lines, tables as "cell | cell" rows, links as "text <url>", evidence labels in square brackets, figures as their key numbers or alt text. No Markdown syntax.

## 5. Preview and self-check

1. Render with a headless browser at 640 px and at 375 px, full page: `./render_preview.sh /abs/path/email.html out.png 640`. For CID images, render a preview copy with local file paths substituted.
2. Look at every screen of both renders. Fix overflow, broken words, cramped tables, low contrast and orphaned headings, then render again.
3. Run `python3 check.py email.html --text email.txt --attachments a.png b.png`. It checks size, `<style>` and `<script>`, CID references against attachments, alt and width attributes, dash characters, and total attachment size under 25 MB.
4. Stop when the render and the check pass. Report what you could not verify, for example a real Gmail iOS dark-mode render.

## 6. Sending

- Send only to the recipients the user named, exactly once. If a send errors, check the Sent folder before trying again.
- Keep the HTML final before attaching files: some draft-update calls drop existing attachments.
- Never reply, forward, delete, archive or relabel other mail as part of sending a report.
- Record the sent message ID in the report back.
