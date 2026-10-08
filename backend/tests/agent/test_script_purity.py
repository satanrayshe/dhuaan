from dhuaan.agent.advisory import _script_ok


def test_rejects_mixed_scripts_in_punjabi():
    # Real flash-lite output leaked Devanagari, Tamil and Hebrew letters into a Gurmukhi notice.
    assert not _script_ok("pa", "सरकारी सीनियर ਬாய்ਜ਼ ਸਕੂਲ ਨੂੰ ਪਰਾਲੀ ਦੇ ਧੂੰਏਂ ਦਾ (רੇਂਜ 60-60)")


def test_accepts_clean_scripts_with_units():
    assert _script_ok("pa", "ਸਕੂਲ ਦੇ ਸਮੇਂ ਧੂੰਏਂ ਦਾ ਕੋਈ ਖ਼ਾਸ ਅਸਰ ਨਹੀਂ ਹੋਣ ਦਾ ਅਨੁਮਾਨ ਹੈ (ਅਨੁਮਾਨਿਤ PM2.5 60 µg/m³)")
    assert _script_ok("hi", "स्कूल के समय धुएँ का कोई खास असर नहीं होने का अनुमान है (अनुमानित PM2.5 60 µg/m³)")
