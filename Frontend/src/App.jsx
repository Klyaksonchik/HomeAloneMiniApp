import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { TimerModal } from "./TimerModal";
import { HowItWorks } from "./HowItWorks";
import { SupportProject } from "./SupportProject";
import { EmergencyGuide } from "./EmergencyGuide";
import { PrivacyPolicy } from "./PrivacyPolicy";

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
  const [currentPage, setCurrentPage] = useState('home'); // 'home', 'how-it-works', 'support', 'emergency', 'privacy'

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

  // Если не на главной странице, показываем соответствующую страницу
  if (currentPage === 'how-it-works') {
    return <HowItWorks onBack={() => setCurrentPage('home')} onNavigate={(page) => setCurrentPage(page)} />;
  }
  if (currentPage === 'support') {
    return <SupportProject onBack={() => setCurrentPage('home')} onNavigate={(page) => setCurrentPage(page)} />;
  }
  if (currentPage === 'emergency') {
    return <EmergencyGuide onBack={() => setCurrentPage('home')} onNavigate={(page) => setCurrentPage(page)} />;
  }
  if (currentPage === 'privacy') {
    return <PrivacyPolicy onBack={() => setCurrentPage('home')} onNavigate={(page) => setCurrentPage(page)} />;
  }

  return (
    <div className={`app ${!isHome ? 'not-home' : ''}`}>
      {!isTelegramReady && (
        <div className="telegram-hint">
          Откройте мини‑апп из меню бота после команды /start
        </div>
      )}

      {/* App Name */}
      <p className="app-name">Home Alone Pet</p>
      
      {/* Main Title */}
      <h1 className="main-title">Таймер безопасности</h1>

      {/* Timer Display */}
      <div className="timer-display-container">
        <div className="timer-display-wrapper">
          <div className={`timer-large ${!isHome ? 'timer-red' : 'timer-green'}`}>
            {getDisplayTime()}
          </div>
          <button
            className="change-timer-button"
            onClick={() => setShowTimerModal(true)}
            disabled={!isTelegramReady}
          >
            Изменить
          </button>
        </div>
      </div>

      {/* Slider */}
      <div className="slider-container-new">
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
            ? <>Когда уходишь из дома,<br />сдвинь слайдер в положение «Не дома»</>
            : "Когда вернёшься домой, сдвинь слайдер в положение «Дома»!"
          }
        </p>
      </div>

      {/* Emergency Contact */}
      <div className="emergency-contact-container">
        <h3 className="emergency-contact-title">Экстренный контакт</h3>
        <div className="contact-input-wrapper-new">
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

      {/* Bottom Navigation */}
      <div className="bottom-nav">
        <button 
          className={`nav-button ${currentPage === 'home' ? 'active' : ''}`}
          onClick={() => setCurrentPage('home')}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 9L12 2L21 9V20C21 20.5304 20.7893 21.0391 20.4142 21.4142C20.0391 21.7893 19.5304 22 19 22H5C4.46957 22 3.96086 21.7893 3.58579 21.4142C3.21071 21.0391 3 20.5304 3 20V9Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M9 22V12H15V22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <button 
          className={`nav-button ${currentPage === 'how-it-works' ? 'active' : ''}`}
          onClick={() => setCurrentPage('how-it-works')}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
            <path d="M12 6V12L16 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        </button>
        <button 
          className={`nav-button nav-button-large ${currentPage === 'support' ? 'active' : ''}`}
          onClick={() => setCurrentPage('support')}
        >
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <button 
          className={`nav-button ${currentPage === 'emergency' ? 'active' : ''}`}
          onClick={() => setCurrentPage('emergency')}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M10.29 3.86L1.82 18C1.64538 18.3024 1.55299 18.6453 1.552 19C1.55101 19.3547 1.64145 19.6981 1.81445 20.0016C1.98745 20.3051 2.23675 20.5581 2.53771 20.7359C2.83868 20.9137 3.18082 21.0099 3.53 21H20.47C20.8192 21.0099 21.1613 20.9137 21.4623 20.7359C21.7633 20.5581 22.0126 20.3051 22.1856 20.0016C22.3586 19.6981 22.449 19.3547 22.448 19C22.447 18.6453 22.3546 18.3024 22.18 18L13.71 3.86C13.5317 3.56611 13.2807 3.32311 12.9812 3.15448C12.6817 2.98585 12.3438 2.89725 12 2.89725C11.6562 2.89725 11.3183 2.98585 11.0188 3.15448C10.7193 3.32311 10.4683 3.56611 10.29 3.86V3.86Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M12 9V13" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            <path d="M12 17H12.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        </button>
        <button 
          className={`nav-button ${currentPage === 'privacy' ? 'active' : ''}`}
          onClick={() => setCurrentPage('privacy')}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" stroke="currentColor" strokeWidth="2"/>
            <path d="M7 11V7C7 5.67392 7.52678 4.40215 8.46447 3.46447C9.40215 2.52678 10.6739 2 12 2C13.3261 2 14.5979 2.52678 15.5355 3.46447C16.4732 4.40215 17 5.67392 17 7V11" stroke="currentColor" strokeWidth="2"/>
          </svg>
        </button>
      </div>
    </div>
  );
}

