import { Link } from "react-router-dom";
import { StatusBadge } from "./StatusTracker";

function fmt(n) {
  return Number(n || 0).toLocaleString("ru-RU");
}

export default function CarCard({ car }) {
  const photo = car.photos?.[0];
  return (
    <Link to={`/cars/${car.id}`} className="card flex flex-col hover:shadow-md transition-shadow group">
      <div className="relative overflow-hidden bg-gray-100 h-48">
        {photo ? (
          <img
            src={`/uploads/${photo}`}
            alt={`${car.brand} ${car.model}`}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-5xl text-gray-300">🚗</div>
        )}
        <div className="absolute top-2 left-2">
          <StatusBadge status={car.status} />
        </div>
        {car.order_only ? (
          <div className="absolute top-2 right-2 badge bg-gray-900 text-white">Под заказ</div>
        ) : null}
      </div>

      <div className="p-4 flex flex-col flex-1">
        <h3 className="font-bold text-lg leading-tight">
          {car.brand} {car.model}
        </h3>
        <div className="text-sm text-gray-500 mt-1 flex flex-wrap gap-2">
          <span>{car.year} г.</span>
          {car.mileage > 0 && <span>{fmt(car.mileage)} км</span>}
          <span>{(car.engine_volume / 1000).toFixed(1)} л · {car.engine_type}</span>
          {car.power > 0 && <span>{car.power} л.с.</span>}
        </div>

        <div className="mt-auto pt-3 border-t border-gray-100 mt-3 space-y-1">
          <div className="flex justify-between text-sm text-gray-500">
            <span>Цена в Китае</span>
            <span>¥ {fmt(car.price_cny)}</span>
          </div>
          <div className="flex justify-between font-bold text-lg">
            <span className="text-gray-700">Итого в РФ</span>
            <span className="text-red-600">{fmt(car.total_price)} ₽</span>
          </div>
        </div>
      </div>
    </Link>
  );
}
