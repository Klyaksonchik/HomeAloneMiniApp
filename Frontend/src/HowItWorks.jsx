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
          
          <div className="step-container">
            <img 
              src="https://images.unsplash.com/photo-1551650975-87deedd944c3?w=300&h=150&fit=crop" 
              alt="Шаг 1" 
              className="step-illustration"
            />
            <p>
              1. Укажите имя пользователя в поле "Экстренный контакт".
            </p>
          </div>

          <div className="step-container">
            <img 
              src="https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=300&h=150&fit=crop" 
              alt="Шаг 2" 
              className="step-illustration"
            />
            <p>
              2. Ваш друг обязательно должен зайти в бот и нажать команду /start. Так он появится в системе и бот сможет отправлять ему сообщения.  
            </p>
          </div>

          <div className="step-container">
            <img 
              src="https://images.unsplash.com/photo-1512941937669-90a1b58e7e9c?w=300&h=150&fit=crop" 
              alt="Шаг 3" 
              className="step-illustration"
            />
            <p>
              3. Установите таймер на нужное время перед выходом из дома. Советуем ставить 24 часа. Это оптимально с учетом, что вы можете где-то задержаться. 
            </p>
          </div>

          <div className="step-container">
            <img 
              src="https://images.unsplash.com/photo-1556912172-45b7abe8b7e1?w=300&h=150&fit=crop" 
              alt="Шаг 4" 
              className="step-illustration"
            />
            <p>
              4. Когда вы уходите из дома, сдвиньте слайдер в положение "Не дома". Таймер начнет обратный отсчет.
            </p>
          </div>

          <div className="step-container">
            <img 
              src="https://images.unsplash.com/photo-1583337130417-3346a1be7dee?w=300&h=150&fit=crop" 
              alt="Шаг 5" 
              className="step-illustration"
            />
            <p>
              5. Если вы вернулись домой, сдвиньте слайдер в положение "Дома". Таймер будет сброшен. 
            </p>
          </div>

          <div className="step-container">
            <img 
              src="https://images.unsplash.com/photo-1577563908411-5077b6dc7624?w=300&h=150&fit=crop" 
              alt="Шаг 6" 
              className="step-illustration"
            />
            <p>
              6. Если вы не вернетесь вовремя, приложение отправит 2 напоминания вам, а затем сообщение о тревоге вашему экстренному контакту в телеграм. 
            </p>
          </div>

          <p>
            Вы можете протестировать отправку сообщений, выбрав в таймере 1 минуту. 
          </p>
          <p>
            Совет: договоритесь с вашим экстренным контактом о действиях в случае ЧП. Отдайте ему ключи от квартиры, где остается ваш питомец, или договоритесь с соседями. Ваш малыш будет ждать вас бесконечно долго. Пусть это время он будет с теми, кто о нем позаботится!  
          </p>
          <p>
            Если у вас нет экстренного контакта, напишите в личку основателю проекта @mariandfox. Мы подготовили решение для такого случая. Берегите себя и своих питомцев! 
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
