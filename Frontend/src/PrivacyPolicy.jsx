import React from 'react';

export function PrivacyPolicy({ onBack, onNavigate }) {
  return (
    <div className="info-page">
      <div className="info-header">
        <button className="back-button" onClick={onBack}>←</button>
        <div className="info-page-header">
          <p className="app-name">Home Alone Pet</p>
          <h1 className="page-title">Политика конфиденциальности</h1>
        </div>
      </div>
      <div className="info-content">
        <p>
          Текст политики конфиденциальности будет добавлен позже.
        </p>
      </div>
      <div className="bottom-nav">
        <button className="nav-button" onClick={() => onNavigate('home')}>
          🏠
        </button>
        <button className="nav-button" onClick={() => onNavigate('how-it-works')}>
          🐶
        </button>
        <button className="nav-button nav-button-large" onClick={() => onNavigate('support')}>
          ✨
        </button>
        <button className="nav-button" onClick={() => onNavigate('emergency')}>
          🐱
        </button>
        <button className="nav-button active" onClick={() => onNavigate('privacy')}>
          🔒
        </button>
      </div>
    </div>
  );
}
