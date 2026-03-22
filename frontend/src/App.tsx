import { ChatStream } from './components/stream/ChatStream';
import { MobilePlate } from './components/plate/MobilePlate';

function App() {
  return (
    <div className="relative w-full h-screen bg-black overflow-hidden sm:flex">
      {/* Desktop Split View */}
      <div className="hidden sm:block w-1/3 h-full border-r border-[#333]">
        <ChatStream />
      </div>
      <div className="hidden sm:block w-2/3 h-full bg-[#121212] p-8">
         <h1 className="text-2xl font-medium text-white mb-8">The Plate</h1>
         <div className="text-gray-400">Desktop Dashboard View (Expanded)</div>
         {/* In a full implementation, the logic from MobilePlate is expanded here into columns */}
      </div>

      {/* Mobile Fluid View */}
      <div className="sm:hidden w-full h-full relative">
        <MobilePlate />
        <ChatStream />
      </div>
    </div>
  );
}

export default App;
