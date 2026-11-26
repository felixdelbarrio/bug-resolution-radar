import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useBlocker } from "react-router-dom";
import { fetchJson, putJson } from "../lib/api";

type Person = { legajo: string; name: string; mail: string };
type Config = { enabled: boolean; people: Person[] };
type Payload = Config & { country: string };
type DraftPerson = Person & { draftKey: number };
type Draft = { enabled: boolean; people: DraftPerson[] };
let draftKey = 0;

function toDraft(config: Config): Draft {
  return {
    enabled: config.enabled,
    people: config.people.map((person) => ({ ...person, draftKey: ++draftKey }))
  };
}

function toConfig(draft: Draft): Config {
  return {
    enabled: draft.enabled,
    people: draft.people.map(({ legajo, name, mail }) => ({
      legajo: legajo.trim(), name: name.trim(), mail: mail.trim()
    }))
  };
}

function validate(config: Config) {
  if (config.people.some((person) => !person.legajo || !person.name || !person.mail)) {
    return "Completa el usuario, nombre y correo de todas las filas.";
  }
  if (config.people.some((person) => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(person.mail))) {
    return "Revisa los correos electrónicos.";
  }
  for (const field of ["legajo", "mail"] as const) {
    const values = config.people.map((person) => person[field].toLowerCase());
    if (new Set(values).size !== values.length) return `Hay valores duplicados de ${field === "legajo" ? "usuario" : "correo"}.`;
  }
  return "";
}

export function ContactCenterPymePage({ countries }: { countries: string[] }) {
  const [selection, setSelection] = useState("");
  const country = countries.includes(selection)
    ? selection
    : countries.includes("Argentina") ? "Argentina" : countries[0] ?? "";
  if (!country) {
    return <section className="surface-panel empty-panel">No hay geografías configuradas.</section>;
  }
  return <CountryEditor key={country} country={country} countries={countries} onCountryChange={setSelection} />;
}

function CountryEditor({ country, countries, onCountryChange }: {
  country: string; countries: string[]; onCountryChange: (country: string) => void;
}) {
  const queryClient = useQueryClient();
  const queryKey = ["contact-center-pyme", country];
  const endpoint = `/api/contact-center-pyme/${encodeURIComponent(country)}`;
  const config = useQuery({
    queryKey,
    queryFn: () => fetchJson<Payload>(endpoint),
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false
  });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saved, setSaved] = useState<Config | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (config.data) {
      setDraft(toDraft(config.data));
      setSaved({ enabled: config.data.enabled, people: config.data.people });
    }
  }, [config.data]);
  const dirty = draft !== null && saved !== null &&
    JSON.stringify(toConfig(draft)) !== JSON.stringify(saved);
  const save = useMutation({
    mutationFn: (value: Config) => putJson<Payload>(endpoint, value),
    onSuccess: (payload) => {
      queryClient.setQueryData(queryKey, payload);
      setDraft(toDraft(payload));
      setSaved({ enabled: payload.enabled, people: payload.people });
      setError("");
      setNotice("Configuración guardada.");
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : "No se pudo guardar.")
  });
  const busy = save.isPending;
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    (dirty || busy) && (currentLocation.pathname !== nextLocation.pathname ||
      new URLSearchParams(currentLocation.search).get("settingsTab") !==
      new URLSearchParams(nextLocation.search).get("settingsTab"))
  );
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (busy) blocker.reset();
    else if (window.confirm("Hay cambios sin guardar. ¿Quieres descartarlos?")) blocker.proceed();
    else blocker.reset();
  }, [blocker, busy]);
  useEffect(() => {
    if (!dirty && !busy) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, busy]);

  function edit(next: Draft) {
    setDraft(next);
    setError("");
    setNotice("");
  }
  function saveDraft() {
    if (!draft) return;
    const value = toConfig(draft);
    const problem = validate(value);
    if (problem) { setError(problem); return; }
    setNotice("");
    save.mutate(value);
  }

  return (
    <section className="page-stack">
      <section className="surface-panel page-stack">
        <div className="panel-head">
          <div>
            <p className="section-kicker">Configuración</p>
            <h3>Contact Center PYME</h3>
          </div>
        </div>
        <label className="field taxonomy-country-field">
          <span>Geografía</span>
          <select value={country} disabled={busy} onChange={(event) => {
            if (!dirty || window.confirm("Hay cambios sin guardar. ¿Quieres descartarlos?")) {
              onCountryChange(event.target.value);
            }
          }}>
            {countries.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        {draft && !config.isError ? (
          <label className="checkbox-field checkbox-field-panel">
            <input type="checkbox" checked={draft.enabled} disabled={busy}
              onChange={(event) => edit({ ...draft, enabled: event.target.checked })} />
            <span>Habilitar Contact Center PYME en {country}</span>
          </label>
        ) : null}
      </section>
      {config.isError ? (
        <section className="inline-notice inline-notice-error" role="alert">
          {config.error.message} <button type="button" className="secondary-button"
            onClick={() => void config.refetch()}>Reintentar</button>
        </section>
      ) : !draft ? <section className="surface-panel empty-panel">Cargando configuración...</section> : (
        <section className="surface-card page-stack">
          <div className="section-head">
            <div>
              <h3>Operadores</h3>
              <p>{draft.people.length} registros · {draft.enabled ? "Habilitado" : "Deshabilitado"}</p>
            </div>
            <button type="button" className="secondary-button" disabled={busy || !draft.enabled || draft.people.length >= 5000}
              onClick={() => edit({ ...draft, people: [...draft.people, { draftKey: ++draftKey, legajo: "", name: "", mail: "" }] })}>
              Añadir fila
            </button>
          </div>
          {!draft.enabled ? <p className="inline-caption">Habilita la geografía para editar sus operadores.</p> : null}
          <div className="table-wrap">
            <table style={{ width: "100%", minWidth: 720, borderCollapse: "collapse" }}>
              <thead><tr>
                <th scope="col" style={{ padding: 8, textAlign: "left", width: "17%" }}>Usuario</th>
                <th scope="col" style={{ padding: 8, textAlign: "left", width: "35%" }}>Nombre y apellido</th>
                <th scope="col" style={{ padding: 8, textAlign: "left" }}>Mail</th>
                <th scope="col" style={{ padding: 8, textAlign: "left" }}>Acción</th>
              </tr></thead>
              <tbody>
                {draft.people.map((person, index) => (
                  <tr key={person.draftKey} style={{ borderTop: "1px solid var(--bbva-border)" }}>
                    {([ ["legajo", "Usuario", 80], ["name", "Nombre y apellido", 200], ["mail", "Mail", 254] ] as const).map(([field, label, maxLength]) => (
                      <td key={field} style={{ padding: 8 }}>
                        <label className="field">
                          <input aria-label={`${label}, fila ${index + 1}`} type={field === "mail" ? "email" : "text"}
                            value={person[field]} maxLength={maxLength} disabled={busy || !draft.enabled}
                            onChange={(event) => edit({ ...draft, people: draft.people.map((row) =>
                              row.draftKey === person.draftKey ? { ...row, [field]: event.target.value } : row) })} />
                        </label>
                      </td>
                    ))}
                    <td style={{ padding: 8 }}>
                      <button type="button" className="ghost-button" aria-label={`Eliminar fila ${index + 1}`}
                        disabled={busy || !draft.enabled} onClick={() => edit({ ...draft,
                          people: draft.people.filter((row) => row.draftKey !== person.draftKey) })}>Eliminar</button>
                    </td>
                  </tr>
                ))}
                {draft.people.length === 0 ? <tr><td colSpan={4} style={{ padding: 12 }}>
                  No hay operadores configurados.
                </td></tr> : null}
              </tbody>
            </table>
          </div>
          {error ? <p role="alert" className="inline-notice inline-notice-error">{error}</p> : null}
          {notice ? <p role="status" className="inline-caption">{notice}</p> : null}
          <div className="settings-actions-row">
            <button type="button" className="primary-button" disabled={busy || !dirty} onClick={saveDraft}>
              {busy ? "Guardando..." : "Guardar cambios"}
            </button>
            <button type="button" className="secondary-button" disabled={busy || !dirty || !saved}
              onClick={() => { if (saved) edit(toDraft(saved)); }}>Descartar cambios</button>
          </div>
        </section>
      )}
    </section>
  );
}
