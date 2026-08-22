const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(
  /\/$/,
  "",
);

export type GeneralAlert = {
  pin: string;
  location?: { district?: string; state?: string; name?: string };
  generated_at?: string;
  valid_until?: string;
  weather?: {
    risk_level?: string;
    summary?: string;
    advisories?: string[];
  };
  heat?: { level?: string; thi_max?: number; reason?: string };
  feed_market?: {
    commodities?: Array<{ commodity: string; modal_price_avg?: number }>;
  };
  errors?: string[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function getGeneralAlert(pin: string) {
  return request<GeneralAlert>(
    `/alerts/general/${encodeURIComponent(pin)}`,
  ).catch(async () => {
    const legacy = await request<Record<string, unknown>>(
      "/../weather-api/weather/alert",
      {
        method: "POST",
        body: JSON.stringify({ location_or_pin: pin, days: 3 }),
      },
    );
    return {
      pin,
      weather: {
        risk_level:
          typeof legacy.risk_level === "string" ? legacy.risk_level : undefined,
        summary:
          typeof legacy.summary === "string" ? legacy.summary : undefined,
        advisories: Array.isArray(legacy.advisories)
          ? (legacy.advisories as string[])
          : [],
      },
      heat: { level: "low" },
      location: legacy.resolved_location as GeneralAlert["location"],
      generated_at: new Date().toISOString(),
    } satisfies GeneralAlert;
  });
}

export function getPersonalizedAdvisory(farmerId: string, pin?: string) {
  return request<{
    general_alert: GeneralAlert;
    personalized: { actions?: string[]; watch_items?: string[] };
  }>(`/farmers/${encodeURIComponent(farmerId)}/advisory/personalized`, {
    method: "POST",
    body: JSON.stringify({ pin }),
  });
}

export function queryFarmer(farmerId: string, query: string) {
  return request<{ answer?: string; data?: unknown[]; sql?: string }>(
    `/farmers/${encodeURIComponent(farmerId)}/query`,
    { method: "POST", body: JSON.stringify({ query }) },
  );
}

export type Animal = {
  id: string;
  species: string;
  tag_or_name: string;
  breed?: string;
  age_years?: number;
};
export type Appointment = {
  id: string;
  date: string;
  time: string;
  status: string;
  doctor_id?: string;
  notes?: string;
  animal_id?: string;
  issue_summary?: string;
};

export function listAnimals(farmerId: string) {
  return request<Animal[]>(`/farmers/${encodeURIComponent(farmerId)}/animals`);
}

export function listAppointments(farmerId: string) {
  return request<Appointment[]>(
    `/farmers/${encodeURIComponent(farmerId)}/appointments`,
  );
}

export function createAppointment(
  farmerId: string,
  input: {
    date: string;
    time: string;
    doctor_id: string;
    notes: string;
    animal_id?: string;
    issue_summary: string;
  },
) {
  return request<Appointment>(
    `/farmers/${encodeURIComponent(farmerId)}/appointments`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

export type VoiceAppointmentResponse = {
  session_id: string;
  state: string;
  language: string;
  transcript?: string;
  draft: Record<string, unknown>;
  missing_fields: string[];
  response_text: string;
  response_audio_base64?: string | null;
  audio_error?: string | null;
};

export function appointmentVoiceText(
  farmerId: string,
  sessionId: string,
  text: string,
  language: string,
) {
  return request<VoiceAppointmentResponse>(
    `/farmers/${encodeURIComponent(farmerId)}/appointments/voice/text`,
    {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, text, language }),
    },
  );
}

export async function appointmentVoiceAudio(
  farmerId: string,
  sessionId: string,
  language: string,
  audio: Blob,
) {
  const form = new FormData();
  form.append("audio", audio, "appointment.webm");
  const response = await fetch(
    `${API_BASE}/farmers/${encodeURIComponent(farmerId)}/appointments/voice/turn?session_id=${encodeURIComponent(sessionId)}&language=${encodeURIComponent(language)}`,
    { method: "POST", body: form },
  );
  if (!response.ok)
    throw new Error(
      (await response.text()) || `Request failed (${response.status})`,
    );
  return response.json() as Promise<VoiceAppointmentResponse>;
}

export function appointmentVoiceConfirm(
  farmerId: string,
  sessionId: string,
  response: string,
) {
  return request<VoiceAppointmentResponse>(
    `/farmers/${encodeURIComponent(farmerId)}/appointments/voice/confirm`,
    {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, response }),
    },
  );
}

export function appointmentVoiceSubmit(farmerId: string, sessionId: string) {
  return request<{
    status: string;
    intake?: Record<string, unknown>;
    appointment?: Appointment;
    health_log?: Record<string, unknown>;
  }>(`/farmers/${encodeURIComponent(farmerId)}/appointments/voice/submit`, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, response: "submit" }),
  });
}

export async function appointmentVoiceImage(
  farmerId: string,
  sessionId: string,
  image: File,
) {
  const form = new FormData();
  form.append("image", image);
  const response = await fetch(
    `${API_BASE}/farmers/${encodeURIComponent(farmerId)}/appointments/voice/image?session_id=${encodeURIComponent(sessionId)}`,
    { method: "POST", body: form },
  );
  if (!response.ok)
    throw new Error(
      (await response.text()) || `Image upload failed (${response.status})`,
    );
  return response.json() as Promise<{ attachments: unknown[] }>;
}

export function extractFarm(text: string) {
  return request<Record<string, unknown>>("/llm/extract-farm", {
    method: "POST",
    body: JSON.stringify({ text, language: "en", existing_data: {} }),
  }).catch(() =>
    request<Record<string, unknown>>("/../onboarding-api/onboarding", {
      method: "POST",
      body: JSON.stringify({ text, existing: {}, language: "en" }),
    }),
  );
}
