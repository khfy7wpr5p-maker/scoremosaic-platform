"use strict";

(() => {
  const PROJECTION_VERSION = "scoremosaic-teacher-review-projection-v1";
  const MAX_DIFFERENCES = 200;
  const HASH_RE = /^[0-9a-f]{64}$/;
  const DIFFERENCE_ID_RE = /^difference_[0-9a-f]{24}$/;
  const CANDIDATE_ID_RE = /^candidate_[0-9a-f]{24}$/;

  const TOP_LEVEL_KEYS = [
    "schemaVersion",
    "scope",
    "snapshot",
    "page",
    "capabilities",
    "baseCandidateIds",
    "differences",
    "projectionSha256",
  ];
  const SCOPE_KEYS = [
    "tenantId",
    "jobId",
    "reviewerId",
    "reviewReportId",
    "reviewReportSha256",
    "baseCanonicalSha256",
  ];
  const SNAPSHOT_KEYS = ["kind", "revisionId", "revisionSha256", "stateSha256"];
  const PAGE_KEYS = ["offset", "limit", "returned", "totalDifferences", "hasMore"];
  const CAPABILITY_KEYS = ["readOnly", "canEdit", "canApprove", "canPublish", "authoritativeTruth"];
  const DIFFERENCE_KEYS = ["differenceId", "category", "field", "label", "focus", "observations"];
  const FOCUS_KEYS = [
    "partOrdinal",
    "measureOrdinal",
    "eventOrdinal",
    "partId",
    "measureId",
    "eventId",
    "partPresentInSnapshot",
    "measurePresentInSnapshot",
    "eventPresentInSnapshot",
  ];
  const OBSERVATION_KEYS = ["candidateId", "canonicalSha256", "present", "value"];

  const issueList = document.getElementById("issue-list");
  const issueStatus = document.getElementById("issues-status");
  const focusTitle = document.getElementById("focus-title");
  const focusLocation = document.getElementById("focus-location");
  const focusPresence = document.getElementById("focus-presence");
  const observationList = document.getElementById("observation-list");
  const projectionStatus = document.getElementById("projection-status");
  const snapshotStatus = document.getElementById("snapshot-status");
  const issueCount = document.getElementById("issue-count");
  const reviewerLabel = document.getElementById("reviewer-label");
  const projectionNode = document.getElementById("scoremosaic-projection");

  let projection = null;
  let selectedIndex = -1;
  let optionButtons = [];

  function reject(reason) {
    projection = null;
    selectedIndex = -1;
    optionButtons = [];
    document.body.dataset.reviewState = "rejected";
    issueList.replaceChildren();
    observationList.replaceChildren();
    issueList.removeAttribute("aria-activedescendant");
    issueStatus.textContent = "Rejected";
    projectionStatus.textContent = "rejected";
    snapshotStatus.textContent = "unavailable";
    issueCount.textContent = "0";
    reviewerLabel.textContent = "unavailable";
    focusTitle.textContent = "Projection unavailable";
    focusLocation.textContent = "The embedded read-only projection failed closed validation.";
    focusPresence.textContent = reason;
  }

  function requireCondition(condition, code) {
    if (!condition) {
      throw new Error(code);
    }
  }

  function hasExactKeys(value, expectedKeys) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      return false;
    }
    const actual = Object.keys(value).sort();
    const expected = [...expectedKeys].sort();
    return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
  }

  function requireHash(value, code) {
    requireCondition(typeof value === "string" && HASH_RE.test(value), code);
  }

  function validateFocus(focus) {
    requireCondition(hasExactKeys(focus, FOCUS_KEYS), "FOCUS_KEYS_INVALID");
    requireCondition(Number.isInteger(focus.partOrdinal) && focus.partOrdinal >= 1, "FOCUS_PART_INVALID");
    requireCondition(focus.measureOrdinal === null || (Number.isInteger(focus.measureOrdinal) && focus.measureOrdinal >= 1), "FOCUS_MEASURE_INVALID");
    requireCondition(focus.eventOrdinal === null || (Number.isInteger(focus.eventOrdinal) && focus.eventOrdinal >= 1), "FOCUS_EVENT_INVALID");
    requireCondition(typeof focus.partPresentInSnapshot === "boolean", "FOCUS_PART_PRESENCE_INVALID");
    requireCondition(typeof focus.measurePresentInSnapshot === "boolean", "FOCUS_MEASURE_PRESENCE_INVALID");
    requireCondition(typeof focus.eventPresentInSnapshot === "boolean", "FOCUS_EVENT_PRESENCE_INVALID");
  }

  function validateObservation(observation) {
    requireCondition(hasExactKeys(observation, OBSERVATION_KEYS), "OBSERVATION_KEYS_INVALID");
    requireCondition(typeof observation.candidateId === "string" && CANDIDATE_ID_RE.test(observation.candidateId), "OBSERVATION_CANDIDATE_INVALID");
    requireHash(observation.canonicalSha256, "OBSERVATION_CANONICAL_HASH_INVALID");
    requireCondition(typeof observation.present === "boolean", "OBSERVATION_PRESENCE_INVALID");
  }

  function validateDifference(difference) {
    requireCondition(hasExactKeys(difference, DIFFERENCE_KEYS), "DIFFERENCE_KEYS_INVALID");
    requireCondition(typeof difference.differenceId === "string" && DIFFERENCE_ID_RE.test(difference.differenceId), "DIFFERENCE_ID_INVALID");
    requireCondition(typeof difference.category === "string" && difference.category.length > 0, "DIFFERENCE_CATEGORY_INVALID");
    requireCondition(typeof difference.field === "string" && difference.field.length > 0, "DIFFERENCE_FIELD_INVALID");
    requireCondition(typeof difference.label === "string" && difference.label.length >= 3, "DIFFERENCE_LABEL_INVALID");
    validateFocus(difference.focus);
    requireCondition(Array.isArray(difference.observations) && difference.observations.length >= 2 && difference.observations.length <= 8, "OBSERVATIONS_INVALID");
    difference.observations.forEach(validateObservation);
  }

  function validateProjection(value) {
    requireCondition(hasExactKeys(value, TOP_LEVEL_KEYS), "PROJECTION_KEYS_INVALID");
    requireCondition(value.schemaVersion === PROJECTION_VERSION, "PROJECTION_VERSION_INVALID");

    requireCondition(hasExactKeys(value.scope, SCOPE_KEYS), "SCOPE_KEYS_INVALID");
    requireHash(value.scope.reviewReportSha256, "REPORT_HASH_INVALID");
    requireHash(value.scope.baseCanonicalSha256, "BASE_CANONICAL_HASH_INVALID");
    requireCondition(typeof value.scope.reviewerId === "string" && value.scope.reviewerId.length > 0, "REVIEWER_INVALID");

    requireCondition(hasExactKeys(value.snapshot, SNAPSHOT_KEYS), "SNAPSHOT_KEYS_INVALID");
    requireCondition(value.snapshot.kind === "base" || value.snapshot.kind === "revision", "SNAPSHOT_KIND_INVALID");
    requireHash(value.snapshot.stateSha256, "STATE_HASH_INVALID");
    if (value.snapshot.kind === "revision") {
      requireCondition(typeof value.snapshot.revisionId === "string" && /^rev_[0-9a-f]{32}$/.test(value.snapshot.revisionId), "REVISION_ID_INVALID");
      requireHash(value.snapshot.revisionSha256, "REVISION_HASH_INVALID");
    } else {
      requireCondition(value.snapshot.revisionId === null && value.snapshot.revisionSha256 === null, "BASE_REVISION_IDENTITY_INVALID");
    }

    requireCondition(hasExactKeys(value.page, PAGE_KEYS), "PAGE_KEYS_INVALID");
    requireCondition(Number.isInteger(value.page.offset) && value.page.offset >= 0, "PAGE_OFFSET_INVALID");
    requireCondition(Number.isInteger(value.page.limit) && value.page.limit >= 1 && value.page.limit <= MAX_DIFFERENCES, "PAGE_LIMIT_INVALID");
    requireCondition(Number.isInteger(value.page.returned) && value.page.returned >= 0 && value.page.returned <= MAX_DIFFERENCES, "PAGE_RETURNED_INVALID");
    requireCondition(Number.isInteger(value.page.totalDifferences) && value.page.totalDifferences >= value.page.returned, "PAGE_TOTAL_INVALID");
    requireCondition(typeof value.page.hasMore === "boolean", "PAGE_HAS_MORE_INVALID");

    requireCondition(hasExactKeys(value.capabilities, CAPABILITY_KEYS), "CAPABILITY_KEYS_INVALID");
    requireCondition(value.capabilities.readOnly === true, "READ_ONLY_CAPABILITY_REQUIRED");
    requireCondition(value.capabilities.canEdit === false, "EDIT_CAPABILITY_FORBIDDEN");
    requireCondition(value.capabilities.canApprove === false, "APPROVAL_CAPABILITY_FORBIDDEN");
    requireCondition(value.capabilities.canPublish === false, "PUBLICATION_CAPABILITY_FORBIDDEN");
    requireCondition(value.capabilities.authoritativeTruth === false, "AUTHORITATIVE_TRUTH_FORBIDDEN");

    requireCondition(Array.isArray(value.baseCandidateIds) && value.baseCandidateIds.length >= 1 && value.baseCandidateIds.length <= 8, "BASE_CANDIDATES_INVALID");
    value.baseCandidateIds.forEach((candidateId) => {
      requireCondition(typeof candidateId === "string" && CANDIDATE_ID_RE.test(candidateId), "BASE_CANDIDATE_ID_INVALID");
    });

    requireCondition(Array.isArray(value.differences) && value.differences.length <= MAX_DIFFERENCES, "DIFFERENCE_PAGE_INVALID");
    requireCondition(value.page.returned === value.differences.length, "PAGE_RETURNED_MISMATCH");
    value.differences.forEach(validateDifference);
    requireHash(value.projectionSha256, "PROJECTION_HASH_INVALID");
  }

  function formatValue(value) {
    if (value === null) {
      return "null";
    }
    if (typeof value === "string") {
      return value;
    }
    return JSON.stringify(value);
  }

  function renderObservations(difference) {
    observationList.replaceChildren();
    difference.observations.forEach((observation) => {
      const card = document.createElement("article");
      card.className = "readonly-observation";
      card.setAttribute("role", "listitem");

      const heading = document.createElement("strong");
      heading.textContent = observation.candidateId;

      const value = document.createElement("p");
      value.textContent = `Value: ${formatValue(observation.value)}`;

      const presence = document.createElement("p");
      presence.textContent = observation.present ? "Present in candidate" : "Absent in candidate";

      card.append(heading, value, presence);
      observationList.append(card);
    });
  }

  function renderFocus(difference) {
    const focus = difference.focus;
    const measureText = focus.measureOrdinal === null ? "—" : String(focus.measureOrdinal);
    const eventText = focus.eventOrdinal === null ? "—" : String(focus.eventOrdinal);
    focusTitle.textContent = difference.label;
    focusLocation.textContent = `Part ${focus.partOrdinal} · Measure ${measureText} · Event ${eventText}`;

    if (focus.eventId !== null && !focus.eventPresentInSnapshot) {
      focusPresence.textContent = "The referenced event is not present in this exact snapshot; comparison evidence remains visible and read-only.";
    } else {
      focusPresence.textContent = "The referenced location is present in this exact snapshot.";
    }
  }

  function selectIssue(index, moveKeyboardFocus) {
    requireCondition(projection !== null, "PROJECTION_NOT_READY");
    requireCondition(Number.isInteger(index) && index >= 0 && index < projection.differences.length, "ISSUE_INDEX_INVALID");
    selectedIndex = index;

    optionButtons.forEach((button, buttonIndex) => {
      const selected = buttonIndex === selectedIndex;
      button.setAttribute("aria-selected", selected ? "true" : "false");
      button.tabIndex = selected ? 0 : -1;
    });

    const selectedButton = optionButtons[selectedIndex];
    issueList.setAttribute("aria-activedescendant", selectedButton.id);
    renderFocus(projection.differences[selectedIndex]);
    renderObservations(projection.differences[selectedIndex]);

    if (moveKeyboardFocus) {
      selectedButton.focus();
    }
  }

  function renderIssueList() {
    issueList.replaceChildren();
    optionButtons = projection.differences.map((difference, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "readonly-issue-option";
      button.id = `issue-option-${index}`;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.tabIndex = -1;

      const label = document.createElement("strong");
      label.textContent = difference.label;
      const detail = document.createElement("span");
      const measure = difference.focus.measureOrdinal === null ? "—" : String(difference.focus.measureOrdinal);
      const event = difference.focus.eventOrdinal === null ? "—" : String(difference.focus.eventOrdinal);
      detail.textContent = `Part ${difference.focus.partOrdinal} · Measure ${measure} · Event ${event}`;
      button.append(label, detail);
      button.addEventListener("click", () => selectIssue(index, false));
      issueList.append(button);
      return button;
    });

    if (optionButtons.length > 0) {
      selectIssue(0, false);
    } else {
      focusTitle.textContent = "No differences on this page";
      focusLocation.textContent = "The accepted read-only projection contains no review differences in the current page.";
      focusPresence.textContent = "";
      observationList.replaceChildren();
    }
  }

  function handleIssueNavigation(event) {
    if (projection === null || projection.differences.length === 0) {
      return;
    }

    let nextIndex = selectedIndex;
    if (event.key === "ArrowDown") {
      nextIndex = Math.min(selectedIndex + 1, projection.differences.length - 1);
    } else if (event.key === "ArrowUp") {
      nextIndex = Math.max(selectedIndex - 1, 0);
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = projection.differences.length - 1;
    } else {
      return;
    }

    event.preventDefault();
    selectIssue(nextIndex, true);
  }

  try {
    requireCondition(projectionNode !== null, "PROJECTION_NODE_MISSING");
    const parsed = JSON.parse(projectionNode.textContent);
    validateProjection(parsed);
    projection = parsed;

    issueList.addEventListener("keydown", handleIssueNavigation);
    reviewerLabel.textContent = projection.scope.reviewerId;
    issueStatus.textContent = `${projection.page.returned} shown`;
    projectionStatus.textContent = "accepted read-only";
    snapshotStatus.textContent = projection.snapshot.kind === "revision" ? projection.snapshot.revisionId : "base";
    issueCount.textContent = `${projection.page.returned} / ${projection.page.totalDifferences}`;
    document.body.dataset.reviewState = "read-only";
    renderIssueList();
  } catch (error) {
    const reason = error instanceof Error ? error.message : "PROJECTION_REJECTED";
    reject(reason);
  }
})();
