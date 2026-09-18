// Local login bypass + dummy-data mock for flokiquser UI testing.
// No backend, no DB required. Paste into DevTools console on
// http://localhost:5174/ BEFORE navigating to /login.
//
// Covers: auth flow, dashboard (weather + flock value cards), Animals tab
// (2 dummy animals), Appointments, Shop/products, alerts. Any other GET
// falls back to {results: []} — extend MOCKS below if another screen
// gets stuck on a spinner (means it needs a shape this doesn't provide).
//
// Lost on every hard page reload (typing a URL, refreshing) — re-paste
// after that. Survives in-app navigation (clicking links/tabs).

(function () {
  const FARM_ID = "dummy-farm-1";

  const DUMMY_ANIMALS = {
    list: [
      {
        id: "animal-1",
        species: "goat",
        tagOrName: "G-101",
        breed: "Boer",
        gender: "Female",
        age_months: 18,
        status: "active",
        photos: "",
      },
      {
        id: "animal-2",
        species: "sheep",
        tagOrName: "S-042",
        breed: "Nellore",
        gender: "Male",
        age_months: 24,
        status: "active",
        photos: "",
      },
    ],
    total: 2,
  };

  const DUMMY_WEATHER = {
    temp: 28,
    condition: "Sunny",
    icon: "sunny",
    next24: "Clear skies expected",
    windSpeed: 12,
    windDirection: "NE",
  };

  const MOCKS = [
    { test: (u) => u.includes("/auth/login"), method: "POST", body: { otpId: "mock-otp-id" } },
    {
      test: (u) => u.includes("/auth/verify-otp"),
      method: "POST",
      body: {
        tokens: {
          access: { token: "mock-access-token" },
          refresh: { token: "mock-refresh-token" },
        },
      },
    },
    {
      // Only hit on a real 401 (axiosInstance.ts's response interceptor).
      // Shape must match exactly: tokens.access is read as the raw string
      // (not .access.token like verify-otp), tokens.refresh.token is nested.
      // Kept mocked so a stray 401 can't crash into the same login redirect
      // this whole setup exists to avoid.
      test: (u) => u.includes("/auth/refresh-tokens"),
      method: "POST",
      body: {
        tokens: {
          access: "mock-access-token",
          refresh: { token: "mock-refresh-token" },
        },
      },
    },
    {
      test: (u) => u.includes("/user/me"),
      method: "GET",
      body: {
        id: "dev-mock-user",
        user: {
          id: "dev-mock-user",
          firstName: "Dev",
          lastName: "Mock",
          phone: "9999999999",
          role: "farmer",
        },
        farmer: {
          id: "dev-mock-farmer",
          boardingDetails: null, // null (not undefined) skips KYC redirect
          farms: { id: FARM_ID },
        },
        app_permissions: {},
      },
    },
    { test: (u) => u.includes(`/farms/farm-animals/${FARM_ID}`), method: "GET", body: DUMMY_ANIMALS },
    { test: (u) => u.includes("/weather"), method: "GET", body: DUMMY_WEATHER },
    { test: (u) => u.includes("/farmers/flock/value"), method: "GET", body: { totalValue: 42500 } },
    { test: (u) => u.includes("/alerts/get-vaccination-alerts"), method: "GET", body: { alerts: [] } },
    { test: (u) => u.includes("/appointments"), method: "GET", body: { results: [] } },
    { test: (u) => u.includes("/products"), method: "GET", body: { results: [] } },
    { test: (u) => u.includes("/categories"), method: "GET", body: { results: [] } },
    { test: (u) => u.includes("/config-data"), method: "GET", body: {} },
  ];
  const DEFAULT_BODY = { results: [] };

  function findMock(url, method) {
    return MOCKS.find((m) => m.test(url) && m.method === method);
  }

  const origFetch = window.fetch;
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : input.url;
    const method = ((init && init.method) || "GET").toUpperCase();
    const mock = findMock(url, method);
    if (mock) {
      console.log("[MOCK fetch]", method, url, "->", mock.body);
      return new Response(JSON.stringify(mock.body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.startsWith("/") || url.includes(location.host) || url.includes("sandboxapi.flokiq.com")) {
      console.log("[MOCK fetch default]", method, url);
      return new Response(JSON.stringify(DEFAULT_BODY), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return origFetch.apply(this, arguments);
  };

  const OrigXHR = window.XMLHttpRequest;
  function MockXHR() {
    const xhr = new OrigXHR();
    let _url = "";
    let _method = "GET";
    const origOpen = xhr.open.bind(xhr);
    xhr.open = function (method, url, ...rest) {
      _method = method.toUpperCase();
      _url = url;
      return origOpen(method, url, ...rest);
    };
    const origSend = xhr.send.bind(xhr);
    xhr.send = function (body) {
      const mock = findMock(_url, _method);
      const isLocal = _url.startsWith("/") || _url.includes(location.host) || _url.includes("sandboxapi.flokiq.com");
      if (mock || isLocal) {
        const respBody = mock ? mock.body : DEFAULT_BODY;
        console.log("[MOCK xhr]", _method, _url, "->", respBody);
        setTimeout(() => {
          Object.defineProperty(xhr, "status", { value: 200, configurable: true });
          Object.defineProperty(xhr, "readyState", { value: 4, configurable: true });
          Object.defineProperty(xhr, "responseText", {
            value: JSON.stringify(respBody),
            configurable: true,
          });
          // axios's XHR adapter defaults responseType to 'json' and reads
          // xhr.response directly as an already-parsed object in that case
          // (mirroring native browser JSON auto-parse) — must NOT be a
          // string here, or axios hands back a raw string as response.data
          // and every `.foo.bar` access downstream silently becomes
          // undefined instead of throwing, which is exactly what happened:
          // bento cards never rendered, no console error either.
          const responseValue = xhr.responseType === "json" || xhr.responseType === "" ? respBody : JSON.stringify(respBody);
          Object.defineProperty(xhr, "response", {
            value: responseValue,
            configurable: true,
          });
          xhr.dispatchEvent(new Event("readystatechange"));
          xhr.dispatchEvent(new Event("load"));
          xhr.dispatchEvent(new Event("loadend"));
        }, 50);
        return;
      }
      return origSend(body);
    };
    return xhr;
  }
  window.XMLHttpRequest = MockXHR;
  window.__MOCK_INSTALLED__ = true;
  console.log("mock network layer installed — farmId:", FARM_ID);
})();
