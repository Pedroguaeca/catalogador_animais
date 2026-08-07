"use client";

import { useState } from "react";
import { Loader2, AlertCircle } from "lucide-react";
import { API_BASE, apiHeaders } from "../lib/api";
import type { Client, Project } from "../lib/projectTypes";

// 27 UFs — mesmos códigos do enum UF em backend/api.py.
const UF_OPTIONS: { code: string; label: string }[] = [
  { code: "AC", label: "Acre" }, { code: "AL", label: "Alagoas" }, { code: "AP", label: "Amapá" },
  { code: "AM", label: "Amazonas" }, { code: "BA", label: "Bahia" }, { code: "CE", label: "Ceará" },
  { code: "DF", label: "Distrito Federal" }, { code: "ES", label: "Espírito Santo" }, { code: "GO", label: "Goiás" },
  { code: "MA", label: "Maranhão" }, { code: "MT", label: "Mato Grosso" }, { code: "MS", label: "Mato Grosso do Sul" },
  { code: "MG", label: "Minas Gerais" }, { code: "PA", label: "Pará" }, { code: "PB", label: "Paraíba" },
  { code: "PR", label: "Paraná" }, { code: "PE", label: "Pernambuco" }, { code: "PI", label: "Piauí" },
  { code: "RJ", label: "Rio de Janeiro" }, { code: "RN", label: "Rio Grande do Norte" }, { code: "RS", label: "Rio Grande do Sul" },
  { code: "RO", label: "Rondônia" }, { code: "RR", label: "Roraima" }, { code: "SC", label: "Santa Catarina" },
  { code: "SP", label: "São Paulo" }, { code: "SE", label: "Sergipe" }, { code: "TO", label: "Tocantins" },
];

// 6 biomas oficiais (IBGE) — mesmos valores do enum Bioma em backend/api.py.
const BIOMA_OPTIONS = ["Amazônia", "Caatinga", "Cerrado", "Mata Atlântica", "Pampa", "Pantanal"];

const inputStyle: React.CSSProperties = {
  padding: "8px 12px", borderRadius: 10, fontSize: 13,
  border: "1.5px solid #E7DECF", background: "#FAF6EE",
  color: "#221F1A", fontFamily: "IBM Plex Sans, sans-serif", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: 12, fontWeight: 500, color: "#6B6357" };

interface CreateProjectFormProps {
  idToken?:         string;
  clients:          Client[];
  onCreated:        (project: Project) => void;
  onClientCreated:  (client: Client) => void;
  onCancel:         () => void;
}

// SIAB-222: formulário inline "Criar novo projeto" no upload — cliente
// (existente ou novo), nome, data, área de estudo, UF, bioma. Valida estado/
// bioma já acontece no backend (SIAB-150); aqui só trata o 400 de volta com
// mensagem legível, sem duplicar a validação.
export function CreateProjectForm({ idToken, clients, onCreated, onClientCreated, onCancel }: CreateProjectFormProps) {
  const [clientMode, setClientMode]     = useState<"existing" | "new">(clients.length > 0 ? "existing" : "new");
  const [clientId, setClientId]         = useState(clients[0]?.client_id ?? "");
  const [newClientName, setNewClientName] = useState("");
  // Cliente criado nesta sessão do formulário, ainda ausente de `clients`
  // (o pai só refaz o fetch depois do projeto inteiro ser criado) — sem
  // isso, o <select> "existente" ficaria com um value sem <option> correspondente.
  const [justCreatedClient, setJustCreatedClient] = useState<Client | null>(null);
  const clientOptions = justCreatedClient && !clients.some((c) => c.client_id === justCreatedClient.client_id)
    ? [...clients, justCreatedClient]
    : clients;
  const [nome, setNome]                 = useState("");
  const [data, setData]                 = useState("");
  const [areaEstudo, setAreaEstudo]     = useState("");
  const [estado, setEstado]             = useState("");
  const [bioma, setBioma]               = useState("");
  const [submitting, setSubmitting]     = useState(false);
  const [error, setError]               = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (clientMode === "new" && !newClientName.trim()) {
      setError("Nome do cliente não pode ser vazio.");
      return;
    }
    if (clientMode === "existing" && !clientId) {
      setError("Selecione um cliente.");
      return;
    }
    if (!nome.trim()) { setError("Nome do projeto não pode ser vazio."); return; }
    if (!estado)      { setError("Selecione o estado.");                return; }
    if (!bioma)       { setError("Selecione o bioma.");                 return; }

    setSubmitting(true);
    try {
      let finalClientId = clientId;

      if (clientMode === "new") {
        const cRes = await fetch(`${API_BASE}/clients`, {
          method:  "POST",
          headers: apiHeaders(idToken, { "Content-Type": "application/json" }),
          body:    JSON.stringify({ nome: newClientName.trim() }),
        });
        if (!cRes.ok) {
          throw new Error(await extractErrorDetail(cRes, "Não foi possível criar o cliente"));
        }
        const client: Client = await cRes.json();
        finalClientId = client.client_id;
        onClientCreated(client);
        // Se a criação do projeto falhar a seguir (ex: 400 de estado/bioma),
        // o cliente já existe — troca pra "existente" antes de tentar de
        // novo, senão um re-submit recriaria outro cliente com o mesmo nome.
        setJustCreatedClient(client);
        setClientMode("existing");
        setClientId(finalClientId);
      }

      const pRes = await fetch(`${API_BASE}/projects`, {
        method:  "POST",
        headers: apiHeaders(idToken, { "Content-Type": "application/json" }),
        body: JSON.stringify({
          client_id:         finalClientId,
          nome:               nome.trim(),
          estado,
          bioma,
          data:               data || undefined,
          nome_area_estudo:   areaEstudo.trim() || undefined,
        }),
      });
      if (!pRes.ok) {
        throw new Error(await extractErrorDetail(pRes, "Não foi possível criar o projeto"));
      }
      const project: Project = await pRes.json();
      onCreated(project);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro desconhecido ao criar projeto.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 p-5 rounded-2xl"
      style={{ background: "#FAF6EE", border: "1.5px dashed #C3BAA8" }}
    >
      <p className="text-sm font-semibold" style={{ color: "#221F1A", fontFamily: "IBM Plex Sans, sans-serif" }}>
        Criar novo projeto
      </p>

      {/* Cliente */}
      <div className="flex flex-col gap-1.5">
        <span style={labelStyle}>Cliente</span>
        {clientMode === "existing" ? (
          <div className="flex flex-col gap-1.5">
            <select value={clientId} onChange={(e) => setClientId(e.target.value)} style={inputStyle}>
              <option value="">Selecione um cliente…</option>
              {clientOptions.map((c) => <option key={c.client_id} value={c.client_id}>{c.nome}</option>)}
            </select>
            <button
              type="button"
              onClick={() => setClientMode("new")}
              className="text-xs font-medium self-start"
              style={{ color: "#2F6B4F", textDecoration: "underline" }}
            >
              + criar novo cliente
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <input
              type="text"
              value={newClientName}
              onChange={(e) => setNewClientName(e.target.value)}
              placeholder="Nome do cliente"
              style={inputStyle}
            />
            {clients.length > 0 && (
              <button
                type="button"
                onClick={() => setClientMode("existing")}
                className="text-xs font-medium self-start"
                style={{ color: "#6B6357", textDecoration: "underline" }}
              >
                usar cliente existente
              </button>
            )}
          </div>
        )}
      </div>

      {/* Nome do projeto */}
      <label className="flex flex-col gap-1.5">
        <span style={labelStyle}>Nome do projeto</span>
        <input type="text" value={nome} onChange={(e) => setNome(e.target.value)} style={inputStyle} />
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1.5">
          <span style={labelStyle}>Data</span>
          <input type="date" value={data} onChange={(e) => setData(e.target.value)} style={inputStyle} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span style={labelStyle}>Área de estudo</span>
          <input type="text" value={areaEstudo} onChange={(e) => setAreaEstudo(e.target.value)} style={inputStyle} />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1.5">
          <span style={labelStyle}>Estado</span>
          <select value={estado} onChange={(e) => setEstado(e.target.value)} style={inputStyle}>
            <option value="">Selecione…</option>
            {UF_OPTIONS.map((uf) => <option key={uf.code} value={uf.code}>{uf.code} — {uf.label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1.5">
          <span style={labelStyle}>Bioma</span>
          <select value={bioma} onChange={(e) => setBioma(e.target.value)} style={inputStyle}>
            <option value="">Selecione…</option>
            {BIOMA_OPTIONS.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </label>
      </div>

      {error && (
        <div className="flex items-start gap-2 p-3 rounded-xl" style={{ background: "#FEF2EF", border: "1.5px solid #F5C7BB" }}>
          <AlertCircle size={14} style={{ color: "#C2503A", flexShrink: 0, marginTop: 1 }} />
          <p className="text-xs" style={{ color: "#C2503A" }}>{error}</p>
        </div>
      )}

      <div className="flex items-center gap-2 justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="text-sm font-medium px-3 py-2"
          style={{ color: "#6B6357" }}
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold text-white"
          style={{ background: submitting ? "#C3BAA8" : "#2F6B4F", cursor: submitting ? "not-allowed" : "pointer" }}
        >
          {submitting ? <><Loader2 size={14} className="animate-spin" /> Criando…</> : "Criar projeto"}
        </button>
      </div>
    </form>
  );
}

// Backend devolve dois formatos de erro diferentes: HTTPException(status_code=...)
// manual manda detail como string (ex: 404 de client_id inexistente); erro de
// validação do Pydantic (ex: estado/bioma fora do enum) manda 422 com detail
// como lista de objetos {msg, loc, ...}. Confirmado ao vivo contra o backend
// real (não assumido) — sem tratar o segundo formato, o erro aparecia como
// JSON cru na tela em vez de mensagem legível.
async function extractErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      const msgs = body.detail
        .map((e: { msg?: string; loc?: unknown[] }) => e?.msg)
        .filter(Boolean);
      if (msgs.length) return msgs.join("; ");
    }
  } catch { /* corpo não era JSON — usa o fallback */ }
  return `${fallback} (HTTP ${res.status}).`;
}
