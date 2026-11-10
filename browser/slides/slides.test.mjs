import assert from "node:assert/strict";
import test from "node:test";
import { createSlideRequest, prepareSlideImports } from "./index.js";

const transcript = {
  id: "test-transcript",
  title: "A fictional podcast",
  text: "The project met its deadline. In the second week, the rate was 50% for 1,200 people.",
};

function evidenceFile({ transcriptId = transcript.id, quotes = [], figures = [] } = {}) {
  return new File([
    JSON.stringify({ schema: "sori-slide-evidence/v1", transcriptId, quotes, figures }),
  ], "sori-evidence.json");
}

// An uncompressed ZIP with empty parts, sufficient to exercise Office package
// detection and ensure that a file with a false extension is not accepted.
function zipWithParts(parts, filename) {
  const payload = [];
  const directory = [];
  let offset = 0;
  for (const name of parts) {
    const bytes = Buffer.from(name, "utf8");
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(bytes.length, 26);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(bytes.length, 28);
    central.writeUInt32LE(offset, 42);
    payload.push(local, bytes);
    directory.push(central, bytes);
    offset += local.length + bytes.length;
  }
  const index = Buffer.concat(directory);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(parts.length, 8);
  end.writeUInt16LE(parts.length, 10);
  end.writeUInt32LE(index.length, 12);
  end.writeUInt32LE(offset, 16);
  return new File([...payload, index, end], filename);
}

const slides = ["[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"];

test("the request carries source text and requests real editable slides and an evidence file", () => {
  const request = createSlideRequest(transcript);
  assert.match(request, /editable PowerPoint \(\.pptx\)/);
  assert.match(request, /"transcriptId": "test-transcript"/);
  assert.match(request, /separate study guide/);
  assert.ok(request.endsWith(transcript.text));
});

test("local import links a deck and guide to their selected transcript", async () => {
  const deck = zipWithParts(slides, "CON.pptx");
  const guide = new File(["# Study guide"], "guide.md");
  const { files, errors, evidence } = await prepareSlideImports([deck, guide], transcript);
  assert.deepEqual(errors, []);
  assert.equal(evidence, null);
  assert.deepEqual(files.map(({ kind, transcriptId, name }) => ({ kind, transcriptId, name })), [
    { kind: "deck", transcriptId: "test-transcript", name: "_CON.pptx" },
    { kind: "guide", transcriptId: "test-transcript", name: "guide.md" },
  ]);
  assert.equal(new TextDecoder().decode(files[1].bytes), "# Study guide");
});

test("import rejects false extensions and macro-bearing packages without discarding valid files", async () => {
  const fake = new File(["<script>document.write('hi')</script>"], "fake.pptx");
  const macro = zipWithParts([...slides, "ppt/vbaProject.bin"], "macro.pptx");
  const guide = new File(["# Study guide"], "guide.md");
  const { files, errors } = await prepareSlideImports([fake, macro, guide], transcript);
  assert.equal(files.length, 1);
  assert.deepEqual(errors.map((value) => value.split(":")[0]), ["fake.pptx", "macro.pptx"]);
});

test("evidence checks source excerpts and whole numeric values without requiring a manifest", async () => {
  const quote = { slide: 2, text: "The project met its deadline." };
  const figure = { slide: 3, value: "1,200", excerpt: "the rate was 50% for 1,200 people." };
  const pass = await prepareSlideImports([evidenceFile({ quotes: [quote], figures: [figure] })], transcript);
  assert.deepEqual(pass.evidence, { status: "passed", checked: 2, issues: [] });
  const fail = await prepareSlideImports([
    evidenceFile({ quotes: [{ ...quote, text: "The project missed its deadline." }], figures: [{ ...figure, value: "5%" }] }),
  ], transcript);
  assert.equal(fail.evidence.status, "failed");
  assert.equal(fail.evidence.issues.length, 2);
  const wrong = await prepareSlideImports([evidenceFile({ transcriptId: "different" })], transcript);
  assert.equal(wrong.evidence, null);
  assert.match(wrong.errors[0], /match the request for this transcript/);
});
