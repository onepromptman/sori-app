# Curriculum

The curator reads this before deciding whether an episode earns a training.
Half a page is plenty. Edit freely; `python3 sori.py curate --init` wrote it.

## Audience

Who the trainings are for, in one paragraph: role, what they already know,
what they will not sit through. Example: "People and talent professionals
(recruiters, HRBPs, people-ops) with no coding background, 30-minute
sessions, hands-on, one artifact per session."

## Themes we teach

Five to ten bullets. The curator marks an episode `train` only when it
serves at least one of these with concrete, quotable material.

- Agentic AI fundamentals: what an agent is, where it fails
- Prompt and context engineering for non-engineers
- Verification and trust: how to check an AI's work
- Automating the boring parts of a people-ops workflow
- Claude Code / Cowork for non-engineers
- ...

## Themes we do not teach

What to skip even when the episode is good: model benchmarks, founder
gossip, investment takes, anything that needs code to follow.

## Shape of a training

- Length: N slides, M minutes
- Always: objectives, one DO step with an artifact, a 3-question self-check
- Register: plain English, jargon glossed once
- House rules: every number and quote from the transcript; no invented examples with real names

## Triage thresholds

- `train`: at least three quotable moments that serve a theme above, and a
  DO step that can be run with no tools beyond a browser and a doc
- `park`: good material, no DO step yet; revisit when a second episode covers it
- `skip`: everything else, with the reason in one line
