from __future__ import annotations

import inspect
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.external_auth import (
    EXTERNAL_AUTH_CONTRACT_VERSION,
    AuthenticatedExternalPrincipal,
    ExternalAuthPolicy,
    VerifiedExternalIdentity,
    authenticate_external_principal,
)
from scoremosaic_gateway.external_authorization import (
    EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
    ExternalAuthorizationDecision,
    ExternalAuthorizationError,
    ExternalAuthorizationGrant,
    ExternalAuthorizationPolicy,
    authorize_external_operation,
)
from scoremosaic_gateway.service_auth import build_engine_auth_binding


class ExternalAuthorizationDecisionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 2_000_000_000
        auth_policy = ExternalAuthPolicy(
            version=EXTERNAL_AUTH_CONTRACT_VERSION,
            environment="staging",
            allowed_provider_ids=("test-provider",),
        )
        self.principal = authenticate_external_principal(
            policy=auth_policy,
            provider_id="test-provider",
            credential=b"opaque-authentication-credential",
            verifier=lambda provider_id, credential: VerifiedExternalIdentity(
                provider_id=provider_id,
                subject_id="private-subject-123",
                issued_at_epoch_s=self.now - 60,
                expires_at_epoch_s=self.now + 300,
            ),
            observed_at_epoch_s=self.now,
        )
        self.operation = "platform.operation.alpha"

    def policy_for(
        self,
        *grants: ExternalAuthorizationGrant,
        environment: str = "staging",
    ) -> ExternalAuthorizationPolicy:
        return ExternalAuthorizationPolicy(
            version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
            environment=environment,
            grants=tuple(grants),
        )

    def grant_for(
        self,
        *,
        principal_id: str | None = None,
        operation_id: str | None = None,
    ) -> ExternalAuthorizationGrant:
        return ExternalAuthorizationGrant(
            principal_id=self.principal.principal_id if principal_id is None else principal_id,
            operation_id=self.operation if operation_id is None else operation_id,
        )

    def authorize(
        self,
        policy: ExternalAuthorizationPolicy,
        *,
        principal: object | None = None,
        operation_id: object | None = None,
        observed_at_epoch_s: object | None = None,
    ) -> ExternalAuthorizationDecision:
        return authorize_external_operation(
            policy=policy,
            principal=self.principal if principal is None else principal,
            operation_id=self.operation if operation_id is None else operation_id,
            observed_at_epoch_s=(
                self.now + 1 if observed_at_epoch_s is None else observed_at_epoch_s
            ),
        )

    def test_exact_server_policy_grant_produces_bounded_allowed_decision(self) -> None:
        decision = self.authorize(self.policy_for(self.grant_for()))

        self.assertIs(type(decision), ExternalAuthorizationDecision)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "granted")
        evidence = decision.as_safe_dict()
        self.assertEqual(evidence["principalId"], self.principal.principal_id)
        self.assertEqual(evidence["operationId"], self.operation)
        self.assertEqual(evidence["authorizationState"], "allowed")
        self.assertTrue(evidence["authorizationGranted"])
        self.assertFalse(evidence["operationExecutionAllowed"])
        self.assertFalse(evidence["uploadAllowed"])
        self.assertFalse(evidence["jobCreationAllowed"])
        self.assertFalse(evidence["networkDispatchAllowed"])
        self.assertFalse(evidence["orchestrationAllowed"])

    def test_deny_by_default_when_no_exact_grant_exists(self) -> None:
        decision = self.authorize(self.policy_for())

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "not_granted")
        evidence = decision.as_safe_dict()
        self.assertEqual(evidence["authorizationState"], "denied")
        self.assertFalse(evidence["authorizationGranted"])
        self.assertFalse(evidence["operationExecutionAllowed"])

    def test_same_principal_different_operation_is_denied(self) -> None:
        policy = self.policy_for(self.grant_for(operation_id="platform.operation.beta"))
        decision = self.authorize(policy)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "not_granted")

    def test_different_principal_exact_operation_is_denied(self) -> None:
        other_principal_id = "a" * 64
        self.assertNotEqual(other_principal_id, self.principal.principal_id)
        policy = self.policy_for(self.grant_for(principal_id=other_principal_id))
        decision = self.authorize(policy)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "not_granted")

    def test_authorization_api_has_no_caller_supplied_authority_flags(self) -> None:
        signature = inspect.signature(authorize_external_operation)
        for name in (
            "authorized",
            "authorization_granted",
            "allowed",
            "roles",
            "permissions",
            "grants",
            "upload_allowed",
            "job_creation_allowed",
        ):
            self.assertNotIn(name, signature.parameters)

    def test_policy_rejects_wildcard_noncanonical_and_duplicate_grants(self) -> None:
        invalid_operations = (
            "*",
            "platform.*",
            "Platform.Operation.Alpha",
            " platform.operation.alpha ",
            "platform/operation/alpha",
            "",
        )
        for operation_id in invalid_operations:
            with self.subTest(operation_id=operation_id):
                with self.assertRaises(ExternalAuthorizationError):
                    self.grant_for(operation_id=operation_id)

        grant = self.grant_for()
        with self.assertRaisesRegex(ExternalAuthorizationError, "authorization_policy_invalid"):
            self.policy_for(grant, grant)

    def test_operation_id_must_be_exact_canonical_text(self) -> None:
        policy = self.policy_for(self.grant_for())
        invalid = (
            "*",
            "platform.*",
            "Platform.Operation.Alpha",
            " platform.operation.alpha ",
            "platform/operation/alpha",
            "",
            "x" * 129,
            True,
        )
        for operation_id in invalid:
            with self.subTest(operation_id=operation_id):
                with self.assertRaisesRegex(ExternalAuthorizationError, "operation_invalid"):
                    self.authorize(policy, operation_id=operation_id)

        class OperationString(str):
            pass

        with self.assertRaisesRegex(ExternalAuthorizationError, "operation_invalid"):
            self.authorize(policy, operation_id=OperationString(self.operation))

    def test_policy_is_exact_version_and_environment_bound(self) -> None:
        with self.assertRaisesRegex(
            ExternalAuthorizationError, "authorization_contract_version_mismatch"
        ):
            ExternalAuthorizationPolicy(
                version="scoremosaic-external-authorization-v0",
                environment="staging",
                grants=(),
            )

        with self.assertRaisesRegex(ExternalAuthorizationError, "environment_not_allowed"):
            ExternalAuthorizationPolicy(
                version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
                environment="dev",
                grants=(),
            )

        with self.assertRaisesRegex(ExternalAuthorizationError, "environment_mismatch"):
            self.authorize(self.policy_for(environment="production"))

    def test_expired_principal_fails_closed_at_authorization_time(self) -> None:
        with self.assertRaisesRegex(ExternalAuthorizationError, "principal_expired"):
            self.authorize(
                self.policy_for(self.grant_for()),
                observed_at_epoch_s=self.principal.expires_at_epoch_s,
            )

    def test_invalid_decision_time_fails_closed(self) -> None:
        policy = self.policy_for(self.grant_for())
        for value in (-1, True, 1 << 63):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ExternalAuthorizationError, "authorization_time_invalid"):
                    self.authorize(policy, observed_at_epoch_s=value)

    def test_only_exact_authenticated_external_principal_is_accepted(self) -> None:
        policy = self.policy_for(self.grant_for())
        internal_binding = build_engine_auth_binding(
            EngineEndpoint("homr", "http://homr-foundation:8080"),
            "staging",
        )
        with self.assertRaisesRegex(ExternalAuthorizationError, "principal_invalid"):
            self.authorize(policy, principal=internal_binding)

        class PrincipalProxy:
            principal_id = self.principal.principal_id
            environment = self.principal.environment
            expires_at_epoch_s = self.principal.expires_at_epoch_s

        with self.assertRaisesRegex(ExternalAuthorizationError, "principal_invalid"):
            self.authorize(policy, principal=PrincipalProxy())

    def test_policy_subclass_is_not_authority(self) -> None:
        class DerivedPolicy(ExternalAuthorizationPolicy):
            pass

        derived = DerivedPolicy(
            version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
            environment="staging",
            grants=(self.grant_for(),),
        )
        with self.assertRaisesRegex(ExternalAuthorizationError, "authorization_policy_invalid"):
            self.authorize(derived)

    def test_safe_evidence_excludes_subject_credentials_and_policy_contents(self) -> None:
        hidden_other_principal = "b" * 64
        policy = self.policy_for(
            self.grant_for(),
            self.grant_for(
                principal_id=hidden_other_principal,
                operation_id="platform.operation.beta",
            ),
        )
        decision = self.authorize(policy)
        serialized = repr(decision.as_safe_dict())

        self.assertNotIn(self.principal.subject_id, serialized)
        self.assertNotIn("opaque-authentication-credential", serialized)
        self.assertNotIn(hidden_other_principal, serialized)
        self.assertNotIn("platform.operation.beta", serialized)
        self.assertNotIn("grants", serialized.lower())

    def test_denial_does_not_disclose_other_policy_grants(self) -> None:
        policy = self.policy_for(
            self.grant_for(operation_id="platform.operation.beta"),
        )
        decision = self.authorize(policy)
        evidence = decision.as_safe_dict()

        self.assertEqual(evidence["reason"], "not_granted")
        self.assertNotIn("platform.operation.beta", repr(evidence))

    def test_decision_cannot_be_constructed_directly_as_allowed(self) -> None:
        with self.assertRaisesRegex(
            ExternalAuthorizationError, "authorization_decision_construction_forbidden"
        ):
            ExternalAuthorizationDecision(
                version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
                environment="staging",
                principal_id=self.principal.principal_id,
                operation_id=self.operation,
                allowed=True,
                reason="granted",
            )


if __name__ == "__main__":
    unittest.main()
