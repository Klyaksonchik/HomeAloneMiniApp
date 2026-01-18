import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { TimerModal } from "./TimerModal";

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
  const [showMenu, setShowMenu] = useState(false);
  const [showTimerModal, setShowTimerModal] = useState(false);

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
      setShowTimerModal(false);
      alert("Таймер сохранён");
    } catch (e) {
      alert(e?.response?.data?.error || e?.message || "Ошибка сохранения таймера");
    }
  };

  const handleTimerSet = async (hours, minutes) => {
    if (!userId) return;
    const totalSeconds = hours * 3600 + minutes * 60;
    if (totalSeconds < 60) {
      alert("Таймер должен быть не менее 1 минуты.");
      return;
    }

    // Определяем, это кастомный таймер или пресет
    const isPreset = TIMER_PRESETS.some(p => p.value === totalSeconds);
    
    try {
      await axios.post(`${BACKEND_URL}/timer`, {
        user_id: Number(userId),
        timer_seconds: totalSeconds,
      });
      
      setTimerSeconds(totalSeconds);
      setUseCustomTimer(!isPreset);
      if (!isPreset) {
        setCustomTimerHours(hours);
        setCustomTimerMinutes(minutes);
      }
      
      if (!isHome) {
        setTimeLeft(totalSeconds);
      }
      
      setShowTimerModal(false);
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
      {/* Header */}
      <div className="app-header">
        <h1>Таймер безопасности</h1>
        <button
          className="menu-button"
          onClick={() => setShowMenu(!showMenu)}
          disabled={!isTelegramReady}
        >
          <span className="menu-icon">☰</span>
        </button>
      </div>

      {/* Dropdown Menu */}
      {showMenu && (
        <div className="dropdown-menu">
          <div className="dropdown-item" onClick={() => setShowMenu(false)}>
            Информация о приложении
          </div>
        </div>
      )}

      {!isTelegramReady && (
        <div className="telegram-hint">
          Откройте мини‑апп из меню бота после команды /start
        </div>
      )}

      {/* Timer Display Card */}
      <div className="card timer-card">
        <div className="card-header">
          <span className="card-icon">⏱</span>
          <h2 className="card-title">Таймер обратного отсчёта</h2>
        </div>
        <div className="timer-display-wrapper">
          <div className={`timer-large ${!isHome ? 'timer-red' : 'timer-green'}`}>
            {getDisplayTime()}
          </div>
          <button
            className={`timer-set-btn ${!isHome ? 'btn-red' : 'btn-green'}`}
            onClick={() => setShowTimerModal(true)}
            disabled={!isTelegramReady}
          >
            Установить таймер
          </button>
        </div>
      </div>

      {/* Emergency Contact Card */}
      <div className="card contact-card">
        <div className="card-header">
          <span className="card-icon">📞</span>
          <h3 className="card-title">Экстренный контакт</h3>
        </div>
        <div className="contact-input-wrapper">
          <input
            className="contact-input"
            placeholder="@введите экстренный контакт"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            disabled={!isTelegramReady || !editingContact}
            onFocus={() => setEditingContact(true)}
          />
          {contact && (
            <button 
              className="contact-save-btn"
              onClick={onContactAction} 
              disabled={!isTelegramReady}
            >
              {editingContact ? "Сохранить" : "Изменить"}
            </button>
          )}
        </div>
      </div>

      {/* Slider Card */}
      <div className="card slider-card">
        <div 
          className={`slider-new ${!isHome ? 'slider-red' : 'slider-green'}`}
          onClick={toggleStatus}
          style={{ opacity: isTelegramReady && !toggleDisabled ? 1 : 0.6, cursor: toggleDisabled ? 'not-allowed' : 'pointer' }}
        >
          <div
            className={`slider-knob ${!isHome ? 'knob-right' : 'knob-left'}`}
          >
            <span className="slider-knob-text">{!isHome ? 'Не дома' : 'Дома'}</span>
          </div>
          <div className="slider-labels">
            <span className={`slider-label ${!isHome ? 'label-visible' : 'label-hidden'}`}>
              Дома
            </span>
            <span className={`slider-label ${isHome ? 'label-visible' : 'label-hidden'}`}>
              Не дома
            </span>
          </div>
        </div>
        <p className="slider-hint">
          {isHome 
            ? "Когда уходишь из дома, сдвинь слайдер в положение «Не дома»"
            : "Когда вернёшься домой, сдвинь слайдер в положение «Дома»!"
          }
        </p>
      </div>

      {/* Dog Image */}
      <div className="dog-image-wrapper">
        <img src={isHome ? happyDog : sadDog} alt="dog" className="dog-image-new" />
      </div>

      {!isHome && timerExpired && (
        <div className="timer-expired">
          ⏰ Время вышло! Если ты в порядке, сдвинь слайдер в положение «Дома»
        </div>
      )}

      {/* Timer Modal */}
      {showTimerModal && (
        <TimerModal
          isAway={!isHome}
          onClose={() => setShowTimerModal(false)}
          onSetTimer={handleTimerSet}
          currentDuration={useCustomTimer ? customTimerHours * 3600 + customTimerMinutes * 60 : timerSeconds}
        />
      )}
    </div>
  );
}

