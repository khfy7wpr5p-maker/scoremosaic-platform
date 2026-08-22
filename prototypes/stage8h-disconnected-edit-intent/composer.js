"use strict";

(() => {
  const PROJECTION_VERSION = "scoremosaic-teacher-review-projection-v1";
  const INTENT_VERSION = "scoremosaic-teacher-review-browser-edit-intent-v1";
  const HASH_RE = /^[0-9a-f]{64}$/;
  const DIFFERENCE_ID_RE = /^difference_[0-9a-f]{24}$/;
  const CANDIDATE_ID_RE = /^candidate_[0-9a-f]{24}$/;
  const REVISION_ID_RE = /^rev_[0-9a-f]{32}$/;
  const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/;
  const BEATS_RE = /^[1-9][0-9]*(\+[1-9][0-9]*)*$/;
  const MAX_DIFFERENCES = 200;

  const TOP_LEVEL_KEYS = ["schemaVersion", "scope", "snapshot", "page", "capabilities", "baseCandidateIds", "differences", "projectionSha256"];
  const SCOPE_KEYS = ["tenantId", "jobId", "reviewerId", "reviewReportId", "reviewReportSha256", "baseCanonicalSha256"];
  const SNAPSHOT_KEYS = ["kind", "revisionId", "revisionSha256", "stateSha256"];
  const PAGE_KEYS = ["offset", "limit", "returned", "totalDifferences", "hasMore"];
  const CAPABILITY_KEYS = ["readOnly", "canEdit", "canApprove", "canPublish", "authoritativeTruth"];
  const DIFFERENCE_KEYS = ["differenceId", "category", "field", "label", "focus", "observations"];
  const FOCUS_KEYS = ["partOrdinal", "measureOrdinal", "eventOrdinal", "partId", "measureId", "eventId", "partPresentInSnapshot", "measurePresentInSnapshot", "eventPresentInSnapshot"];
  const OBSERVATION_KEYS = ["candidateId", "canonicalSha256", "present", "value"];
  const OPERATIONS = new Set([
    "set_pitch",
    "set_effective_duration",
    "set_written_type",
    "set_dots",
    "set_staff_voice",
    "set_time_signature",
    "set_tab",
    "remove_event",
  ]);

  const projectionNode = document.getElementById("scoremosaic-projection");
  const issueList = document.getElementById("issue-list");
  const issueStatus = document.getElementById("issues-status");
  const focusTitle = document.getElementById("focus-title");
  const focusLocation = document.getElementById("focus-location");
  const focusPresence = document.getElementById("focus-presence");
  const observationList = document.getElementById("observation-list");
  const reviewerLabel = document.getElementById("reviewer-label");
  const projectionStatus = document.getElementById("projection-status");
  const snapshotStatus = document.getElementById("snapshot-status");
  const intentStatus = document.getElementById("intent-status");
  const footerIntentStatus = document.getElementById("footer-intent-status");
  const operationType = document.getElementById("operation-type");
  const valueFields = document.getElementById("value-fields");
  const reason = document.getElementById("reason");
  const prepareIntentButton = document.getElementById("prepare-intent");
  const clearIntentButton = document.getElementById("clear-intent");
  const intentPreview = document.getElementById("intent-preview");

  let projection = null;
  let selectedIndex = -1;
  let issueButtons = [];

  function requireCondition(condition, code) {
    if (!condition) {
      throw new Error(code);
    }
  }

  function hasExactKeys(value, keys) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      return false;
    }
    const actual = Object.keys(value).sort();
    const expected = [...keys].sort();
    return actual.length === expected.length && actual.every((item, index) => item === expected[index]);
  }

  function requireHash(value, code) {
    requireCondition(typeof value === "string" && HASH_RE.test(value), code);
  }

  function requireId(value, code, nullable = false) {
    if (nullable && value === null) {
      return;
    }
    requireCondition(typeof value === "string" && ID_RE.test(value), code);
  }

  function validateFocus(focus) {
    requireCondition(hasExactKeys(focus, FOCUS_KEYS), "FOCUS_KEYS_INVALID");
    requireCondition(Number.isInteger(focus.partOrdinal) && focus.partOrdinal >= 1, "FOCUS_PART_INVALID");
    requireCondition(focus.measureOrdinal === null || (Number.isInteger(focus.measureOrdinal) && focus.measureOrdinal >= 1), "FOCUS_MEASURE_INVALID");
    requireCondition(focus.eventOrdinal === null || (Number.isInteger(focus.eventOrdinal) && focus.eventOrdinal >= 1), "FOCUS_EVENT_INVALID");
    requireId(focus.partId, "FOCUS_PART_ID_INVALID");
    requireId(focus.measureId, "FOCUS_MEASURE_ID_INVALID", true);
    requireId(focus.eventId, "FOCUS_EVENT_ID_INVALID", true);
    requireCondition(typeof focus.partPresentInSnapshot === "boolean", "FOCUS_PART_PRESENCE_INVALID");
    requireCondition(typeof focus.measurePresentInSnapshot === "boolean", "FOCUS_MEASURE_PRESENCE_INVALID");
    requireCondition(typeof focus.eventPresentInSnapshot === "boolean", "FOCUS_EVENT_PRESENCE_INVALID");
    if (focus.eventPresentInSnapshot) {
      requireCondition(focus.measureId !== null && focus.eventId !== null, "FOCUS_PRESENT_IDENTITY_INVALID");
    }
  }

  function validateObservation(observation) {
    requireCondition(hasExactKeys(observation, OBSERVATION_KEYS), "OBSERVATION_KEYS_INVALID");
    requireCondition(typeof observation.candidateId === "string" && CANDIDATE_ID_RE.test(observation.candidateId), "OBSERVATION_CANDIDATE_INVALID");
    requireHash(observation.canonicalSha256, "OBSERVATION_CANONICAL_INVALID");
    requireCondition(typeof observation.present === "boolean", "OBSERVATION_PRESENCE_INVALID");
  }

  function validateDifference(difference) {
    requireCondition(hasExactKeys(difference, DIFFERENCE_KEYS), "DIFFERENCE_KEYS_INVALID");
    requireCondition(typeof difference.differenceId === "string" && DIFFERENCE_ID_RE.test(difference.differenceId), "DIFFERENCE_ID_INVALID");
    requireCondition(typeof difference.category === "string" && difference.category.length > 0 && difference.category.length <= 80, "DIFFERENCE_CATEGORY_INVALID");
    requireCondition(typeof difference.field === "string" && difference.field.length > 0 && difference.field.length <= 120, "DIFFERENCE_FIELD_INVALID");
    requireCondition(typeof difference.label === "string" && difference.label.length > 0 && difference.label.length <= 240, "DIFFERENCE_LABEL_INVALID");
    validateFocus(difference.focus);
    requireCondition(Array.isArray(difference.observations) && difference.observations.length >= 2 && difference.observations.length <= 8, "OBSERVATIONS_INVALID");
    difference.observations.forEach(validateObservation);
  }

  function validateProjection(value) {
    requireCondition(hasExactKeys(value, TOP_LEVEL_KEYS), "PROJECTION_KEYS_INVALID");
    requireCondition(value.schemaVersion === PROJECTION_VERSION, "PROJECTION_VERSION_INVALID");
    requireCondition(hasExactKeys(value.scope, SCOPE_KEYS), "SCOPE_KEYS_INVALID");
    requireId(value.scope.tenantId, "TENANT_INVALID");
    requireId(value.scope.jobId, "JOB_INVALID");
    requireId(value.scope.reviewerId, "REVIEWER_INVALID");
    requireId(value.scope.reviewReportId, "REPORT_INVALID");
    requireHash(value.scope.reviewReportSha256, "REPORT_HASH_INVALID");
    requireHash(value.scope.baseCanonicalSha256, "CANONICAL_HASH_INVALID");

    requireCondition(hasExactKeys(value.snapshot, SNAPSHOT_KEYS), "SNAPSHOT_KEYS_INVALID");
    requireCondition(value.snapshot.kind === "base" || value.snapshot.kind === "revision", "SNAPSHOT_KIND_INVALID");
    requireHash(value.snapshot.stateSha256, "STATE_HASH_INVALID");
    if (value.snapshot.kind === "revision") {
      requireCondition(typeof value.snapshot.revisionId === "string" && REVISION_ID_RE.test(value.snapshot.revisionId), "REVISION_ID_INVALID");
      requireHash(value.snapshot.revisionSha256, "REVISION_HASH_INVALID");
    } else {
      requireCondition(value.snapshot.revisionId === null && value.snapshot.revisionSha256 === null, "BASE_REVISION_INVALID");
    }

    requireCondition(hasExactKeys(value.page, PAGE_KEYS), "PAGE_KEYS_INVALID");
    requireCondition(Number.isInteger(value.page.offset) && value.page.offset >= 0, "PAGE_OFFSET_INVALID");
    requireCondition(Number.isInteger(value.page.limit) && value.page.limit >= 1 && value.page.limit <= MAX_DIFFERENCES, "PAGE_LIMIT_INVALID");
    requireCondition(Number.isInteger(value.page.returned) && value.page.returned >= 0 && value.page.returned <= MAX_DIFFERENCES, "PAGE_RETURNED_INVALID");
    requireCondition(Number.isInteger(value.page.totalDifferences) && value.page.totalDifferences >= value.page.returned, "PAGE_TOTAL_INVALID");
    requireCondition(typeof value.page.hasMore === "boolean", "PAGE_MORE_INVALID");

    requireCondition(hasExactKeys(value.capabilities, CAPABILITY_KEYS), "CAPABILITY_KEYS_INVALID");
    requireCondition(value.capabilities.readOnly === true, "READ_ONLY_REQUIRED");
    requireCondition(value.capabilities.canEdit === false, "SERVER_EDIT_CAPABILITY_FORBIDDEN");
    requireCondition(value.capabilities.canApprove === false, "APPROVAL_CAPABILITY_FORBIDDEN");
    requireCondition(value.capabilities.canPublish === false, "PUBLICATION_CAPABILITY_FORBIDDEN");
    requireCondition(value.capabilities.authoritativeTruth === false, "AUTHORITATIVE_TRUTH_FORBIDDEN");

    requireCondition(Array.isArray(value.baseCandidateIds) && value.baseCandidateIds.length >= 1 && value.baseCandidateIds.length <= 8, "BASE_CANDIDATES_INVALID");
    value.baseCandidateIds.forEach((candidateId) => requireCondition(typeof candidateId === "string" && CANDIDATE_ID_RE.test(candidateId), "BASE_CANDIDATE_INVALID"));
    requireCondition(Array.isArray(value.differences) && value.differences.length <= MAX_DIFFERENCES, "DIFFERENCES_INVALID");
    requireCondition(value.page.returned === value.differences.length, "PAGE_RETURNED_MISMATCH");
    value.differences.forEach(validateDifference);
    requireHash(value.projectionSha256, "PROJECTION_HASH_INVALID");
  }

  function stableValue(value) {
    if (Array.isArray(value)) {
      return value.map(stableValue);
    }
    if (value !== null && typeof value === "object") {
      const result = {};
      Object.keys(value).sort().forEach((key) => {
        result[key] = stableValue(value[key]);
      });
      return result;
    }
    return value;
  }

  function stableStringify(value) {
    return JSON.stringify(stableValue(value), null, 2);
  }

  function fieldLabel(text, input) {
    const label = document.createElement("label");
    label.textContent = text;
    label.htmlFor = input.id;
    return label;
  }

  function numberInput(id, minimum, maximum, value) {
    const input = document.createElement("input");
    input.type = "number";
    input.id = id;
    input.min = String(minimum);
    input.max = String(maximum);
    input.step = "1";
    input.value = String(value);
    input.required = true;
    return input;
  }

  function textInput(id, maximum, value = "") {
    const input = document.createElement("input");
    input.type = "text";
    input.id = id;
    input.maxLength = maximum;
    input.value = value;
    input.required = true;
    return input;
  }

  function selectInput(id, values, selected) {
    const select = document.createElement("select");
    select.id = id;
    values.forEach((item) => {
      const option = document.createElement("option");
      option.value = item;
      option.textContent = item;
      if (item === selected) {
        option.selected = true;
      }
      select.append(option);
    });
    return select;
  }

  function appendField(labelText, input) {
    valueFields.append(fieldLabel(labelText, input), input);
  }

  function renderOperationFields() {
    valueFields.replaceChildren();
    const operation = operationType.value;
    requireCondition(OPERATIONS.has(operation), "OPERATION_INVALID");

    if (operation === "set_pitch") {
      appendField("Step", selectInput("pitch-step", ["A", "B", "C", "D", "E", "F", "G"], "C"));
      appendField("Alter numerator", numberInput("pitch-alter-n", -8, 8, 0));
      appendField("Alter denominator", numberInput("pitch-alter-d", 1, 1000000, 1));
      appendField("Octave", numberInput("pitch-octave", -2, 12, 4));
    } else if (operation === "set_effective_duration") {
      appendField("Duration numerator", numberInput("duration-n", 1, 1000000000, 1));
      appendField("Duration denominator", numberInput("duration-d", 1, 1000000, 1));
    } else if (operation === "set_written_type") {
      appendField("Written type", selectInput("written-type", ["maxima", "long", "breve", "whole", "half", "quarter", "eighth", "16th", "32nd", "64th", "128th", "256th", "512th", "1024th"], "quarter"));
    } else if (operation === "set_dots") {
      appendField("Dots", numberInput("dots", 0, 8, 0));
    } else if (operation === "set_staff_voice") {
      appendField("Staff", numberInput("staff", 1, 128, 1));
      appendField("Voice", textInput("voice", 40, "1"));
    } else if (operation === "set_time_signature") {
      appendField("Beats", textInput("beats", 40, "4"));
      appendField("Beat type", numberInput("beat-type", 1, 1024, 4));
    } else if (operation === "set_tab") {
      appendField("String", numberInput("tab-string", 1, 24, 1));
      appendField("Fret", numberInput("tab-fret", 0, 96, 0));
    } else if (operation === "remove_event") {
      const note = document.createElement("p");
      note.className = "security-note";
      note.textContent = "Remove event carries no value. Server-side old-value and current-location checks are still mandatory.";
      valueFields.append(note);
    }
  }

  function integerValue(id, minimum, maximum, code) {
    const node = document.getElementById(id);
    requireCondition(node instanceof HTMLInputElement, code);
    const value = Number(node.value);
    requireCondition(Number.isSafeInteger(value) && value >= minimum && value <= maximum, code);
    return value;
  }

  function stringValue(id, maximum, code, pattern = null) {
    const node = document.getElementById(id);
    requireCondition(node instanceof HTMLInputElement || node instanceof HTMLSelectElement, code);
    const value = node.value;
    requireCondition(value.length >= 1 && value.length <= maximum, code);
    if (pattern !== null) {
      requireCondition(pattern.test(value), code);
    }
    return value;
  }

  function operationPayload() {
    const type = operationType.value;
    requireCondition(OPERATIONS.has(type), "OPERATION_INVALID");
    if (type === "set_pitch") {
      return {
        type,
        value: {
          step: stringValue("pitch-step", 1, "PITCH_STEP_INVALID", /^[A-G]$/),
          alter: {numerator: integerValue("pitch-alter-n", -8, 8, "PITCH_ALTER_INVALID"), denominator: integerValue("pitch-alter-d", 1, 1000000, "PITCH_ALTER_INVALID")},
          octave: integerValue("pitch-octave", -2, 12, "PITCH_OCTAVE_INVALID"),
        },
      };
    }
    if (type === "set_effective_duration") {
      return {type, value: {numerator: integerValue("duration-n", 1, 1000000000, "DURATION_INVALID"), denominator: integerValue("duration-d", 1, 1000000, "DURATION_INVALID")}};
    }
    if (type === "set_written_type") {
      return {type, value: stringValue("written-type", 40, "WRITTEN_TYPE_INVALID")};
    }
    if (type === "set_dots") {
      return {type, value: integerValue("dots", 0, 8, "DOTS_INVALID")};
    }
    if (type === "set_staff_voice") {
      return {type, value: {staff: integerValue("staff", 1, 128, "STAFF_INVALID"), voice: stringValue("voice", 40, "VOICE_INVALID", /^[^\u0000-\u001f\u007f]+$/)}};
    }
    if (type === "set_time_signature") {
      return {type, value: {beats: stringValue("beats", 40, "BEATS_INVALID", BEATS_RE), beatType: integerValue("beat-type", 1, 1024, "BEAT_TYPE_INVALID")}};
    }
    if (type === "set_tab") {
      return {type, value: {string: integerValue("tab-string", 1, 24, "TAB_STRING_INVALID"), fret: integerValue("tab-fret", 0, 96, "TAB_FRET_INVALID")}};
    }
    return {type, value: null};
  }

  function defaultOperation(difference) {
    if (difference.category === "pitch" || difference.field.startsWith("pitch.")) return "set_pitch";
    if (difference.category === "duration" || difference.field === "effectiveDuration") return "set_effective_duration";
    if (difference.field === "writtenType") return "set_written_type";
    if (difference.field === "dots") return "set_dots";
    if (difference.category === "tab" || difference.field.startsWith("tab.")) return "set_tab";
    if (difference.category === "meter" || difference.field.includes("timeSignature")) return "set_time_signature";
    return "set_pitch";
  }

  function clearIntent(message = "No local intent prepared.") {
    intentPreview.textContent = message;
    footerIntentStatus.textContent = "none";
    clearIntentButton.disabled = true;
  }

  function setComposerAvailability(difference) {
    const focus = difference.focus;
    const available = focus.partPresentInSnapshot && focus.measurePresentInSnapshot && focus.eventPresentInSnapshot && focus.partId !== null && focus.measureId !== null && focus.eventId !== null;
    operationType.disabled = !available;
    reason.disabled = !available;
    prepareIntentButton.disabled = !available;
    if (available) {
      intentStatus.textContent = "Local draft only";
      intentStatus.className = "status-pill status-pill--neutral";
      operationType.value = defaultOperation(difference);
      renderOperationFields();
    } else {
      intentStatus.textContent = "Target absent";
      intentStatus.className = "status-pill status-pill--locked";
      valueFields.replaceChildren();
    }
  }

  function renderObservations(difference) {
    observationList.replaceChildren();
    difference.observations.forEach((observation) => {
      const item = document.createElement("article");
      item.className = "readonly-observation";
      item.setAttribute("role", "listitem");
      const name = document.createElement("strong");
      name.textContent = observation.candidateId;
      const value = document.createElement("p");
      value.textContent = `Value: ${observation.value === null ? "null" : typeof observation.value === "string" ? observation.value : JSON.stringify(observation.value)}`;
      item.append(name, value);
      observationList.append(item);
    });
  }

  function selectIssue(index, moveFocus) {
    requireCondition(projection !== null, "PROJECTION_NOT_READY");
    requireCondition(Number.isInteger(index) && index >= 0 && index < projection.differences.length, "ISSUE_INDEX_INVALID");
    selectedIndex = index;
    issueButtons.forEach((button, current) => {
      const selected = current === index;
      button.setAttribute("aria-selected", selected ? "true" : "false");
      button.tabIndex = selected ? 0 : -1;
    });
    const button = issueButtons[index];
    issueList.setAttribute("aria-activedescendant", button.id);
    const difference = projection.differences[index];
    focusTitle.textContent = difference.label;
    focusLocation.textContent = `Part ${difference.focus.partOrdinal} · Measure ${difference.focus.measureOrdinal ?? "—"} · Event ${difference.focus.eventOrdinal ?? "—"}`;
    focusPresence.textContent = difference.focus.eventPresentInSnapshot ? "Target event is present in this exact snapshot." : "Target event is absent in this exact snapshot. Local intent preparation is disabled.";
    renderObservations(difference);
    setComposerAvailability(difference);
    clearIntent();
    if (moveFocus) button.focus();
  }

  function renderIssues() {
    issueList.replaceChildren();
    issueButtons = projection.differences.map((difference, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.id = `intent-issue-${index}`;
      button.className = "readonly-issue-option";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.tabIndex = -1;
      const label = document.createElement("strong");
      label.textContent = difference.label;
      const location = document.createElement("span");
      location.textContent = `Part ${difference.focus.partOrdinal} · Measure ${difference.focus.measureOrdinal ?? "—"} · Event ${difference.focus.eventOrdinal ?? "—"}`;
      button.append(label, location);
      button.addEventListener("click", () => selectIssue(index, false));
      issueList.append(button);
      return button;
    });
    if (issueButtons.length > 0) {
      selectIssue(0, false);
    } else {
      intentStatus.textContent = "No target";
      focusTitle.textContent = "No differences";
    }
  }

  function navigateIssues(event) {
    if (projection === null || projection.differences.length === 0) return;
    let next = selectedIndex;
    if (event.key === "ArrowDown") next = Math.min(selectedIndex + 1, projection.differences.length - 1);
    else if (event.key === "ArrowUp") next = Math.max(selectedIndex - 1, 0);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = projection.differences.length - 1;
    else return;
    event.preventDefault();
    selectIssue(next, true);
  }

  function prepareIntent() {
    requireCondition(projection !== null && selectedIndex >= 0, "INTENT_TARGET_INVALID");
    const difference = projection.differences[selectedIndex];
    requireCondition(difference.focus.eventPresentInSnapshot, "INTENT_TARGET_ABSENT");
    const note = reason.value.trim();
    requireCondition(note.length <= 500, "INTENT_REASON_INVALID");
    const intent = {
      schemaVersion: INTENT_VERSION,
      projectionSha256: projection.projectionSha256,
      snapshot: {
        kind: projection.snapshot.kind,
        revisionId: projection.snapshot.revisionId,
        revisionSha256: projection.snapshot.revisionSha256,
        stateSha256: projection.snapshot.stateSha256,
      },
      differenceId: difference.differenceId,
      target: {
        partId: difference.focus.partId,
        measureId: difference.focus.measureId,
        eventId: difference.focus.eventId,
      },
      operation: operationPayload(),
      reason: note.length === 0 ? null : note,
      authority: {
        authoritativeCapability: false,
        serverAuthorizationIncluded: false,
        oldValuePreconditionIncluded: false,
        commandIdentityIncluded: false,
        networkSubmissionAllowed: false,
      },
    };
    intentPreview.textContent = stableStringify(intent);
    footerIntentStatus.textContent = "prepared locally";
    clearIntentButton.disabled = false;
  }

  function reject(reasonCode) {
    projection = null;
    selectedIndex = -1;
    issueButtons = [];
    document.body.dataset.reviewState = "rejected";
    issueList.replaceChildren();
    observationList.replaceChildren();
    operationType.disabled = true;
    reason.disabled = true;
    prepareIntentButton.disabled = true;
    clearIntentButton.disabled = true;
    valueFields.replaceChildren();
    issueStatus.textContent = "Rejected";
    reviewerLabel.textContent = "unavailable";
    projectionStatus.textContent = "rejected";
    snapshotStatus.textContent = "unavailable";
    intentStatus.textContent = "Unavailable";
    focusTitle.textContent = "Projection unavailable";
    focusLocation.textContent = "The embedded projection failed closed validation.";
    focusPresence.textContent = reasonCode;
    intentPreview.textContent = "No intent can be prepared from a rejected projection.";
    footerIntentStatus.textContent = "blocked";
  }

  try {
    requireCondition(projectionNode !== null, "PROJECTION_NODE_MISSING");
    const parsed = JSON.parse(projectionNode.textContent);
    validateProjection(parsed);
    projection = parsed;
    reviewerLabel.textContent = projection.scope.reviewerId;
    projectionStatus.textContent = "accepted read-only";
    snapshotStatus.textContent = projection.snapshot.kind === "revision" ? projection.snapshot.revisionId : "base";
    issueStatus.textContent = `${projection.page.returned} shown`;
    document.body.dataset.reviewState = "intent-composer";
    issueList.addEventListener("keydown", navigateIssues);
    operationType.addEventListener("change", () => {
      renderOperationFields();
      clearIntent("Operation changed. Prepare a new local intent.");
    });
    prepareIntentButton.addEventListener("click", () => {
      try {
        prepareIntent();
      } catch (error) {
        const code = error instanceof Error ? error.message : "INTENT_INVALID";
        intentPreview.textContent = `Intent rejected locally: ${code}`;
        footerIntentStatus.textContent = "rejected locally";
        clearIntentButton.disabled = false;
      }
    });
    clearIntentButton.addEventListener("click", () => clearIntent());
    renderIssues();
  } catch (error) {
    reject(error instanceof Error ? error.message : "PROJECTION_REJECTED");
  }
})();
