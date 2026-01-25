import React from 'react';

export function SupportProject({ onBack, onNavigate }) {
  return (
    <div className="info-page">
      <div className="info-header">
        <button className="back-button" onClick={onBack}>←</button>
        <div className="info-page-header">
          <p className="app-name">Home Alone Pet</p>
          <h1 className="page-title">Поддержи проект</h1>
        </div>
      </div>
      <div className="info-content">
        <p>
          Приложение полностью бесплатное, но если вы хотите помочь проекту вырасти и стать частью жизни каждого ответственного хозяина - поддержите нас!
        </p>
        <div className="support-button-container">
          <a 
            href="https://i.postimg.cc/43yHG1xZ/photo-2026-01-21-21-05-46.jpg" 
            target="_blank" 
            rel="noopener noreferrer"
            className="support-button-link"
          >
            <button className="support-button">
              Поддержать
            </button>
          </a>
        </div>
      </div>
      <div className="bottom-nav">
        <button className="nav-button" onClick={() => onNavigate('home')}>
          🏠
        </button>
        <button className="nav-button" onClick={() => onNavigate('how-it-works')}>
          🐶
        </button>
        <button className="nav-button nav-button-large active" onClick={() => onNavigate('support')}>
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
