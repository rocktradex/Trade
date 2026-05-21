import { useState, useEffect } from "react";
import axios from "axios";
import PriceBreakdown from "../components/PriceBreakdown";

const ENGINE_TYPES = ["бензин", "дизель", "электро", "гибрид"];

export default function Calculator() {
  const [form, setForm] = useState({
    brand: "", model: "", year: new Date().getFullYear() - 2,
    engine_volume: 1600, engine_type: "бензин",
    price_cny: 150000, cny_rate: "",
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [settings, setSettings] = useState(null);

  useEffect(() => {
    axios.get("/api/settings/public").then((r) => setSettings(r.data));
  }, []);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const calculate = async () => {
    setLoading(true);
    try {
      const payload = { ...form };
      if (!payload.cny_rate) delete payload.cny_rate;
      else payload.cny_rate = parseFloat(payload.cny_rate);
      payload.year = parseInt(payload.year);
      payload.engine_volume = parseInt(payload.engine_volume);
      payload.price_cny = parseFloat(payload.price_cny);
      const { data } = await axios.post("/api/calculator", payload);
      setResult(data);
      setTimeout(() => document.getElementById("calc-result")?.scrollIntoView({ behavior: "smooth" }), 100);
    } catch (e) {
      alert("Ошибка расчёта. Проверьте введённые данные.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <h1 className="text-3xl font-extrabold mb-2">Калькулятор стоимости</h1>
      <p className="text-gray-500 mb-8">
        Введите данные автомобиля — получите полную разбивку цены под ключ до Новороссийска.
      </p>

      <div className="card p-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <label className="label">Марка</label>
            <input className="input" placeholder="BYD" value={form.brand} onChange={(e) => set("brand", e.target.value)} />
          </div>
          <div>
            <label className="label">Модель</label>
            <input className="input" placeholder="Han" value={form.model} onChange={(e) => set("model", e.target.value)} />
          </div>
          <div>
            <label className="label">Год выпуска</label>
            <input className="input" type="number" min="2000" max={new Date().getFullYear()}
              value={form.year} onChange={(e) => set("year", e.target.value)} />
          </div>
          <div>
            <label className="label">Объём двигателя (куб.см)</label>
            <input className="input" type="number" placeholder="1600" min="500" max="7000"
              value={form.engine_volume} onChange={(e) => set("engine_volume", e.target.value)} />
            <p className="text-xs text-gray-400 mt-1">Например: 1.6 л = 1600 куб.см</p>
          </div>
          <div>
            <label className="label">Тип двигателя</label>
            <select className="input" value={form.engine_type} onChange={(e) => set("engine_type", e.target.value)}>
              {ENGINE_TYPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Цена в Китае (¥ юань)</label>
            <input className="input" type="number" min="10000" placeholder="150000"
              value={form.price_cny} onChange={(e) => set("price_cny", e.target.value)} />
          </div>
          <div>
            <label className="label">Курс CNY/RUB (оставьте пустым — актуальный)</label>
            <input className="input" type="number" step="0.1"
              placeholder={settings ? `текущий: ${settings.cny_rate} ₽` : "12.5"}
              value={form.cny_rate} onChange={(e) => set("cny_rate", e.target.value)} />
          </div>
        </div>

        <button onClick={calculate} disabled={loading}
          className="btn-red mt-6 w-full text-base py-3 disabled:opacity-50">
          {loading ? "Считаю..." : "Рассчитать стоимость"}
        </button>
      </div>

      {result && (
        <div id="calc-result" className="mt-8 space-y-4">
          <h2 className="text-xl font-bold">
            {result.brand || "Ваш автомобиль"} {result.model} {result.year}
          </h2>
          <PriceBreakdown car={result} />
          <div className="card p-4 text-sm text-gray-500 leading-relaxed">
            <strong className="text-gray-700">Важно:</strong> расчёт ориентировочный, для коммерческого ввоза (юрлицо).
            Точная стоимость зависит от актуального курса, конкретных условий таможни и логистики.
            Для точного расчёта и оформления заявки — свяжитесь с менеджером.
          </div>
        </div>
      )}
    </div>
  );
}
