  import React from 'react';

  export function HowItWorks({ onBack, onNavigate }) {
    return (
      <div className="info-page">
        <div className="info-header">
          <button className="back-button" onClick={onBack}>←</button>
          <div className="info-page-header">
            <p className="app-name">Home Alone Pet</p>
            <h1 className="page-title">Как работает приложение</h1>
          </div>
        </div>
        <div className="info-content">
          <p>
            Приложение помогает вам быть спокойным за вашего питомца, если вы не вернетесь домой вовремя. 
          </p>
          <p>
            Установите таймер на нужное время и укажите экстренный контакт. Когда вы уходите из дома, сдвиньте слайдер в положение "Не дома".
          </p>
          <p>
            Если вы не вернетесь вовремя, приложение отправит напоминания вам и вашему экстренному контакту.
          </p>
          <p>
            Если вы вернулись домой, сдвиньте слайдер в положение "Дома". Таймер будет сброшен.
          </p>
        </div>
        <div className="bottom-nav">
          <button className="nav-button" onClick={() => onNavigate('home')}>
            🏠
          </button>
          <button className="nav-button active" onClick={() => onNavigate('how-it-works')}>
            🐶
          </button>
          <button className="nav-button nav-button-large" onClick={() => onNavigate('support')}>
            ✨
          </button>
          <button className="nav-button" onClick={() => onNavigate('emergency')}>
            🐱
          </button>
          <button className="nav-button" onClick={() => onNavigate('privacy')}>
            🔒
          </button>
        </div>
      </div>
    );
  }

