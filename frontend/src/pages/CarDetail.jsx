import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import PriceBreakdown from "../components/PriceBreakdown";
import StatusTracker from "../components/StatusTracker";

function fmt(n) { return Number(n || 0).toLocaleString("ru-RU"); }

const SPECS = [
  { key: "year",           label: "Год выпуска" },
  { key: "mileage",        label: "Пробег",        fmt: (v) => `${fmt(v)} км` },
  { key: "color",          label: "Цвет" },
  { key: "engine_volume",  label: "Объём двигателя", fmt: (v) => `${(v/1000).toFixed(1)} л (${fmt(v)} куб.см)` },
  { key: "engine_type",    label: "Тип двигателя" },
  { key: "power",          label: "Мощность",       fmt: (v) => `${v} л.с.` },
  { key: "transmission",   label: "Трансмиссия" },
  { key: "drive",          label: "Привод" },
  { key: "configuration",  label: "Комплектация" },
];

export default function CarDetail() {
  const { id } = useParams();
  const [car, setCar] = useState(null);
  const [photo, setPhoto] = useState(0);
  const [err, setErr] = useState(false);

  useEffect(() => {
    axios.get(`/api/cars/${id}`)
      .then((r) => setCar(r.data))
      .catch(() => setErr(true));
  }, [id]);

  if (err) return <div className="text-center py-20 text-red-500">Авто не найдено</div>;
  if (!car) return <div className="text-center py-20 text-gray-400">Загрузка...</div>;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <Link to="/" className="text-sm text-gray-500 hover:text-red-600 mb-6 inline-block">← Назад к каталогу</Link>

      <h1 className="text-3xl font-extrabold mb-1">{car.brand} {car.model}</h1>
      <p className="text-gray-500 mb-6">{car.year} · {car.engine_type} · {(car.engine_volume/1000).toFixed(1)} л</p>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
        {/* Left: gallery + specs + status */}
        <div className="lg:col-span-3 space-y-6">
          {/* Gallery */}
          <div className="card overflow-hidden">
            <div className="bg-gray-100 h-72 flex items-center justify-center overflow-hidden">
              {car.photos.length > 0 ? (
                <img src={`/uploads/${car.photos[photo]}`} alt="" className="h-full w-full object-cover" />
              ) : (
                <div className="text-7xl text-gray-300">🚗</div>
              )}
            </div>
            {car.photos.length > 1 && (
              <div className="flex gap-2 p-3 overflow-x-auto">
                {car.photos.map((p, i) => (
                  <img
                    key={i}
                    src={`/uploads/${p}`}
                    alt=""
                    onClick={() => setPhoto(i)}
                    className={`h-16 w-24 object-cover rounded-lg cursor-pointer border-2 transition-all
                      ${i === photo ? "border-red-500" : "border-transparent opacity-70 hover:opacity-100"}`}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Specs */}
          <div className="card p-5">
            <h2 className="font-bold text-lg mb-4">Характеристики</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {SPECS.map(({ key, label, fmt: fmtFn }) => {
                const val = car[key];
                if (!val && val !== 0) return null;
                return (
                  <div key={key} className="flex justify-between py-1.5 border-b border-gray-50 text-sm">
                    <span className="text-gray-500">{label}</span>
                    <span className="font-medium">{fmtFn ? fmtFn(val) : val}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Status */}
          <div className="card p-5">
            <StatusTracker status={car.status} />
          </div>

          {/* Description */}
          {car.description && (
            <div className="card p-5">
              <h2 className="font-bold text-lg mb-3">Описание</h2>
              <p className="text-gray-700 text-sm leading-relaxed whitespace-pre-line">{car.description}</p>
            </div>
          )}
        </div>

        {/* Right: price breakdown */}
        <div className="lg:col-span-2 space-y-4">
          <PriceBreakdown car={car} />
          <div className="card p-5 bg-red-50 border-red-100">
            <p className="text-sm text-gray-700 font-medium mb-1">Интересует этот автомобиль?</p>
            <p className="text-sm text-gray-500 mb-3">Свяжитесь с нами — ответим на все вопросы.</p>
            <a href="tel:+7XXXXXXXXXX" className="btn-red block text-center w-full">
              Позвонить менеджеру
            </a>
          </div>
          <div className="card p-4 text-xs text-gray-500 leading-relaxed">
            Цены рассчитаны для коммерческого ввоза (юрлицо).
            Курс CNY/RUB: {car.cny_rate} ₽. Все расходы прозрачны.
          </div>
        </div>
      </div>
    </div>
  );
}
