import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { StatusBadge } from "../components/StatusTracker";

function fmt(n) { return Number(n || 0).toLocaleString("ru-RU"); }

const EMPTY_CAR = {
  brand: "", model: "", year: 2023, mileage: 0, color: "", engine_volume: 1600,
  engine_type: "бензин", transmission: "автомат", drive: "передний", power: 0,
  configuration: "", description: "", status: "в Китае", available: 1, order_only: 0,
  price_cny: 0, cny_rate: 12.5, delivery_china: 30000, delivery_russia: 180000,
  customs_duty: 0, customs_fee: 0, sbkts: 35000, recycling_fee: 0,
  other_expenses: 15000, commission: 0,
};

const STATUSES = ["в Китае", "в пути", "в Новороссийске", "на таможне", "готова к выдаче"];
const ENGINE_TYPES = ["бензин", "дизель", "электро", "гибрид"];

function api(token) {
  return axios.create({ headers: { "X-Admin-Password": token } });
}

// ── Login ──────────────────────────────────────────────────────────────────
function Login({ onLogin }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      const { data } = await axios.post("/api/admin/login", { password: pw });
      onLogin(data.token);
    } catch {
      setErr("Неверный пароль");
    }
  };

  return (
    <div className="max-w-sm mx-auto mt-24 card p-8">
      <h1 className="text-xl font-bold mb-6 text-center">Вход в панель управления</h1>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="label">Пароль</label>
          <input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus />
        </div>
        {err && <p className="text-red-500 text-sm">{err}</p>}
        <button type="submit" className="btn-red w-full">Войти</button>
      </form>
      <p className="text-xs text-gray-400 mt-4 text-center">По умолчанию: china2024</p>
    </div>
  );
}

// ── Car Form ────────────────────────────────────────────────────────────────
function CarForm({ initial, token, onSave, onCancel }) {
  const [form, setForm] = useState(initial || EMPTY_CAR);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const Field = ({ k, label, type = "text", placeholder = "" }) => (
    <div>
      <label className="label">{label}</label>
      <input className="input" type={type} placeholder={placeholder}
        value={form[k] ?? ""} onChange={(e) => set(k, type === "number" ? +e.target.value : e.target.value)} />
    </div>
  );

  const save = async () => {
    setSaving(true);
    try {
      const A = api(token);
      if (form.id) {
        await A.put(`/api/admin/cars/${form.id}`, form);
      } else {
        await A.post("/api/admin/cars", form);
      }
      onSave();
    } catch (e) {
      alert("Ошибка: " + (e.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card p-6">
      <h2 className="font-bold text-lg mb-5">{form.id ? "Редактировать" : "Добавить"} автомобиль</h2>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
        <Field k="brand" label="Марка" placeholder="BYD" />
        <Field k="model" label="Модель" placeholder="Han EV" />
        <Field k="year" label="Год" type="number" />
        <Field k="mileage" label="Пробег (км)" type="number" />
        <Field k="color" label="Цвет" placeholder="Белый" />
        <Field k="engine_volume" label="Объём (куб.см)" type="number" />
        <div>
          <label className="label">Тип двигателя</label>
          <select className="input" value={form.engine_type} onChange={(e) => set("engine_type", e.target.value)}>
            {ENGINE_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Трансмиссия</label>
          <select className="input" value={form.transmission} onChange={(e) => set("transmission", e.target.value)}>
            {["автомат", "механика", "CVT", "робот"].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Привод</label>
          <select className="input" value={form.drive} onChange={(e) => set("drive", e.target.value)}>
            {["передний", "задний", "полный"].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        <Field k="power" label="Мощность (л.с.)" type="number" />
        <Field k="configuration" label="Комплектация" />
        <div>
          <label className="label">Статус</label>
          <select className="input" value={form.status} onChange={(e) => set("status", e.target.value)}>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
      </div>

      <div className="mb-6">
        <label className="label">Описание</label>
        <textarea className="input" rows={3} value={form.description}
          onChange={(e) => set("description", e.target.value)} />
      </div>

      <h3 className="font-semibold mb-3 text-gray-700">Разбивка цены (₽)</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-6">
        <Field k="price_cny" label="Цена в Китае (¥)" type="number" />
        <Field k="cny_rate" label="Курс CNY/RUB" type="number" />
        <Field k="delivery_china" label="Доставка по Китаю (₽)" type="number" />
        <Field k="delivery_russia" label="Доставка до Новороссийска (₽)" type="number" />
        <Field k="customs_duty" label="Таможенная пошлина (₽)" type="number" />
        <Field k="customs_fee" label="Таможенный сбор (₽)" type="number" />
        <Field k="sbkts" label="СБКТС (₽)" type="number" />
        <Field k="recycling_fee" label="Утилизационный сбор (₽)" type="number" />
        <Field k="other_expenses" label="Прочие расходы (₽)" type="number" />
        <Field k="commission" label="Комиссия (₽)" type="number" />
      </div>

      <div className="flex gap-3 flex-wrap mb-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={!!form.available}
            onChange={(e) => set("available", e.target.checked ? 1 : 0)} />
          <span className="text-sm">Показывать в каталоге</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={!!form.order_only}
            onChange={(e) => set("order_only", e.target.checked ? 1 : 0)} />
          <span className="text-sm">Только под заказ</span>
        </label>
      </div>

      <div className="flex gap-3">
        <button onClick={save} disabled={saving} className="btn-red disabled:opacity-50">
          {saving ? "Сохраняю..." : "Сохранить"}
        </button>
        <button onClick={onCancel} className="btn-outline">Отмена</button>
      </div>
    </div>
  );
}

// ── Photo Manager ───────────────────────────────────────────────────────────
function PhotoManager({ car, token, onUpdate }) {
  const ref = useRef();
  const [uploading, setUploading] = useState(false);

  const upload = async (e) => {
    const files = e.target.files;
    if (!files.length) return;
    setUploading(true);
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    try {
      await api(token).post(`/api/admin/cars/${car.id}/photos`, fd);
      onUpdate();
    } catch (err) {
      alert("Ошибка загрузки");
    } finally {
      setUploading(false);
      ref.current.value = "";
    }
  };

  const del = async (filename) => {
    if (!confirm(`Удалить фото?`)) return;
    await api(token).delete(`/api/admin/cars/${car.id}/photos/${filename}`);
    onUpdate();
  };

  return (
    <div className="mt-3">
      <div className="flex flex-wrap gap-2 mb-2">
        {car.photos.map((p) => (
          <div key={p} className="relative group">
            <img src={`/uploads/${p}`} alt="" className="h-20 w-28 object-cover rounded-lg" />
            <button onClick={() => del(p)}
              className="absolute top-1 right-1 bg-red-600 text-white rounded-full w-5 h-5 text-xs
                flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
              ×
            </button>
          </div>
        ))}
      </div>
      <label className="cursor-pointer text-sm text-red-600 hover:underline">
        {uploading ? "Загружаю..." : "+ Добавить фото"}
        <input ref={ref} type="file" multiple accept="image/*" className="hidden" onChange={upload} />
      </label>
    </div>
  );
}

// ── Settings Panel ──────────────────────────────────────────────────────────
function SettingsPanel({ token }) {
  const [s, setS] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api(token).get("/api/admin/settings").then((r) => setS(r.data));
  }, [token]);

  if (!s) return <div className="text-sm text-gray-400">Загрузка...</div>;

  const set = (k, v) => setS((prev) => ({ ...prev, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      await api(token).put("/api/admin/settings", s);
      alert("Настройки сохранены");
    } catch {
      alert("Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  const F = ({ k, label }) => (
    <div>
      <label className="label">{label}</label>
      <input className="input" type="number" step="any" value={s[k] ?? ""}
        onChange={(e) => set(k, parseFloat(e.target.value))} />
    </div>
  );

  return (
    <div className="card p-5">
      <h2 className="font-bold text-lg mb-4">Настройки калькулятора</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
        <F k="cny_rate" label="Курс CNY/RUB (₽)" />
        <F k="eur_rate" label="Курс EUR/RUB (₽)" />
        <F k="delivery_base" label="Базовая доставка до Новороссийска (₽)" />
        <F k="sbkts_cost" label="Стоимость СБКТС (₽)" />
        <F k="commission_pct" label="Комиссия (%)" />
      </div>
      <div className="mb-4">
        <label className="label">Новый пароль (оставьте пустым — не менять)</label>
        <input className="input max-w-xs" type="password"
          placeholder="Новый пароль"
          onChange={(e) => set("admin_password", e.target.value || undefined)} />
      </div>
      <button onClick={save} disabled={saving} className="btn-red disabled:opacity-50">
        {saving ? "Сохраняю..." : "Сохранить настройки"}
      </button>
    </div>
  );
}

// ── Main Admin ──────────────────────────────────────────────────────────────
export default function Admin() {
  const [token, setToken] = useState(() => localStorage.getItem("admin_token") || "");
  const [cars, setCars] = useState([]);
  const [editing, setEditing] = useState(null);  // null=list, "new"=create, car=edit
  const [tab, setTab] = useState("cars");

  const onLogin = (t) => {
    setToken(t);
    localStorage.setItem("admin_token", t);
  };
  const logout = () => {
    setToken("");
    localStorage.removeItem("admin_token");
  };

  const loadCars = () => {
    api(token).get("/api/admin/cars")
      .then((r) => setCars(r.data))
      .catch(() => { logout(); });
  };

  useEffect(() => {
    if (token) loadCars();
  }, [token]);

  if (!token) return <Login onLogin={onLogin} />;

  const del = async (id) => {
    if (!confirm("Удалить автомобиль?")) return;
    await api(token).delete(`/api/admin/cars/${id}`);
    loadCars();
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-extrabold">Панель управления</h1>
        <button onClick={logout} className="text-sm text-gray-500 hover:text-red-600 underline">Выйти</button>
      </div>

      <div className="flex gap-3 mb-6">
        <button onClick={() => setTab("cars")}
          className={tab === "cars" ? "btn-red" : "btn-outline"}>
          Автомобили ({cars.length})
        </button>
        <button onClick={() => setTab("settings")}
          className={tab === "settings" ? "btn-red" : "btn-outline"}>
          Настройки
        </button>
      </div>

      {tab === "settings" && <SettingsPanel token={token} />}

      {tab === "cars" && (
        <>
          {editing ? (
            <CarForm
              initial={editing === "new" ? null : editing}
              token={token}
              onSave={() => { setEditing(null); loadCars(); }}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <>
              <button onClick={() => setEditing("new")} className="btn-red mb-5">+ Добавить автомобиль</button>

              <div className="space-y-3">
                {cars.length === 0 && (
                  <div className="text-center py-16 text-gray-400">Нет автомобилей. Добавьте первый!</div>
                )}
                {cars.map((c) => (
                  <div key={c.id} className="card p-4">
                    <div className="flex items-start gap-4">
                      {c.photos[0] ? (
                        <img src={`/uploads/${c.photos[0]}`} alt=""
                          className="h-20 w-28 object-cover rounded-lg shrink-0" />
                      ) : (
                        <div className="h-20 w-28 bg-gray-100 rounded-lg flex items-center justify-center text-3xl text-gray-300 shrink-0">🚗</div>
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="font-bold">{c.brand} {c.model} {c.year}</span>
                          <StatusBadge status={c.status} />
                          {!c.available && <span className="badge bg-gray-200 text-gray-600">Скрыт</span>}
                          {c.order_only ? <span className="badge bg-gray-900 text-white">Под заказ</span> : null}
                        </div>
                        <div className="text-sm text-gray-500 mt-0.5">
                          {(c.engine_volume/1000).toFixed(1)} л · {c.engine_type} · {fmt(c.price_cny)} ¥
                          · Итого: <strong className="text-red-600">{fmt(c.total_price)} ₽</strong>
                        </div>
                        <PhotoManager car={c} token={token} onUpdate={loadCars} />
                      </div>
                      <div className="flex gap-2 shrink-0">
                        <button onClick={() => setEditing(c)} className="btn-outline text-sm py-1.5 px-3">Изменить</button>
                        <button onClick={() => del(c.id)} className="text-sm text-red-600 hover:text-red-800 px-2">Удалить</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
