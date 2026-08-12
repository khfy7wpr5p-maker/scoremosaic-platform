from __future__ import annotations

from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.external_auth import (
    EXTERNAL_AUTH_CONTRACT_VERSION,
    AuthenticatedExternalPrincipal,
    ExternalAuthError,
    ExternalAuthPolicy,
    VerifiedExternalIdentity,
    authenticate_external_principal,
)


class ExternalAuthConvergenceTests(unittest.TestCase):
    def test_authenticated_principal_cannot_be_constructed_without_verifier_seal(self) -> None:
        now = 2_000_000_000
        policy = ExternalAuthPolicy(
            version=EXTERNAL_AUTH_CONTRACT_VERSION,
            environment="staging",
            allowed_provider_ids=("test-provider",),
        )
        principal = authenticate_external_principal(
            policy=policy,
            provider_id="test-provider",
            credential=b"verified-token",
            verifier=lambda provider_id, credential: VerifiedExternalIdentity(
                provider_id=provider_id,
                subject_id="user-123",
                issued_at_epoch_s=now - 60,
                expires_at_epoch_s=now + 300,
            ),
            observed_at_epoch_s=now,
        )

        with self.assertRaisesRegex(
            ExternalAuthError,
            "principal_construction_forbidden",
        ):
            AuthenticatedExternalPrincipal(
                version=principal.version,
                environment=principal.environment,
                provider_id=principal.provider_id,
                subject_id=principal.subject_id,
                principal_id=principal.principal_id,
                authenticated_at_epoch_s=principal.authenticated_at_epoch_s,
                expires_at_epoch_s=principal.expires_at_epoch_s,
            )


if __name__ == "__main__":
    unittest.main()
