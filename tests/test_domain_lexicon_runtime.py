from src.rag.domain_lexicon import get_domain_lexicon


def test_domain_lexicon_normalizes_variants_and_prefers_long_terms():
    lexicon = get_domain_lexicon()

    normalized = lexicon.normalize_text("七煞与偏官同论，杀重身轻，伤官佩印。")
    hits = lexicon.extract("甲木生申月，杀旺身弱，宜杀印相生或食神制杀。")
    names = [hit.canonical for hit in hits]

    assert "七杀" in normalized
    assert "杀旺身弱" in normalized
    assert "伤官配印" in normalized
    assert "甲木" in names
    assert "申月" in names
    assert "杀旺身弱" in names
    assert "杀印相生" in names
    assert "食神制杀" in names
    assert "杀" not in names


def test_domain_lexicon_tokenizes_for_search_with_domain_terms():
    lexicon = get_domain_lexicon()

    tokens = lexicon.tokenize_for_search("甲木生申月，杀旺身弱，食神制杀。")

    assert "甲木" in tokens
    assert "申月" in tokens
    assert "杀旺身弱" in tokens
    assert "食神制杀" in tokens
