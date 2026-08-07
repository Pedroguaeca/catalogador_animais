"use client";

import { useEffect, useState } from "react";
import { API_BASE, apiHeaders } from "./api";

export interface Project {
  project_id:        string;
  client_id:          string;
  nome:                string;
  estado:              string;
  bioma:               string;
  data?:               string;
  nome_area_estudo?:   string;
  created_at:          string;
}

export interface Client {
  client_id:  string;
  nome:       string;
  created_at: string;
}

export function clientName(clients: Client[], clientId: string): string {
  return clients.find((c) => c.client_id === clientId)?.nome ?? "Cliente desconhecido";
}

// SIAB-221/222: busca compartilhada de /projects + /clients — usada pelo
// ProjectSelector nas 4 telas (upload, videos, dashboard, export) pra não
// triplicar o fetch e o parse de erro em cada uma.
export function useProjectsAndClients(idToken?: string, reloadKey: number = 0) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [clients,  setClients]  = useState<Client[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  useEffect(() => {
    if (!idToken) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [pRes, cRes] = await Promise.all([
          fetch(`${API_BASE}/projects`, { headers: apiHeaders(idToken) }),
          fetch(`${API_BASE}/clients`,  { headers: apiHeaders(idToken) }),
        ]);
        if (!pRes.ok) throw new Error(`Falha ao carregar projetos (HTTP ${pRes.status})`);
        if (!cRes.ok) throw new Error(`Falha ao carregar clientes (HTTP ${cRes.status})`);
        const pData = await pRes.json();
        const cData = await cRes.json();
        if (!cancelled) {
          setProjects(pData.items ?? []);
          setClients(cData.items ?? []);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Erro desconhecido ao carregar projetos.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idToken, reloadKey]);

  return { projects, clients, loading, error };
}
