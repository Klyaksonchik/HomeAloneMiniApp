import React, { useState, useEffect } from 'react';

const TIMER_PRESETS = [
  { label: "1 минута", value: 1 * 60 },
  { label: "30 минут", value: 30 * 60 },
  { label: "1 час", value: 60 * 60 },
  { label: "2 часа", value: 2 * 60 * 60 },
  { label: "4 часа", value: 4 * 60 * 60 },
  { label: "8 часов", value: 8 * 60 * 60 },
  { label: "24 часа", value: 24 * 60 * 60 },
  { label: "48 часов", value: 48 * 60 * 60 },
];

export function TimerModal({ isAway, onClose, onSetTimer, currentDuration }) {
  const [selectedPreset, setSelectedPreset] = useState(null);
  const [useCustom, setUseCustom] = useState(false);
  const [customHours, setCustomHours] = useState(0);
  const [customMinutes, setCustomMinutes] = useState(0);

  useEffect(() => {
    // Находим пресет по текущей длительности
    const preset = TIMER_PRESETS.find(p => p.value === currentDuration);
    if (preset) {
      setSelectedPreset(preset.value);
      setUseCustom(false);
    } else {
      setUseCustom(true);
      const hours = Math.floor(currentDuration / 3600);
      const minutes = Math.floor((currentDuration % 3600) / 60);
      setCustomHours(hours);
      setCustomMinutes(minutes);
    }
  }, [currentDuration]);

  const handleSave = () => {
    if (useCustom) {
      const totalSeconds = customHours * 3600 + customMinutes * 60;
      if (totalSeconds < 60) {
        alert("Таймер должен быть не менее 1 минуты.");
        return;
      }
      onSetTimer(customHours, customMinutes);
    } else if (selectedPreset) {
      const preset = TIMER_PRESETS.find(p => p.value === selectedPreset);
      const hours = Math.floor(preset.value / 3600);
      const minutes = Math.floor((preset.value % 3600) / 60);
      onSetTimer(hours, minutes);
    }
  };

  return (
    <div className="timer-modal-overlay" onClick={onClose}>
      <div className="timer-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="timer-modal-header">
          <h2>Настройка таймера</h2>
          <button className="timer-modal-close" onClick={onClose}>×</button>
        </div>
        
        <div className="timer-modal-body">
          <div className="timer-presets-section">
            <label className="timer-section-label">Выберите таймер:</label>
            <div className="timer-presets-grid">
              {TIMER_PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  onClick={() => {
                    setSelectedPreset(preset.value);
                    setUseCustom(false);
                  }}
                  className={`timer-preset-btn ${selectedPreset === preset.value && !useCustom ? 'active' : ''}`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <div className="timer-custom-section">
            <label className="timer-custom-checkbox">
              <input
                type="checkbox"
                checked={useCustom}
                onChange={(e) => {
                  setUseCustom(e.target.checked);
                  if (e.target.checked) {
                    setSelectedPreset(null);
                  }
                }}
              />
              <span>Свой таймер</span>
            </label>
            
            {useCustom && (
              <div className="timer-custom-inputs">
                <div className="timer-input-group">
                  <label>Часы</label>
                  <input
                    type="number"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    min="0"
                    max="168"
                    step="1"
                    value={customHours}
                    onChange={(e) => {
                      const val = parseInt(e.target.value) || 0;
                      setCustomHours(Math.max(0, Math.min(168, val)));
                    }}
                    onFocus={(e) => e.target.select()}
                    className="timer-input"
                    placeholder="0"
                  />
                </div>
                <div className="timer-input-group">
                  <label>Минуты</label>
                  <input
                    type="number"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    min="0"
                    max="59"
                    step="1"
                    value={customMinutes}
                    onChange={(e) => {
                      const val = parseInt(e.target.value) || 0;
                      setCustomMinutes(Math.max(0, Math.min(59, val)));
                    }}
                    onFocus={(e) => e.target.select()}
                    className="timer-input"
                    placeholder="0"
                  />
                </div>
              </div>
            )}
          </div>

          <button 
            className="timer-modal-save-btn"
            onClick={handleSave}
          >
            Сохранить таймер
          </button>
        </div>
      </div>
    </div>
  );
}
