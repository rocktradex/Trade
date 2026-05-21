import { Link, NavLink } from "react-router-dom";

export default function Navbar() {
  return (
    <nav className="bg-gray-900 text-white">
      <div className="max-w-7xl mx-auto px-4 flex items-center h-16 gap-8">
        <Link to="/" className="flex items-center gap-2 font-bold text-xl text-red-500 shrink-0">
          🚗 Chi Mall & NoS
        </Link>
        <div className="flex gap-6 text-sm font-medium">
          <NavLink to="/" end className={({ isActive }) => isActive ? "text-red-400" : "hover:text-white text-gray-300"}>
            Каталог
          </NavLink>
          <NavLink to="/calculator" className={({ isActive }) => isActive ? "text-red-400" : "hover:text-white text-gray-300"}>
            Калькулятор
          </NavLink>
        </div>
        <div className="ml-auto text-sm text-gray-400">
          Новороссийск · <span className="text-white font-medium">+7 (XXX) XXX-XX-XX</span>
        </div>
      </div>
    </nav>
  );
}
