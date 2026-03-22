import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAppStore } from '../../store/appStore';
import { CheckCircle2, Circle, Clock } from 'lucide-react';

export const MobilePlate: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const { nodes } = useAppStore(); // In real app, this is synced via PowerSync

  // Dummy data for MVP if no nodes
  const activeTasks = nodes.length > 0 ? nodes : [
    { id: '1', content: 'Buy milk', status: 'OPEN', deadline: 'Today' },
    { id: '2', content: 'Email Sarah about thesis', status: 'OPEN', deadline: 'Tomorrow' }
  ];

  return (
    <>
      {/* The Handle / Swipe area */}
      <div 
        className="absolute top-0 left-0 w-full h-8 z-50 flex justify-center items-center cursor-pointer"
        onClick={() => setIsOpen(!isOpen)}
        onTouchStart={() => setIsOpen(true)}
      >
        <div className="w-12 h-1.5 bg-gray-600 rounded-full opacity-50" />
      </div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ y: '-100%' }}
            animate={{ y: 0 }}
            exit={{ y: '-100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="absolute top-0 left-0 w-full h-[70vh] bg-[#121212] z-40 rounded-b-3xl shadow-2xl border-b border-[#333] p-6 pt-12 overflow-y-auto"
          >
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-medium text-white">Top of Mind</h2>
              <button onClick={() => setIsOpen(false)} className="text-sm text-gray-400">Close</button>
            </div>

            <div className="space-y-4">
              {activeTasks.map((task) => (
                <div key={task.id} className="bg-[#1E1E1E] p-4 rounded-xl border border-[#2A2A2A] flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <button className="text-gray-500 hover:text-green-500 transition-colors">
                      {task.status === 'DONE' ? <CheckCircle2 className="w-6 h-6 text-green-500" /> : <Circle className="w-6 h-6" />}
                    </button>
                    <div>
                      <p className="text-white text-sm">{task.content}</p>
                      {task.deadline && (
                        <p className="text-xs text-orange-400 mt-1 flex items-center">
                          <Clock className="w-3 h-3 mr-1" /> {task.deadline}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            
            <div className="mt-8">
                <h3 className="text-sm font-medium text-gray-500 mb-4 uppercase tracking-wider">Metrics</h3>
                <div className="flex items-end space-x-2 h-16 bg-[#1A1A1A] p-3 rounded-lg border border-[#222]">
                    {/* Dummy Sparkline */}
                    <div className="w-4 bg-blue-500 rounded-sm h-[20%]"></div>
                    <div className="w-4 bg-blue-500 rounded-sm h-[40%]"></div>
                    <div className="w-4 bg-blue-500 rounded-sm h-[30%]"></div>
                    <div className="w-4 bg-blue-500 rounded-sm h-[80%]"></div>
                    <div className="w-4 bg-blue-500 rounded-sm h-[60%]"></div>
                    <span className="text-xs text-gray-400 ml-2">Focus Score</span>
                </div>
            </div>

          </motion.div>
        )}
      </AnimatePresence>
      
      {/* Backdrop overlay */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsOpen(false)}
            className="absolute inset-0 bg-black/60 z-30"
          />
        )}
      </AnimatePresence>
    </>
  );
};
