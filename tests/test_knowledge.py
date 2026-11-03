from __future__ import annotations

from backend import oa, resources


def test_resource_catalog_is_legal_and_linked():
    catalog = resources.catalog()
    assert catalog["counts"]["items"] >= 30
    assert catalog["policy"]["sci_hub"] == "excluded"
    urls = [item["url"] for group in catalog["groups"] for item in group["items"] if item.get("url")]
    assert all(url.startswith("https://") for url in urls)
    assert not any("sci-hub" in url.lower() for url in urls)
    ids = {item["id"] for group in catalog["groups"] for item in group["items"]}
    assert {"pubchem", "uniprot", "europepmc", "openalex", "unpaywall", "scut_library", "carsi"} <= ids


def test_identifier_parser_accepts_doi_and_pmid():
    assert oa._identifier("10.3390/polym17131871") == ("doi", "10.3390/polym17131871")
    assert oa._identifier("https://doi.org/10.1038/s41586-020-2649-2") == ("doi", "10.1038/s41586-020-2649-2")
    assert oa._identifier("PMID: 41386882") == ("pmid", "41386882")
    assert oa._identifier("41386882") == ("pmid", "41386882")


def test_generated_links_do_not_include_sci_hub():
    links = oa._links("10.3390/polym17131871", "41386882")
    assert all("sci-hub" not in link["url"].lower() for link in links)
    assert any(link["kind"] == "institution" for link in links)
    assert any(link["kind"] == "doi" for link in links)


def test_postgres_pgvector_has_synced_corpus():
    from backend import db

    status = db.status()
    if not status.get("available"):
        return
    assert status["pgvector"]
    assert status["counts"]["sources"] >= 16
    assert status["counts"]["literature_records"] >= 10000
    assert status["counts"]["literature_chunks"] >= 25000
    assert status["counts"]["graph_edges"] >= 76000
    hits = db.search_literature("quercetin stability", 2)
    assert hits and hits[0]["title"]
