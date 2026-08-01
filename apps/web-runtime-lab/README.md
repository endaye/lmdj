# Web Realtime Audio Lab

This product-neutral experimental Host measures whether a browser can run the
realtime primitives needed for a later Web Host. It does not use Product
Assembly or the Application Facade, and it does not change Core behavior.

The decision remains **Pending threshold approval**. Browser event-to-render
acknowledgements are not physical Touch-to-Sound evidence and the UI never
reports a product pass or failure. Physical acoustic onset is collected with
the separate protocol in
[`docs/quality/web-runtime-lab-acceptance.md`](../../docs/quality/web-runtime-lab-acceptance.md).

## Local operation

From the repository root, run the automated gate:

```bash
scripts/web-runtime-lab.sh test
```

Start the loopback-only server:

```bash
scripts/web-runtime-lab.sh serve --port 4173
```

Open <http://127.0.0.1:4173>, choose the output route category, and select
**Start audio**. Audio creation and resume are intentionally tied to explicit
buttons. **Trigger pad** uses the same bounded shared ring as MIDI note-on
events. **Export report** downloads one local JSON report.

The server sets COOP, COEP, CORP, and `no-store` headers. A visible page or a
successful automated browser smoke is not physical Touch-to-Sound evidence.

## Trusted HTTPS for a physical device

LAN binding is rejected unless both trusted TLS files are supplied:

```bash
scripts/web-runtime-lab.sh serve-lan \
  --bind 0.0.0.0 \
  --port 4173 \
  --cert-file /absolute/path/to/trusted-cert.pem \
  --key-file /absolute/path/to/key.pem
```

The certificate must be trusted by the physical device and valid for the host
used in its HTTPS URL. The server rejects symlinked certificate/key files. Do
not use an untrusted-certificate bypass as acceptance evidence.

## Evidence and privacy boundary

The report contains capability flags, browser environment strings, selected
route category, AudioContext metadata, observed render quantum sizes,
privacy-bounded trigger acknowledgements, aggregate MIDI counts, lifecycle
events, and diagnostics. `physicalMeasurement` remains `null`.

The report excludes:

- MIDI input names, manufacturers, serials, and stable IDs;
- SysEx data and raw MIDI messages;
- physical device serials and acoustic measurements;
- product pass/fail fields;
- persistent browser storage: the lab uses no local, session, or database
  storage.

Downloaded reports remain local until the operator deliberately shares them.
Use the acceptance protocol for macOS Safari/Chrome, physical MIDI, iPadOS
Safari, lifecycle, and acoustic evidence.
