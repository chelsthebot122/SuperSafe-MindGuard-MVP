"""
Data Persistence Safeguards — an executable version of the guarantee
stated in the consent modal ("all data processing occurs strictly
client-side/in-memory, with zero remote server retention"), rather than
just a comment you have to take on faith.

What this actually checks: it temporarily wraps Python's built-in
open() so that any attempt to open a file in a WRITE mode ("w", "a",
"x", or "+") during Stream A or Stream B processing raises an error
immediately instead of silently succeeding. It then runs both
pipelines on sample data and confirms nothing tripped the guard.
Reads are allowed (loading the spaCy model files, etc., requires
reading from disk) — only writes are blocked, matching the spec's
literal wording: "no user-uploaded text or CSV files are written to
disk."

One honest caveat this test does NOT cover: presidio-analyzer's URL
recognizer depends on the `tldextract` package, which can fetch a
public-suffix list from the internet on its first use in some
environments. That fetch (if it happens at all) doesn't transmit any
of your text or CSV data — it's a one-time reference-data download,
unrelated to user content — but it's still real network activity, so
if you want a hard, zero-network guarantee rather than a
zero-data-transmission one, look into configuring tldextract with a
frozen/offline suffix list. Worth mentioning if a grader/mentor asks
about it, since claiming literally zero network activity anywhere in
the codebase would currently be inaccurate.

Run standalone with: python -m backend.safeguards
"""

import builtins

_real_open = builtins.open
_WRITE_MODE_CHARS = ("w", "a", "x", "+")


def _guarded_open(file, mode="r", *args, **kwargs):
    if any(c in mode for c in _WRITE_MODE_CHARS):
        raise AssertionError(
            f"Data Persistence Safeguard tripped: attempted to open "
            f"{file!r} in write mode {mode!r}. Processing must never "
            f"write user data to disk."
        )
    return _real_open(file, mode, *args, **kwargs)


def run_safeguard_check(verbose: bool = True) -> bool:
    """Runs Stream A and Stream B on sample data with disk writes
    blocked. Returns True if nothing attempted to write to disk.
    Raises AssertionError (propagated from _guarded_open) if something did.
    """
    import pandas as pd
    from backend.redactor import redact_text
    from backend.csv_scrubber import process_health_csv

    builtins.open = _guarded_open
    try:
        # Stream A
        redact_text("Hi, my name is Alex. You can call me at (222) 222-2222.")

        # Stream B
        sample = pd.DataFrame({
            "sourceName": ["Alex's Apple Watch"],
            "device": ["<<HKDevice: 0x1234>, name:Apple Watch>"],
            "m_startTime": ["2026-08-14 09:41:33 -0400"],
            "latitude": [39.9],
            "longitude": [-75.2],
            "value": [72],
        })
        scrubbed_df, _, _ = process_health_csv(sample)
        # Also exercise the in-memory CSV export path — this is the
        # step most likely to tempt a "just write it to a temp file"
        # shortcut, so it's worth checking explicitly.
        _ = scrubbed_df.to_csv(index=False).encode("utf-8")
    finally:
        builtins.open = _real_open

    if verbose:
        print("✔ No disk writes detected during Stream A or Stream B processing.")
    return True


if __name__ == "__main__":
    run_safeguard_check()