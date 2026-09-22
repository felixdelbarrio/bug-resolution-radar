import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useBlocker, useOutletContext } from "react-router-dom";
import { invalidateDashboardQueries } from "../lib/queryCache";
import type { ShellContextValue } from "../components/AppShell";
import {
  deleteJson,
  fetchJson,
  putJson,
  type FunctionalityTaxonomyCategory,
  type FunctionalityTaxonomyPayload
} from "../lib/api";

type DraftCategory = FunctionalityTaxonomyCategory & { draftKey: string };

let nextDraftKey = 0;

function toDraft(taxonomy: FunctionalityTaxonomyCategory[]): DraftCategory[] {
  return taxonomy.map((category) => ({
    ...category,
    keywords: [...category.keywords],
    draftKey: `taxonomy-category-${nextDraftKey++}`
  }));
}

function persistedTaxonomy(draft: DraftCategory[]): FunctionalityTaxonomyCategory[] {
  return draft.map(({ label, keywords }) => ({ label: label.trim(), keywords }));
}

function sameKeyword(left: string, right: string) {
  return left.localeCompare(right, "es", { sensitivity: "base" }) === 0;
}

export function FunctionalityTaxonomiesPage() {
  const { workspace, dashboardState } = useOutletContext<ShellContextValue>();
  const queryClient = useQueryClient();
  const countries = workspace?.countries.map((item) => item.country) ?? [];
  const [selectedCountry, setSelectedCountry] = useState("");
  const [draft, setDraft] = useState<DraftCategory[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (selectedCountry || countries.length === 0) {
      return;
    }
    const preferred = dashboardState.params.country || workspace?.selectedCountry || "";
    setSelectedCountry(countries.includes(preferred) ? preferred : countries[0]);
  }, [countries, dashboardState.params.country, selectedCountry, workspace?.selectedCountry]);

  const taxonomy = useQuery({
    queryKey: ["functionality-taxonomy", selectedCountry],
    queryFn: () =>
      fetchJson<FunctionalityTaxonomyPayload>(
        `/api/functionality-taxonomies/${encodeURIComponent(selectedCountry)}`
      ),
    enabled: Boolean(selectedCountry),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false
  });

  useEffect(() => {
    if (!taxonomy.data) {
      return;
    }
    setDraft(toDraft(taxonomy.data.taxonomy));
    setError("");
  }, [taxonomy.data]);

  const dirty = useMemo(() => {
    if (!taxonomy.data) {
      return false;
    }
    return JSON.stringify(persistedTaxonomy(draft)) !== JSON.stringify(taxonomy.data.taxonomy);
  }, [draft, taxonomy.data]);

  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty && (currentLocation.pathname !== nextLocation.pathname ||
      new URLSearchParams(currentLocation.search).get("settingsTab") !==
      new URLSearchParams(nextLocation.search).get("settingsTab"))
  );

  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm("Hay cambios sin guardar. ¿Quieres descartarlos?")) blocker.proceed();
    else blocker.reset();
  }, [blocker]);

  useEffect(() => {
    if (!dirty) {
      return;
    }
    const confirmNavigation = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", confirmNavigation);
    return () => window.removeEventListener("beforeunload", confirmNavigation);
  }, [dirty]);

  function applySavedTaxonomy(payload: FunctionalityTaxonomyPayload) {
    queryClient.setQueryData(["functionality-taxonomy", payload.country], payload);
    setDraft(toDraft(payload.taxonomy));
    setError("");
    void invalidateDashboardQueries(queryClient);
  }

  const save = useMutation({
    mutationFn: (nextTaxonomy: FunctionalityTaxonomyCategory[]) =>
      putJson<FunctionalityTaxonomyPayload>(
        `/api/functionality-taxonomies/${encodeURIComponent(selectedCountry)}`,
        { taxonomy: nextTaxonomy }
      ),
    onSuccess: applySavedTaxonomy,
    onError: (reason) => {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la taxonomía.");
    }
  });

  const reset = useMutation({
    mutationFn: () =>
      deleteJson<FunctionalityTaxonomyPayload>(
        `/api/functionality-taxonomies/${encodeURIComponent(selectedCountry)}`
      ),
    onSuccess: applySavedTaxonomy,
    onError: (reason) => {
      setError(reason instanceof Error ? reason.message : "No se pudo restaurar la taxonomía predeterminada.");
    }
  });

  const busy = save.isPending || reset.isPending;

  function chooseCountry(country: string) {
    if (busy) return;
    if (country === selectedCountry) {
      return;
    }
    if (dirty && !window.confirm("Hay cambios sin guardar. ¿Quieres descartarlos?")) {
      return;
    }
    setError("");
    setSelectedCountry(country);
  }

  function updateCategory(index: number, update: Partial<DraftCategory>) {
    setDraft((current) =>
      current.map((category, categoryIndex) =>
        categoryIndex === index ? { ...category, ...update } : category
      )
    );
  }

  function moveCategory(index: number, offset: -1 | 1) {
    setDraft((current) => {
      const target = index + offset;
      if (target < 0 || target >= current.length) {
        return current;
      }
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function addKeyword(index: number, rawKeyword: string) {
    const keyword = rawKeyword.trim();
    if (!keyword || draft[index].keywords.some((item) => sameKeyword(item, keyword))) {
      return false;
    }
    updateCategory(index, { keywords: [...draft[index].keywords, keyword] });
    return true;
  }

  function validateAndSave() {
    const payload = persistedTaxonomy(draft);
    if (payload.length === 0) {
      setError("Añade al menos una categoría antes de guardar.");
      return;
    }
    if (payload.some((category) => !category.label || category.keywords.length === 0)) {
      setError("Todas las categorías necesitan un nombre y al menos una keyword.");
      return;
    }
    save.mutate(payload);
  }

  const loading = taxonomy.isLoading || (!selectedCountry && countries.length > 0);
  const backendError = taxonomy.error instanceof Error ? taxonomy.error.message : "";

  return (
    <section className="page-stack taxonomy-admin-page">
      <section className="surface-panel">
        <div className="panel-head taxonomy-admin-head">
          <div>
            <p className="section-kicker">Configuración</p>
            <h3>Taxonomías de funcionalidades</h3>
            <p className="inline-caption">Configura cómo se clasifican las incidencias.</p>
          </div>
          <span className="taxonomy-source-badge">
            Usando: {taxonomy.data?.source === "override" ? "Personalizada" : "Predeterminada"}
          </span>
        </div>
        <label className="field taxonomy-country-field">
          <span>Geografía</span>
          <select
            aria-label="Geografía de la taxonomía"
            disabled={busy}
            value={selectedCountry}
            onChange={(event) => chooseCountry(event.target.value)}
          >
            {countries.map((country) => (
              <option key={country} value={country}>{country}</option>
            ))}
          </select>
        </label>
      </section>

      {loading ? <section className="surface-panel empty-panel">Cargando taxonomía...</section> : null}
      {taxonomy.isError || error ? (
        <section className="inline-notice inline-notice-error" role="alert">
          {error || backendError || "No se pudo cargar la taxonomía."}
        </section>
      ) : null}

      {!loading && taxonomy.data ? (
        <fieldset className="page-stack taxonomy-editor" disabled={busy}>
          <section className="surface-panel taxonomy-priority-panel">
            <p className="section-kicker">Prioridad</p>
            <div className="taxonomy-category-list">
              {draft.map((category, index) => (
                <article className="surface-card taxonomy-category-card" key={category.draftKey}>
                  <div className="taxonomy-category-heading">
                    <strong aria-label={`Prioridad ${index + 1}`}>{index + 1}</strong>
                    <label className="field taxonomy-label-field">
                      <span>Nombre de categoría</span>
                      <input
                        value={category.label}
                        maxLength={100}
                        onChange={(event) => updateCategory(index, { label: event.target.value })}
                      />
                    </label>
                  </div>
                  <div className="taxonomy-keyword-list" aria-label={`Keywords de ${category.label}`}>
                    {category.keywords.map((keyword, keywordIndex) => (
                      <span className="taxonomy-keyword-chip" key={`${category.draftKey}-${keywordIndex}`}>
                        {keyword}
                        <button
                          type="button"
                          aria-label={`Eliminar keyword ${keyword}`}
                          onClick={() =>
                            updateCategory(index, {
                              keywords: category.keywords.filter((_, itemIndex) => itemIndex !== keywordIndex)
                            })
                          }
                        >×</button>
                      </span>
                    ))}
                  </div>
                  <label className="field taxonomy-keyword-input">
                    <span>Añadir keyword</span>
                    <input
                      maxLength={150}
                      placeholder="Escribe y pulsa Enter"
                      onKeyDown={(event) => {
                        if (event.key !== "Enter") {
                          return;
                        }
                        event.preventDefault();
                        if (addKeyword(index, event.currentTarget.value)) {
                          event.currentTarget.value = "";
                        }
                      }}
                    />
                  </label>
                  <div className="taxonomy-category-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      aria-label={`Subir ${category.label}`}
                      disabled={index === 0}
                      onClick={() => moveCategory(index, -1)}
                    >↑</button>
                    <button
                      type="button"
                      className="secondary-button"
                      aria-label={`Bajar ${category.label}`}
                      disabled={index === draft.length - 1}
                      onClick={() => moveCategory(index, 1)}
                    >↓</button>
                    <button
                      type="button"
                      className="ghost-button taxonomy-delete-button"
                      onClick={() => setDraft((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                    >Eliminar</button>
                  </div>
                </article>
              ))}
            </div>
            <button
              type="button"
              className="secondary-button taxonomy-add-button"
              onClick={() =>
                setDraft((current) => [
                  ...current,
                  { label: "Nueva categoría", keywords: [], draftKey: `taxonomy-category-${nextDraftKey++}` }
                ])
              }
            >+ Añadir categoría</button>
          </section>

          <section className="surface-panel taxonomy-other-card">
            <h3>Otros</h3>
            <p className="inline-caption">
              Las incidencias sin coincidencia se clasifican aquí. Es una categoría implícita del sistema.
            </p>
          </section>

          <section className="surface-panel taxonomy-footer-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={busy || taxonomy.data.source === "default"}
              onClick={() => {
                if (window.confirm("¿Restaurar la taxonomía por defecto de esta geografía?")) {
                  reset.mutate();
                }
              }}
            >Restaurar predeterminada</button>
            <div className="settings-actions-row">
              <button
                type="button"
                className="secondary-button"
                disabled={!dirty || busy}
                onClick={() => setDraft(toDraft(taxonomy.data.taxonomy))}
              >Cancelar</button>
              <button
                type="button"
                className="action-button"
                disabled={!dirty || busy}
                onClick={validateAndSave}
              >{save.isPending ? "Guardando..." : "Guardar"}</button>
            </div>
          </section>
        </fieldset>
      ) : null}
    </section>
  );
}
