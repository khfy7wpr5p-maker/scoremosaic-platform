from pathlib import Path
import unittest


DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


class HomrDockerfileDownloadPolicyTests(unittest.TestCase):
    def _model_download_block(self) -> str:
        text = DOCKERFILE.read_text(encoding="utf-8")
        start = text.index("curl --fail --location --proto '=https' --tlsv1.2")
        end = text.index('echo "${archive_sha}  /tmp/${archive}"', start)
        return text[start:end]

    def test_model_download_uses_bounded_resilient_retry_budget(self) -> None:
        block = self._model_download_block()
        self.assertIn("--retry 8", block)
        self.assertIn("--retry-all-errors", block)
        self.assertIn("--retry-max-time 180", block)
        self.assertIn("--connect-timeout 20", block)

    def test_model_and_extracted_artifact_checksums_remain_required(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn(
            'echo "${archive_sha}  /tmp/${archive}" | sha256sum --check --strict;',
            text,
        )
        self.assertIn(
            'echo "${output_sha}  ${destination}/${output_name}" \\\n        | sha256sum --check --strict;',
            text,
        )


if __name__ == "__main__":
    unittest.main()
