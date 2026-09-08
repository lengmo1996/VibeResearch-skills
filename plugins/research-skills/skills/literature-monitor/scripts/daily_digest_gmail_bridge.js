(() => {
  "use strict";

  const ERROR_TEXT = /^(?:error\b|tool error\b|mcp .*error\b|exception\b|failed\b|failure\b|unauthorized\b|forbidden\b|permission denied\b|invalid request\b|rate limit(?:ed)?\b|internal server error\b)/i;
  const PYTHON_OUTPUT_TOKENS = 4000;
  // 24,000 source bytes produce 32,000 base64 characters.  Keep attachment
  // transport budgets separate from the small receipt/attestation JSON budget.
  const MIME_CHUNK_BYTES = 24000;
  const MIME_CHUNK_OUTPUT_TOKENS = Object.freeze([12000, 24000, 48000]);
  const HTML_MAX_BYTES = 90000;
  const PDF_MAX_BYTES = 10 * 1024 * 1024;
  const MIME_OUTPUT_TRUNCATION =
    /\b(?:\d+\s+(?:tokens?|characters?|chars?|bytes?|lines?)\s+(?:truncated|omitted)|(?:output|content)\s+(?:was\s+)?truncated|truncated\s+(?:output|content)|(?:output|content)\s+omitted)\b/i;
  const MAX_SEND_ATTEMPTS = 2;
  const SEND_OBSERVATION_DELAYS_MS = Object.freeze([0, 2000, 5000]);
  // Connector throws are safe to retry only for side-effect-free reads.
  const READ_ONLY_CONNECTOR_RETRY_DELAYS_MS = Object.freeze([0, 2000, 5000]);
  const SEND_AUTHORIZATION_SCOPE =
    "daily_arxiv_email_to_authenticated_self";
  const SEND_REAUTHORIZATION_SCHEMA =
    "daily_arxiv_send_reauthorization_v1";
  const SEND_REAUTHORIZATION_DECISION =
    "send_same_verified_draft_once";
  const LEGACY_SEND_REAUTHORIZATION_SCHEMA =
    "daily_arxiv_legacy_send_reauthorization_v1";
  const LEGACY_SEND_REAUTHORIZATION_DECISION =
    "recover_legacy_unknown_once_after_exact_sent_zero";
  const LEGACY_SEND_AUTHORIZATION_ORIGIN =
    "interactive_legacy_unreleased";
  // Every ConPTY write is newline-terminated and bounded.  Windows ConPTY
  // otherwise buffers a long Gmail base64url value until its input queue
  // overflows, even when the child disables console line mode.
  const RAW_FRAME_LINE_CHARS = 8 * 1024;
  const INPUT_WRITE_CHARS = 128 * 1024;
  const PUBLIC_READ_OPERATIONS = new Set([
    "get_profile",
    "list_drafts",
    "read_email",
    "read_email_thread",
    "search_email_ids",
    "search_emails",
  ]);
  const rawAttestationResults = new WeakSet();
  const verifiedRawResults = new WeakSet();
  const rawAttestationContexts = new WeakMap();
  const recordedDraftReceiptContexts = new WeakMap();
  const leaseRetryDraftReceiptContexts = new WeakMap();
  const activeSendLeaseCapabilities = new WeakSet();
  const LOCAL_SEND_PROOF_TOKENS = Symbol.for(
    "daily-arxiv.gmail-send-proof-tokens-issued-in-this-eval-phase",
  );
  const locallyIssuedSendProofTokens =
    globalThis[LOCAL_SEND_PROOF_TOKENS] instanceof Set
      ? globalThis[LOCAL_SEND_PROOF_TOKENS]
      : new Set();
  if (!(globalThis[LOCAL_SEND_PROOF_TOKENS] instanceof Set)) {
    Object.defineProperty(globalThis, LOCAL_SEND_PROOF_TOKENS, {
      value: locallyIssuedSendProofTokens,
      configurable: false,
      enumerable: false,
      writable: false,
    });
  }
  const SEND_OUTCOME_UNKNOWN = Object.freeze({
    failure_code: "gmail_send_outcome_unknown",
    failure_detail:
      "Gmail send write-ahead is pending; reconcile exact SENT before any retry",
  });
  const SEND_ATTEMPT_AUTOMATIC_RETRY_BLOCKED = Object.freeze({
    failure_code: "gmail_send_automatic_retry_blocked",
    failure_detail:
      "Gmail send attempt started; automatic retry stays blocked unless the connector explicitly reports transport outcome unknown",
  });
  const PRE_DISPATCH_DENIAL =
    /(?:unacceptable\s+risk|(?:policy|safety|risk)\s+(?:denial|denied|rejection|rejected)|(?:explicit|additional)\s+(?:user\s+)?(?:approval|authorization)\s+(?:is\s+)?required|(?:please|must)\s+explicitly\s+(?:approve|authorize)|not\s+explicitly\s+(?:approved|authorized)|external(?:-write|\s+email|\s+egress)[^\r\n]{0,80}(?:denied|rejected|not\s+authorized)|not\s+authorized\s+to\s+(?:send|dispatch))/i;
  const EXPLICIT_OUTCOME_UNKNOWN =
    /(?:response\s+(?:was\s+)?lost|outcome\s+(?:is\s+)?unknown|unknown\s+whether[^\r\n]{0,80}(?:sent|dispatch)|connection\s+(?:reset|closed|lost|aborted)|unexpected[_\s-]*eof|econnreset|broken\s+pipe|transport[^\r\n]{0,80}(?:timeout|failure|lost)|timed?\s*out\s+(?:after|while\s+waiting\s+for)\s+(?:dispatch|send|response))/i;

  class GmailBridgeError extends Error {
    constructor(failureCode, detail) {
      super(detail);
      this.name = "GmailBridgeError";
      this.failureCode = failureCode;
    }
  }

  const own = (value, key) =>
    value !== null &&
    typeof value === "object" &&
    Object.prototype.hasOwnProperty.call(value, key);

  function failureOf(value) {
    if (!value || typeof value !== "object") return null;
    if (value.isError === true) return "isError=true";
    if (
      own(value, "error") &&
      value.error !== null &&
      value.error !== false &&
      value.error !== ""
    ) return "error field";
    if (value.success === false) return "success=false";
    if (
      typeof value.status === "string" &&
      /^(?:error|failed|failure)$/i.test(value.status.trim())
    ) return `status=${value.status}`;
    return null;
  }

  function connectorText(value) {
    if (typeof value === "string") return value;
    if (!value || typeof value !== "object") return "";
    const content = (Array.isArray(value.content) ? value.content : [])
      .filter(block => block?.type === "text" && typeof block.text === "string")
      .map(block => block.text)
      .join("\n");
    const direct = [value.message, value.error, value.detail, value.reason]
      .filter(item => typeof item === "string")
      .join("\n");
    const nested = [value.structuredContent, value.result]
      .filter(item => item && typeof item === "object" && item !== value)
      .map(item => connectorText(item))
      .join("\n");
    return [content, direct, nested].filter(Boolean).join("\n");
  }

  function isPreDispatchDenial(value) {
    return PRE_DISPATCH_DENIAL.test(connectorText(value));
  }

  function isExplicitOutcomeUnknown(value) {
    return EXPLICIT_OUTCOME_UNKNOWN.test(connectorText(value));
  }

  function sendOutcomeUnknownError(detail) {
    const error = new GmailBridgeError(
      "gmail_send_transport_outcome_unknown",
      detail,
    );
    error.retryAllowed = true;
    return error;
  }

  function connectorFailure(operation, failureCode, reason) {
    throw new GmailBridgeError(
      failureCode,
      `${operation} failed closed: ${reason}`,
    );
  }

  function requireToolSuccess(operation, result) {
    if (typeof result === "string") {
      result = {content: [{type: "text", text: result}]};
    }
    if (!result || typeof result !== "object") {
      connectorFailure(
        operation,
        "gmail_connector_result_missing",
        "missing connector result",
      );
    }
    if (isPreDispatchDenial(result)) {
      connectorFailure(
        operation,
        "gmail_connector_pre_dispatch_denied",
        "external-write approval denied before Gmail dispatch",
      );
    }
    if (
      operation === "gmail.send_draft" &&
      isExplicitOutcomeUnknown(result) &&
      (result.isError === true || failureOf(result) !== null)
    ) {
      throw sendOutcomeUnknownError(
        "gmail.send_draft returned an explicit transport outcome-unknown result",
      );
    }
    if (result.isError === true) {
      connectorFailure(operation, "gmail_connector_is_error", "isError=true");
    }
    const outerFailure = failureOf(result);
    if (outerFailure) {
      connectorFailure(
        operation,
        "gmail_connector_error_payload",
        outerFailure,
      );
    }

    const parsed = [];
    for (const block of Array.isArray(result.content) ? result.content : []) {
      const blockFailure = failureOf(block);
      if (blockFailure || block?.type === "error") {
        connectorFailure(
          operation,
          "gmail_connector_error_payload",
          "connector error block",
        );
      }
      if (block?.type !== "text" || typeof block.text !== "string") continue;
      const candidate = block.text.trim();
      if (ERROR_TEXT.test(candidate)) {
        connectorFailure(
          operation,
          "gmail_connector_error_payload",
          "connector error text",
        );
      }
      if (/^[{[]/.test(candidate)) {
        try {
          parsed.push(JSON.parse(candidate));
        } catch {
          connectorFailure(
            operation,
            "gmail_connector_error_payload",
            "malformed JSON content",
          );
        }
      }
    }

    const candidates = [];
    if (result.structuredContent !== undefined) {
      candidates.push(result.structuredContent);
    }
    candidates.push(...parsed);
    for (const candidate of candidates) {
      const nestedFailure =
        failureOf(candidate) || failureOf(candidate?.result);
      if (nestedFailure) {
        connectorFailure(
          operation,
          "gmail_connector_error_payload",
          nestedFailure,
        );
      }
    }
    const envelope =
      result.structuredContent ??
      parsed.find(value => value && typeof value === "object");
    if (!envelope || typeof envelope !== "object") {
      connectorFailure(
        operation,
        "gmail_connector_result_missing",
        "no structured success payload",
      );
    }
    const payload = own(envelope, "result") ? envelope.result : envelope;
    if (!payload || typeof payload !== "object") {
      connectorFailure(
        operation,
        "gmail_connector_result_missing",
        "missing result payload",
      );
    }
    return payload;
  }

  async function checkedGmailCall(operation, args, validate) {
    if (typeof validate !== "function") {
      connectorFailure(
        `gmail.${operation}`,
        "gmail_connector_validation_failed",
        "operation-specific success validation is required",
      );
    }
    const toolName = `mcp__codex_apps__gmail_${operation}`;
    if (typeof tools[toolName] !== "function") {
      connectorFailure(
        `gmail.${operation}`,
        "gmail_connector_tool_missing",
        "connector tool is unavailable",
      );
    }
    let rawResult;
    const invocationDelays = PUBLIC_READ_OPERATIONS.has(operation)
      ? READ_ONLY_CONNECTOR_RETRY_DELAYS_MS
      : [0];
    for (let attempt = 0; attempt < invocationDelays.length; attempt += 1) {
      const delay = invocationDelays[attempt];
      if (delay > 0) await pause(delay);
      try {
        rawResult = await tools[toolName](args);
        break;
      } catch (error) {
        if (operation === "send_draft" && isPreDispatchDenial(error)) {
          connectorFailure(
            "gmail.send_draft",
            "gmail_connector_pre_dispatch_denied",
            "external-write approval denied before Gmail dispatch",
          );
        }
        if (operation === "send_draft" && isExplicitOutcomeUnknown(error)) {
          throw sendOutcomeUnknownError(
            "gmail.send_draft transport failed after dispatch became uncertain",
          );
        }
        if (attempt + 1 < invocationDelays.length) continue;
        connectorFailure(
          `gmail.${operation}`,
          "gmail_connector_call_error",
          "connector threw before returning a result",
        );
      }
    }
    const payload = requireToolSuccess(`gmail.${operation}`, rawResult);
    try {
      validate(payload);
    } catch (error) {
      if (error instanceof GmailBridgeError) throw error;
      connectorFailure(
        `gmail.${operation}`,
        "gmail_connector_validation_failed",
        "success payload failed operation-specific validation",
      );
    }
    return payload;
  }

  async function callGmail(operation, args, validate) {
    if (!PUBLIC_READ_OPERATIONS.has(operation)) {
      throw new GmailBridgeError(
        "gmail_connector_validation_failed",
        `gmail.${operation} is not on the bridge read-only allowlist`,
      );
    }
    return checkedGmailCall(operation, args, validate);
  }

  const nonEmptyString = value =>
    typeof value === "string" && value.trim().length > 0;

  async function getProfile() {
    return checkedGmailCall("get_profile", {}, payload => {
      if (!nonEmptyString(payload.email)) {
        throw new Error("profile email is missing");
      }
    });
  }

  function draftIdentity(payload, expectedDraftId = null) {
    if (
      !nonEmptyString(payload.id) ||
      (expectedDraftId !== null && payload.id !== expectedDraftId) ||
      !payload.message ||
      !nonEmptyString(payload.message.id) ||
      !Array.isArray(payload.message.label_ids) ||
      !payload.message.label_ids.includes("DRAFT")
    ) {
      throw new Error("Draft response does not bind Draft and message IDs");
    }
    return Object.freeze({
      draftId: payload.id,
      messageId: payload.message.id,
    });
  }

  function sentIdentity(payload) {
    if (!nonEmptyString(payload.id)) {
      throw new GmailBridgeError(
        "gmail_connector_validation_failed",
        "gmail.send_draft failed closed: sent message ID is missing",
      );
    }
    if (!nonEmptyString(payload.threadId)) {
      throw new GmailBridgeError(
        "gmail_connector_validation_failed",
        "gmail.send_draft failed closed: sent thread ID is missing",
      );
    }
    if (!Array.isArray(payload.labelIds) || !payload.labelIds.includes("SENT")) {
      throw new GmailBridgeError(
        "gmail_connector_validation_failed",
        "gmail.send_draft failed closed: SENT label is missing",
      );
    }
    return Object.freeze({
      id: payload.id,
      threadId: payload.threadId,
      labelIds: [...payload.labelIds],
    });
  }

  async function createDraft(args) {
    const payload = await checkedGmailCall(
      "create_draft",
      {...args, response_fields: ["id", "message"]},
      value => draftIdentity(value),
    );
    return draftIdentity(payload);
  }

  async function updateDraft(args) {
    if (!nonEmptyString(args?.draft_id)) {
      throw new GmailBridgeError(
        "gmail_connector_validation_failed",
        "gmail.update_draft requires a verified Draft ID",
      );
    }
    const payload = await checkedGmailCall(
      "update_draft",
      {...args, response_fields: ["id", "message"]},
      value => draftIdentity(value, args.draft_id),
    );
    return draftIdentity(payload, args.draft_id);
  }

  async function requireDraftBinding(draftId, messageId) {
    if (!nonEmptyString(draftId) || !nonEmptyString(messageId)) {
      throw new GmailBridgeError(
        "gmail_connector_validation_failed",
        "Draft attestation requires both Draft and message IDs",
      );
    }
    let nextPageToken;
    for (let page = 0; page < 20; page += 1) {
      const args = {max_results: 100};
      if (nextPageToken !== undefined) args.next_page_token = nextPageToken;
      const payload = await checkedGmailCall("list_drafts", args, value => {
        if (!Array.isArray(value.drafts)) {
          throw new Error("Draft listing is missing rows");
        }
      });
      const row = payload.drafts.find(item => item?.draft_id === draftId);
      if (row !== undefined) {
        if (row.message_id !== messageId) {
          throw new GmailBridgeError(
            "gmail_connector_validation_failed",
            "Gmail Draft ID does not own the attested message ID",
          );
        }
        return Object.freeze({draftId, messageId});
      }
      nextPageToken = nonEmptyString(payload.next_page_token)
        ? payload.next_page_token
        : undefined;
      if (nextPageToken === undefined) break;
    }
    throw new GmailBridgeError(
      "gmail_connector_validation_failed",
      "Gmail Draft ID could not be recovered from the checked Draft listing",
    );
  }

  async function attemptVerifiedDraftOnce({
    draftId,
    messageId,
    attestation,
    receiptContext,
    leaseCapability,
  }) {
    if (
      !activeSendLeaseCapabilities.has(leaseCapability) ||
      !verifiedRawResults.has(attestation) ||
      attestation.stage !== "draft_verified" ||
      attestation.gmail_draft_id !== draftId ||
      attestation.gmail_draft_message_id !== messageId ||
      recordedDraftReceiptContexts.get(attestation) !== receiptContext &&
      leaseRetryDraftReceiptContexts.get(attestation) !== receiptContext
    ) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "private send boundary requires a live Draft attestation bound to the active send lease",
      );
    }
    if (
      !Number.isInteger(receiptContext.sendAttemptCount) ||
      receiptContext.sendAttemptCount < 0 ||
      receiptContext.sendAttemptCount >= MAX_SEND_ATTEMPTS
    ) {
      const budgetError = new GmailBridgeError(
        "gmail_send_attempt_budget_exhausted",
        "verified Draft has no remaining bounded send attempt",
      );
      budgetError.deliveryOutcome = "not_attempted";
      budgetError.receiptStage = "draft_verified";
      throw budgetError;
    }
    verifiedRawResults.delete(attestation);
    let activeAttemptCount = receiptContext.sendAttemptCount;

    const annotate = (error, deliveryOutcome, receiptStage) => {
      const bridgeError = error instanceof GmailBridgeError
        ? error
        : new GmailBridgeError(
            "gmail_connector_call_error",
            "Gmail orchestration failed without a verified connector result",
          );
      bridgeError.deliveryOutcome = deliveryOutcome;
      bridgeError.receiptStage = receiptStage;
      return bridgeError;
    };
    const persistAmbiguous = async (failure, {incrementAttempt = false} = {}) => {
      const fields =
        failure === SEND_OUTCOME_UNKNOWN ||
        failure === SEND_ATTEMPT_AUTOMATIC_RETRY_BLOCKED
        ? failure
        : diagnostic(failure);
      const nextAttemptCount = incrementAttempt
        ? activeAttemptCount + 1
        : activeAttemptCount;
      Object.assign(attestation, {
        ok: false,
        stage: "ambiguous",
        gmail_message_id: null,
        failure_code: fields.failure_code,
        failure_detail: fields.failure_detail,
        send_attempt_count: nextAttemptCount,
      });
      const persisted = await recordReceipt({
        receiptInput: attestation,
        sendLeaseToken: leaseCapability.leaseToken,
        ...receiptContext,
      });
      activeAttemptCount = persisted.send_attempt_count;
      return persisted;
    };

    try {
      await requireDraftBinding(draftId, messageId);
    } catch (error) {
      const bridgeError = annotate(error, "not_attempted", "draft_verified");
      try {
        await persistAmbiguous(bridgeError);
      } catch (receiptError) {
        const persistence = diagnostic(receiptError);
        throw annotate(
          new GmailBridgeError(
            "local_attestation_process_error",
            `ambiguous receipt persistence failed before send (${persistence.failure_code})`,
          ),
          "not_attempted",
          "draft_verified",
        );
      }
      throw annotate(bridgeError, "not_attempted", "ambiguous");
    }

    try {
      await persistAmbiguous(
        SEND_ATTEMPT_AUTOMATIC_RETRY_BLOCKED,
        {incrementAttempt: true},
      );
    } catch (error) {
      const persistence = diagnostic(error);
      throw annotate(
        new GmailBridgeError(
          "local_attestation_process_error",
          `Gmail send was not attempted because write-ahead persistence failed (${persistence.failure_code})`,
        ),
        "not_attempted",
        "draft_verified",
      );
    }

    try {
      const payload = await checkedGmailCall(
        "send_draft",
        {draft_id: draftId},
        value => sentIdentity(value),
      );
      return Object.freeze({
        candidate: sentIdentity(payload),
        sendAttemptCount: activeAttemptCount,
      });
    } catch (error) {
      const preDispatchDenied =
        error instanceof GmailBridgeError &&
        error.failureCode === "gmail_connector_pre_dispatch_denied";
      const retryAllowed = error?.retryAllowed === true;
      const bridgeError = annotate(
        error,
        preDispatchDenied
          ? "definitely_not_sent"
          : retryAllowed
            ? "unknown_after_send_attempt"
            : "unknown_no_automatic_retry",
        "ambiguous",
      );
      bridgeError.retryAllowed = retryAllowed;
      bridgeError.sendAttemptCount = activeAttemptCount;
      const persistedFailure = !retryAllowed && !preDispatchDenied
        ? new GmailBridgeError(
            "gmail_send_automatic_retry_blocked",
            `automatic retry blocked after ${bridgeError.failureCode}`,
          )
        : bridgeError;
      persistedFailure.deliveryOutcome = bridgeError.deliveryOutcome;
      persistedFailure.receiptStage = "ambiguous";
      persistedFailure.retryAllowed = retryAllowed;
      persistedFailure.sendAttemptCount = activeAttemptCount;
      try {
        if (retryAllowed) {
          await persistAmbiguous(SEND_OUTCOME_UNKNOWN);
        } else if (preDispatchDenied) {
          await persistAmbiguous(persistedFailure);
        }
      } catch (receiptError) {
        const blocked = new GmailBridgeError(
          "gmail_send_automatic_retry_blocked",
          `automatic retry stayed blocked because send disposition persistence failed (${diagnostic(receiptError).failure_code})`,
        );
        blocked.deliveryOutcome = bridgeError.deliveryOutcome;
        blocked.receiptStage = "ambiguous";
        blocked.retryAllowed = false;
        blocked.sendAttemptCount = activeAttemptCount;
        throw blocked;
      }
      throw persistedFailure;
    }
  }

  const pause = milliseconds => new Promise(
    resolve => setTimeout(resolve, milliseconds),
  );

  function draftReceiptContext({draftId, messageId, attestation}) {
    const receiptContext = recordedDraftReceiptContexts.get(attestation);
    if (
      !verifiedRawResults.has(attestation) ||
      attestation?.stage !== "draft_verified" ||
      attestation.gmail_draft_id !== draftId ||
      attestation.gmail_draft_message_id !== messageId ||
      receiptContext === undefined
    ) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "operation requires a live verified Draft and its persisted receipt",
      );
    }
    return receiptContext;
  }

  function exactSubjectQuery(subject) {
    if (!nonEmptyString(subject) || /[\r\n]/.test(subject)) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "exact SENT reconciliation requires one non-empty subject line",
      );
    }
    const escaped = subject.replaceAll("\\", "\\\\").replaceAll('"', '\\"');
    return `subject:"${escaped}"`;
  }

  async function searchExactSentMessageIds(subject) {
    const ids = [];
    const seen = new Set();
    let nextPageToken;
    for (let page = 0; page < 5; page += 1) {
      const args = {
        query: exactSubjectQuery(subject),
        label_ids: ["SENT"],
        max_results: 100,
      };
      if (nextPageToken !== undefined) args.next_page_token = nextPageToken;
      const payload = await checkedGmailCall("search_emails", args, value => {
        if (!Array.isArray(value.emails)) {
          throw new Error("SENT search result is missing email rows");
        }
        for (const row of value.emails) {
          if (
            !row ||
            !nonEmptyString(row.id) ||
            typeof row.subject !== "string" ||
            !Array.isArray(row.labels)
          ) {
            throw new Error("SENT search row is malformed");
          }
        }
      });
      for (const row of payload.emails) {
        if (
          row.subject === subject &&
          row.labels.includes("SENT") &&
          !seen.has(row.id)
        ) {
          seen.add(row.id);
          ids.push(row.id);
        }
      }
      nextPageToken = nonEmptyString(payload.next_page_token)
        ? payload.next_page_token
        : undefined;
      if (nextPageToken === undefined) return ids;
    }
    throw new GmailBridgeError(
      "gmail_connector_validation_failed",
      "exact SENT reconciliation exceeded the bounded search page limit",
    );
  }

  async function requireStableExactSentZero(subject) {
    for (const delay of [0, 2000]) {
      if (delay > 0) await pause(delay);
      const candidates = await searchExactSentMessageIds(subject);
      if (candidates.length !== 0) {
        const error = new GmailBridgeError(
          "gmail_connector_validation_failed",
          "legacy recovery requires exact-subject SENT candidate count to remain zero",
        );
        error.noSendRetry = true;
        throw error;
      }
    }
  }

  async function attestExactSent({
    subject,
    receiptContext,
    preferredMessageId = null,
  }) {
    const ids = [];
    const seen = new Set();
    if (nonEmptyString(preferredMessageId)) {
      ids.push(preferredMessageId);
      seen.add(preferredMessageId);
    }
    for (const messageId of await searchExactSentMessageIds(subject)) {
      if (!seen.has(messageId)) {
        ids.push(messageId);
        seen.add(messageId);
      }
    }
    const verified = [];
    for (const messageId of ids) {
      const result = await attestRaw({
        ...receiptContext,
        messageId,
        stage: "sent",
      });
      if (
        result.ok === true &&
        result.stage === "sent_verified" &&
        result.subject === subject &&
        result.gmail_message_id === messageId
      ) {
        verified.push(result);
      }
    }
    if (verified.length > 1) {
      const error = new GmailBridgeError(
        "gmail_connector_validation_failed",
        "multiple exact-subject SENT messages passed raw MIME attestation",
      );
      error.noSendRetry = true;
      throw error;
    }
    return verified[0] ?? null;
  }

  async function persistVerifiedSent({
    sentAttestation,
    receiptContext,
    sendCandidate = null,
    recovery,
    leaseToken = null,
  }) {
    const receipt = await recordReceipt({
      receiptInput: sentAttestation,
      sendLeaseToken: leaseToken,
      ...receiptContext,
    });
    return Object.freeze({
      status: "sent_verified",
      id: sentAttestation.gmail_message_id,
      threadId: sendCandidate?.threadId ?? null,
      labelIds: ["SENT"],
      recovery,
      send_attempt_count: receipt.send_attempt_count,
      receipt,
    });
  }

  async function observeSendOutcome({
    subject,
    draftId,
    messageId,
    receiptContext,
    preferredMessageId = null,
    requireStableDraft,
  }) {
    let consecutiveStableDrafts = 0;
    let stableDraftAttestation = null;
    let lastObservationError = null;
    for (const delay of SEND_OBSERVATION_DELAYS_MS) {
      if (delay > 0) await pause(delay);
      let sentSearchComplete = false;
      try {
        const sentAttestation = await attestExactSent({
          subject,
          receiptContext,
          preferredMessageId,
        });
        sentSearchComplete = true;
        if (sentAttestation !== null) {
          return Object.freeze({sentAttestation, stableDraftAttestation: null});
        }
      } catch (error) {
        if (error?.noSendRetry === true) throw error;
        lastObservationError = error;
      }
      if (!requireStableDraft) continue;
      if (!sentSearchComplete) {
        consecutiveStableDrafts = 0;
        stableDraftAttestation = null;
        continue;
      }
      try {
        const draftAttestation = await attestRaw({
          ...receiptContext,
          messageId,
          draftId,
          stage: "draft",
        });
        if (
          draftAttestation.ok === true &&
          draftAttestation.stage === "draft_verified" &&
          draftAttestation.gmail_draft_id === draftId &&
          draftAttestation.gmail_draft_message_id === messageId
        ) {
          consecutiveStableDrafts += 1;
          stableDraftAttestation = draftAttestation;
        } else {
          consecutiveStableDrafts = 0;
          stableDraftAttestation = null;
        }
      } catch (error) {
        consecutiveStableDrafts = 0;
        stableDraftAttestation = null;
        lastObservationError = error;
      }
    }
    if (lastObservationError !== null && !requireStableDraft) {
      lastObservationError.deliveryOutcome = "unknown_after_send_attempt";
      lastObservationError.receiptStage = "ambiguous";
    }
    return Object.freeze({
      sentAttestation: null,
      stableDraftAttestation:
        consecutiveStableDrafts >= 2 ? stableDraftAttestation : null,
      lastObservationError,
    });
  }

  function requireSendAuthorizationScope(authorizationScope) {
    if (authorizationScope !== SEND_AUTHORIZATION_SCOPE) {
      throw new GmailBridgeError(
        "gmail_connector_pre_dispatch_denied",
        "daily arXiv send requires explicit authorization to authenticated self",
      );
    }
  }

  function requirePreparedSendProof({
    sendProof,
    draftId,
    messageId,
    attestation,
    receiptContext,
    authorizationScope,
  }) {
    const isLegacyRecovery =
      sendProof?.reauthorization_schema === LEGACY_SEND_REAUTHORIZATION_SCHEMA;
    if (
      !sendProof ||
      sendProof.prepared !== true ||
      sendProof.proof_schema !== "daily_arxiv_send_proof_v1" ||
      !nonEmptyString(sendProof.proof_token) ||
      !/^[0-9a-f]{64}$/.test(sendProof.proof_token_sha256 ?? "") ||
      !/^[0-9a-f]{64}$/.test(sendProof.proof_sha256 ?? "") ||
      sendProof.authorization_scope !== authorizationScope ||
      sendProof.subject !== attestation.subject ||
      sendProof.gmail_draft_id !== draftId ||
      sendProof.gmail_draft_message_id !== messageId ||
      sendProof.html_sha256 !== attestation.html_sha256 ||
      sendProof.pdf_sha256 !== attestation.pdf_sha256 ||
      sendProof.send_attempt_count !== receiptContext.sendAttemptCount ||
      (isLegacyRecovery && (
        sendProof.authorization_decision !==
          LEGACY_SEND_REAUTHORIZATION_DECISION ||
        sendProof.authorization_origin !== LEGACY_SEND_AUTHORIZATION_ORIGIN ||
        sendProof.exact_sent_zero_required !== true
      )) ||
      (sendProof.reauthorization_schema === SEND_REAUTHORIZATION_SCHEMA &&
        sendProof.authorization_decision !== SEND_REAUTHORIZATION_DECISION)
    ) {
      throw new GmailBridgeError(
        "gmail_connector_pre_dispatch_denied",
        "phase two requires the matching persisted phase-one send proof",
      );
    }
    return sendProof;
  }

  async function persistPreparedSendProof({
    proofInput,
    receiptContext,
  }) {
    const json = asciiJson(proofInput);
    const result = await runPythonWithInput({
      ...receiptContext,
      command: "prepare-send-proof-stdin",
      stdinChunks: [`DAXRCP1 ${json.length};\n`, `${json}\n`],
      allowedExitCodes: [0],
    });
    requirePreparedSendProof({
      sendProof: result,
      draftId: proofInput.gmail_draft_id,
      messageId: proofInput.gmail_draft_message_id,
      attestation: {
        subject: proofInput.subject,
        html_sha256: proofInput.html_sha256,
        pdf_sha256: proofInput.pdf_sha256,
      },
      receiptContext,
      authorizationScope: proofInput.authorization_scope,
    });
    locallyIssuedSendProofTokens.add(result.proof_token);
    return result;
  }

  async function acquireSendLease({
    sendProof,
    draftId,
    messageId,
    attestation,
    receiptContext,
    authorizationScope,
  }) {
    requirePreparedSendProof({
      sendProof,
      draftId,
      messageId,
      attestation,
      receiptContext,
      authorizationScope,
    });
    if (locallyIssuedSendProofTokens.has(sendProof.proof_token)) {
      throw new GmailBridgeError(
        "gmail_connector_pre_dispatch_denied",
        "phase-one proof must be consumed by a newly isolated execution phase",
      );
    }
    const profile = await getProfile();
    if (profile.email !== sendProof.destination) {
      throw new GmailBridgeError(
        "gmail_connector_pre_dispatch_denied",
        "phase-two Gmail profile does not match the authorized destination",
      );
    }
    const result = await runPythonJsonCommand({
      ...receiptContext,
      command: "gmail-send-lease-acquire",
      arguments: [
        ["--proof-token", sendProof.proof_token],
        ["--owner", "daily-arxiv-phase-two"],
        ["--wait-seconds", "45"],
      ],
    });
    const capability = result.acquired === true && nonEmptyString(result.lease_token)
      ? Object.freeze({leaseToken: result.lease_token})
      : null;
    if (capability !== null) activeSendLeaseCapabilities.add(capability);
    if (
      result.acquired !== true ||
      !nonEmptyString(result.lease_token) ||
      result.proof_sha256 !== sendProof.proof_sha256 ||
      result.authorization_scope !== authorizationScope ||
      result.destination !== sendProof.destination ||
      result.destination !== profile.email ||
      result.manifest !== sendProof.manifest ||
      result.manifest_sha256 !== sendProof.manifest_sha256 ||
      result.subject !== attestation.subject ||
      result.html_sha256 !== attestation.html_sha256 ||
      result.pdf_sha256 !== attestation.pdf_sha256 ||
      (result.reauthorization_id ?? null) !==
        (sendProof.reauthorization_id ?? null) ||
      (result.reauthorization_schema ?? null) !==
        (sendProof.reauthorization_schema ?? null) ||
      (result.authorization_decision ?? null) !==
        (sendProof.authorization_decision ?? null) ||
      (result.authorization_origin ?? null) !==
        (sendProof.authorization_origin ?? null) ||
      (result.exact_sent_zero_required ?? null) !==
        (sendProof.exact_sent_zero_required ?? null) ||
      !Number.isInteger(result.send_attempt_count) ||
      result.send_attempt_count !== sendProof.send_attempt_count ||
      result.gmail_draft_id !== draftId ||
      result.gmail_draft_message_id !== messageId
    ) {
      const mismatch = new GmailBridgeError(
        "gmail_send_lease_unavailable",
        "phase-two proof could not acquire the matching exclusive send lease",
      );
      if (capability !== null) {
        try {
          await releaseSendLease({
            leaseCapability: capability,
            receiptContext,
          });
        } catch (releaseError) {
          mismatch.leaseReleaseFailure = diagnostic(releaseError).failure_code;
        }
      }
      throw mismatch;
    }
    return Object.freeze({capability, result});
  }

  async function releaseSendLease({leaseCapability, receiptContext}) {
    if (!activeSendLeaseCapabilities.has(leaseCapability)) return;
    let lastError = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const result = await runPythonJsonCommand({
          ...receiptContext,
          command: "gmail-send-lease-release",
          arguments: [["--lease-token", leaseCapability.leaseToken]],
        });
        if (result.released !== true) {
          throw new GmailBridgeError(
            "local_attestation_process_error",
            "exclusive send lease release was not confirmed",
          );
        }
        activeSendLeaseCapabilities.delete(leaseCapability);
        return;
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError;
  }

  async function prepareVerifiedDraftSend({
    draftId,
    messageId,
    attestation,
    authorizationScope,
  }) {
    requireSendAuthorizationScope(authorizationScope);
    const receiptContext = draftReceiptContext({draftId, messageId, attestation});
    await requireDraftBinding(draftId, messageId);
    const existingSent = await attestExactSent({
      subject: attestation.subject,
      receiptContext,
    });
    if (existingSent !== null) {
      return persistVerifiedSent({
        sentAttestation: existingSent,
        receiptContext,
        recovery: "pre_send_exact_sent",
      });
    }
    if (receiptContext.sendAttemptCount >= MAX_SEND_ATTEMPTS) {
      return Object.freeze({
        status: "send_blocked",
        proof_schema: "daily_arxiv_verified_draft_send_v1",
        authorization_scope: SEND_AUTHORIZATION_SCOPE,
        reason: "send_attempt_budget_exhausted",
        subject: attestation.subject,
        gmail_draft_id: draftId,
        gmail_draft_message_id: messageId,
        send_attempt_count: receiptContext.sendAttemptCount,
        max_send_attempts: MAX_SEND_ATTEMPTS,
        attempts_remaining: 0,
      });
    }
    const profile = await getProfile();
    const evidence = attestation.attestation ?? {};
    const proof = await persistPreparedSendProof({
      receiptContext,
      proofInput: {
        authorization_scope: SEND_AUTHORIZATION_SCOPE,
        destination: profile.email,
        subject: attestation.subject,
        gmail_draft_id: draftId,
        gmail_draft_message_id: messageId,
        html_sha256: attestation.html_sha256,
        pdf_sha256: attestation.pdf_sha256,
        send_attempt_count: receiptContext.sendAttemptCount,
      },
    });
    return Object.freeze({
      ...proof,
      status: "ready_to_send",
      authorization_scope: SEND_AUTHORIZATION_SCOPE,
      authorization_status: "explicit_user_authorized",
      operation: "gmail.send_draft",
      destination: profile.email,
      recipient_count: 1,
      cc_count: 0,
      bcc_count: 0,
      subject: attestation.subject,
      gmail_draft_id: draftId,
      gmail_draft_message_id: messageId,
      html_bytes: evidence.html_bytes,
      html_sha256: attestation.html_sha256,
      pdf_filename: evidence.pdf_filename,
      pdf_bytes: evidence.pdf_bytes,
      pdf_sha256: attestation.pdf_sha256,
      raw_mime_attested: true,
      exact_subject_sent_candidates_verified: 0,
      send_attempt_count: receiptContext.sendAttemptCount,
      max_send_attempts: MAX_SEND_ATTEMPTS,
      attempts_remaining:
        MAX_SEND_ATTEMPTS - receiptContext.sendAttemptCount,
      required_next_step:
        "start a new execution phase, re-attest this same Draft, then call sendVerifiedDraftRecovering",
    });
  }

  async function inspectLegacyRecoveryCandidate({
    draftId,
    messageId,
    attestation,
    authorizationScope,
  }) {
    requireSendAuthorizationScope(authorizationScope);
    if (
      !verifiedRawResults.has(attestation) ||
      attestation?.stage !== "draft_verified" ||
      attestation.gmail_draft_id !== draftId ||
      attestation.gmail_draft_message_id !== messageId
    ) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "legacy recovery inspection requires a fresh verified Draft raw-MIME attestation",
      );
    }
    await requireDraftBinding(draftId, messageId);
    const profile = await getProfile();
    await requireStableExactSentZero(attestation.subject);
    return Object.freeze({
      status: "legacy_recovery_conditions_verified",
      authorization_scope: SEND_AUTHORIZATION_SCOPE,
      destination: profile.email,
      subject: attestation.subject,
      gmail_draft_id: draftId,
      gmail_draft_message_id: messageId,
      html_sha256: attestation.html_sha256,
      pdf_sha256: attestation.pdf_sha256,
      send_attempt_count: 1,
      exact_subject_sent_candidates_verified: 0,
      raw_mime_attested: true,
    });
  }

  function requireSendReauthorizationGrant({
    reauthorizationGrant,
    draftId,
    messageId,
    attestation,
    authorizationScope,
    legacyRecovery = false,
  }) {
    const expectedSchema = legacyRecovery
      ? LEGACY_SEND_REAUTHORIZATION_SCHEMA
      : SEND_REAUTHORIZATION_SCHEMA;
    const expectedDecision = legacyRecovery
      ? LEGACY_SEND_REAUTHORIZATION_DECISION
      : SEND_REAUTHORIZATION_DECISION;
    if (
      !reauthorizationGrant ||
      reauthorizationGrant.issued !== true ||
      reauthorizationGrant.reauthorization_schema !== expectedSchema ||
      !nonEmptyString(reauthorizationGrant.reauthorization_token) ||
      !/^[0-9a-f]{32}$/.test(
        reauthorizationGrant.reauthorization_id ?? "",
      ) ||
      !/^[0-9a-f]{64}$/.test(
        reauthorizationGrant.reauthorization_token_sha256 ?? "",
      ) ||
      !/^[0-9a-f]{64}$/.test(
        reauthorizationGrant.reauthorization_binding_sha256 ?? "",
      ) ||
      reauthorizationGrant.authorization_scope !== authorizationScope ||
      reauthorizationGrant.authorization_decision !== expectedDecision ||
      reauthorizationGrant.subject !== attestation.subject ||
      reauthorizationGrant.gmail_draft_id !== draftId ||
      reauthorizationGrant.gmail_draft_message_id !== messageId ||
      reauthorizationGrant.html_sha256 !== attestation.html_sha256 ||
      reauthorizationGrant.pdf_sha256 !== attestation.pdf_sha256 ||
      reauthorizationGrant.send_attempt_count !== 1 ||
      (legacyRecovery && (
        reauthorizationGrant.authorization_origin !==
          LEGACY_SEND_AUTHORIZATION_ORIGIN ||
        reauthorizationGrant.exact_sent_zero_required !== true
      ))
    ) {
      throw new GmailBridgeError(
        "gmail_connector_pre_dispatch_denied",
        "explicit reauthorization grant does not match the fresh verified Draft",
      );
    }
    return reauthorizationGrant;
  }

  async function prepareReauthorizedDraftSend({
    draftId,
    messageId,
    attestation,
    authorizationScope,
    reauthorizationGrant,
    legacyRecovery,
  }) {
    requireSendAuthorizationScope(authorizationScope);
    if (
      !verifiedRawResults.has(attestation) ||
      attestation?.stage !== "draft_verified" ||
      attestation.gmail_draft_id !== draftId ||
      attestation.gmail_draft_message_id !== messageId
    ) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "explicit reauthorization requires a live fresh Draft raw-MIME attestation",
      );
    }
    const grant = requireSendReauthorizationGrant({
      reauthorizationGrant,
      draftId,
      messageId,
      attestation,
      authorizationScope,
      legacyRecovery,
    });
    const processContext = rawAttestationContexts.get(attestation);
    if (processContext === undefined) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "explicit reauthorization lost the raw-attestation process context",
      );
    }
    const profile = await getProfile();
    if (profile.email !== grant.destination) {
      throw new GmailBridgeError(
        "gmail_connector_pre_dispatch_denied",
        "reauthorization destination does not match the active Gmail profile",
      );
    }
    const preSendContext = Object.freeze({
      ...processContext,
      sendAttemptCount: grant.send_attempt_count,
    });
    if (legacyRecovery) {
      await requireStableExactSentZero(attestation.subject);
    } else {
      const existingSent = await attestExactSent({
        subject: attestation.subject,
        receiptContext: preSendContext,
      });
      if (existingSent !== null) {
        return persistVerifiedSent({
          sentAttestation: existingSent,
          receiptContext: preSendContext,
          recovery: "reauthorization_pre_send_exact_sent",
        });
      }
    }
    const json = asciiJson(attestation);
    const proof = await runPythonWithInput({
      ...processContext,
      command: "prepare-reauthorized-send-proof-stdin",
      arguments: [
        ["--reauthorization-token", grant.reauthorization_token],
      ],
      stdinChunks: [`DAXRCP1 ${json.length};\n`, `${json}\n`],
      allowedExitCodes: [0],
    });
    const receiptContext = Object.freeze({
      ...processContext,
      receiptProof: Object.freeze({
        receipt: proof.reauthorized_receipt,
        manifest: proof.manifest,
        manifestSha256: proof.manifest_sha256,
      }),
      sendAttemptCount: proof.send_attempt_count,
    });
    requirePreparedSendProof({
      sendProof: proof,
      draftId,
      messageId,
      attestation,
      receiptContext,
      authorizationScope,
    });
    if (
      proof.reauthorization_consumed !== true ||
      proof.reauthorization_id !== grant.reauthorization_id ||
      proof.reauthorization_schema !== grant.reauthorization_schema ||
      (legacyRecovery && (
        proof.authorization_origin !== LEGACY_SEND_AUTHORIZATION_ORIGIN ||
        proof.exact_sent_zero_required !== true
      )) ||
      !nonEmptyString(proof.reauthorized_receipt) ||
      proof.destination !== grant.destination
    ) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "reauthorized proof result did not preserve the audited grant binding",
      );
    }
    attestation.send_attempt_count = proof.send_attempt_count;
    recordedDraftReceiptContexts.set(attestation, receiptContext);
    locallyIssuedSendProofTokens.add(proof.proof_token);
    return Object.freeze({
      ...proof,
      status: "ready_to_send",
      authorization_status: legacyRecovery
        ? "explicit_user_authorized_legacy_recovery"
        : "explicit_user_reauthorized",
      operation: "gmail.send_draft",
      recipient_count: 1,
      cc_count: 0,
      bcc_count: 0,
      raw_mime_attested: true,
      exact_subject_sent_candidates_verified: 0,
      max_send_attempts: MAX_SEND_ATTEMPTS,
      attempts_remaining: MAX_SEND_ATTEMPTS - proof.send_attempt_count,
      required_next_step:
        "start a new isolated execution phase, re-attest this same Draft, then call sendVerifiedDraftRecovering",
    });
  }

  async function prepareExplicitlyReauthorizedDraftSend(args) {
    return prepareReauthorizedDraftSend({...args, legacyRecovery: false});
  }

  async function prepareExplicitlyAuthorizedLegacyDraftSend(args) {
    return prepareReauthorizedDraftSend({...args, legacyRecovery: true});
  }

  async function sendVerifiedDraftRecovering({
    draftId,
    messageId,
    attestation,
    authorizationScope,
    sendProof,
  }) {
    requireSendAuthorizationScope(authorizationScope);
    const initialReceiptContext = draftReceiptContext({
      draftId,
      messageId,
      attestation,
    });
    const lease = await acquireSendLease({
      sendProof,
      draftId,
      messageId,
      attestation,
      receiptContext: initialReceiptContext,
      authorizationScope,
    });
    const leaseCapability = lease.capability;
    let primaryError = null;
    let outcome = null;
    try {
      outcome = await (async () => {
        let receiptContext = Object.freeze({
          ...initialReceiptContext,
          sendAttemptCount: lease.result.send_attempt_count,
        });
        recordedDraftReceiptContexts.set(attestation, receiptContext);
        const isLegacyRecovery =
          sendProof.reauthorization_schema ===
            LEGACY_SEND_REAUTHORIZATION_SCHEMA;
        if (isLegacyRecovery) {
          await requireStableExactSentZero(attestation.subject);
        } else {
          const alreadySent = await attestExactSent({
            subject: attestation.subject,
            receiptContext,
          });
          if (alreadySent !== null) {
            return persistVerifiedSent({
              sentAttestation: alreadySent,
              receiptContext,
              recovery: "pre_attempt_exact_sent",
              leaseToken: leaseCapability.leaseToken,
            });
          }
        }

        let firstCandidate = null;
        let firstError = null;
        try {
          const firstAttempt = await attemptVerifiedDraftOnce({
            draftId,
            messageId,
            attestation,
            receiptContext,
            leaseCapability,
          });
          firstCandidate = firstAttempt.candidate;
          receiptContext = Object.freeze({
            ...receiptContext,
            sendAttemptCount: firstAttempt.sendAttemptCount,
          });
        } catch (error) {
          firstError = error;
          if (Number.isInteger(error?.sendAttemptCount)) {
            receiptContext = Object.freeze({
              ...receiptContext,
              sendAttemptCount: error.sendAttemptCount,
            });
          }
        }
        if (
          firstError?.failureCode === "gmail_connector_pre_dispatch_denied" ||
          firstError?.deliveryOutcome === "not_attempted"
        ) {
          throw firstError;
        }

        const firstObservation = await observeSendOutcome({
          subject: attestation.subject,
          draftId,
          messageId,
          receiptContext,
          preferredMessageId: firstCandidate?.id ?? null,
          requireStableDraft: firstError?.retryAllowed === true,
        });
        if (firstObservation.sentAttestation !== null) {
          return persistVerifiedSent({
            sentAttestation: firstObservation.sentAttestation,
            receiptContext,
            sendCandidate: firstCandidate,
            recovery: firstCandidate === null
              ? "first_attempt_reconciled"
              : "first_attempt_verified",
            leaseToken: leaseCapability.leaseToken,
          });
        }
        if (firstCandidate !== null) {
          const blocked = new GmailBridgeError(
            "gmail_send_automatic_retry_blocked",
            "send returned a candidate identity but SENT attestation did not stabilize; automatic resend is blocked",
          );
          blocked.deliveryOutcome = "unknown_no_automatic_retry";
          blocked.receiptStage = "ambiguous";
          blocked.retryAllowed = false;
          throw blocked;
        }
        if (firstError?.retryAllowed !== true) {
          throw firstError ?? new GmailBridgeError(
            "gmail_send_outcome_unknown",
            "send produced no candidate and no explicitly retryable transport outcome",
          );
        }
        if (firstObservation.stableDraftAttestation === null) {
          throw firstError;
        }

        const retryAttestation = firstObservation.stableDraftAttestation;
        retryAttestation.send_attempt_count = receiptContext.sendAttemptCount;
        leaseRetryDraftReceiptContexts.set(retryAttestation, receiptContext);
        let retryCandidate = null;
        let retryError = null;
        try {
          const retryAttempt = await attemptVerifiedDraftOnce({
            draftId,
            messageId,
            attestation: retryAttestation,
            receiptContext,
            leaseCapability,
          });
          retryCandidate = retryAttempt.candidate;
          receiptContext = Object.freeze({
            ...receiptContext,
            sendAttemptCount: retryAttempt.sendAttemptCount,
          });
        } catch (error) {
          retryError = error;
          if (Number.isInteger(error?.sendAttemptCount)) {
            receiptContext = Object.freeze({
              ...receiptContext,
              sendAttemptCount: error.sendAttemptCount,
            });
          }
        }
        if (
          retryError?.failureCode === "gmail_connector_pre_dispatch_denied" ||
          retryError?.deliveryOutcome === "not_attempted"
        ) {
          throw retryError;
        }

        const retryObservation = await observeSendOutcome({
          subject: retryAttestation.subject,
          draftId,
          messageId,
          receiptContext,
          preferredMessageId: retryCandidate?.id ?? null,
          requireStableDraft: false,
        });
        if (retryObservation.sentAttestation !== null) {
          return persistVerifiedSent({
            sentAttestation: retryObservation.sentAttestation,
            receiptContext,
            sendCandidate: retryCandidate,
            recovery: retryCandidate === null
              ? "retry_reconciled"
              : "retry_verified",
            leaseToken: leaseCapability.leaseToken,
          });
        }
        const exhausted = retryCandidate !== null
          ? new GmailBridgeError(
              "gmail_send_automatic_retry_blocked",
              "bounded retry returned a candidate identity but no raw-MIME-attested SENT message; automatic resend is blocked",
            )
          : retryError ?? new GmailBridgeError(
              "gmail_send_automatic_retry_blocked",
              "bounded retry returned no raw-MIME-attested SENT message; automatic resend is blocked",
            );
        exhausted.deliveryOutcome = retryCandidate !== null
          ? "unknown_no_automatic_retry"
          : "unknown_after_send_attempt";
        exhausted.receiptStage = "ambiguous";
        exhausted.retryAllowed = false;
        throw exhausted;
      })();
    } catch (error) {
      primaryError = error;
    }
    let releaseError = null;
    try {
      await releaseSendLease({
        leaseCapability,
        receiptContext: initialReceiptContext,
      });
    } catch (error) {
      releaseError = error;
    }
    if (primaryError !== null) {
      if (releaseError !== null) {
        primaryError.leaseReleaseFailure = diagnostic(releaseError).failure_code;
      }
      throw primaryError;
    }
    if (releaseError !== null) throw releaseError;
    return outcome;
  }

  async function readRawMessage(messageId) {
    const readMinimal = () => callGmail(
      "read_email",
      {message_id: messageId, format: "minimal"},
      payload => {
        if (
          payload.id !== messageId ||
          !Array.isArray(payload.label_ids) ||
          !nonEmptyString(payload.history_id)
        ) {
          throw new Error("invalid minimal readback payload");
        }
      },
    );
    const metadataBefore = await readMinimal();
    const raw = await callGmail(
      "read_email",
      {message_id: messageId, format: "raw"},
      payload => {
        if (
          payload.id !== messageId ||
          typeof payload.raw !== "string" ||
          payload.raw.length === 0
        ) {
          throw new Error("invalid raw readback payload");
        }
      },
    );
    const metadataAfter = await readMinimal();
    const beforeLabels = [...metadataBefore.label_ids].sort();
    const afterLabels = [...metadataAfter.label_ids].sort();
    if (
      metadataBefore.history_id !== metadataAfter.history_id ||
      metadataBefore.internal_date !== metadataAfter.internal_date ||
      JSON.stringify(beforeLabels) !== JSON.stringify(afterLabels) ||
      (raw.history_id !== null &&
        raw.history_id !== undefined &&
        raw.history_id !== metadataAfter.history_id) ||
      (raw.internal_date !== null &&
        raw.internal_date !== undefined &&
        raw.internal_date !== metadataAfter.internal_date) ||
      (Array.isArray(raw.label_ids) &&
        JSON.stringify([...raw.label_ids].sort()) !== JSON.stringify(afterLabels))
    ) {
      throw new GmailBridgeError(
        "gmail_connector_validation_failed",
        "Gmail message changed during raw MIME readback",
      );
    }
    return {...raw, label_ids: metadataAfter.label_ids};
  }

  function quotePowerShell(value) {
    return `'${String(value).replaceAll("'", "''")}'`;
  }

  function mimePreparationError(failureCode, detail, stage = "mime_prepare") {
    const error = new GmailBridgeError(failureCode, detail);
    error.failureStage = stage;
    return error;
  }

  function validateMimePreparationContext(context) {
    const reject = () => {
      throw mimePreparationError(
        "local_mime_manifest_invalid",
        "MIME preparation requires a validated single HTML and PDF delivery manifest",
      );
    };
    if (!context || typeof context !== "object") reject();
    for (const field of ["pythonExe", "scriptPath", "workdir"]) {
      if (!nonEmptyString(context[field]) || /[\x00\r\n]/.test(context[field])) {
        reject();
      }
    }
    if (context.publicConfigPath !== undefined && (
      !nonEmptyString(context.publicConfigPath) || /[\x00\r\n]/.test(context.publicConfigPath)
    )) reject();
    const manifest = context.manifest;
    if (
      !manifest || typeof manifest !== "object" || Array.isArray(manifest) ||
      manifest.validated !== true ||
      manifest.delivery_format !== "html_pdf_single" ||
      manifest.message_count !== 1 || manifest.attachment_count !== 1 ||
      manifest.mime_chunk_bytes !== MIME_CHUNK_BYTES ||
      !nonEmptyString(manifest.pdf_filename) ||
      /[\x00-\x1f\x7f/\\]/.test(manifest.pdf_filename) ||
      manifest.pdf_filename === "." || manifest.pdf_filename === ".."
    ) reject();
    for (const [kind, limit] of [["html", HTML_MAX_BYTES], ["pdf", PDF_MAX_BYTES]]) {
      if (
        !nonEmptyString(manifest[`${kind}_path`]) ||
        /[\x00\r\n]/.test(manifest[`${kind}_path`]) ||
        !Number.isSafeInteger(manifest[`${kind}_bytes`]) ||
        manifest[`${kind}_bytes`] <= 0 || manifest[`${kind}_bytes`] > limit ||
        typeof manifest[`${kind}_sha256`] !== "string" ||
        !/^[0-9a-f]{64}$/.test(manifest[`${kind}_sha256`])
      ) reject();
    }
    if (manifest.pdf_path.split(/[\\/]/).at(-1) !== manifest.pdf_filename) reject();
    // Snapshot only validated scalar inputs before the first asynchronous read.
    return Object.freeze({
      pythonExe: context.pythonExe,
      scriptPath: context.scriptPath,
      workdir: context.workdir,
      publicConfigPath: context.publicConfigPath,
      manifest: Object.freeze({
        html_path: manifest.html_path,
        html_bytes: manifest.html_bytes,
        html_sha256: manifest.html_sha256,
        pdf_path: manifest.pdf_path,
        pdf_bytes: manifest.pdf_bytes,
        pdf_sha256: manifest.pdf_sha256,
        pdf_filename: manifest.pdf_filename,
      }),
    });
  }

  function validMimeChunkBase64(value, byteCount) {
    if (
      typeof value !== "string" ||
      value.length !== 4 * Math.ceil(byteCount / 3) ||
      !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)
    ) return false;
    const remainder = byteCount % 3;
    const padding = remainder === 0 ? 0 : 3 - remainder;
    if (
      (padding === 0 && value.endsWith("=")) ||
      (padding === 1 && (!value.endsWith("=") || value.endsWith("=="))) ||
      (padding === 2 && !value.endsWith("=="))
    ) return false;
    // Require canonical pad bits as well as alphabet, size and padding count.
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    if (padding > 0) {
      const last = alphabet.indexOf(value[value.length - padding - 1]);
      if ((last & (padding === 2 ? 15 : 3)) !== 0) return false;
    }
    return true;
  }

  async function runMimeChunkRead(context, kind, offset, outputTokens) {
    const {pythonExe, scriptPath, workdir, publicConfigPath, manifest} = context;
    const shellCommand =
      `& ${quotePowerShell(pythonExe)} -B ${quotePowerShell(scriptPath)}` +
      (publicConfigPath === undefined ? "" : ` --public-config ${quotePowerShell(publicConfigPath)}`) +
      ` mime-chunk --path ${quotePowerShell(manifest[`${kind}_path`])}` +
      ` --expected-size ${manifest[`${kind}_bytes`]}` +
      ` --expected-sha256 ${quotePowerShell(manifest[`${kind}_sha256`])}` +
      ` --offset ${offset} --max-bytes ${MIME_CHUNK_BYTES}` +
      "; exit $LASTEXITCODE";
    const processError = () => mimePreparationError(
      "local_mime_chunk_process_error",
      "Attested MIME chunk reader did not complete successfully",
      "mime_chunk_read",
    );
    let current;
    let output = "";
    let truncated = false;
    let sessionId;
    const collect = result => {
      if (
        !result || typeof result !== "object" ||
        typeof result.output !== "string" || failureOf(result) !== null
      ) throw processError();
      if (result.session_id !== undefined) {
        if (
          !Number.isSafeInteger(result.session_id) || result.session_id <= 0 ||
          (sessionId !== undefined && sessionId !== result.session_id)
        ) throw processError();
        sessionId = result.session_id;
      }
      output += result.output;
      truncated ||= result.truncated === true || result.output_truncated === true ||
        MIME_OUTPUT_TRUNCATION.test(result.output);
      return result;
    };
    try {
      current = collect(await tools.exec_command({
        cmd: shellCommand,
        workdir,
        shell: "powershell",
        login: false,
        tty: false,
        yield_time_ms: 30000,
        max_output_tokens: outputTokens,
      }));
      // Drain this exact process before considering a fresh read.  An unfinished
      // session, connector/tool exception, or nonzero exit is never a retry cue.
      for (let poll = 0; current.exit_code === undefined && poll < 15; poll += 1) {
        if (sessionId === undefined) throw processError();
        current = collect(await tools.write_stdin({
          session_id: sessionId,
          chars: "",
          yield_time_ms: 10000,
          max_output_tokens: outputTokens,
        }));
      }
    } catch {
      throw processError();
    }
    if (current.exit_code !== 0) throw processError();
    return {output, truncated: truncated || MIME_OUTPUT_TRUNCATION.test(output)};
  }

  async function readMimeArtifact(context, kind) {
    const expectedSize = context.manifest[`${kind}_bytes`];
    const chunks = [];
    let offset = 0;
    while (offset < expectedSize) {
      let result;
      for (const outputTokens of MIME_CHUNK_OUTPUT_TOKENS) {
        result = await runMimeChunkRead(context, kind, offset, outputTokens);
        if (!result.truncated) break;
      }
      if (result.truncated) {
        throw mimePreparationError(
          "local_mime_chunk_output_truncated",
          "Attested MIME chunk output remained truncated after bounded read-only recovery",
          "mime_chunk_read",
        );
      }
      const invalid = () => mimePreparationError(
        "local_mime_chunk_invalid",
        "Attested MIME chunk failed JSON, offset, length, EOF or base64 validation",
        "mime_chunk_read",
      );
      let chunk;
      try {
        // Never salvage a JSON-looking substring from terminal noise or errors.
        chunk = JSON.parse(result.output);
      } catch {
        throw invalid();
      }
      const expectedBytes = Math.min(MIME_CHUNK_BYTES, expectedSize - offset);
      if (
        !chunk || typeof chunk !== "object" || Array.isArray(chunk) ||
        Object.keys(chunk).sort().join(",") !== "base64,bytes,eof,next_offset,offset" ||
        chunk.offset !== offset || chunk.bytes !== expectedBytes ||
        chunk.next_offset !== offset + expectedBytes ||
        chunk.eof !== (offset + expectedBytes === expectedSize) ||
        !validMimeChunkBase64(chunk.base64, expectedBytes)
      ) throw invalid();
      chunks.push(chunk.base64);
      offset = chunk.next_offset;
    }
    // All nonfinal reads have a size divisible by three, so concatenation never
    // places base64 padding inside the payload.  Each source was SHA-256 checked
    // by the Python reader on every read, including any truncation recovery.
    const encoded = chunks.join("");
    if (offset !== expectedSize || encoded.length !== 4 * Math.ceil(expectedSize / 3)) {
      throw mimePreparationError(
        "local_mime_chunk_invalid",
        "Attested MIME artifact total length does not match its manifest",
        "mime_chunk_read",
      );
    }
    return encoded.replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
  }

  async function prepareMimePayload(input) {
    const context = validateMimePreparationContext(input);
    const html = await readMimeArtifact(context, "html");
    const pdf = await readMimeArtifact(context, "pdf");
    return {
      mime_type: "multipart/mixed",
      parts: [
        {
          mime_type: "text/html",
          charset: "utf-8",
          content_disposition: "inline",
          body: {base64_url_content: html},
        },
        {
          mime_type: "application/pdf",
          filename: context.manifest.pdf_filename,
          content_disposition: "attachment",
          body: {base64_url_content: pdf},
        },
      ],
    };
  }

  function asciiJson(value) {
    return JSON.stringify(value).replace(
      /[^\x00-\x7f]/g,
      character =>
        `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`,
    );
  }

  function stripTerminalControls(value) {
    return String(value)
      .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
      .replace(/\x1b\[[0-?]*[ -\/]*[@-~]/g, "");
  }

  function sawReady(output) {
    return stripTerminalControls(output)
      .split(/[\r\n]+/)
      .some(line => line.trim() === "DAX_STDIN_READY");
  }

  function parseCompactJson(output, operation) {
    const clean = stripTerminalControls(String(output));
    const lines = clean
      .split(/\r?\n/)
      .map(line => line.trim())
      .filter(Boolean);
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      if (!lines[index].startsWith("{")) continue;
      try {
        const value = JSON.parse(lines[index]);
        if (value && typeof value === "object") return value;
      } catch {
        // Continue looking for the one compact JSON result line.
      }
    }
    // ConPTY may visually wrap a long one-line JSON result into physical lines.
    // Scan balanced objects after removing those transport newlines, choosing the
    // last parseable object so an echoed framed input can never replace the result.
    const joined = clean.replace(/[\r\n]+/g, "");
    const finalBrace = joined.lastIndexOf("}");
    if (finalBrace >= 0) {
      for (
        let candidateStart = joined.lastIndexOf("{", finalBrace);
        candidateStart >= 0;
        candidateStart = joined.lastIndexOf("{", candidateStart - 1)
      ) {
        try {
          const parsed = JSON.parse(joined.slice(candidateStart, finalBrace + 1));
          if (parsed && typeof parsed === "object") return parsed;
        } catch {
          // Move to the prior opening brace until the complete final object parses.
        }
      }
    }
    const parsedObjects = [];
    let start = -1;
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let index = 0; index < joined.length; index += 1) {
      const character = joined[index];
      if (start < 0) {
        if (character === "{") {
          start = index;
          depth = 1;
          inString = false;
          escaped = false;
        }
        continue;
      }
      if (inString) {
        if (escaped) escaped = false;
        else if (character === "\\") escaped = true;
        else if (character === '"') inString = false;
        continue;
      }
      if (character === '"') inString = true;
      else if (character === "{") depth += 1;
      else if (character === "}") {
        depth -= 1;
        if (depth === 0) {
          try {
            parsedObjects.push(JSON.parse(joined.slice(start, index + 1)));
          } catch {
            // Ignore terminal noise and echoed, incomplete JSON objects.
          }
          start = -1;
        }
      }
    }
    if (parsedObjects.length > 0) return parsedObjects.at(-1);
    throw new GmailBridgeError(
      "local_attestation_process_error",
      `${operation} returned no compact JSON result`,
    );
  }

  async function runPythonJsonCommand({
    pythonExe,
    scriptPath,
    command,
    root,
    manifestPath,
    arguments: commandArguments = [],
    workdir,
    allowedExitCodes = [0],
  }) {
    const argumentText = commandArguments
      .map(([name, value]) => {
        if (!/^--[a-z0-9-]+$/.test(name)) {
          throw new GmailBridgeError(
            "local_attestation_process_error",
            "local delivery command has an invalid argument name",
          );
        }
        return ` ${name} ${quotePowerShell(value)}`;
      })
      .join("");
    const shellCommand =
      `& ${quotePowerShell(pythonExe)} -B ${quotePowerShell(scriptPath)}` +
      ` ${command} --root ${quotePowerShell(root)}` +
      ` --manifest ${quotePowerShell(manifestPath)}${argumentText}` +
      "; exit $LASTEXITCODE";
    let current = await tools.exec_command({
      cmd: shellCommand,
      workdir,
      shell: "powershell",
      login: false,
      tty: false,
      yield_time_ms: 30000,
      max_output_tokens: PYTHON_OUTPUT_TOKENS,
    });
    let output = current.output ?? "";
    let sessionId = current.session_id;
    for (let poll = 0; current.exit_code === undefined && poll < 15; poll += 1) {
      if (sessionId === undefined) break;
      current = await tools.write_stdin({
        session_id: sessionId,
        chars: "",
        yield_time_ms: 10000,
        max_output_tokens: PYTHON_OUTPUT_TOKENS,
      });
      output += current.output ?? "";
      if (current.session_id !== undefined) sessionId = current.session_id;
    }
    if (
      current.exit_code === undefined ||
      !allowedExitCodes.includes(current.exit_code)
    ) {
      const processFailure = safeProcessFailure(output);
      throw new GmailBridgeError(
        "local_attestation_process_error",
        `${command} failed (${processFailure ?? `exit=${current.exit_code ?? "timeout"}`})`,
      );
    }
    return parseCompactJson(output, command);
  }

  function safeProcessFailure(output) {
    const clean = stripTerminalControls(output);
    const match = clean.match(/(?:^|[\r\n])error:\s+([^\r\n]{1,512})/i);
    if (match !== null) return match[1].trim();
    if (clean.includes("Traceback (most recent call last):")) {
      const lines = clean
        .split(/[\r\n]+/)
        .map(line => line.trim())
        .filter(Boolean);
      const last = lines.at(-1) ?? "unknown Python exception";
      return `local validator exception: ${last.slice(0, 384)}`;
    }
    return null;
  }

  function asciiBase64(value) {
    if (!/^[\x00-\x7f]*$/.test(value)) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "piped receipt frame must be ASCII",
      );
    }
    const alphabet =
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let encoded = "";
    for (let offset = 0; offset < value.length; offset += 3) {
      const first = value.charCodeAt(offset);
      const hasSecond = offset + 1 < value.length;
      const hasThird = offset + 2 < value.length;
      const second = hasSecond ? value.charCodeAt(offset + 1) : 0;
      const third = hasThird ? value.charCodeAt(offset + 2) : 0;
      encoded += alphabet[first >> 2];
      encoded += alphabet[((first & 3) << 4) | (second >> 4)];
      encoded += hasSecond
        ? alphabet[((second & 15) << 2) | (third >> 6)]
        : "=";
      encoded += hasThird ? alphabet[third & 63] : "=";
    }
    return encoded;
  }

  async function runPythonWithPipedReceipt({
    pythonExe,
    scriptPath,
    command,
    root,
    manifestPath,
    sendLeaseToken,
    commandArguments,
    stdinChunks,
    workdir,
    allowedExitCodes,
  }) {
    const processArguments = [
      "-B",
      scriptPath,
      command,
      "--root",
      root,
      "--manifest",
      manifestPath,
    ];
    if (sendLeaseToken !== null) {
      processArguments.push("--send-lease-token", sendLeaseToken);
    }
    for (const [name, value] of commandArguments) {
      processArguments.push(name, String(value));
    }
    const addArguments = processArguments
      .map(value => `[void]$daxPsi.ArgumentList.Add(${quotePowerShell(value)})`)
      .join("; ");
    const framedBase64 = asciiBase64(stdinChunks.join(""));
    if (framedBase64.length > 24_000) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "piped receipt frame exceeds the bounded Windows command length",
      );
    }
    const shellCommand =
      "$daxPsi=[Diagnostics.ProcessStartInfo]::new(); " +
      `$daxPsi.FileName=${quotePowerShell(pythonExe)}; ` +
      "$daxPsi.UseShellExecute=$false; " +
      "$daxPsi.RedirectStandardInput=$true; " +
      "$daxPsi.RedirectStandardOutput=$true; " +
      "$daxPsi.RedirectStandardError=$true; " +
      `${addArguments}; ` +
      "$daxProcess=[Diagnostics.Process]::new(); " +
      "$daxProcess.StartInfo=$daxPsi; [void]$daxProcess.Start(); " +
      `$daxBytes=[Convert]::FromBase64String(${quotePowerShell(framedBase64)}); ` +
      "$daxProcess.StandardInput.BaseStream.Write($daxBytes,0,$daxBytes.Length); " +
      "$daxProcess.StandardInput.Close(); " +
      "$daxStdout=$daxProcess.StandardOutput.ReadToEnd(); " +
      "$daxStderr=$daxProcess.StandardError.ReadToEnd(); " +
      "$daxProcess.WaitForExit(); [Console]::Out.Write($daxStdout); " +
      "if($daxStderr){[Console]::Error.Write($daxStderr)}; " +
      "exit $daxProcess.ExitCode";
    let current = await tools.exec_command({
      cmd: shellCommand,
      workdir,
      shell: "powershell",
      login: false,
      tty: false,
      yield_time_ms: 30000,
      max_output_tokens: PYTHON_OUTPUT_TOKENS,
    });
    let output = current.output ?? "";
    let sessionId = current.session_id;
    for (let poll = 0; current.exit_code === undefined && poll < 15; poll += 1) {
      current = await tools.write_stdin({
        session_id: sessionId,
        chars: "",
        yield_time_ms: 10000,
        max_output_tokens: PYTHON_OUTPUT_TOKENS,
      });
      output += current.output ?? "";
      if (current.session_id !== undefined) sessionId = current.session_id;
    }
    if (
      current.exit_code === undefined ||
      !allowedExitCodes.includes(current.exit_code)
    ) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        `${command} piped receipt process failed (${safeProcessFailure(output) ?? `exit=${current.exit_code ?? "timeout"}`})`,
      );
    }
    return parseCompactJson(output, command);
  }

  async function runPythonWithInput({
    pythonExe,
    scriptPath,
    command,
    root,
    manifestPath,
    stage = null,
    sendLeaseToken = null,
    arguments: commandArguments = [],
    stdinChunks,
    workdir,
    allowedExitCodes,
    pipedReceiptInput = false,
  }) {
    if (pipedReceiptInput && command === "record-receipt-stdin") {
      return runPythonWithPipedReceipt({
        pythonExe,
        scriptPath,
        command,
        root,
        manifestPath,
        sendLeaseToken,
        commandArguments,
        stdinChunks,
        workdir,
        allowedExitCodes,
      });
    }
    const stageArgs = stage === null ? "" : ` --stage ${quotePowerShell(stage)}`;
    const leaseArgs = sendLeaseToken === null
      ? ""
      : ` --send-lease-token ${quotePowerShell(sendLeaseToken)}`;
    const argumentText = commandArguments
      .map(([name, value]) => {
        if (!/^--[a-z0-9-]+$/.test(name)) {
          throw new GmailBridgeError(
            "local_attestation_process_error",
            "local framed-input command has an invalid argument name",
          );
        }
        return ` ${name} ${quotePowerShell(value)}`;
      })
      .join("");
    const shellCommand =
      `& ${quotePowerShell(pythonExe)} -B ${quotePowerShell(scriptPath)}` +
      ` ${command} --root ${quotePowerShell(root)}` +
      ` --manifest ${quotePowerShell(manifestPath)}${stageArgs}${leaseArgs}${argumentText}` +
      "; exit $LASTEXITCODE";
    const started = await tools.exec_command({
      cmd: shellCommand,
      workdir,
      shell: "powershell",
      login: false,
      tty: true,
      yield_time_ms: 10000,
      max_output_tokens: PYTHON_OUTPUT_TOKENS,
    });
    let sessionId = started.session_id;
    let current = started;
    let output = started.output ?? "";
    if (sessionId === undefined) {
      if (
        started.exit_code !== undefined &&
        allowedExitCodes.includes(started.exit_code)
      ) {
        return parseCompactJson(output, command);
      }
      throw new GmailBridgeError(
        "local_attestation_process_error",
        `${command} exited before framed stdin was written`,
      );
    }
    for (let poll = 0; !sawReady(output) && poll < 5; poll += 1) {
      current = await tools.write_stdin({
        session_id: sessionId,
        chars: "",
        yield_time_ms: 1000,
        max_output_tokens: PYTHON_OUTPUT_TOKENS,
      });
      output += current.output ?? "";
      if (current.session_id !== undefined) sessionId = current.session_id;
      if (current.exit_code !== undefined) break;
    }
    if (!sawReady(output)) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        `${command} did not declare framed-stdin readiness`,
      );
    }
    for (let index = 0; index < stdinChunks.length; index += 1) {
      current = await tools.write_stdin({
        session_id: sessionId,
        chars: stdinChunks[index],
        yield_time_ms: index === stdinChunks.length - 1 ? 5000 : 50,
        max_output_tokens: PYTHON_OUTPUT_TOKENS,
      });
      output += current.output ?? "";
      if (current.session_id !== undefined) sessionId = current.session_id;
      if (current.exit_code !== undefined && index !== stdinChunks.length - 1) {
        // A bounded validator may reject the frame from its header alone
        // (for example raw_too_large) and intentionally exit before the
        // remaining secret payload is written.  Preserve its compact,
        // content-free diagnostic when that exit code is part of the CLI
        // contract; otherwise fail closed below.
        break;
      }
    }
    for (let poll = 0; current.exit_code === undefined && poll < 6; poll += 1) {
      current = await tools.write_stdin({
        session_id: sessionId,
        chars: "",
        yield_time_ms: 2000,
        max_output_tokens: PYTHON_OUTPUT_TOKENS,
      });
      output += current.output ?? "";
      if (current.session_id !== undefined) sessionId = current.session_id;
    }
    if (current.exit_code === undefined) {
      try {
        await tools.write_stdin({
          session_id: sessionId,
          chars: "\u0003",
          yield_time_ms: 1000,
          max_output_tokens: 500,
        });
      } catch {
        // The session may have exited between the last poll and cancellation.
      }
    }
    if (
      current.exit_code === undefined ||
      !allowedExitCodes.includes(current.exit_code)
    ) {
      const processFailure = safeProcessFailure(output);
      const processSummary =
        processFailure === null
          ? `; output_chars=${output.length}; ready=${output.includes("DAX_STDIN_READY")}`
          : `: ${processFailure}`;
      throw new GmailBridgeError(
        "local_attestation_process_error",
        `${command} did not finish with an allowed exit code (exit=${
          current.exit_code === undefined ? "timeout" : current.exit_code
        })${processSummary}`,
      );
    }
    return parseCompactJson(output, command);
  }

  async function attestRaw({
    messageId,
    draftId = null,
    stage,
    pythonExe,
    scriptPath,
    root,
    manifestPath,
    workdir,
  }) {
    if (stage === "draft") {
      await requireDraftBinding(draftId, messageId);
    } else if (stage !== "sent") {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "raw attestation stage must be draft or sent",
      );
    }
    const profile = await getProfile();
    const readback = await readRawMessage(messageId);
    const metadata = JSON.stringify({
      message_id: readback.id,
      expected_message_id: messageId,
      draft_id: draftId,
      label_ids: readback.label_ids,
      profile_email: profile.email,
    });
    if (!/^[\x00-\x7f]*$/.test(metadata) || !/^[\x00-\x7f]*$/.test(readback.raw)) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "raw attestation frame is not ASCII",
      );
    }
    const frame =
      `DAXGMR2 ${metadata.length} ${readback.raw.length} ${RAW_FRAME_LINE_CHARS};\n`;
    const stdinChunks = [frame, `${metadata}\n`];
    let writeGroup = "";
    for (
      let offset = 0;
      offset < readback.raw.length;
      offset += RAW_FRAME_LINE_CHARS
    ) {
      const line = `${readback.raw.slice(
        offset,
        offset + RAW_FRAME_LINE_CHARS,
      )}\n`;
      if (writeGroup.length > 0 && writeGroup.length + line.length > INPUT_WRITE_CHARS) {
        stdinChunks.push(writeGroup);
        writeGroup = "";
      }
      writeGroup += line;
    }
    if (writeGroup.length > 0) stdinChunks.push(writeGroup);
    const result = await runPythonWithInput({
      pythonExe,
      scriptPath,
      command: "attest-gmail-raw",
      root,
      manifestPath,
      stage,
      stdinChunks,
      workdir,
      allowedExitCodes: [0, 4],
    });
    rawAttestationResults.add(result);
    rawAttestationContexts.set(
      result,
      Object.freeze({pythonExe, scriptPath, root, manifestPath, workdir}),
    );
    if (result.ok === true) verifiedRawResults.add(result);
    return result;
  }

  async function recordReceipt({
    receiptInput,
    sendLeaseToken = null,
    pipedReceiptInput = false,
    pythonExe,
    scriptPath,
    root,
    manifestPath,
    workdir,
  }) {
    if (
      receiptInput?.stage === "draft_verified" ||
      receiptInput?.stage === "sent_verified"
    ) {
      if (!verifiedRawResults.has(receiptInput)) {
        throw new GmailBridgeError(
          "local_attestation_process_error",
          "verified receipt must use the live raw MIME attestation result",
        );
      }
    } else if (
      receiptInput?.stage === "ambiguous" &&
      receiptInput?.attestation !== null &&
      receiptInput?.attestation !== undefined &&
      !rawAttestationResults.has(receiptInput)
    ) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "raw MIME failure receipt must use the live validator result",
      );
    }
    const priorContext =
      recordedDraftReceiptContexts.get(receiptInput) ??
      leaseRetryDraftReceiptContexts.get(receiptInput);
    const isSendDisposition =
      receiptInput?.stage === "ambiguous" &&
      [
        SEND_OUTCOME_UNKNOWN.failure_code,
        SEND_ATTEMPT_AUTOMATIC_RETRY_BLOCKED.failure_code,
        "gmail_connector_pre_dispatch_denied",
      ].includes(receiptInput?.failure_code);
    if (
      isSendDisposition &&
      priorContext === undefined
    ) {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        "Gmail send disposition requires the matching persisted Draft receipt",
      );
    }
    if (receiptInput?.stage === "draft_verified") {
      recordedDraftReceiptContexts.delete(receiptInput);
    }
    const processContext = Object.freeze({
      pythonExe,
      scriptPath,
      root,
      manifestPath,
      workdir,
    });
    const json = asciiJson(receiptInput);
    const result = await runPythonWithInput({
      pythonExe,
      scriptPath,
      command: "record-receipt-stdin",
      root,
      manifestPath,
      sendLeaseToken,
      stdinChunks: [`DAXRCP1 ${json.length};\n`, `${json}\n`],
      workdir,
      allowedExitCodes: [0],
      pipedReceiptInput,
    });
    const comparablePath = value => String(value)
      .trim()
      .replace(/\\/g, "/")
      .replace(/\/+$/g, "")
      .toLowerCase();
    const nullableString = value => nonEmptyString(value) ? value.trim() : null;
    const rejectResult = reason => {
      throw new GmailBridgeError(
        "local_attestation_process_error",
        `record-receipt-stdin returned an unverified receipt (${reason})`,
      );
    };
    const manifestMatch = comparablePath(manifestPath).match(
      /\/deliveries\/arxiv-daily-(\d{4}-\d{2}-\d{2})-delivery\.json$/,
    );
    const expectedReceiptPath = manifestMatch === null
      ? null
      : `${comparablePath(root)}/deliveries/` +
        `arxiv-daily-${manifestMatch[1]}-receipt-v4.json`;
    if (
      !result ||
      typeof result !== "object" ||
      !nonEmptyString(result.receipt) ||
      !nonEmptyString(result.manifest) ||
      expectedReceiptPath === null ||
      comparablePath(result.receipt) !== expectedReceiptPath ||
      comparablePath(result.manifest) !== comparablePath(manifestPath) ||
      !/^[0-9a-f]{64}$/.test(result.manifest_sha256 ?? "")
    ) {
      rejectResult("path or manifest hash mismatch");
    }
    for (const field of [
      "schema_version",
      "stage",
      "subject",
      "html_sha256",
      "pdf_sha256",
      "body_verified",
      "attachment_verified",
      "attestation_schema_version",
    ]) {
      if (result[field] !== receiptInput?.[field]) {
        rejectResult(`${field} mismatch`);
      }
    }
    for (const field of ["gmail_message_id", "failure_code"]) {
      if (nullableString(result[field]) !== nullableString(receiptInput?.[field])) {
        rejectResult(`${field} mismatch`);
      }
    }
    if (
      !Number.isInteger(result.send_attempt_count) ||
      result.send_attempt_count < 0 ||
      result.send_attempt_count > MAX_SEND_ATTEMPTS
    ) {
      rejectResult("send_attempt_count is invalid");
    }
    if (
      receiptInput?.send_attempt_count !== undefined &&
      result.send_attempt_count !== receiptInput.send_attempt_count
    ) {
      rejectResult("send_attempt_count mismatch");
    }
    const strictDraftIdentity =
      receiptInput?.stage === "draft_verified" ||
      isSendDisposition;
    for (const field of ["gmail_draft_id", "gmail_draft_message_id"]) {
      const observed = nullableString(result[field]);
      const expected = nullableString(receiptInput?.[field]);
      if ((strictDraftIdentity || expected !== null) && observed !== expected) {
        rejectResult(`${field} mismatch`);
      }
    }
    if (
      receiptInput?.stage === "ambiguous" &&
      !nonEmptyString(result.failure_detail)
    ) {
      rejectResult("failure_detail is missing");
    }
    if (
      priorContext?.receiptProof !== undefined &&
      (
        comparablePath(result.receipt) !==
          comparablePath(priorContext.receiptProof.receipt) ||
        comparablePath(result.manifest) !==
          comparablePath(priorContext.receiptProof.manifest) ||
        result.manifest_sha256 !== priorContext.receiptProof.manifestSha256
      )
    ) {
      rejectResult("write-ahead does not continue the persisted Draft receipt");
    }
    const receiptProof = Object.freeze({
      receipt: result.receipt,
      manifest: result.manifest,
      manifestSha256: result.manifest_sha256,
    });
    if (receiptInput && typeof receiptInput === "object") {
      receiptInput.send_attempt_count = result.send_attempt_count;
    }
    if (receiptInput?.stage === "draft_verified" || isSendDisposition) {
      recordedDraftReceiptContexts.set(
        receiptInput,
        Object.freeze({
          ...processContext,
          pipedReceiptInput,
          receiptProof,
          sendAttemptCount: result.send_attempt_count,
        }),
      );
    } else if (receiptInput && typeof receiptInput === "object") {
      recordedDraftReceiptContexts.delete(receiptInput);
    }
    return result;
  }

  function diagnostic(error) {
    if (error instanceof GmailBridgeError) {
      const result = {
        failure_code: error.failureCode,
        failure_detail: error.message,
      };
      if (nonEmptyString(error.deliveryOutcome)) {
        result.delivery_outcome = error.deliveryOutcome;
      }
      if (nonEmptyString(error.receiptStage)) {
        result.receipt_stage = error.receiptStage;
      }
      if (["mime_prepare", "mime_chunk_read"].includes(error.failureStage)) {
        result.failure_stage = error.failureStage;
      }
      return result;
    }
    return {
      failure_code: "local_orchestration_error",
      failure_detail: "Local delivery orchestration failed without a classified result",
      failure_stage: "orchestration",
    };
  }

  return Object.freeze({
    GmailBridgeError,
    requireToolSuccess,
    callGmail,
    getProfile,
    prepareMimePayload,
    createDraft,
    updateDraft,
    requireDraftBinding,
    inspectLegacyRecoveryCandidate,
    prepareVerifiedDraftSend,
    prepareExplicitlyReauthorizedDraftSend,
    prepareExplicitlyAuthorizedLegacyDraftSend,
    sendVerifiedDraftRecovering,
    readRawMessage,
    attestRaw,
    recordReceipt,
    diagnostic,
  });
})()
