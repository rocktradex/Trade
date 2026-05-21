import { Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Catalog from "./pages/Catalog";
import CarDetail from "./pages/CarDetail";
import Calculator from "./pages/Calculator";
import Admin from "./pages/Admin";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Catalog />} />
          <Route path="/cars/:id" element={<CarDetail />} />
          <Route path="/calculator" element={<Calculator />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>
      <footer className="bg-gray-900 text-gray-400 text-center text-sm py-6 mt-12">
        © 2025 AutoChina · Автомобили из Китая под ключ · Новороссийск
      </footer>
    </div>
  );
}
