"""Unit tests for high-value actor seed loading."""
import pytest


def test_load_actor_seeds_riza_kandemir():
    """actor_seeds.yaml contains Rıza Kandemir with known companies."""
    from trailing_edge.scrapers.ticaret_sicil.targets import load_actor_seeds

    seeds = load_actor_seeds()
    assert "RIZA KANDEMİR" in seeds
    companies = seeds["RIZA KANDEMİR"]
    assert isinstance(companies, list)
    # At minimum Hera Teknik (scraped in Session 2)
    assert any("Hera" in c for c in companies)


def test_load_actor_seeds_empty_actors_return_list():
    """Actors with no seeds return empty list, not None."""
    from trailing_edge.scrapers.ticaret_sicil.targets import load_actor_seeds

    seeds = load_actor_seeds()
    for name, companies in seeds.items():
        assert isinstance(companies, list), f"{name} must have a list, got {type(companies)}"


def test_is_legal_entity_detects_company():
    """Known legal entity names from the cross-reference report are detected."""
    from trailing_edge.scrapers.ticaret_sicil.targets import is_legal_entity_name

    assert is_legal_entity_name("MEDİAZZ YENİ MEDYA VE TEKNOLOJİ YATIRIMLARI ANONİM ŞİRKETİ")
    assert is_legal_entity_name("TOPAZ TELEKOMİNİKASYON YAYINCILIK REKLAMCILIK SAN.VE TİC.A.Ş.")
    assert is_legal_entity_name("ÇOKYAŞAR HOLDİNG ANONİM ŞİRKETİ")
    assert is_legal_entity_name("RAL GİRİŞİM SERMAYESİ YATIRIM ORTAKLIĞI ANONİM ŞİRKETİ")


def test_is_legal_entity_allows_person():
    """Real natural person names are not flagged as legal entities."""
    from trailing_edge.scrapers.ticaret_sicil.targets import is_legal_entity_name

    assert not is_legal_entity_name("RIZA KANDEMİR")
    assert not is_legal_entity_name("MURAT İLKER DEMİREL")
    assert not is_legal_entity_name("HALİT ENGİN KEHALE")
    assert not is_legal_entity_name("AHMET ZORLU")


@pytest.mark.asyncio
async def test_high_value_actors_excludes_legal_entities(monkeypatch):
    """Legal entity names are excluded from high_value_actors even at top cluster score."""
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock

    import trailing_edge.scrapers.ticaret_sicil.targets as mod
    from trailing_edge.scrapers.kap.helpers import normalize_name

    entity_name = "MEDIAZZ YENI MEDYA ANONIM SIRKETI"

    cluster_row = MagicMock()
    cluster_row.insider_name = entity_name
    cluster_row.peak_score = 100.0

    person_obj = MagicMock()
    person_obj.name_normalized = normalize_name(entity_name)
    person_obj.id = 42
    person_obj.full_name = entity_name

    res1 = MagicMock()
    res1.all.return_value = [cluster_row]
    res2 = MagicMock()
    res2.all.return_value = []
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [person_obj]
    res3 = MagicMock()
    res3.scalars.return_value = scalars_mock

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(side_effect=[res1, res2, res3])

    @asynccontextmanager
    async def mock_get_session():
        yield mock_session

    monkeypatch.setattr(mod, "get_session", mock_get_session)

    result = await mod.get_high_value_actors(top_n=10)
    assert result == [], "Legal entity with top score must be excluded"
