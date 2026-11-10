# Design handoffs

The brief is shared by all backends. A design handoff copies the validated brief,
evidence and optional outline/critique/triage into handoff/<backend>/.

| Backend | Local result | Remaining step |
| --- | --- | --- |
| offline | Handoff and, when outline.json exists, editable PPTX and study guide | Review output |
| claude-design | Brief and evidence instructions | Use a client with supported slide tools |
| html | Generic slide-map.json and handoff | Supply your own templates and renderer |
| chatslide | source-document.md and handoff | Check accepted formats and upload manually |
| figma | Brief and evidence instructions | Use a supported Figma Slides authoring tool |

Configure with `python sori.py design-config design_backend offline`.
An optional design_system_url is a reference for your own slide workflow; Sori
does not fetch it. HTML layout names are suggestions, not bundled templates.
No private repository, personal design system or proprietary theme is required.

External service availability, access and costs are not guaranteed. The handoff
does not upload, publish, or prove that an external tool preserved your content.
Review quotes, values, sources and accessibility after rendering.
