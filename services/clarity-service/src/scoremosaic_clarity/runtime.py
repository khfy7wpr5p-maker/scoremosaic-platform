        raise RuntimeExecutionError("clarity_musicxml_unsafe_declaration")

    sanitized = document[: match.start()] + document[match.end() :]
    sanitized_upper = sanitized.upper()
    if b"<!DOCTYPE" in sanitized_upper or b"<!ENTITY" in sanitized_upper:
        raise RuntimeExecutionError("clarity_musicxml_unsafe_declaration")
    return sanitized


def _replace_musicxml_atomically(path: Path, document: bytes) -> None:
    temporary = path.with_name(f".{path.name}.sanitized")
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeExecutionError("clarity_musicxml_sanitize_target_exists")
    try:
        with temporary.open("xb") as stream:
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise RuntimeExecutionError("clarity_musicxml_sanitize_failed") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _validate_musicxml(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeExecutionError("clarity_musicxml_not_created")
    size = path.stat().st_size
    if size <= 0 or size > _MAX_MUSICXML_BYTES:
        raise RuntimeExecutionError("clarity_musicxml_size_invalid")
    try:
        document = path.read_bytes()
    except OSError as exc:
        raise RuntimeExecutionError("clarity_musicxml_read_failed") from exc

    sanitized = _sanitize_musicxml_document(document)
    try:
        root = ET.fromstring(sanitized)
    except ET.ParseError as exc:
        raise RuntimeExecutionError("clarity_musicxml_invalid_xml") from exc
    root_name = root.tag.rsplit("}", 1)[-1]
    if root_name not in {"score-partwise", "score-timewise"}:
        raise RuntimeExecutionError("clarity_musicxml_invalid_root")

    try:
        validate_musicxml_bytes(sanitized)
    except CandidateSafetyError as exc:
        raise RuntimeExecutionError(f"clarity_candidate_unsafe:{exc.code}") from exc

    if sanitized != document:
        _replace_musicxml_atomically(path, sanitized)


def transcribe_file(
    input_path: Path,
    output_dir: Path,
    config: ServiceConfig,
    *,
    runner: Runner = subprocess.run,
    probe: Probe = probe_runtime,
) -> TranscriptionResult:
    """Run one private CPU transcription and validate the generated MusicXML."""

    runtime_probe = probe(config)
    if not runtime_probe.ready:
        raise RuntimeExecutionError(runtime_probe.reason)
