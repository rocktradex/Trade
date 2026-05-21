function fmt(n) {
  return Number(n || 0).toLocaleString("ru-RU");
}

const ROWS = [
  { key: "price_rub",        label: "Цена в Китае",              note: (c) => `¥ ${fmt(c.price_cny)} × ${c.cny_rate} ₽` },
  { key: "delivery_china",   label: "Доставка до порта (Китай)" },
  { key: "delivery_russia",  label: "Фрахт + доставка до Новороссийска" },
  { key: "customs_duty",     label: "Таможенная пошлина" },
  { key: "customs_fee",      label: "Таможенный сбор" },
  { key: "sbkts",            label: "СБКТС (одобрение типа ТС)" },
  { key: "recycling_fee",    label: "Утилизационный сбор" },
  { key: "other_expenses",   label: "Прочие расходы (оформление)" },
  { key: "commission",       label: "Комиссия" },
];

export default function PriceBreakdown({ car }) {
  return (
    <div className="card p-5">
      <h2 className="font-bold text-lg mb-4">Полная стоимость</h2>
      <div className="space-y-0 divide-y divide-gray-100">
        {ROWS.map(({ key, label, note }) => {
          const val = car[key];
          if (!val && val !== 0) return null;
          return (
            <div key={key} className="price-row text-sm">
              <div>
                <span className="text-gray-700">{label}</span>
                {note && <div className="text-xs text-gray-400">{note(car)}</div>}
              </div>
              <span className="font-medium text-gray-900 ml-4 whitespace-nowrap">
                {fmt(val)} ₽
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-4 border-t-2 border-gray-900 flex justify-between items-center">
        <span className="font-bold text-gray-900">Итого</span>
        <span className="font-bold text-2xl text-red-600">{fmt(car.total_price)} ₽</span>
      </div>

      {car.note && (
        <p className="mt-3 text-xs text-blue-600 bg-blue-50 rounded-lg px-3 py-2">{car.note}</p>
      )}
    </div>
  );
}
