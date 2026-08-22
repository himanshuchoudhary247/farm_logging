import { useEffect, useRef, useState } from "react";
import {
  appointmentVoiceAudio,
  appointmentVoiceConfirm,
  appointmentVoiceImage,
  appointmentVoiceSubmit,
  appointmentVoiceText,
  createAppointment,
  extractFarm,
  GeneralAlert,
  getGeneralAlert,
  getPersonalizedAdvisory,
  listAnimals,
  listAppointments,
  queryFarmer,
  Animal,
  Appointment,
  VoiceAppointmentResponse,
} from "./api";

type Page =
  | "home"
  | "weather"
  | "onboarding"
  | "animals"
  | "appointments"
  | "appointments-new"
  | "advisory"
  | "about"
  | "api-docs";

const pages: Array<{ id: Page; label: string; path: string }> = [
  { id: "home", label: "Overview", path: "/" },
  { id: "weather", label: "Weather", path: "/weather" },
  { id: "onboarding", label: "Onboarding", path: "/onboarding" },
  { id: "animals", label: "My Herd", path: "/animals" },
  { id: "appointments", label: "Appointments", path: "/appointments" },
  {
    id: "appointments-new",
    label: "New Voice Intake",
    path: "/appointments/new",
  },
  { id: "advisory", label: "Advisory", path: "/advisory" },
  { id: "about", label: "About", path: "/about" },
  { id: "api-docs", label: "API Docs", path: "/api-docs" },
];

function pageFromPath(pathname: string): Page {
  return pages.find((page) => page.path === pathname)?.id ?? "home";
}

function navigate(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function RiskPill({ level }: { level?: string }) {
  const value = level?.toLowerCase() || "low";
  return <span className={`pill pill-${value}`}>{value} risk</span>;
}

export function App() {
  const [page, setPage] = useState<Page>(() =>
    pageFromPath(window.location.pathname),
  );
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("fh-theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("fh-theme", theme);
  }, [theme]);

  useEffect(() => {
    const onPopState = () => setPage(pageFromPath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          className="brand"
          onClick={() => navigate("/")}
          aria-label="FarmHerd home"
        >
          <span className="brand-mark">FH</span>
          <span>
            FarmHerd <em>AI</em>
          </span>
        </button>
        <nav aria-label="Main navigation">
          {pages.slice(0, 6).map((item) => (
            <button
              key={item.id}
              className={page === item.id ? "nav-link active" : "nav-link"}
              onClick={() => navigate(item.path)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <button
          className="theme-toggle"
          onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          aria-label="Toggle theme"
        >
          {theme === "dark" ? "☀️" : "🌙"}
        </button>
        <button className="about-link" onClick={() => navigate("/about")}>
          About us
        </button>
      </header>
      <main>
        {page === "home" && <Home />}
        {page === "weather" && <Weather />}
        {page === "onboarding" && <Onboarding />}
        {page === "animals" && <Animals />}
        {page === "appointments" && <Appointments />}
        {page === "appointments-new" && <VoiceAppointment />}
        {page === "advisory" && <Advisory />}
        {page === "about" && <About />}
        {page === "api-docs" && <ApiDocs />}
      </main>
      <footer>
        <span>FarmHerd AI</span>
        <span>Smarter alerts. Healthier herds. Stronger farmers.</span>
        <span>Livestock-first intelligence</span>
      </footer>
    </div>
  );
}

function Home() {
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">LIVESTOCK INTELLIGENCE PLATFORM</span>
          <h1>
            Every herd has a story.
            <br />
            <i>We help you read it.</i>
          </h1>
          <p>
            FarmHerd AI brings weather risk, animal health, feed markets, and
            farm history together in one calm, practical workspace.
          </p>
          <div className="hero-actions">
            <button
              className="button primary"
              onClick={() => navigate("/weather")}
            >
              Check herd conditions <span>→</span>
            </button>
            <button className="text-button" onClick={() => navigate("/about")}>
              How it works <span>↗</span>
            </button>
          </div>
        </div>
        <div className="hero-art">
          <div className="sun"></div>
          <div className="field field-back"></div>
          <div className="field field-front"></div>
          <div className="hero-card">
            <span>HERD CONDITIONS</span>
            <strong>Good to graze</strong>
            <small>Bellary · Updated today</small>
            <div className="mini-bars">
              <i></i>
              <i></i>
              <i></i>
              <i></i>
              <i></i>
            </div>
          </div>
          <div className="animal-line">◡</div>
        </div>
      </section>
      <section className="demo-banner">
        <div>
          <span className="eyebrow">LIVE SHOWCASE</span>
          <h2>Try the synthetic demo farm.</h2>
          <p>
            Explore a pre-filled herd, health history, PIN alert, and
            personalized recommendation without using real farmer data.
          </p>
        </div>
        <div className="demo-details">
          <code>demo</code>
          <span>username</span>
          <code>farmherd-demo</code>
          <span>password</span>
          <button
            className="button primary"
            onClick={() => navigate("/advisory?demo=1")}
          >
            Open demo advisory <span>→</span>
          </button>
        </div>
      </section>
      <section className="section intro-grid">
        <div>
          <span className="eyebrow">ONE VIEW, BETTER DECISIONS</span>
          <h2>
            From forecast
            <br />
            to field action.
          </h2>
        </div>
        <div>
          <p className="large-copy">
            The right warning at the right time can protect an entire herd.
            FarmHerd turns complex signals into clear next steps for the people
            who care for animals every day.
          </p>
          <button className="text-button" onClick={() => navigate("/advisory")}>
            Explore the advisory workspace <span>↗</span>
          </button>
        </div>
      </section>
      <section className="feature-grid">
        <Feature
          number="01"
          title="Weather-aware care"
          text="PIN-specific forecasts and heat-stress signals make shelter, hydration, and grazing decisions easier."
        />
        <Feature
          number="02"
          title="A memory for your herd"
          text="Health logs and animal history turn generic advice into recommendations that fit your farm."
        />
        <Feature
          number="03"
          title="Built for the field"
          text="A focused experience designed for practical decisions, not dashboards for dashboard's sake."
        />
      </section>
    </>
  );
}

function Feature({
  number,
  title,
  text,
}: {
  number: string;
  title: string;
  text: string;
}) {
  return (
    <article className="feature">
      <span>{number}</span>
      <h3>{title}</h3>
      <p>{text}</p>
      <button className="arrow-button">↗</button>
    </article>
  );
}

function Weather() {
  const [pin, setPin] = useState("583101");
  const [alert, setAlert] = useState<GeneralAlert | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function load() {
    setLoading(true);
    setError("");
    try {
      setAlert(await getGeneralAlert(pin));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load alert");
    } finally {
      setLoading(false);
    }
  }
  return (
    <PageFrame
      eyebrow="WEATHER + HERD SAFETY"
      title="Know what the sky means for your animals."
      intro="Get a PIN-specific alert bundle with weather risk, heat stress, and practical livestock actions."
    >
      <div className="lookup">
        <label>
          Farm PIN code
          <input
            value={pin}
            onChange={(event) => setPin(event.target.value)}
            inputMode="numeric"
          />
        </label>
        <button className="button primary" onClick={load} disabled={loading}>
          {loading ? "Loading..." : "Check conditions"}
        </button>
      </div>
      {error && (
        <div className="error-box">
          {error}
          <small>
            Make sure the cache refresh service has configured this PIN.
          </small>
        </div>
      )}
      {alert && (
        <div className="dashboard-grid">
          <div className="panel highlight">
            <span className="eyebrow">
              {alert.location?.district || alert.pin}
            </span>
            <div className="panel-heading">
              <h2>{alert.weather?.summary || "Conditions available"}</h2>
              <RiskPill level={alert.weather?.risk_level} />
            </div>
            <p>
              Updated{" "}
              {alert.generated_at
                ? new Date(alert.generated_at).toLocaleString()
                : "recently"}
            </p>
            <ul>
              {(alert.weather?.advisories || []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="panel">
            <span className="eyebrow">HEAT STRESS</span>
            <div className="metric">
              {alert.heat?.thi_max ?? "--"}
              <small>THI max</small>
            </div>
            <p>{alert.heat?.reason || "No elevated heat-stress signal."}</p>
          </div>
          <div className="panel">
            <span className="eyebrow">FEED MARKET</span>
            {(alert.feed_market?.commodities || []).slice(0, 4).map((item) => (
              <div className="price-row" key={item.commodity}>
                <span>{item.commodity}</span>
                <strong>
                  {item.modal_price_avg
                    ? `Rs ${Math.round(item.modal_price_avg)}/qtl`
                    : "--"}
                </strong>
              </div>
            ))}
          </div>
        </div>
      )}
    </PageFrame>
  );
}

function Onboarding() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  async function submit() {
    setError("");
    try {
      setResult(await extractFarm(text));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to process onboarding",
      );
    }
  }
  return (
    <PageFrame
      eyebrow="FARM SETUP"
      title="Start with a conversation."
      intro="Tell us about your farm in your own words. The assistant turns the conversation into a structured starting profile."
    >
      <div className="form-panel">
        <label>
          Describe your farm
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="I have 40 goats and 20 sheep near Bellary..."
            rows={5}
          />
        </label>
        <button
          className="button primary"
          disabled={!text.trim()}
          onClick={submit}
        >
          Build farm profile <span>→</span>
        </button>
        {error && <div className="error-box">{error}</div>}
        {result && (
          <pre className="result-box">{JSON.stringify(result, null, 2)}</pre>
        )}
      </div>
    </PageFrame>
  );
}

function Animals() {
  return (
    <PageFrame
      eyebrow="HERD RECORDS"
      title="A clear record for every animal."
      intro="Track the animals, conditions, and history that make your farm different."
    >
      <div className="empty-state">
        <div className="empty-icon">+</div>
        <h2>Connect your herd records</h2>
        <p>
          Once your farmer account is connected, this page will show animals,
          health logs, and follow-up care in one place.
        </p>
        <button
          className="button secondary"
          onClick={() => navigate("/onboarding")}
        >
          Set up your farm
        </button>
      </div>
    </PageFrame>
  );
}

function Appointments() {
  const demo = new URLSearchParams(window.location.search).get("demo") === "1";
  const [farmerId, setFarmerId] = useState(demo ? "demo-farmer" : "");
  const [animals, setAnimals] = useState<Animal[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [animalId, setAnimalId] = useState("");
  const [date, setDate] = useState("2026-08-22");
  const [time, setTime] = useState("10:00");
  const [doctor, setDoctor] = useState("demo-vet");
  const [issue, setIssue] = useState("Follow-up animal health review");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  async function loadSchedule() {
    setError("");
    setMessage("");
    if (!farmerId.trim()) return;
    setLoading(true);
    try {
      const [animalRows, appointmentRows] = await Promise.all([
        listAnimals(farmerId),
        listAppointments(farmerId),
      ]);
      setAnimals(animalRows);
      setAppointments(appointmentRows);
      if (!animalId && animalRows[0]) setAnimalId(animalRows[0].id);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load appointments",
      );
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    if (demo) void loadSchedule();
  }, []);
  async function book() {
    setError("");
    setMessage("");
    try {
      const created = await createAppointment(farmerId, {
        date,
        time,
        doctor_id: doctor,
        notes,
        animal_id: animalId || undefined,
        issue_summary: issue,
      });
      setAppointments((current) => [created, ...current]);
      setMessage("Appointment saved successfully.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to save appointment",
      );
    }
  }
  return (
    <PageFrame
      eyebrow="VETERINARY CARE"
      title="Keep the next visit in view."
      intro="Schedule follow-ups, link them to an animal, and keep the care journey connected to the health record."
    >
      {demo && (
        <div className="demo-note">
          Synthetic demo schedule loaded for Ravi's Green Valley Demo Farm.
        </div>
      )}
      <div className="lookup">
        <label>
          Farmer ID
          <input
            value={farmerId}
            onChange={(event) => setFarmerId(event.target.value)}
            placeholder="demo-farmer"
          />
        </label>
        <button
          className="button secondary"
          onClick={loadSchedule}
          disabled={!farmerId.trim() || loading}
        >
          {loading ? "Loading..." : "Load schedule"}
        </button>
        <button
          className="button primary"
          onClick={() => navigate("/appointments/new?demo=1")}
        >
          Use voice supervisor
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      {message && <div className="success-box">{message}</div>}
      <div className="appointment-layout">
        <div className="form-panel">
          <span className="eyebrow">NEW APPOINTMENT</span>
          <label>
            Animal
            <select
              value={animalId}
              onChange={(event) => setAnimalId(event.target.value)}
            >
              <option value="">General farm visit</option>
              {animals.map((animal) => (
                <option value={animal.id} key={animal.id}>
                  {animal.tag_or_name} - {animal.species}
                </option>
              ))}
            </select>
          </label>
          <label>
            Date
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </label>
          <label>
            Time
            <input
              type="time"
              value={time}
              onChange={(event) => setTime(event.target.value)}
            />
          </label>
          <label>
            Veterinarian or clinic
            <input
              value={doctor}
              onChange={(event) => setDoctor(event.target.value)}
            />
          </label>
          <label>
            Issue summary
            <input
              value={issue}
              onChange={(event) => setIssue(event.target.value)}
            />
          </label>
          <label>
            Notes
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={3}
              placeholder="Symptoms, follow-up questions, or preparation notes"
            />
          </label>
          <button
            className="button primary"
            onClick={book}
            disabled={!farmerId.trim() || !date || !time || !issue.trim()}
          >
            Save appointment
          </button>
        </div>
        <div className="schedule-list">
          <span className="eyebrow">UPCOMING CARE</span>
          {appointments.length === 0 ? (
            <div className="empty-state compact">
              <h2>No appointments yet</h2>
              <p>Load a farmer schedule or create the first follow-up visit.</p>
            </div>
          ) : (
            appointments.map((appointment) => (
              <article className="appointment-card" key={appointment.id}>
                <div>
                  <strong>{appointment.date}</strong>
                  <span>
                    {appointment.time} ·{" "}
                    {appointment.doctor_id || "Veterinary visit"}
                  </span>
                </div>
                <span className={`status status-${appointment.status}`}>
                  {appointment.status}
                </span>
                <p>
                  {appointment.issue_summary ||
                    appointment.notes ||
                    "General care visit"}
                </p>
              </article>
            ))
          )}
        </div>
      </div>
    </PageFrame>
  );
}

function VoiceAppointment() {
  const [farmerId, setFarmerId] = useState("demo-farmer");
  const [language, setLanguage] = useState("en-IN");
  const [text, setText] = useState("");
  const [response, setResponse] = useState<VoiceAppointmentResponse | null>(
    null,
  );
  const [error, setError] = useState("");
  const [activity, setActivity] = useState<"idle" | "recording" | "processing">("idle");
  const [submitted, setSubmitted] = useState(false);
  const [sessionId] = useState(() => crypto.randomUUID());
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  async function sendText() {
    if (!farmerId.trim() || !text.trim()) return;
    setError("");
    setActivity("processing");
    try {
      setResponse(
        await appointmentVoiceText(farmerId, sessionId, text, language),
      );
      setText("");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to process message",
      );
    } finally {
      setActivity("idle");
    }
  }
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const media = new MediaRecorder(stream);
      chunks.current = [];
      media.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data);
      };
      media.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        try {
          setResponse(
            await appointmentVoiceAudio(
              farmerId,
              sessionId,
              language,
              new Blob(chunks.current, {
                type: media.mimeType || "audio/webm",
              }),
            ),
          );
        } catch (err) {
          setError(
            err instanceof Error ? err.message : "Unable to process audio",
          );
        } finally {
          setActivity("idle");
        }
      };
      recorder.current = media;
      media.start();
      setActivity("recording");
    } catch {
      setError("Microphone permission is required for voice intake.");
    }
  }
  function stopRecording() {
    recorder.current?.stop();
    setActivity("processing");
  }
  async function confirm(value: string) {
    setActivity("processing");
    try {
      setResponse(await appointmentVoiceConfirm(farmerId, sessionId, value));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to confirm details",
      );
    } finally {
      setActivity("idle");
    }
  }
  async function submit() {
    setActivity("processing");
    try {
      await appointmentVoiceSubmit(farmerId, sessionId);
      setSubmitted(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to submit appointment",
      );
    } finally {
      setActivity("idle");
    }
  }
  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      await appointmentVoiceImage(farmerId, sessionId, file);
      setText("Image attached to the appointment draft.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to upload image");
    }
  }
  const audioSrc = response?.response_audio_base64
    ? `data:audio/mp3;base64,${response.response_audio_base64}`
    : null;
  return (
    <PageFrame
      eyebrow="VOICE APPOINTMENT SUPERVISOR"
      title="Tell us what happened. We will prepare the visit."
      intro="Speak naturally. FarmHerd will capture the animal issue, symptoms, appointment details, notes, and optional image, then read everything back before saving."
    >
      <div className="voice-intake">
        <div className="voice-controls">
          <label>
            Farmer ID
            <input
              value={farmerId}
              onChange={(event) => setFarmerId(event.target.value)}
              placeholder="demo-farmer"
            />
          </label>
          <label>
            Language
            <select
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
            >
              <option value="en-IN">English</option>
              <option value="hi-IN">Hindi</option>
              <option value="ta-IN">Tamil</option>
              <option value="te-IN">Telugu</option>
              <option value="kn-IN">Kannada</option>
            </select>
          </label>
          <button
            className={
              activity === "recording"
                ? "record-button recording"
                : activity === "processing"
                  ? "record-button processing"
                  : "record-button"
            }
            onClick={activity === "recording" ? stopRecording : startRecording}
            disabled={!farmerId.trim() || activity === "processing"}
          >
            {activity === "recording"
              ? "Listening... Stop"
              : activity === "processing"
                ? "Processing..."
                : "Start voice intake"}
          </button>
          <label className="image-upload">
            Attach optional image
            <input type="file" accept="image/*" onChange={upload} />
          </label>
        </div>
        <div className="voice-chat">
          <span className="eyebrow">SUPERVISOR CONVERSATION</span>
          <div className={`activity-indicator activity-${activity}`} aria-live="polite">
            <span className="activity-dot" />
            {activity === "recording"
              ? "Listening to you"
              : activity === "processing"
                ? "Understanding and preparing a response"
                : "Ready for your next answer"}
          </div>
          {response ? (
            <>
              <div className="supervisor-response">
                {response.response_text}
              </div>
              {response.transcript && (
                <div className="transcript-preview">
                  <span className="eyebrow">WHAT WE HEARD</span>
                  <p>{response.transcript}</p>
                </div>
              )}
              {audioSrc && <audio controls src={audioSrc} />}
              {response.audio_error && (
                <small className="muted">
                  Text confirmation is available; audio is unavailable for this
                  voice configuration.
                </small>
              )}
              <div className="draft-card">
                <span className="eyebrow">CURRENT DRAFT</span>
                <pre>{JSON.stringify(response.draft, null, 2)}</pre>
                <p>
                  Missing:{" "}
                  {response.missing_fields.length
                    ? response.missing_fields.join(", ")
                    : "none"}
                </p>
              </div>
              {response.state === "CONFIRMING" && (
                <div className="voice-actions">
                  <button
                    className="button primary"
                    onClick={() => confirm("yes")}
                  >
                    Yes, correct
                  </button>
                  <button
                    className="button secondary"
                    onClick={() => confirm("no")}
                  >
                    No, correct it
                  </button>
                </div>
              )}
              {response.state === "READY_TO_SUBMIT" && (
                <button className="button primary" onClick={submit}>
                  Submit appointment
                </button>
              )}
            </>
          ) : (
            <p className="muted">
              Your confirmation and the structured draft will appear here.
            </p>
          )}
          {submitted && (
            <div className="success-box">
              Appointment and health record saved.
            </div>
          )}
        </div>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div className="text-fallback">
        <span className="eyebrow">TEXT FALLBACK</span>
        <div className="query-row">
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Type what you would say to the supervisor"
          />
          <button
            className="button secondary"
            onClick={sendText}
            disabled={!farmerId.trim() || !text.trim()}
          >
            Send
          </button>
        </div>
      </div>
    </PageFrame>
  );
}

function Advisory() {
  const demo = new URLSearchParams(window.location.search).get("demo") === "1";
  const [farmerId, setFarmerId] = useState(demo ? "demo-farmer" : "");
  const [pin, setPin] = useState(demo ? "583101" : "");
  const [result, setResult] = useState<{
    general_alert: GeneralAlert;
    personalized: { actions?: string[]; watch_items?: string[] };
  } | null>(null);
  const [query, setQuery] = useState(
    demo ? "Which animals have recent health issues?" : "",
  );
  const [queryResult, setQueryResult] = useState<{
    answer?: string;
    data?: unknown[];
  } | null>(null);
  const [error, setError] = useState("");
  async function submit() {
    setError("");
    try {
      setResult(await getPersonalizedAdvisory(farmerId, pin || undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load advisory");
    }
  }
  async function ask() {
    setError("");
    try {
      setQueryResult(await queryFarmer(farmerId, query));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to answer query");
    }
  }
  return (
    <PageFrame
      eyebrow="PERSONALIZED CARE"
      title="Advice that knows your herd."
      intro="Combine your cached local alert with the animals, health issues, and history recorded on your farm."
    >
      {demo && (
        <div className="demo-note">
          Synthetic demo profile loaded: Ravi, Green Valley Demo Farm, PIN
          583101.
        </div>
      )}
      <div className="lookup">
        <label>
          Farmer ID
          <input
            value={farmerId}
            onChange={(event) => setFarmerId(event.target.value)}
            placeholder="F001"
          />
        </label>
        <label>
          PIN (optional)
          <input
            value={pin}
            onChange={(event) => setPin(event.target.value)}
            placeholder="583101"
          />
        </label>
        <button
          className="button primary"
          disabled={!farmerId.trim()}
          onClick={submit}
        >
          Generate advice
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      {result && (
        <div className="dashboard-grid">
          <div className="panel highlight">
            <span className="eyebrow">YOUR NEXT ACTIONS</span>
            <ul>
              {(result.personalized.actions || []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="panel">
            <span className="eyebrow">WATCH ITEMS</span>
            <ul>
              {(result.personalized.watch_items || []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
      <div className="query-panel">
        <span className="eyebrow">ASK ABOUT THIS FARM</span>
        <h2>Ask a question about the herd.</h2>
        <div className="query-row">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Which animals need follow-up?"
          />
          <button
            className="button secondary"
            disabled={!farmerId.trim() || !query.trim()}
            onClick={ask}
          >
            Ask FarmHerd
          </button>
        </div>
        {queryResult && (
          <div className="query-answer">
            <strong>{queryResult.answer || "No answer returned"}</strong>
            {Array.isArray(queryResult.data) && (
              <pre>{JSON.stringify(queryResult.data, null, 2)}</pre>
            )}
          </div>
        )}
      </div>
    </PageFrame>
  );
}

function About() {
  return (
    <PageFrame
      eyebrow="ABOUT FARMHERD AI"
      title="Technology that respects the work."
      intro="FarmHerd AI is a livestock-first intelligence platform for farmers who need useful guidance, not more noise."
    >
      <div className="story-grid">
        <div>
          <h2>
            Smarter alerts.
            <br />
            Healthier herds.
          </h2>
        </div>
        <div>
          <p>
            We bring weather, heat-stress detection, feed-market signals,
            disease knowledge, and farm history into one practical workflow.
          </p>
          <p>
            Our goal is simple: help farmers act earlier, reduce preventable
            losses, and make better everyday decisions for their animals.
          </p>
          <button
            className="button secondary"
            onClick={() =>
              window.open(
                "https://github.com/himanshuchoudhary247/farm_logging",
                "_blank",
              )
            }
          >
            View the project on GitHub ↗
          </button>
        </div>
      </div>
    </PageFrame>
  );
}

type Endpoint = {
  method: "GET" | "POST" | "PATCH";
  path: string;
  purpose: string;
  input: string;
  output: string;
};
const endpointGroups: Array<{
  title: string;
  description: string;
  endpoints: Endpoint[];
}> = [
  {
    title: "System",
    description: "Availability and authentication endpoints.",
    endpoints: [
      {
        method: "GET",
        path: "/healthz",
        purpose: "Check whether the API is running.",
        input: "None",
        output: '{ "status": "ok" }',
      },
      {
        method: "POST",
        path: "/auth/login",
        purpose: "Authenticate a farmer or administrator.",
        input: '{ "username": "ramu", "password": "..." }',
        output:
          '{ "id": "F001", "name": "Ramu", "login_username": "ramu", "phone": "", "role": "farmer" }',
      },
      {
        method: "GET",
        path: "/farmers?role=farmer",
        purpose: "List farmer accounts for supported workflows.",
        input: "Optional query: role=farmer",
        output: '[{ "id": "F001", "name": "Ramu", "role": "farmer" }]',
      },
    ],
  },
  {
    title: "Weather and Alerts",
    description:
      "Location-aware livestock weather intelligence and cached PIN alerts.",
    endpoints: [
      {
        method: "POST",
        path: "/weather/alert",
        purpose:
          "Generate a live weather alert with rain, wind, humidity, and THI heat-stress signals.",
        input:
          '{ "location_or_pin": "583101", "country_code": "in", "days": 3 }',
        output:
          '{ "risk_level": "high", "summary": "Severe heat stress expected...", "alerts": [], "forecast_days": [] }',
      },
      {
        method: "GET",
        path: "/alerts/general/{pin}",
        purpose:
          "Serve the pre-generated general alert bundle for a configured PIN.",
        input:
          "Path parameter: pin, for example 583101. Optional query: force_refresh=true",
        output:
          '{ "pin": "583101", "weather": {}, "heat": {}, "feed_market": {}, "valid_until": "..." }',
      },
      {
        method: "POST",
        path: "/weather/seasonal-advisory",
        purpose:
          "Combine current forecast and historical weather context into a seasonal advisory.",
        input:
          '{ "location_or_pin": "Bellary", "country_code": "in", "days": 7 }',
        output:
          '{ "district": "Bellary", "location": "...", "advisory": "..." }',
      },
      {
        method: "GET",
        path: "/weather/alerts",
        purpose: "Read stored weather notifications for the current farmer.",
        input: "Path parameter: farmer_id",
        output: '[{ "id": "...", "risk_level": "medium", "summary": "..." }]',
      },
    ],
  },
  {
    title: "Livestock Records",
    description: "Animal, health, consultation, and appointment workflows.",
    endpoints: [
      {
        method: "GET",
        path: "/farmers/{farmer_id}/animals",
        purpose: "List animals belonging to a farmer.",
        input: "Path parameter: farmer_id",
        output:
          '[{ "id": "A001", "species": "sheep", "tag_or_name": "S-12", "breed": "" }]',
      },
      {
        method: "POST",
        path: "/farmers/{farmer_id}/animals",
        purpose: "Register a new animal.",
        input:
          '{ "tag_or_name": "S-12", "species": "sheep", "sex": "female", "breed": "Deccani", "age_years": 2, "feeding_details": "" }',
        output:
          '{ "id": "A001", "farmer_id": "F001", "species": "sheep", "tag_or_name": "S-12" }',
      },
      {
        method: "PATCH",
        path: "/farmers/{farmer_id}/animals",
        purpose: "Update animal details by animal_id or animal_name.",
        input: '{ "animal_id": "A001", "feeding_details": "Green fodder" }',
        output: '{ "id": "A001", "feeding_details": "Green fodder" }',
      },
      {
        method: "POST",
        path: "/farmers/{farmer_id}/voice/health-log",
        purpose:
          "Extract a structured health log from natural-language or voice-transcribed text.",
        input: '{ "text": "My sheep S-12 has foot swelling" }',
        output:
          '{ "intent": "health_log", "animal_id": "A001", "issue": "foot swelling", "missing": [] }',
      },
      {
        method: "POST",
        path: "/farmers/{farmer_id}/consultations",
        purpose: "Save a farmer or animal consultation.",
        input:
          '{ "animal_id": "A001", "messages": [{ "role": "user", "content": "..." }], "summary": "..." }',
        output: '{ "id": "C001", "status": "saved", "animal_id": "A001" }',
      },
      {
        method: "GET",
        path: "/farmers/{farmer_id}/appointments",
        purpose: "List veterinary appointments.",
        input: "Path parameter: farmer_id",
        output:
          '[{ "date": "2026-08-20", "time": "10:00", "status": "pending" }]',
      },
    ],
  },
  {
    title: "Personalized Intelligence",
    description:
      "Merge cached location alerts with a farmer's herd and health history.",
    endpoints: [
      {
        method: "POST",
        path: "/farmers/{farmer_id}/advisory/personalized",
        purpose: "Generate animal-specific recommendations.",
        input: '{ "pin": "583101", "force_refresh": false }',
        output:
          '{ "pin": "583101", "general_alert": {}, "personalized": { "actions": [], "watch_items": [] } }',
      },
      {
        method: "POST",
        path: "/farmers/{farmer_id}/query",
        purpose: "Ask a natural-language question about stored farm data.",
        input: '{ "query": "Which animals had health issues this month?" }',
        output: '{ "answer": "...", "data": [] }',
      },
      {
        method: "POST",
        path: "/llm/extract-farm",
        purpose: "Extract structured farm information from onboarding text.",
        input:
          '{ "text": "I am Ramu with 200 sheep", "language": "en", "existing_data": {} }',
        output:
          '{ "farmer": { "name": "Ramu" }, "farm": { "sheepCount": 200 } }',
      },
    ],
  },
];

function ApiDocs() {
  return (
    <PageFrame
      eyebrow="DEVELOPER REFERENCE"
      title="Build on FarmHerd intelligence."
      intro="A practical reference for connecting farmer experiences, dashboards, and future services to the FarmHerd API."
    >
      <div className="api-doc-intro">
        <div>
          <span className="eyebrow">BASE URL</span>
          <code>https://65.0.181.84/api</code>
        </div>
        <div>
          <span className="eyebrow">FORMAT</span>
          <code>application/json</code>
        </div>
        <div>
          <span className="eyebrow">AUTH</span>
          <code>Farmer login required for private routes</code>
        </div>
      </div>
      <div className="api-note">
        <strong>Important:</strong> Always treat recommendations as decision
        support, not a replacement for a qualified veterinarian. Validate animal
        emergencies with a veterinary professional.
      </div>
      {endpointGroups.map((group) => (
        <section className="endpoint-group" key={group.title}>
          <div className="endpoint-heading">
            <span className="eyebrow">API GROUP</span>
            <h2>{group.title}</h2>
            <p>{group.description}</p>
          </div>
          <div className="endpoint-list">
            {group.endpoints.map((endpoint) => (
              <EndpointCard
                endpoint={endpoint}
                key={`${endpoint.method}-${endpoint.path}`}
              />
            ))}
          </div>
        </section>
      ))}
    </PageFrame>
  );
}

function EndpointCard({ endpoint }: { endpoint: Endpoint }) {
  return (
    <article className="endpoint-card">
      <div className="endpoint-top">
        <span className={`method method-${endpoint.method.toLowerCase()}`}>
          {endpoint.method}
        </span>
        <code>{endpoint.path}</code>
      </div>
      <p>{endpoint.purpose}</p>
      <div className="endpoint-io">
        <div>
          <span>INPUT</span>
          <pre>{endpoint.input}</pre>
        </div>
        <div>
          <span>OUTPUT</span>
          <pre>{endpoint.output}</pre>
        </div>
      </div>
    </article>
  );
}

function PageFrame({
  eyebrow,
  title,
  intro,
  children,
}: {
  eyebrow: string;
  title: string;
  intro: string;
  children: React.ReactNode;
}) {
  return (
    <section className="page">
      <div className="page-heading">
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{intro}</p>
      </div>
      {children}
    </section>
  );
}
