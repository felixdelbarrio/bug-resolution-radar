from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "frontend" / "src" / "pages" / "FunctionalityTaxonomiesPage.tsx").read_text(
    encoding="utf-8"
)


def test_taxonomy_page_loads_only_selected_geography() -> None:
    assert '["functionality-taxonomy", selectedCountry]' in PAGE
    assert "/api/functionality-taxonomies/${encodeURIComponent(selectedCountry)}" in PAGE
    assert "enabled: Boolean(selectedCountry)" in PAGE


def test_taxonomy_page_changes_geography_with_dirty_confirmation() -> None:
    assert "function chooseCountry(country: string)" in PAGE
    assert "dirty && !window.confirm" in PAGE
    assert "setSelectedCountry(country)" in PAGE


def test_taxonomy_page_adds_category_with_ui_only_key() -> None:
    assert "+ Añadir categoría" in PAGE
    assert 'label: "Nueva categoría", keywords: [], draftKey:' in PAGE
    assert "persistedTaxonomy" in PAGE
    assert "return draft.map(({ label, keywords })" in PAGE


def test_taxonomy_page_deletes_category_locally() -> None:
    assert "current.filter((_, itemIndex) => itemIndex !== index)" in PAGE
    assert ">Eliminar</button>" in PAGE


def test_taxonomy_page_moves_priority_up_and_down_accessibly() -> None:
    assert "function moveCategory(index: number, offset: -1 | 1)" in PAGE
    assert "moveCategory(index, -1)" in PAGE
    assert "moveCategory(index, 1)" in PAGE
    assert "disabled={index === 0}" in PAGE
    assert "disabled={index === draft.length - 1}" in PAGE


def test_taxonomy_page_adds_and_removes_keywords_without_requests() -> None:
    assert 'event.key !== "Enter"' in PAGE
    assert "addKeyword(index, event.currentTarget.value)" in PAGE
    assert "category.keywords.filter" in PAGE
    assert "sameKeyword(item, keyword)" in PAGE


def test_taxonomy_page_tracks_dirty_state_and_cancel() -> None:
    assert "const dirty = useMemo" in PAGE
    assert "JSON.stringify(persistedTaxonomy(draft))" in PAGE
    assert "setDraft(toDraft(taxonomy.data.taxonomy))" in PAGE
    assert 'window.addEventListener("beforeunload"' in PAGE


def test_taxonomy_save_is_one_atomic_request() -> None:
    assert PAGE.count("putJson<FunctionalityTaxonomyPayload>") == 1
    assert "{ taxonomy: nextTaxonomy }" in PAGE
    assert "save.mutate(payload)" in PAGE


def test_taxonomy_reset_confirms_and_deletes_override() -> None:
    assert PAGE.count("deleteJson<FunctionalityTaxonomyPayload>") == 1
    assert "¿Restaurar la taxonomía por defecto" in PAGE
    assert "reset.mutate()" in PAGE
    assert 'taxonomy.data.source === "default"' in PAGE


def test_taxonomy_backend_errors_are_visible() -> None:
    assert 'className="inline-notice inline-notice-error" role="alert"' in PAGE
    assert "taxonomy.error instanceof Error" in PAGE
    assert "setError(reason instanceof Error ? reason.message" in PAGE
