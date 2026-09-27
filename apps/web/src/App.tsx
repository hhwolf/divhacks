import { Route, Routes } from 'react-router-dom';
import { PaymentPage } from './ui/PaymentPage';
import { Home } from './ui/Home';
import { EditorPage } from './ui/EditorPage';
import { ComparePage } from './ui/ComparePage';
import { SnapshotPage } from './ui/SnapshotPage';
import { ThumbPage } from './ui/ThumbPage';
import { DevicePreview } from './ui/DevicePreview';

export function App() {
  return (
    <Routes>
      <Route path="/payment/:id" element={<PaymentPage />} />
      <Route path="/" element={<Home />} />
      <Route path="/layout/:id" element={<EditorPage />} />
      <Route path="/preview/:sample" element={<EditorPage />} />
      <Route path="/compare/:a/:b" element={<ComparePage />} />
      <Route path="/snapshot/:id" element={<SnapshotPage />} />
      <Route path="/thumb/:furnitureId" element={<ThumbPage />} />
      {import.meta.env.DEV && <Route path="/device" element={<DevicePreview />} />}
    </Routes>
  );
}
