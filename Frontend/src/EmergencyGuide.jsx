import React from 'react';

export function EmergencyGuide({ onBack, onNavigate }) {
  return (
    <div className="info-page">
      <div className="info-header">
        <button className="back-button" onClick={onBack}>←</button>
        <div className="info-page-header">
          <p className="app-name">Home Alone Pet</p>
          <h1 className="page-title">Что делать при экстренном сообщении</h1>
        </div>
      </div>
      <div className="info-content">
        <p>
          Если вы получили экстренное сообщение, это означает, что таймер истек и хозяин не вернулся домой.
        </p>
        <p>
          Свяжитесь с хозяином по телефону или другим способом. Если не удается связаться, проверьте, все ли в порядке.
        </p>
        <p>
          При необходимости обратитесь в службы экстренной помощи.
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
        <button className="nav-button active" onClick={() => onNavigate('emergency')}>
          🐱
        </button>
        <button className="nav-button" onClick={() => onNavigate('privacy')}>
          🔒
        </button>
      </div>
    </div>
  );
}
