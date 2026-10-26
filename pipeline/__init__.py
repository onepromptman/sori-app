"""
pipeline — what happens to an episode after its transcript lands.

Sori's engine (app.py, transcribe.py) stops at a transcript. This package is
the rest of the training pipeline, as data and gates rather than as model
calls: the session's agents (curator, ld-architect, training-critic,
deck-designer; see agents/) do the thinking, and these modules give them a
ledger to record stages in, a brief contract to write against, a sourcing
gate that checks evidence against the transcript, and a design hand-off that
packages a brief for whichever slide tool renders it.

    ledger.py   one JSONL row per stage change, per episode; `sori.py ledger`
    brief.py    the brief.md contract + the evidence-in-transcript gate
    design.py   design backends: offline pptx, Claude Design, ChatSlide,
                Figma Slides, d_sign HTML; each gets a hand-off package
    cli.py      the verbs sori.py routes here: ledger, curate, brief-check, design

Nothing here calls a model or the network. Everything honours SORI_HOME.
"""
