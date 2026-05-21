const STEPS = [
  "в Китае",
  "в пути",
  "в Новороссийске",
  "на таможне",
  "готова к выдаче",
];

const COLORS = {
  "в Китае": "bg-blue-500",
  "в пути": "bg-yellow-500",
  "в Новороссийске": "bg-orange-500",
  "на таможне": "bg-purple-500",
  "готова к выдаче": "bg-green-500",
};

const TEXT_COLORS = {
  "в Китае": "text-blue-600",
  "в пути": "text-yellow-600",
  "в Новороссийске": "text-orange-600",
  "на таможне": "text-purple-600",
  "готова к выдаче": "text-green-600",
};

export function StatusBadge({ status }) {
  const color = TEXT_COLORS[status] || "text-gray-500";
  return (
    <span className={`badge bg-gray-100 ${color}`}>{status}</span>
  );
}

export default function StatusTracker({ status }) {
  const current = STEPS.indexOf(status);
  return (
    <div className="mt-4">
      <p className="text-sm font-medium text-gray-500 mb-3">Этап доставки</p>
      <div className="flex items-center gap-0">
        {STEPS.map((step, i) => {
          const done = i <= current;
          const active = i === current;
          return (
            <div key={step} className="flex items-center flex-1">
              <div className="flex flex-col items-center flex-1">
                <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center
                  ${done ? `${COLORS[status]} border-transparent` : "border-gray-300 bg-white"}`}>
                  {done && <div className="w-2 h-2 bg-white rounded-full" />}
                </div>
                <span className={`text-xs mt-1 text-center leading-tight w-16
                  ${active ? "font-semibold text-gray-900" : "text-gray-400"}`}>
                  {step}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`h-0.5 flex-1 mb-4 ${i < current ? COLORS[status] : "bg-gray-200"}`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
