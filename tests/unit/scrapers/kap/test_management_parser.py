"""Unit tests for management board HTML parser (pure, no network, no DB)."""
from datetime import date

from trailing_edge.scrapers.kap.management import parse_board_html

# Minimal fixture matching the actual KAP HTML structure observed on 2026-05-28.
# Columns: Adı-Soyadı | Tüzel Kişi | Cinsiyeti | Görevi | Mesleği |
#          Yönetim Kuruluna İlk Seçilme Tarihi | İcrada Görevli |
#          Son 5 Yıl | Dışarıdaki Görev | Finans Deneyimi |
#          Sermayedeki Payı | Pay Grubu |
#          Bağımsız Yönetim Kurulu Üyesi Olup Olmadığı | (4 more cols)
_FIXTURE_HTML = """
<html><body>
<table class="table-auto w-full text-left">
  <thead>
    <tr>
      <th>Adı-Soyadı</th>
      <th>Tüzel Kişi Üye Adına Hareket Eden Kişi</th>
      <th>Cinsiyeti</th>
      <th>Görevi</th>
      <th>Mesleği</th>
      <th>Yönetim Kuruluna İlk Seçilme Tarihi</th>
      <th>İcrada Görevli Olup Olmadığı</th>
      <th>Son 5 Yılda Ortaklıkta Üstlendiği Görevler</th>
      <th>Son Durum itibariyle Ortaklık Dışında Aldığı Görevler</th>
      <th>Denetim, Muhasebe ve/veya Finans Alanında En Az 5 Yıllık Deneyime Sahip Olup Olmadığı</th>
      <th>Sermayedeki Payı (%)</th>
      <th>Temsil Ettiği Pay Grubu</th>
      <th>Bağımsız Yönetim Kurulu Üyesi Olup Olmadığı</th>
      <th>Bağımsızlık Beyanının Yer Aldığı KAP Duyurusunun Bağlantısı</th>
      <th>Bağımsız Üyenin Aday Gösterme Komitesi Tarafından Değerlendirilip Değerlendirilmediği</th>
      <th>Bağımsızlığını Kaybeden Üye Olup Olmadığı</th>
      <th>Yer Aldığı Komiteler ve Görevi</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>RIZA KANDEMİR</td><td></td><td>Erkek</td>
      <td>Yönetim Kurulu Başkanı</td><td>İş Adamı</td>
      <td>31/10/2025</td><td>İcrada Görevli</td>
      <td>YOKTUR</td><td>YÖNETİM KURULU BAŞKANLIĞI</td><td>Evet</td>
      <td>17,52</td><td></td>
      <td>Bağımsız Üye Değil</td><td></td><td></td><td></td><td>--</td>
    </tr>
    <tr>
      <td>MUHAMMED DENİZ</td><td></td><td>Erkek</td>
      <td>Yönetim Kurulu Üyesi</td><td>Akademisyen</td>
      <td>04/12/2025</td><td>İcrada Görevli Değil</td>
      <td>YOKTUR</td><td>DENETİMDEN SORUMLU KOMİTE BAŞKANLIĞI</td><td>Evet</td>
      <td>0</td><td></td>
      <td>Bağımsız Üye</td><td></td><td>Evet</td><td>Hayır</td><td>DENETİMDEN SORUMLU KOMİTE BAŞKANI</td>
    </tr>
  </tbody>
</table>
</body></html>
"""

_EMPTY_HTML = "<html><body><p>No board data here.</p></body></html>"


def test_parse_empty_page_returns_empty_list():
    assert parse_board_html(_EMPTY_HTML) == []


def test_independent_member_flagged():
    members = parse_board_html(_FIXTURE_HTML)
    independent = [m for m in members if m.is_independent]
    assert len(independent) == 1
    assert independent[0].full_name == "MUHAMMED DENİZ"


def test_non_independent_member_not_flagged():
    members = parse_board_html(_FIXTURE_HTML)
    not_independent = [m for m in members if not m.is_independent]
    assert len(not_independent) == 1
    assert not_independent[0].full_name == "RIZA KANDEMİR"


def test_board_member_role_type_is_board():
    members = parse_board_html(_FIXTURE_HTML)
    assert all(m.role_type == "BOARD" for m in members)


def test_valid_from_parsed_from_date_string():
    members = parse_board_html(_FIXTURE_HTML)
    kandemir = next(m for m in members if m.full_name == "RIZA KANDEMİR")
    assert kandemir.valid_from == date(2025, 10, 31)


def test_two_members_returned():
    members = parse_board_html(_FIXTURE_HTML)
    assert len(members) == 2
