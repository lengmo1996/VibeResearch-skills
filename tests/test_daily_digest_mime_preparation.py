"""Exercise MIME preparation across the bounded tool-output transport."""

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "skills/global/literature-monitor/scripts/daily_digest_gmail_bridge.js"

HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const source = fs.readFileSync(process.argv[1], 'utf8');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const success = result => ({content: [], structuredContent: {result}});
function argument(command, name) {
  const match = command.match(new RegExp('--' + name + " (?:'((?:[^']|'')*)'|([^ ;]+))"));
  assert.ok(match, `missing ${name}`);
  return match[1] === undefined ? match[2] : match[1].replaceAll("''", "'");
}
function harness(options = {}) {
  const html = Buffer.from('<html>' + '正文'.repeat(329) + '</html>');
  const pdf = Buffer.alloc(options.pdfBytes ?? 70216);
  for (let i = 0; i < pdf.length; i++) pdf[i] = (i * 31 + 17) % 256;
  const manifest = {
    schema_version: 4, coverage_policy: 'fixture-policy-v4',
    validated: true, delivery_format: 'html_pdf_single', message_count: 1,
    attachment_count: 1, recipient: 'me', subject: '[arXiv Daily] fixture', mime_chunk_bytes: 24000,
    html_path: "C:\\Digest's $safe\\body.html", html_bytes: html.length, html_sha256: sha(html),
    pdf_path: "C:\\Digest's $safe\\arxiv-daily-fixture.pdf", pdf_bytes: pdf.length, pdf_sha256: sha(pdf),
    pdf_filename: 'arxiv-daily-fixture.pdf',
  };
  const state = {calls: [], polls: [], gmail: 0, sessions: new Map()};
  const tools = {
    async exec_command(args) {
      const path = argument(args.cmd, 'path');
      const offset = Number(argument(args.cmd, 'offset'));
      const bytes = Number(argument(args.cmd, 'max-bytes'));
      assert.equal(bytes, 24000);
      assert.equal(args.tty, false);
      assert.equal(args.login, false);
      assert.ok(args.cmd.includes("Digest''s $safe"), 'PowerShell path was not single-quoted');
      const data = path === manifest.html_path ? html : pdf;
      assert.equal(Number(argument(args.cmd, 'expected-size')), data.length);
      assert.equal(argument(args.cmd, 'expected-sha256'), sha(data));
      const chunk = data.subarray(offset, offset + bytes);
      const value = {
        offset, bytes: chunk.length, next_offset: offset + chunk.length,
        eof: offset + chunk.length === data.length, base64: chunk.toString('base64'),
      };
      const call = {path, offset, budget: args.max_output_tokens, command: args.cmd};
      state.calls.push(call);
      const output = JSON.stringify(value) + '\n';
      if (options.respond) {
        const overridden = options.respond({args, call, value, output, state, manifest});
        if (overridden !== undefined) return overridden;
      }
      if (options.session) {
        assert.equal(state.sessions.size, 0, 'overlapped a running read');
        const id = state.calls.length;
        const split = Math.floor(output.length / 2);
        state.sessions.set(id, output.slice(split));
        return {output: output.slice(0, split), session_id: id};
      }
      return {exit_code: 0, output};
    },
    async write_stdin(args) {
      state.polls.push(args);
      assert.ok(state.sessions.has(args.session_id));
      assert.equal(args.chars, '');
      if (options.poll) return options.poll(args, state);
      const output = state.sessions.get(args.session_id);
      state.sessions.delete(args.session_id);
      return {exit_code: 0, output};
    },
    async mcp__codex_apps__gmail_create_draft(args) {
      state.gmail++;
      assert.equal(args.payload.mime_type, 'multipart/mixed');
      return success({id: 'draft-fixture', message: {id: 'message-fixture', label_ids: ['DRAFT']}});
    },
    async mcp__codex_apps__gmail_send_draft() { state.gmail++; throw new Error('unexpected send'); },
  };
  const bridge = vm.runInNewContext(source, {tools, setTimeout});
  const prepare = () => bridge.prepareMimePayload({
    pythonExe: "C:\\Python's $safe\\python.exe", scriptPath: 'C:\\scripts\\daily_digest_delivery.py',
    workdir: 'C:\\Digest', manifest, ...options.context,
  });
  return {bridge, manifest, html, pdf, state, prepare};
}
function verifyPayload(payload, fixture) {
  assert.equal(payload.mime_type, 'multipart/mixed');
  assert.equal(payload.parts.length, 2);
  const [html, pdf] = payload.parts;
  assert.equal(html.mime_type, 'text/html');
  assert.equal(html.charset, 'utf-8');
  assert.equal(html.content_disposition, 'inline');
  assert.equal(pdf.mime_type, 'application/pdf');
  assert.equal(pdf.content_disposition, 'attachment');
  assert.equal(pdf.filename, fixture.manifest.pdf_filename);
  for (const [part, expected] of [[html, fixture.html], [pdf, fixture.pdf]]) {
    assert.match(part.body.base64_url_content, /^[A-Za-z0-9_-]+$/);
    const decoded = Buffer.from(part.body.base64_url_content, 'base64url');
    assert.deepEqual(decoded, expected);
    assert.equal(sha(decoded), sha(expected));
  }
}
"""


class DailyDigestMimePreparationTests(unittest.TestCase):
    def run_js(self, body: str) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is unavailable")
        script = HARNESS + "\n(async () => {\n" + body + r"""
})().catch(error => { process.stderr.write(error.stack + '\n'); process.exit(1); });
"""
        result = subprocess.run(
            [node, "-e", script, str(BRIDGE)], capture_output=True, text=True, timeout=40,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_complete_payload_roundtrips_all_padding_cases_and_multiple_chunks(self):
        self.run_js(r"""
for (const pdfBytes of [24000, 24001, 24002, 70216]) {
  const f = harness({pdfBytes});
  verifyPayload(await f.prepare(), f);
  assert.equal(f.state.gmail, 0);
  assert.ok(f.state.calls.every(call => call.budget >= 12000));
  assert.deepEqual(f.state.calls.filter(c => c.path === f.manifest.pdf_path).map(c => c.offset),
    Array.from({length: Math.ceil(pdfBytes / 24000)}, (_, i) => i * 24000));
}
""")

    def test_truncation_automatically_rereads_same_chunk_then_continues_to_draft(self):
        self.run_js(r"""
const f = harness({respond({call, output, manifest}) {
  if (call.path === manifest.pdf_path && call.offset === 24000 && call.budget < 48000) {
    return {exit_code: 0, original_token_count: 8018,
      output: 'Warning: truncated output (original token count: 8018)\n' + output.slice(0, 50) +
        '... 4000 tokens truncated ...' + output.slice(-50)};
  }
}});
const payload = await f.prepare();
verifyPayload(payload, f);
const retried = f.state.calls.filter(c => c.path === f.manifest.pdf_path && c.offset === 24000);
assert.deepEqual(retried.map(c => c.budget), [12000, 24000, 48000]);
assert.equal(f.state.calls.filter(c => c.path === f.manifest.html_path).length, 1);
assert.equal(f.state.gmail, 0);
await f.bridge.createDraft({to: 'me@example.com', subject: f.manifest.subject, payload});
assert.equal(f.state.gmail, 1, 'recovered preparation did not continue exactly once');
""")

    def test_exhausted_truncation_stops_locally_without_any_gmail_mutation(self):
        self.run_js(r"""
const f = harness({respond() {
  return {exit_code: 0, output: 'Warning: truncated output\n... 100 tokens omitted ...'};
}});
let failure;
try {
  const payload = await f.prepare();
  await f.bridge.createDraft({payload});
} catch (error) { failure = error; }
assert.ok(failure);
assert.match(f.bridge.diagnostic(failure).failure_code, /^local_/);
assert.match(f.bridge.diagnostic(failure).failure_code, /truncat/);
assert.equal(f.state.calls.length, 3);
assert.equal(f.state.gmail, 0);
""")

    def test_session_output_is_collected_before_advancing_the_offset(self):
        self.run_js(r"""
const f = harness({session: true});
verifyPayload(await f.prepare(), f);
assert.equal(f.state.calls.length, f.state.polls.length);
assert.equal(f.state.sessions.size, 0);
assert.ok(f.state.polls.every(p => p.max_output_tokens >= 12000));
assert.equal(f.state.gmail, 0);
""")

    def test_source_or_validation_failures_are_not_retried_or_called_gmail_errors(self):
        self.run_js(r"""
const responses = [
  () => ({exit_code: 2, output: 'error: attested MIME source identity mismatch'}),
  () => ({exit_code: 2, output: 'Warning: truncated output\nsource mismatch'}),
  () => ({exit_code: 0, output: '{invalid json'}),
  ({value}) => ({exit_code: 0, output: JSON.stringify({...value, offset: 1})}),
  ({value}) => ({exit_code: 0, output: JSON.stringify({...value, next_offset: 0})}),
  ({value}) => ({exit_code: 0, output: JSON.stringify({...value, bytes: value.bytes - 1})}),
  ({value}) => ({exit_code: 0, output: JSON.stringify({...value, eof: !value.eof})}),
  ({value}) => ({exit_code: 0, output: JSON.stringify({...value, base64: value.base64.slice(4)})}),
  ({value}) => ({exit_code: 0, output: JSON.stringify({...value, base64: '?' + value.base64.slice(1)})}),
];
for (const respond of responses) {
  const f = harness({respond});
  let failure;
  try { await f.prepare(); } catch (error) { failure = error; }
  assert.ok(failure, 'invalid source/output was accepted');
  assert.match(f.bridge.diagnostic(failure).failure_code, /^local_/);
  assert.equal(f.state.calls.length, 1, 'validation failure was retried');
  assert.equal(f.state.gmail, 0);
}
""")

    def test_truncated_session_is_drained_before_retry_even_when_marker_is_split(self):
        self.run_js(r"""
const f = harness({respond({call, state}) {
  assert.equal(state.sessions.size, 0, 'started another read before draining the session');
  if (state.calls.length === 1) {
    state.sessions.set(71, 'cated output\n... 100 tokens omitted ...');
    return {output: 'Warning: trun', session_id: 71};
  }
}});
verifyPayload(await f.prepare(), f);
assert.equal(f.state.polls.length, 1);
assert.equal(f.state.polls[0].session_id, 71);
assert.deepEqual(f.state.calls.slice(0, 2).map(c => [c.path, c.offset, c.budget]), [
  [f.manifest.html_path, 0, 12000], [f.manifest.html_path, 0, 24000],
]);
assert.equal(f.state.gmail, 0);
""")

    def test_unfinished_local_reader_is_not_restarted_or_allowed_to_create_a_draft(self):
        self.run_js(r"""
const f = harness({session: true, poll(args) {
  return {output: '', session_id: args.session_id};
}});
let failure;
try {
  const payload = await f.prepare();
  await f.bridge.createDraft({payload});
} catch (error) { failure = error; }
assert.equal(f.bridge.diagnostic(failure).failure_code, 'local_mime_chunk_process_error');
assert.equal(f.state.calls.length, 1);
assert.ok(f.state.polls.length > 0 && f.state.polls.length <= 20);
assert.equal(f.state.gmail, 0);
""")

    def test_manifest_bounds_are_checked_before_reading(self):
        self.run_js(r"""
for (const patch of [
  {validated: false}, {delivery_format: 'legacy'}, {attachment_count: 2}, {message_count: 2},
  {html_bytes: 90001}, {pdf_bytes: 10485761}, {pdf_bytes: 0}, {pdf_bytes: 1.5},
  {html_sha256: 'bad'}, {pdf_sha256: 'bad'}, {pdf_filename: ''}, {html_path: ''},
]) {
  const f = harness();
  Object.assign(f.manifest, patch);
  await assert.rejects(f.prepare());
  assert.equal(f.state.calls.length, 0);
  assert.equal(f.state.gmail, 0);
}
""")

    def test_unclassified_local_error_does_not_masquerade_as_gmail_failure(self):
        self.run_js(r"""
const f = harness();
const detail = f.bridge.diagnostic(new SyntaxError('PRIVATE_BODY_SECRET'));
assert.match(detail.failure_code, /^local_/);
assert.ok(!JSON.stringify(detail).includes('PRIVATE_BODY_SECRET'));
const gmail = f.bridge.diagnostic(new f.bridge.GmailBridgeError('gmail_connector_call_error', 'safe detail'));
assert.equal(gmail.failure_code, 'gmail_connector_call_error');
assert.equal(gmail.failure_detail, 'safe detail');
""")

    def test_public_config_is_quoted_before_subcommand_and_invalid_paths_stop_locally(self):
        self.run_js(r"""
const path = "C:\\User's $safe\\digest-config.json";
const f = harness({context: {publicConfigPath: path}});
verifyPayload(await f.prepare(), f);
for (const call of f.state.calls) {
  assert.equal(argument(call.command, 'public-config'), path);
  assert.ok(call.command.indexOf(' --public-config ') < call.command.indexOf(' mime-chunk '));
}
const privateFixture = harness();
await privateFixture.prepare();
assert.ok(privateFixture.state.calls.every(call => !call.command.includes('--public-config')));
for (const publicConfigPath of ['', null, 42, 'bad\npath', 'bad\rpath', 'bad\0path']) {
  const invalid = harness({context: {publicConfigPath}});
  await assert.rejects(invalid.prepare());
  assert.equal(invalid.state.calls.length, 0);
}
""")


if __name__ == "__main__":
    unittest.main()
