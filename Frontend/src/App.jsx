import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";

const BACKEND_URL = "https://homealoneminiapp.onrender.com";
const LS_KEY_CONTACT = "homealone_emergency_contact";
const LS_KEY_TIMER = "homealone_timer";

// Варианты таймера в секундах
const TIMER_PRESETS = [
  { label: "1 минута", value: 1 * 60 }, // Для тестирования
  { label: "30 минут", value: 30 * 60 },
  { label: "1 час", value: 60 * 60 },
  { label: "2 часа", value: 2 * 60 * 60 },
  { label: "4 часа", value: 4 * 60 * 60 },
  { label: "8 часов", value: 8 * 60 * 60 },
  { label: "24 часа", value: 24 * 60 * 60 },
  { label: "48 часов", value: 48 * 60 * 60 },
];

export default function App() {
  const tg = typeof window !== "undefined" ? window.Telegram?.WebApp : null;
  const userId = useMemo(() => tg?.initDataUnsafe?.user?.id ?? null, [tg]);
  const usernameFromTG = useMemo(() => {
    const u = tg?.initDataUnsafe?.user?.username;
    return u ? `@${u}` : null;
  }, [tg]);

  const [isHome, setIsHome] = useState(true);
  const [timeLeft, setTimeLeft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [contact, setContact] = useState("");
  const [editingContact, setEditingContact] = useState(false);
  const [hasServerContact, setHasServerContact] = useState(false);
  const [timerSeconds, setTimerSeconds] = useState(3600); // По умолчанию 1 час
  const [showTimerSettings, setShowTimerSettings] = useState(false);
  const [customTimerHours, setCustomTimerHours] = useState(1);
  const [customTimerMinutes, setCustomTimerMinutes] = useState(0);
  const [useCustomTimer, setUseCustomTimer] = useState(false);
  const [timerExpired, setTimerExpired] = useState(false);

  const happyDog = "https://i.postimg.cc/BncFqv31/Snimok-ekrana-2025-08-19-v-16-37-23-copy.png";
  const sadDog = "https://i.postimg.cc/KY8NKWm0/sad-dog.png";

  useEffect(() => {
    try {
      tg?.ready?.();
      tg?.expand?.();
      tg?.MainButton?.hide?.();
    } catch {}
  }, [tg]);

  useEffect(() => {
    if (!userId) return;
    const loadStatus = async () => {
      try {
        const r = await axios.get(`${BACKEND_URL}/status`, { params: { user_id: userId } });
        const serverStatus = r?.data?.status;
        setIsHome(serverStatus === "не дома" ? false : true);
        setHasServerContact(Boolean(r?.data?.emergency_contact_set));
        if (r?.data?.timer_seconds) {
          setTimerSeconds(r.data.timer_seconds);
        }
        // Восстанавливаем таймер, если пользователь "не дома"
        if (serverStatus === "не дома" && r?.data?.time_remaining !== null && r?.data?.time_remaining !== undefined) {
          const remaining = Math.max(0, Math.floor(r.data.time_remaining));
          setTimeLeft(remaining);
          setTimerExpired(remaining <= 0);
        }
      } catch (e) {
        console.error("Ошибка загрузки статуса:", e);
      }
    };
    loadStatus();
    // Синхронизируем каждые 10 секунд
    const syncInterval = setInterval(loadStatus, 10000);
    return () => clearInterval(syncInterval);
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    axios
      .get(`${BACKEND_URL}/contact`, { params: { user_id: userId } })
      .then((r) => {
        const c = r?.data?.emergency_contact || "";
        if (c) {
          setContact(c);
          setHasServerContact(true);
          try {
            localStorage.setItem(LS_KEY_CONTACT, c);
          } catch {}
        } else {
          try {
            const cached = localStorage.getItem(LS_KEY_CONTACT);
            if (cached) setContact(cached);
          } catch {}
        }
      })
      .catch(() => {
        try {
          const cached = localStorage.getItem(LS_KEY_CONTACT);
          if (cached) setContact(cached);
        } catch {}
      });
  }, [userId]);

  useEffect(() => {
    if (!timeLeft && timeLeft !== 0) return;
    const id = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev === null) return null;
        const newValue = prev > 0 ? prev - 1 : 0;
        if (newValue === 0 && !timerExpired) {
          setTimerExpired(true);
        }
        return newValue;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [timeLeft, timerExpired]);

  const formatTime = (seconds) => {
    // Если меньше 60 минут - формат MM:SS, иначе HH:MM:SS
    const totalMinutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    
    if (totalMinutes < 60) {
      // Меньше часа - MM:SS
      return `${String(totalMinutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    } else {
      // Больше или равно часу - HH:MM:SS
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
  };

  const toggleStatus = async () => {
    if (!userId || busy) return;
    const contactTrimmed = (contact || "").trim();
    const contactValid = contactTrimmed.startsWith("@") && contactTrimmed.length > 1;
    if (isHome && !contactValid) {  
      alert("Укажите экстренный контакт (@username), прежде чем уходить из дома.");
      return;
    }

    setBusy(true);
    try {
      if (isHome) {
        // Вычисляем таймер
        let finalTimerSeconds = timerSeconds;
        if (useCustomTimer) {
          finalTimerSeconds = customTimerHours * 3600 + customTimerMinutes * 60;
          if (finalTimerSeconds < 60) {
            alert("Таймер должен быть не менее 1 минуты.");
            setBusy(false);
            return;
          }
        }

        setIsHome(false);
        setTimeLeft(finalTimerSeconds);
        setTimerExpired(false);
        await axios.post(`${BACKEND_URL}/status`, {
          user_id: Number(userId),
          status: "не дома",
          username: usernameFromTG,
          timer_seconds: finalTimerSeconds,
        });
        // Сохраняем таймер на сервере
        try {
          await axios.post(`${BACKEND_URL}/timer`, {
            user_id: Number(userId),
            timer_seconds: finalTimerSeconds,
          });
        } catch {}
      } else {
        setIsHome(true);
        setTimeLeft(null);
        setTimerExpired(false);
        await axios.post(`${BACKEND_URL}/status`, {
          user_id: Number(userId),
          status: "дома",
          username: usernameFromTG,
        });
      }
    } catch (e) {
      const msg = e?.response?.data?.error || e?.message || "Ошибка запроса";
      if (msg === "contact_required") {
        alert("Сначала укажите экстренный контакт (@username).");
      } else {
        alert(msg);
      }
      try {
        const r = await axios.get(`${BACKEND_URL}/status`, { params: { user_id: userId } });
        const serverStatus = r?.data?.status;
        setIsHome(serverStatus === "не дома" ? false : true);
      } catch {}
    } finally {
      setBusy(false);
    }
  };

  const onContactAction = async () => {
    if (!userId) return;
    if (!editingContact) {
      setEditingContact(true);
      return;
    }
    let value = (contact || "").trim();
    if (value && !value.startsWith("@")) value = `@${value}`;
    if (!value || value === "@") {
      alert("Введите корректный @username экстренного контакта.");
      return;
    }
    try {
      await axios.post(`${BACKEND_URL}/contact`, {
        user_id: Number(userId),
        contact: value,
      });
      setContact(value);
      setEditingContact(false);
      setHasServerContact(true);
      try {
        localStorage.setItem(LS_KEY_CONTACT, value);
      } catch {}
      alert("Контакт сохранён");
    } catch (e) {
      alert(e?.response?.data?.error || e?.message || "Ошибка сохранения контакта");
    }
  };

  const saveTimer = async () => {
    if (!userId) return;
    let finalTimerSeconds = timerSeconds;
    if (useCustomTimer) {
      finalTimerSeconds = customTimerHours * 3600 + customTimerMinutes * 60;
      if (finalTimerSeconds < 60) {
        alert("Таймер должен быть не менее 1 минуты.");
        return;
      }
    }

    try {
      await axios.post(`${BACKEND_URL}/timer`, {
        user_id: Number(userId),
        timer_seconds: finalTimerSeconds,
      });
      setTimerSeconds(finalTimerSeconds);
      setShowTimerSettings(false);
      alert("Таймер сохранён");
    } catch (e) {
      alert(e?.response?.data?.error || e?.message || "Ошибка сохранения таймера");
    }
  };

  const isTelegramReady = !!userId;
  const toggleDisabled = !isTelegramReady || busy || !(contact && contact.trim().length > 1);

  // Функция для получения текста выбранного таймера
  const getSelectedTimerText = () => {
    if (useCustomTimer) {
      const totalMinutes = customTimerHours * 60 + customTimerMinutes;
      if (totalMinutes === 0) return "Не выбран";
      if (customTimerHours > 0 && customTimerMinutes > 0) {
        return `${customTimerHours}ч ${customTimerMinutes}м`;
      } else if (customTimerHours > 0) {
        return `${customTimerHours}ч`;
      } else {
        return `${customTimerMinutes}м`;
      }
    } else {
      const preset = TIMER_PRESETS.find(p => p.value === timerSeconds);
      return preset ? preset.label : "Не выбран";
    }
  };

  // Функция для получения времени таймера для отображения
  const getDisplayTime = () => {
    if (!isHome && timeLeft !== null && timeLeft > 0) {
      return formatTime(timeLeft);
    }
    // Когда дома, показываем выбранное время таймера
    if (useCustomTimer) {
      const totalSeconds = customTimerHours * 3600 + customTimerMinutes * 60;
      return formatTime(totalSeconds);
    }
    return formatTime(timerSeconds);
  };

  return (
    <div className={`app ${!isHome ? 'not-home' : ''}`}>
      <h1>Таймер безопасности</h1>

      {!isTelegramReady && (
        <div style={{ marginBottom: 12, color: "#a00", fontWeight: "bold" }}>
          Откройте мини‑апп из меню бота после команды /start
        </div>
      )}

      <div className="slider-container" style={{ opacity: isTelegramReady ? 1 : 0.6 }}>
        <span className="status-label">Дома</span>
        <label className="switch">
          <input
            type="checkbox"
            checked={!isHome}
            onChange={toggleStatus}
            disabled={toggleDisabled}
          />
          <span className="slider round"></span>
        </label>
        <span className="status-label">Не дома</span>
      </div>

      <div className="status-hint">
        {isHome 
          ? "Когда уходишь из дома, сдвинь слайдер в положение «Не дома»"
          : "Когда вернёшься домой, сдвинь слайдер в положение «Дома»!"
        }
      </div>

      {/* Таймер всегда виден на одном месте */}
      <div className="timer-large">{getDisplayTime()}</div>
      {!showTimerSettings && (
        <button 
          className="change-timer-btn"
          onClick={() => setShowTimerSettings(!showTimerSettings)}
          disabled={!isTelegramReady}
        >
          Изменить таймер
        </button>
      )}

      <img src={isHome ? happyDog : sadDog} alt="dog" className="dog-image" />

      {/* Экстренный контакт под картинкой */}
      <div className="contact-section">
        <div className="contact-header">
          <span className="contact-label">Экстренный контакт</span>
          {contact && (
            <button 
              className="contact-change-btn"
              onClick={onContactAction} 
              disabled={!isTelegramReady}
            >
              {editingContact ? "Сохранить" : "Изменить"}
            </button>
          )}
        </div>
        <input
          className="contact-input"
          placeholder="@введите экстренный контакт"
          value={contact}
          onChange={(e) => setContact(e.target.value)}
          disabled={!isTelegramReady || !editingContact}
          onFocus={() => setEditingContact(true)}
        />
      </div>

      {!isHome && timerExpired && (
        <div className="timer-expired">
          ⏰ Время вышло! Если ты в порядке, сдвинь слайдер в положение «Дома»
        </div>
      )}

      {/* Настройка таймера */}
      {showTimerSettings && (
        <div className="timer-section">
          <div className="timer-settings">
              <div style={{ marginBottom: 15 }}>
                <label style={{ display: "block", marginBottom: 10, fontWeight: 600 }}>
                  Выберите таймер:
                </label>
                {TIMER_PRESETS.map((preset) => (
                  <button
                    key={preset.value}
                    onClick={() => {
                      setTimerSeconds(preset.value);
                      setUseCustomTimer(false);
                    }}
                    className={`timer-preset-btn ${timerSeconds === preset.value && !useCustomTimer ? 'active' : ''}`}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>

              <div style={{ marginBottom: 15 }}>
                <label style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
                  <input
                    type="checkbox"
                    checked={useCustomTimer}
                    onChange={(e) => setUseCustomTimer(e.target.checked)}
                    style={{ marginRight: 8 }}
                  />
                  <span style={{ fontWeight: 600 }}>Свой таймер</span>
                </label>
                {useCustomTimer && (
                  <div className="custom-timer-inputs">
                    <div className="timer-input-group">
                      <label>Часы</label>
                      <input
                        type="number"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        min="0"
                        max="168"
                        step="1"
                        value={customTimerHours}
                        onChange={(e) => {
                          const val = parseInt(e.target.value) || 0;
                          setCustomTimerHours(Math.max(0, Math.min(168, val)));
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
                        value={customTimerMinutes}
                        onChange={(e) => {
                          const val = parseInt(e.target.value) || 0;
                          setCustomTimerMinutes(Math.max(0, Math.min(59, val)));
                        }}
                        onFocus={(e) => e.target.select()}
                        className="timer-input"
                        placeholder="0"
                      />
                    </div>
                  </div>
                )}
              </div>

              <button onClick={saveTimer} disabled={!isTelegramReady}>
                Сохранить таймер
              </button>
          </div>
        </div>
      )}
    </div>
  );
}

