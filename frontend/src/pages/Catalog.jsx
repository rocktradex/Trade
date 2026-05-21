import { useEffect, useState } from "react";
import axios from "axios";
import CarCard from "../components/CarCard";
import { Link } from "react-router-dom";

const ENGINE_TYPES = ["", "бензин", "дизель", "электро", "гибрид"];
const STATUSES = ["", "в Китае", "в пути", "в Новороссийске", "на таможне", "готова к выдаче"];

export default function Catalog() {
  const [cars, setCars] = useState([]);
  const [brands, setBrands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    brand: "", engine_type: "", year_min: "", year_max: "", price_max: "", status: "",
  });

  useEffect(() => {
    axios.get("/api/cars/brands").then((r) => setBrands(r.data));
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== ""));
    axios.get("/api/cars", { params })
      .then((r) => setCars(r.data))
      .finally(() => setLoading(false));
  }, [filters]);

  const set = (key, val) => setFilters((f) => ({ ...f, [key]: val }));
  const reset = () => setFilters({ brand: "", engine_type: "", year_min: "", year_max: "", price_max: "", status: "" });

  return (
    <div>
      {/* Hero */}
      <div className="bg-gray-900 text-white py-14 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-4xl font-extrabold mb-3">
            <span className="text-red-500">Chi Mall</span> & <span className="text-white">NoS</span>
          </h1>
          <p className="text-gray-400 text-lg mb-6">
            Показываем полную стоимость — цена в Китае, доставка до Новороссийска, таможня, все расходы в РФ.
            Никаких скрытых платежей.
          </p>
          <Link to="/calculator" className="btn-red inline-block text-base">
            Рассчитать свой автомобиль →
          </Link>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Filters */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mb-8">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <div>
              <label className="label">Марка</label>
              <select className="input" value={filters.brand} onChange={(e) => set("brand", e.target.value)}>
                <option value="">Все</option>
                {brands.map((b) => <option key={b}>{b}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Тип двигателя</label>
              <select className="input" value={filters.engine_type} onChange={(e) => set("engine_type", e.target.value)}>
                {ENGINE_TYPES.map((t) => <option key={t} value={t}>{t || "Все"}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Год от</label>
              <input className="input" type="number" placeholder="2020" min="2000" max="2025"
                value={filters.year_min} onChange={(e) => set("year_min", e.target.value)} />
            </div>
            <div>
              <label className="label">Год до</label>
              <input className="input" type="number" placeholder="2025" min="2000" max="2025"
                value={filters.year_max} onChange={(e) => set("year_max", e.target.value)} />
            </div>
            <div>
              <label className="label">Макс. цена (₽)</label>
              <input className="input" type="number" placeholder="5 000 000"
                value={filters.price_max} onChange={(e) => set("price_max", e.target.value)} />
            </div>
            <div>
              <label className="label">Статус</label>
              <select className="input" value={filters.status} onChange={(e) => set("status", e.target.value)}>
                {STATUSES.map((s) => <option key={s} value={s}>{s || "Все"}</option>)}
              </select>
            </div>
          </div>
          <button onClick={reset} className="mt-3 text-sm text-gray-500 hover:text-red-600 underline">
            Сбросить фильтры
          </button>
        </div>

        {/* Grid */}
        {loading ? (
          <div className="text-center py-20 text-gray-400">Загрузка...</div>
        ) : cars.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-gray-500 text-lg mb-4">Автомобилей не найдено</p>
            <button onClick={reset} className="btn-outline">Сбросить фильтры</button>
          </div>
        ) : (
          <>
            <p className="text-sm text-gray-500 mb-4">{cars.length} авто</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
              {cars.map((c) => <CarCard key={c.id} car={c} />)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
